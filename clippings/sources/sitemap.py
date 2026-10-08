"""A news section with no feed, read through the publisher's sitemap.

Anthropic publishes news at anthropic.com/news and offers no RSS or Atom feed (every usual
feed path answered 404 on 2026-10-08). It does publish a sitemap, the machine-readable list
of its pages that a site offers crawlers, with a last-modified date on each. This adapter
reads that list and nothing a site does not publish for machines, then reads the
publisher's own description of each new page from the page's metadata.

Two dates, used for different things:

- **lastmod** in the sitemap says a page changed. It picks which pages to look at, newest
  first, and at most `MAX_PAGES` a run, so the requests a run makes are bounded however
  large the sitemap.
- **The page's own publication date** (`article:published_time`, or `datePublished` in its
  structured data) decides whether it is news. An old post that was edited has a fresh
  lastmod and an old publication date, and is skipped: the measured case on 2026-10-08 was
  a post published 2026-09-23 with a lastmod of 2026-10-07. A page that states no
  publication date is skipped too, because without one an edited page cannot be told from a
  new one.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import NamedTuple
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from clippings.config.audience import Audience, Sitemap
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

# Pages read per sitemap per run. A news section posts a few items a week; ten covers a busy
# day and bounds what a sitemap full of edits can cost the publisher.
MAX_PAGES = 10

# A sitemap index points at child sitemaps; this many are followed, one level deep.
MAX_CHILD_SITEMAPS = 5

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
DATE_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')


class Entry(NamedTuple):
    url: str
    lastmod: datetime


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_sitemap(body: bytes) -> tuple[list[Entry], list[str]]:
    """The pages a sitemap lists with their lastmod, and any child sitemaps it points at.

    A page with no lastmod is left out: there is no way to tell whether it is new.
    """
    root = ElementTree.fromstring(body)
    if root.tag == f"{NS}sitemapindex":
        children = [
            (node.findtext(f"{NS}loc") or "").strip() for node in root.findall(f"{NS}sitemap")
        ]
        return [], [child for child in children if child]
    entries: list[Entry] = []
    for node in root.findall(f"{NS}url"):
        loc = (node.findtext(f"{NS}loc") or "").strip()
        lastmod = _parse_time(node.findtext(f"{NS}lastmod") or "")
        if loc and lastmod is not None:
            entries.append(Entry(loc, lastmod))
    return entries, []


def candidates(entries: list[Entry], sitemap: Sitemap, since: datetime) -> list[Entry]:
    """Pages under the news prefix changed since the watermark, newest first, capped."""
    prefix = sitemap.include
    chosen = [
        entry
        for entry in entries
        if urlsplit(entry.url).path.startswith(prefix)
        and urlsplit(entry.url).path.rstrip("/") != prefix.rstrip("/")
        and entry.lastmod > since
    ]
    chosen.sort(key=lambda entry: entry.lastmod, reverse=True)
    return chosen[:MAX_PAGES]


class PageMeta(NamedTuple):
    title: str
    description: str
    published: datetime | None


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "meta":
            name = values.get("property") or values.get("name") or ""
            if name and name not in self.meta:
                self.meta[name] = values.get("content", "")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def page_meta(html: str) -> PageMeta:
    """The publisher's own title, description and publication date for a page."""
    parser = _MetaParser()
    parser.feed(html)
    title = parser.meta.get("og:title") or parser.title
    description = parser.meta.get("og:description") or parser.meta.get("description", "")
    published = _parse_time(parser.meta.get("article:published_time", ""))
    if published is None:
        match = DATE_PUBLISHED.search(html)
        published = _parse_time(match.group(1)) if match else None
    return PageMeta(title.strip(), description.strip(), published)


class SitemapSource:
    """Every sitemap listed in the audience file."""

    kind: SourceKind = "sitemap"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        for sitemap in audience.sources.sitemaps:
            yield self._fetch_one(sitemap, context)

    def _fetch_one(self, sitemap: Sitemap, context: FetchContext) -> FetchResult:
        key, origin = sitemap.terms, sitemap.url
        if not context.permitted(key):
            return context.refusal(key, origin)
        if not context.robots.allows(origin):
            return FetchResult.failure(key, origin, "refused: robots.txt disallows it")
        since = context.since(key, origin)
        try:
            entries = self._entries(origin, context)
        except (httpx.HTTPError, ElementTree.ParseError) as exc:
            return FetchResult.failure(key, origin, f"{type(exc).__name__}: {exc}")

        items: list[RawItem] = []
        skipped: dict[str, int] = {}
        for entry in candidates(entries, sitemap, since):
            reason = self._read_page(entry, sitemap, since, context, items)
            if reason:
                skipped[reason] = skipped.get(reason, 0) + 1
        detail = ", ".join(f"{count} {reason}" for reason, count in sorted(skipped.items()))
        return FetchResult(source_key=key, origin=origin, items=tuple(items), detail=detail)

    def _entries(self, url: str, context: FetchContext) -> list[Entry]:
        response = context.client.get(url)
        response.raise_for_status()
        entries, children = parse_sitemap(response.content)
        for child in children[:MAX_CHILD_SITEMAPS]:
            if not context.robots.allows(child):
                continue
            child_response = context.client.get(child)
            child_response.raise_for_status()
            entries.extend(parse_sitemap(child_response.content)[0])
        return entries

    def _read_page(
        self,
        entry: Entry,
        sitemap: Sitemap,
        since: datetime,
        context: FetchContext,
        items: list[RawItem],
    ) -> str:
        """Read one page's metadata into `items`, or return why it was skipped."""
        if not context.robots.allows(entry.url):
            return "disallowed by robots.txt"
        try:
            response = context.client.get(entry.url)
            response.raise_for_status()
        except httpx.HTTPError:
            return "failed to load"
        meta = page_meta(response.text)
        if meta.published is None:
            return "with no publication date"
        if meta.published <= since:
            return "edited, not new"
        if not meta.title:
            return "with no title"
        items.append(
            RawItem(
                source_key=sitemap.terms,
                source_kind="sitemap",
                url=entry.url,
                title=meta.title,
                summary=meta.description,
                published_at=meta.published,
                origin=sitemap.url,
            )
        )
        return ""
