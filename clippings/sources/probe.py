"""Checking that a configured feed is actually a feed.

Written after the first live run, where six of the thirteen feeds in the example audiences
turned out to be wrong: four returned 404, and two returned a 200 with an HTML page that
the parser read as zero entries. A feed URL is a guess until something fetches it, and a
silent zero-entry feed is worse than a 404 because the run reports it as a success.

`clippings sources probe` is that something. It is a manual command, never part of a run
and never part of CI: it makes one request per feed and belongs to the person adding a
source, not to the daily job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser
import httpx

from clippings.config.audience import Audience, Feed
from clippings.sources.rss import entry_published

# Long enough to tell a slow publisher from one that is not answering us at all.
PROBE_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


@dataclass(frozen=True)
class ProbeResult:
    """What one feed URL turned out to be."""

    feed: Feed
    ok: bool
    detail: str
    entries: int = 0
    newest: datetime | None = None

    @property
    def line(self) -> str:
        age = ""
        if self.newest is not None:
            hours = (datetime.now(UTC) - self.newest).total_seconds() / 3600
            age = f"newest {hours:.0f}h old" if hours < 72 else f"newest {hours / 24:.0f}d old"
        mark = "ok " if self.ok else "FAIL"
        return f"  {mark}  {self.feed.terms:20s} {self.detail:34s} {age}"


def probe_feed(client: httpx.Client, feed: Feed) -> ProbeResult:
    """Fetch one feed and say what came back."""
    try:
        response = client.get(feed.url)
    except httpx.HTTPError as exc:
        return ProbeResult(feed, False, f"{type(exc).__name__}")
    if response.status_code != httpx.codes.OK:
        return ProbeResult(feed, False, f"HTTP {response.status_code}")
    parsed = feedparser.parse(response.content)
    if not parsed.entries:
        # The failure that matters: a 200 with a web page in it. Without this check the run
        # counts the source as healthy and the digest is quietly short.
        kind = response.headers.get("content-type", "unknown").split(";")[0]
        return ProbeResult(feed, False, f"200 but no entries ({kind})")
    dates = [date for date in (entry_published(entry) for entry in parsed.entries) if date]
    return ProbeResult(
        feed,
        True,
        f"{len(parsed.entries)} entries",
        entries=len(parsed.entries),
        newest=max(dates) if dates else None,
    )


def probe_audience(client: httpx.Client, audience: Audience) -> list[ProbeResult]:
    """Probe every feed in one audience file."""
    return [probe_feed(client, feed) for feed in audience.sources.feeds]
