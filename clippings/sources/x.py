"""X, through its official API v2: one recent search a day, for one post (rank/x_pick.py).

Added 2026-10-10 while Reddit's access request was unanswered; Reddit was dropped on
2026-11-07 and X stays (Peter). X is not a `Source` in the ingest sense. Its posts never enter the
pool or a story: X's display rules allow a post to be shown only whole and unaltered, so a
twenty-five-word quote of one inside a story summary is exactly what they forbid. The only
use is the day's pick, shown whole on the day it is picked.

Every read is billed (pay-per-use since February 2026): US$0.005 a post and US$0.010 a user,
counted once per resource per UTC day. A day for one audience is one search of
`candidates` posts from named people, and a second of `topic_candidates` by subject where
the audience has `topics`, and, for the pick only, one author lookup. The search asks for no user
expansion, because that would bill a user per candidate; the one author is fetched after the
pick. `MONTHLY_CAP_USD` is enforced from the fetch log before any request leaves, as the
second line of defence behind the spend limit set in X's developer console.

The credential is an app-only bearer token (`X_BEARER_TOKEN`, from the environment, never
committed). Without it, or without credits on the account, this reports itself unavailable
and the run carries on without the section.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from typing import Any
from urllib.parse import urlsplit

import httpx

from clippings.config.audience import Audience
from clippings.ingest.normalise import NormaliseError, dedup_key
from clippings.sources.base import FetchContext

SOURCE_KEY = "x"
API = "https://api.x.com/2"
SEARCH = f"{API}/tweets/search/recent"
TOKEN_ENV = "X_BEARER_TOKEN"

# X's list prices on 2026-10-10 (docs.x.com/x-api/getting-started/pricing), in US dollars.
PRICE_POST_USD = 0.005
PRICE_USER_USD = 0.010
# AI at fifty posts a day (thirty from named people, twenty by subject), Toronto and
# Newfoundland and Labrador at ten each, and an author a day for each, is about US$11.40 a
# month (Peter chose fifty on 2026-10-15). Raised from US$10 for that; this leaves room for
# a rerun and stops anything more. Raise it in a commit.
MONTHLY_CAP_USD = 12.0
# The fetch log's origin for an author lookup, so its price can be told from a search's.
AUTHOR_ORIGIN = "author lookup"

# A link to a post, a photo or a video on X is not an article.
X_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com", "t.co"})

# The pick is the day's: the last twenty-four hours, whatever the watermark of other sources.
WINDOW = timedelta(hours=24)

# X's own profile images are served from this host and nowhere else; the page's content
# policy allows images from it and nothing else outside the site.
IMAGE_HOST = "https://pbs.twimg.com/"


class XUnavailable(RuntimeError):
    """No token, no credits, or X refused the request. The section is left out."""


@dataclass(frozen=True)
class XPost:
    id: str
    author_id: str
    # The whole post: `note_tweet` for a long post, whose `text` X truncates.
    text: str
    created_at: datetime
    likes: int
    reposts: int
    replies: int
    # The articles the post links to, as X expanded them; X's own links are left out.
    links: tuple[str, ...] = ()

    @property
    def engagement(self) -> int:
        return self.likes + self.reposts + self.replies


@dataclass(frozen=True)
class XAuthor:
    id: str
    username: str
    name: str
    # Empty unless it is an X-hosted image.
    image_url: str


def post_url(username: str, post_id: str) -> str:
    return f"https://x.com/{username}/status/{post_id}"


def token(context: FetchContext) -> str:
    value = context.secrets.get(TOKEN_ENV, "")
    if not value:
        raise XUnavailable(f"{TOKEN_ENV} is not set")
    return value


def query_for(audience: Audience, terms: str) -> str:
    """One of the audience's queries, without reposts or replies, in its language if it has
    one."""
    query = f"({terms}) -is:retweet -is:reply"
    if len(audience.languages) == 1:
        query += f" lang:{audience.languages[0]}"
    return query


def spent_usd(reads: dict[str, int]) -> float:
    """What a month's fetch-log reads cost at list price, by origin. An upper bound: X counts
    a post read twice in one UTC day once."""
    return sum(
        count * (PRICE_USER_USD if origin == AUTHOR_ORIGIN else PRICE_POST_USD)
        for origin, count in reads.items()
    )


def headroom(spent: float, reads: int) -> bool:
    """Whether a day's reads for one audience still fit under the monthly cap."""
    return spent + reads * PRICE_POST_USD + PRICE_USER_USD <= MONTHLY_CAP_USD


