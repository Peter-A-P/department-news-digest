"""Reddit, through a registered application on the free tier.

The item is the Reddit post, not the page it links to. A link post's target arrives through
the feeds and GDELT on its own terms, and clustering puts the two together; taking the
target here instead would mean fetching a publisher's page on the strength of Reddit's
terms, which is exactly the kind of bending PLAN.md section 2.2 rules out.

Credentials come from the environment (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and
`REDDIT_USERNAME` for the user agent) and are never committed. Without them this source reports itself unavailable and the run continues:
the pipeline runs with any subset of sources.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from clippings.config.audience import Audience
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
SOURCE_KEY = "reddit"


def user_agent(context: FetchContext) -> dict[str, str]:
    """The user agent Reddit's API rules ask for: platform, app id, version, and the account
    that owns the application, so Reddit knows whom to contact. Reddit throttles a generic
    one. Still this project's product token and still true; only the shape is Reddit's."""
    username = context.secrets.get("REDDIT_USERNAME", "")
    client_id = context.secrets.get("REDDIT_CLIENT_ID", "")
    if not username or not client_id:
        return {}
    return {"User-Agent": f"python:clippings:{client_id}:0.1 (by /u/{username})"}


class RedditAuthError(RuntimeError):
    """The application credentials were refused."""


def access_token(context: FetchContext) -> str:
    """A client-credentials token for the registered application."""
    client_id = context.secrets.get("REDDIT_CLIENT_ID", "")
    client_secret = context.secrets.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RedditAuthError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not set")
    response = context.client.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        headers=user_agent(context),
    )
    if response.status_code != httpx.codes.OK:
        raise RedditAuthError(f"token request returned {response.status_code}")
    token = response.json().get("access_token")
    if not token:
        raise RedditAuthError("token request returned no access_token")
    return str(token)


def parse_listing(payload: Any, subreddit: str, since: datetime) -> tuple[RawItem, ...]:
    """Turn a listing response into raw items posted since the watermark."""
    if not isinstance(payload, dict):
        return ()
    children = payload.get("data", {}).get("children")
    if not isinstance(children, list):
        return ()
    items: list[RawItem] = []
    for child in children:
        if not isinstance(child, dict) or child.get("kind") != "t3":
            continue
        post = child.get("data")
        if not isinstance(post, dict):
            continue
        permalink = post.get("permalink")
        title = post.get("title")
        if not permalink or not title:
            continue
        created = post.get("created_utc")
        posted = (
            datetime.fromtimestamp(float(created), tz=UTC)
            if isinstance(created, int | float)
            else None
        )
        if posted is not None and posted <= since:
            continue
        items.append(
            RawItem(
                source_key=SOURCE_KEY,
                source_kind="reddit",
                url=f"https://www.reddit.com{permalink}",
                title=str(title),
                summary=str(post.get("selftext", ""))[:2000],
                author=str(post["author"]) if post.get("author") else None,
                published_at=posted,
                origin=subreddit,
                score=int(post["score"]) if isinstance(post.get("score"), int) else None,
                comments=(
                    int(post["num_comments"]) if isinstance(post.get("num_comments"), int) else None
                ),
            )
        )
    return tuple(items)


class RedditSource:
    """One listing request per subreddit in the audience file."""

    kind: SourceKind = "reddit"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        config = audience.sources.reddit
        if not config.subreddits:
            return
        if not context.permitted(SOURCE_KEY):
            for subreddit in config.subreddits:
                yield context.refusal(SOURCE_KEY, subreddit)
            return
        try:
            token = access_token(context)
        except (RedditAuthError, httpx.HTTPError) as exc:
            for subreddit in config.subreddits:
                yield FetchResult.failure(SOURCE_KEY, subreddit, f"unavailable: {exc}")
            return
        for subreddit in config.subreddits:
            yield self._fetch_one(subreddit, config.listing, config.limit, token, context)

    def _fetch_one(
        self, subreddit: str, listing: str, limit: int, token: str, context: FetchContext
    ) -> FetchResult:
        since = context.since(SOURCE_KEY, subreddit)
        try:
            response = context.client.get(
                f"{API}/r/{subreddit}/{listing}",
                params={"limit": str(limit)},
                headers={"Authorization": f"Bearer {token}", **user_agent(context)},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, subreddit, f"{type(exc).__name__}: {exc}")
        except ValueError as exc:
            return FetchResult.failure(SOURCE_KEY, subreddit, f"not JSON: {exc}")
        return FetchResult(
            source_key=SOURCE_KEY,
            origin=subreddit,
            items=parse_listing(payload, subreddit, since),
        )
