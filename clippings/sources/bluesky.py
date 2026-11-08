"""Bluesky, through the AT Protocol search endpoint.

The item is the post: public discussion is what this source is for, and a
link in a post reaches the pool through the publisher's own feed.

Search needs a session. Measured on 2026-09-13: `app.bsky.actor.getProfile` answers 200 on
the public AppView without credentials, while `app.bsky.feed.searchPosts` on the same host
answers 403, so search is authenticated now whatever it was before. The official route is
an app password, which is what this uses (`BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` from the
environment, never committed). Without them this source reports itself unavailable and the
run continues. There is no unauthenticated way to search that does not mean going around
the refusal, and going around it is what this project does not do.

Deleted posts are honoured by the thirty-day retention: nothing here is kept longer, and a
digest that has already been published shows the post's text only as a quote of at most
twenty-five words, verified against what was fetched.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from clippings.config.audience import Audience
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

HOST = "https://bsky.social"
SEARCH = f"{HOST}/xrpc/app.bsky.feed.searchPosts"
CREATE_SESSION = f"{HOST}/xrpc/com.atproto.server.createSession"
SOURCE_KEY = "bluesky"
# Bluesky's public read-only AppView: no session, for checking a post still exists.
PUBLIC = "https://public.api.bsky.app/xrpc"


class BlueskyAuthError(RuntimeError):
    """The app password was refused, or was never set."""


def access_token(context: FetchContext) -> str:
    """An access token from an app password.

    An app password, not the account password: it is revocable on its own and cannot change
    the account. Bluesky issues them for exactly this.
    """
    handle = context.secrets.get("BLUESKY_HANDLE", "")
    password = context.secrets.get("BLUESKY_APP_PASSWORD", "")
    if not handle or not password:
        raise BlueskyAuthError("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD are not set")
    response = context.client.post(
        CREATE_SESSION, json={"identifier": handle, "password": password}
    )
    if response.status_code != httpx.codes.OK:
        raise BlueskyAuthError(f"createSession returned {response.status_code}")
    token = response.json().get("accessJwt")
    if not token:
        raise BlueskyAuthError("createSession returned no accessJwt")
    return str(token)


def own_posts(payload: Any) -> dict[str, list[Any]]:
    """An author feed as a search response, without the posts the author only reposted."""
    feed = payload.get("feed") if isinstance(payload, dict) else None
    entries = feed if isinstance(feed, list) else []
    return {
        "posts": [
            entry["post"]
            for entry in entries
            if isinstance(entry, dict) and not entry.get("reason") and "post" in entry
        ]
    }


def post_url(uri: str, handle: str) -> str:
    """A web link for an `at://did/app.bsky.feed.post/rkey` URI."""
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _created_at(record: Any) -> datetime | None:
    if not isinstance(record, dict):
        return None
    value = record.get("createdAt")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_posts(
    payload: Any, query: str, since: datetime, languages: tuple[str, ...] = ()
) -> tuple[RawItem, ...]:
    """Turn a search response into raw items posted since the watermark.

    A post whose author tagged its languages and named none of the audience's is skipped.
    The first deployed AI digest (2026-10-08) carried a Japanese roundup post as a must-read
    for an English audience; the audience file's `languages` was being ignored here.
    """
    if not isinstance(payload, dict):
        return ()
    posts = payload.get("posts")
    if not isinstance(posts, list):
        return ()
    items: list[RawItem] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        uri = post.get("uri")
        author = post.get("author")
        record = post.get("record")
        if not uri or not isinstance(author, dict) or not isinstance(record, dict):
            continue
        handle = author.get("handle")
        text = str(record.get("text", "")).strip()
        if not handle or not text:
            continue
        # A reply is half a conversation, and quoted alone it misleads; an account with no
        # display name is most often a bot or an empty account. Neither is kept, inside a
        # story or as the day's most discussed post (2026-10-10).
        if record.get("reply") or not str(author.get("displayName") or "").strip():
            continue
        created = _created_at(record)
        if created is not None and created <= since:
            continue
        tagged = record.get("langs")
        spoken = (
            {str(code).split("-")[0].lower() for code in tagged}
            if isinstance(tagged, list)
            else set()
        )
        if languages and spoken and not spoken & set(languages):
            continue
        # A post has no title. The first line stands in for one, which is what a reader of
        # the digest sees before the quote.
        title = text.splitlines()[0][:200]
        items.append(
            RawItem(
                source_key=SOURCE_KEY,
                source_kind="bluesky",
                url=post_url(str(uri), str(handle)),
                title=title,
                summary=text,
                author=str(handle),
                published_at=created,
                origin=query,
                score=int(post["likeCount"]) if isinstance(post.get("likeCount"), int) else None,
                comments=int(post["replyCount"])
                if isinstance(post.get("replyCount"), int)
                else None,
            )
        )
    return tuple(items)


def person_origin(handle: str) -> str:
    """The origin a person's posts are logged and watermarked under."""
    return f"from:{handle}"


