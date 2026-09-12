"""RSS and Atom feeds: the core of the pool.

One adapter for every publisher, because a feed is a format, not a relationship. What
differs per publisher is its row in the terms record and its entry in the audience file.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from clippings.config.audience import Audience, Feed
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult


def _entry_published(entry: Any) -> datetime | None:
    """The entry's publication time, from whichever of the date fields it filled in."""
    for attribute in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attribute, None)
        if parsed:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
    return None


def _entry_link(entry: Any) -> str:
    link = getattr(entry, "link", "") or ""
    if link:
        return str(link)
    for candidate in getattr(entry, "links", []) or []:
        href = candidate.get("href") if isinstance(candidate, dict) else None
        if href:
            return str(href)
    return ""


def _entry_summary(entry: Any) -> str:
    for attribute in ("summary", "description"):
        value = getattr(entry, attribute, None)
        if value:
            return str(value)
    content = getattr(entry, "content", None)
    if content:
        first = content[0]
        value = first.get("value") if isinstance(first, dict) else None
        if value:
            return str(value)
    return ""


def _entry_author(entry: Any) -> str | None:
    author = getattr(entry, "author", None)
    return str(author) if author else None


def parse_feed(body: bytes, feed: Feed, since: datetime) -> tuple[RawItem, ...]:
    """Parse a feed body into raw items published since the watermark.

    Entries without a date are kept: a feed that publishes no dates is common, and dropping
    its items would silently lose a publisher. Normalisation records the fetch time as an
    upper bound and the timeliness measurement excludes them and says so.
    """
    parsed = feedparser.parse(body)
    items: list[RawItem] = []
    for entry in parsed.entries:
        link = _entry_link(entry)
        if not link:
            continue
        published = _entry_published(entry)
        if published is not None and published <= since:
            continue
        items.append(
            RawItem(
                source_key=feed.terms,
                source_kind="rss",
                url=link,
                title=str(getattr(entry, "title", "") or ""),
                summary=_entry_summary(entry),
                author=_entry_author(entry),
                published_at=published,
                origin=feed.url,
            )
        )
    return tuple(items)


class RssSource:
    """Every feed listed in the audience file."""

    kind: SourceKind = "rss"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        for feed in audience.sources.feeds:
            yield self._fetch_one(feed, context)

    def _fetch_one(self, feed: Feed, context: FetchContext) -> FetchResult:
        if not context.permitted(feed.terms):
            return context.refusal(feed.terms, feed.url)
        if not context.robots.allows(feed.url):
            return FetchResult.failure(feed.terms, feed.url, "refused: robots.txt disallows it")
        since = context.since(feed.terms, feed.url)
        try:
            response = context.client.get(feed.url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return FetchResult.failure(feed.terms, feed.url, f"{type(exc).__name__}: {exc}")
        try:
            items = parse_feed(response.content, feed, since)
        # Broad on purpose: one malformed feed must not end the day's run.
        except Exception as exc:
            return FetchResult.failure(feed.terms, feed.url, f"unparseable feed: {exc}")
        return FetchResult(source_key=feed.terms, origin=feed.url, items=items)