def link_keys(urls: Iterable[str]) -> frozenset[str]:
    """The links in the form an item's id is made from, so a post's link and a story's
    source match however each was written. A link that is not http(s) is left out."""
    keys = set()
    for url in urls:
        try:
            keys.add(dedup_key(url))
        except NormaliseError:
            continue
    return frozenset(keys)


def _links(raw: dict[str, Any]) -> tuple[str, ...]:
    entities = raw.get("entities")
    found = entities.get("urls") if isinstance(entities, dict) else None
    links = []
    for entry in found if isinstance(found, list) else []:
        if not isinstance(entry, dict):
            continue
        url = entry.get("unwound_url") or entry.get("expanded_url")
        if isinstance(url, str) and urlsplit(url).hostname not in X_HOSTS:
            links.append(url)
    return tuple(links)


def _int(metrics: dict[str, Any], key: str) -> int:
    value = metrics.get(key)
    return value if isinstance(value, int) else 0


def billed(payload: Any) -> int:
    """How many posts a search response returned, and so was billed for, shown or not."""
    data = payload.get("data") if isinstance(payload, dict) else None
    return len(data) if isinstance(data, list) else 0


def parse_search(payload: Any) -> tuple[XPost, ...]:
    """The posts in a search response. A post X flags as possibly sensitive is skipped.

    X returns post text with `&amp;`, `&lt;` and `&gt;` escaped; they are turned back into
    the characters the author wrote, and the page escapes them again for HTML.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return ()
    posts = []
    for raw in payload["data"]:
        if not isinstance(raw, dict) or raw.get("possibly_sensitive"):
            continue
        post_id, author_id = raw.get("id"), raw.get("author_id")
        note = raw.get("note_tweet")
        text = note.get("text") if isinstance(note, dict) else None
        text = text if isinstance(text, str) and text.strip() else raw.get("text")
        created = raw.get("created_at")
        if not post_id or not author_id or not isinstance(text, str) or not text.strip():
            continue
        try:
            when = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except ValueError:
            continue
        metrics = raw.get("public_metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        posts.append(
            XPost(
                id=str(post_id),
                author_id=str(author_id),
                text=unescape(text.strip()),
                created_at=when,
                likes=_int(metrics, "like_count"),
                reposts=_int(metrics, "retweet_count"),
                replies=_int(metrics, "reply_count"),
                links=_links(raw),
            )
        )
    return tuple(posts)


def _get(context: FetchContext, url: str, params: dict[str, str]) -> Any:
    try:
        response = context.client.get(
            url, params=params, headers={"Authorization": f"Bearer {token(context)}"}
        )
    except httpx.HTTPError as exc:
        raise XUnavailable(f"{type(exc).__name__}: {exc}") from exc
    status = response.status_code
    if status in {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN}:
        raise XUnavailable(f"unavailable: X answered {status} (token or access)")
    if status == httpx.codes.PAYMENT_REQUIRED:
        raise XUnavailable("unavailable: X answered 402 (no credits, or the spend limit)")
    if status == httpx.codes.TOO_MANY_REQUESTS:
        raise XUnavailable("rate limited: X answered 429")
    if status != httpx.codes.OK:
        raise XUnavailable(f"X answered {status}")
    try:
        return response.json()
    except ValueError as exc:
        raise XUnavailable(f"not JSON: {exc}") from exc


def search(
    audience: Audience, context: FetchContext, terms: str, count: int
) -> tuple[tuple[XPost, ...], int]:
    """One search's candidates by X's relevance order, and how many posts were billed."""
    payload = _get(
        context,
        SEARCH,
        {
            "query": query_for(audience, terms),
            "max_results": str(count),
            "sort_order": "relevancy",
            "start_time": (context.now - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tweet.fields": (
                "created_at,public_metrics,author_id,note_tweet,possibly_sensitive,entities"
            ),
        },
    )
    return parse_search(payload), billed(payload)


def author(context: FetchContext, author_id: str) -> XAuthor:
    """The picked post's author: what X's display rules require beside the post."""
    payload = _get(
        context,
        f"{API}/users/{author_id}",
        {"user.fields": "profile_image_url"},
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or not data.get("username"):
        raise XUnavailable("the author lookup returned no user")
    image = str(data.get("profile_image_url") or "")
    return XAuthor(
        id=author_id,
        username=str(data["username"]),
        name=str(data.get("name") or data["username"]),
        image_url=image if image.startswith(IMAGE_HOST) else "",
    )