class BlueskySource:
    """One search request per query in the audience file, and one author feed per person."""

    kind: SourceKind = "bluesky"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        config = audience.sources.bluesky
        if not config.queries and not config.people:
            return
        if not context.permitted(SOURCE_KEY):
            for origin in (*config.queries, *map(person_origin, config.people)):
                yield context.refusal(SOURCE_KEY, origin)
            return
        # A person's own posts come from the public AppView, which needs no session.
        for handle in config.people:
            yield self._fetch_person(handle, context, audience.languages)
        if not config.queries:
            return
        try:
            token = access_token(context)
        except (BlueskyAuthError, httpx.HTTPError) as exc:
            for query in config.queries:
                yield FetchResult.failure(SOURCE_KEY, query, f"unavailable: {exc}")
            return
        for query in config.queries:
            yield self._fetch_one(
                query, config.limit, token, context, audience.languages, config.sort
            )

    def _fetch_person(
        self, handle: str, context: FetchContext, languages: tuple[str, ...]
    ) -> FetchResult:
        origin = person_origin(handle)
        since = context.since(SOURCE_KEY, origin)
        try:
            response = context.client.get(
                f"{PUBLIC}/app.bsky.feed.getAuthorFeed",
                params={"actor": handle, "limit": "30", "filter": "posts_no_replies"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, origin, f"{type(exc).__name__}: {exc}")
        except ValueError as exc:
            return FetchResult.failure(SOURCE_KEY, origin, f"not JSON: {exc}")
        return FetchResult(
            source_key=SOURCE_KEY,
            origin=origin,
            items=parse_posts(own_posts(payload), origin, since, languages),
        )

    def _fetch_one(
        self,
        query: str,
        limit: int,
        token: str,
        context: FetchContext,
        languages: tuple[str, ...] = (),
        sort: str = "top",
    ) -> FetchResult:
        since = context.since(SOURCE_KEY, query)
        params = {"q": query, "limit": str(limit), "sort": sort}
        if len(languages) == 1:
            # The search filters by one language server-side; with several, parse_posts does.
            params["lang"] = languages[0]
        try:
            response = context.client.get(
                SEARCH,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
        except ValueError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"not JSON: {exc}")
        return FetchResult(
            source_key=SOURCE_KEY,
            origin=query,
            items=parse_posts(payload, query, since, languages),
        )


# Bluesky serves avatars from this host; the page's content policy allows images from it.
IMAGE_HOST = "https://cdn.bsky.app/"


@dataclass(frozen=True)
class PostView:
    """What Bluesky's public API says about one post: whether it exists, and, if it does,
    who wrote it and how it was received. `found` is None when the answer is unknown."""

    found: bool | None
    name: str = ""
    image_url: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0


def post_view(client: httpx.Client, url: str) -> PostView:
    """Look up the post at a bsky.app link on the public, unauthenticated AppView.

    The handle is resolved to the account's DID and the post looked up by its AT URI. An
    empty answer is a deleted post; a handle that no longer resolves is a deleted or renamed
    account, and is treated as gone, since the post is no longer where the link said.
    Anything else (a timeout, a 5xx) is unknown.
    """
    parts = url.rstrip("/").split("/")
    if len(parts) < 7 or parts[-2] != "post" or parts[-4] != "profile":
        return PostView(None)
    handle, rkey = parts[-3], parts[-1]
    try:
        resolved = client.get(
            f"{PUBLIC}/com.atproto.identity.resolveHandle", params={"handle": handle}
        )
        if resolved.status_code == httpx.codes.BAD_REQUEST:
            return PostView(False)
        resolved.raise_for_status()
        did = resolved.json().get("did")
        if not did:
            return PostView(None)
        found = client.get(
            f"{PUBLIC}/app.bsky.feed.getPosts",
            params={"uris": f"at://{did}/app.bsky.feed.post/{rkey}"},
        )
        found.raise_for_status()
        posts = found.json().get("posts")
    except (httpx.HTTPError, ValueError):
        return PostView(None)
    if not isinstance(posts, list):
        return PostView(None)
    if not posts or not isinstance(posts[0], dict):
        return PostView(False)
    post = posts[0]
    found_author = post.get("author")
    author: dict[str, Any] = found_author if isinstance(found_author, dict) else {}
    avatar = str(author.get("avatar") or "")

    def count(key: str) -> int:
        value = post.get(key)
        return value if isinstance(value, int) else 0

    return PostView(
        found=True,
        name=str(author.get("displayName") or "").strip(),
        image_url=avatar if avatar.startswith(IMAGE_HOST) else "",
        likes=count("likeCount"),
        reposts=count("repostCount"),
        replies=count("replyCount"),
    )


def post_exists(client: httpx.Client, url: str) -> bool | None:
    """Whether the post at a bsky.app link still exists: True, False, or None if unknown.

    The digest shows a picked post in full only while it exists (PLAN.md section 2.3), so a
    run asks.
    """
    return post_view(client, url).found
