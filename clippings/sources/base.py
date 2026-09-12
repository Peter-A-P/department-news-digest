"""What every source adapter is, and the one HTTP client they all use.

A source is asked for what it has published since a watermark and yields `RawItem`s. It
does not decide whether it is allowed to run: the terms gate does that, and an adapter
that cannot show an `allowed` row in `docs/sources.md` never sends a request.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from clippings.config.audience import Audience
from clippings.constants import USER_AGENT
from clippings.models import RawItem, SourceKind
from clippings.sources.robots import RobotsCache
from clippings.sources.terms import TermsGate, TermsRecordError

# Feeds and public APIs are small; a slow one must not hold up the daily job.
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# How far back a source is read when it has no watermark yet, on a first run.
COLD_START = timedelta(days=2)


def http_client(timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.Client:
    """The one client every adapter uses, identifying itself in every request."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        # A publisher that is slow or briefly down should not cost the digest its source,
        # but the daily job must still finish, so this is retries at the transport level
        # only: connection failures, not error responses.
        transport=httpx.HTTPTransport(retries=2),
    )


@dataclass(frozen=True)
class FetchResult:
    """What one origin within a source produced on one attempt.

    A result is recorded whether or not it succeeded: source yield and uptime are numbers
    this project publishes, and a source that failed silently would flatter both.
    """

    source_key: str
    origin: str
    items: tuple[RawItem, ...] = ()
    ok: bool = True
    detail: str = ""

    @classmethod
    def failure(cls, source_key: str, origin: str, detail: str) -> FetchResult:
        return cls(source_key=source_key, origin=origin, items=(), ok=False, detail=detail)


@dataclass
class FetchContext:
    """Everything an adapter needs that is not the audience."""

    client: httpx.Client
    gate: TermsGate
    robots: RobotsCache
    # The watermark for (source_key, origin); None on a first run.
    watermarks: dict[tuple[str, str], datetime] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Credentials for the sources that need them, read from the environment, never committed.
    secrets: dict[str, str] = field(default_factory=dict)

    def since(self, source_key: str, origin: str) -> datetime:
        """How far back to read this origin."""
        return self.watermarks.get((source_key, origin), self.now - COLD_START)

    def permitted(self, source_key: str) -> bool:
        """Whether the terms record allows this source. Adapters call this first."""
        try:
            self.gate.check(source_key)
        except TermsRecordError:
            return False
        return True

    def refusal(self, source_key: str, origin: str) -> FetchResult:
        """The result recorded when the terms record refuses a source."""
        try:
            self.gate.check(source_key)
        except TermsRecordError as exc:
            return FetchResult.failure(source_key, origin, f"refused: {exc}")
        raise AssertionError("refusal() called for a permitted source")


class Source(Protocol):
    """A place items come from. One adapter per kind, not per publisher."""

    kind: SourceKind

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        """Yield one result per origin this source has for this audience."""
        ...
