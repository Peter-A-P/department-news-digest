"""GDELT's document API: global coverage of an audience's entities.

GDELT indexes news worldwide and returns article metadata, not article text, which is what
this project wants from it: the link and the title, with extraction and quoting governed by
the publisher's own terms as for any other item.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx

from clippings.config.audience import Audience
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult

API = "https://api.gdeltproject.org/api/v2/doc/doc"
SOURCE_KEY = "gdelt"

# GDELT's own words in its 429 body, observed 2026-09-13: "Please limit requests to one
# every 5 seconds." It is free and open, and this is the whole of what it asks in return,
# so the interval is enforced here rather than left to how many queries an audience happens
# to configure. Six seconds, not five, because the clock that matters is theirs.
MIN_INTERVAL_SECONDS = 6.0

# GDELT is slow to answer and slow even to complete a TLS handshake: measured at 10 to 12
# seconds for a bare request on 2026-09-13, against a 10 second default that was timing the
# handshake out before the query was ever sent. Its own timeout, rather than a longer one
# for every publisher, because no feed needs this.
TIMEOUT = httpx.Timeout(45.0, connect=30.0)

# How long to wait before asking once more after a rate limit or a dropped connection. GDELT
# counts requests per address, and Cloud Run's outbound addresses are shared with everyone
# else on Google Cloud who queries it: from 2026-10-07 to 2026-10-10 most of this project's
# requests were refused as the first request of a run, six seconds after nothing. One retry,
# half a minute later, is still far inside "one every 5 seconds" from this project.
RETRY_AFTER_SECONDS = 30.0

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
    """One request per query in the audience file, spaced to GDELT's stated rate limit."""

    kind: SourceKind = "gdelt"

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_SECONDS,
        retry_after: float = RETRY_AFTER_SECONDS,
    ) -> None:
        self._min_interval = min_interval
        self._retry_after = retry_after
        self._last_request: float | None = None

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        config = audience.sources.gdelt
        for query in config.queries:
            yield self._fetch_one(query, config.limit, audience, context)

    def _wait_turn(self) -> None:
        """Hold until GDELT's stated interval has passed since the last request."""
        if self._last_request is not None:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

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
        for attempt in (1, 2):
            if attempt == 2:
                time.sleep(self._retry_after)
            self._wait_turn()
            try:
                response = context.client.get(API, params=params, timeout=TIMEOUT)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt == 1:
                    continue
                return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
            except httpx.HTTPError as exc:
                return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
                break
            if attempt == 2:
                # Asked once more after waiting, and refused again: reported, not pressed.
                return FetchResult.failure(
                    SOURCE_KEY, query, f"rate limited: {response.text[:120].strip()}"
                )
        try:
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return FetchResult.failure(SOURCE_KEY, query, f"{type(exc).__name__}: {exc}")
        except ValueError:
            # GDELT answers a rejected query, and a rate limit it did not label 429, with
            # plain text and a 200. Its own words are the useful part, so they are what gets
            # recorded rather than the JSON parser's complaint about column one.
            return FetchResult.failure(
                SOURCE_KEY, query, f"refused the query: {response.text[:160].strip()}"
            )
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
