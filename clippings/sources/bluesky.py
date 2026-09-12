"""Bluesky, through the public AT Protocol search endpoint.

The public AppView answers search without authentication, so this source needs no
credentials. As with Reddit, the item is the post: public discussion is what this source is
for, and a link in a post reaches the pool through the publisher's own feed.

Deleted posts are honoured by the thirty-day retention: nothing here is kept longer, and a
digest that has already been published shows the post's text only as a quote of at most
twenty-five words, verified against what was fetched.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx

from clippings.config.audience import Audience
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

API = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
SOURCE_KEY = "bluesky"


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


def parse_posts(payload: Any, query: str, since: datetime) -> tuple[RawItem, ...]:
    """Turn a search response into raw items posted since the watermark."""
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
        created = _created_at(record)
        if created is not None and created <= since:
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


class BlueskySource:
    """One search request per query in the audience file."""

    kind: SourceKind = "bluesky"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        config = audience.sources.bluesky
        for query in config.queries:
            yield self._fetch_one(query, config.limit, context)

    def _fetch_one(self, query: str, limit: int, context: FetchContext) -> FetchResult:
        if not context.permitted(SOURCE_KEY):
            return context.refusal(SOURCE_KEY, query)
        since = context.since(SOURCE_KEY, query)
        try:
            response = context.client.get(
                API, params={"q": query, "limit": str(limit), "sort": "latest"}
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
        except ValueError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"not JSON: {exc}")
        return FetchResult(
            source_key=SOURCE_KEY, origin=query, items=parse_posts(payload, query, since)
        )
