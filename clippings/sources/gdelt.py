"""GDELT's document API: global coverage of an audience's entities.

GDELT indexes news worldwide and returns article metadata, not article text, which is what
this project wants from it: the link and the title, with extraction and quoting governed by
the publisher's own terms as for any other item.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from clippings.config.audience import Audience
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

API = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCE_KEY = "gdelt"

# GDELT stamps articles with the time it saw them, as YYYYMMDDTHHMMSSZ.
SEEN_FORMAT = "%Y%m%dT%H%M%SZ"


def _seen_at(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, SEEN_FORMAT).replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def parse_articles(payload: Any, query: str, since: datetime) -> tuple[RawItem, ...]:
    """Turn a GDELT response into raw items seen since the watermark."""
    if not isinstance(payload, dict):
        return ()
    articles = payload.get("articles")
    if not isinstance(articles, list):
        return ()
    items: list[RawItem] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url = article.get("url")
        title = article.get("title")
        if not url or not title:
            continue
        seen = _seen_at(str(article.get("seendate", "")))
        if seen is not None and seen <= since:
            continue
        items.append(
            RawItem(
                source_key=SOURCE_KEY,
                source_kind="gdelt",
                url=str(url),
                title=str(title),
                published_at=seen,
                origin=query,
            )
        )
    return tuple(items)


def language_of(article: dict[str, Any]) -> str | None:
    """GDELT names languages in full ('English'); the audience file uses ISO 639-1."""
    name = str(article.get("language", "")).strip().lower()
    return {"english": "en", "french": "fr", "spanish": "es", "german": "de"}.get(name)


class GdeltSource:
    """One request per query in the audience file."""

    kind: SourceKind = "gdelt"

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        config = audience.sources.gdelt
        for query in config.queries:
            yield self._fetch_one(query, config.limit, audience, context)

    def _fetch_one(
        self, query: str, limit: int, audience: Audience, context: FetchContext
    ) -> FetchResult:
        if not context.permitted(SOURCE_KEY):
            return context.refusal(SOURCE_KEY, query)
        since = context.since(SOURCE_KEY, query)
        # GDELT takes a timespan rather than a start time; ask for the window the watermark
        # implies, rounded up to whole minutes, and let the parser drop anything older.
        minutes = max(15, int((context.now - since).total_seconds() // 60) + 1)
        params = {
            "query": self._with_language(query, audience),
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(limit),
            "timespan": f"{min(minutes, 60 * 24 * 7)}min",
            "sort": "DateDesc",
        }
        try:
            response = context.client.get(API, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
        except ValueError as exc:
            # GDELT answers a rejected query with plain text and a 200.
            return FetchResult.failure(SOURCE_KEY, query, f"not JSON: {exc}")
        return FetchResult(
            source_key=SOURCE_KEY, origin=query, items=parse_articles(payload, query, since)
        )

    @staticmethod
    def _with_language(query: str, audience: Audience) -> str:
        """Restrict the query to the audience's languages, which GDELT does server-side."""
        names = {"en": "english", "fr": "french", "es": "spanish", "de": "german"}
        languages = [names[code] for code in audience.languages if code in names]
        if not languages:
            return query
        if len(languages) == 1:
            return f"{query} sourcelang:{languages[0]}"
        joined = " OR ".join(f"sourcelang:{name}" for name in languages)
        return f"{query} ({joined})"
