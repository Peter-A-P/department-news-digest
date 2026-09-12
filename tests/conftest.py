"""Fixtures shared by the suite. Nothing here reaches the network."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from clippings.config.audience import Audience
from clippings.ingest.store import Store
from clippings.models import Item, RawItem
from clippings.sources.base import FetchContext
from clippings.sources.robots import AllowAll
from clippings.sources.terms import TermsGate, TermsRow

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def terms_row(key: str, status: str = "allowed") -> TermsRow:
    return TermsRow(
        key=key,
        source=f"{key} (test)",
        terms_url=f"https://{key}/terms",
        date_read=datetime(2026, 9, 12, tzinfo=UTC).date() if status == "allowed" else None,
        status=status,  # type: ignore[arg-type]
        notes="",
    )


def gate(**statuses: str) -> TermsGate:
    """A terms gate with the given keys at the given statuses; everything else is absent."""
    return TermsGate({key: terms_row(key, status) for key, status in statuses.items()})


@pytest.fixture
def audience() -> Audience:
    return Audience(
        id="test-audience",
        name="Test audience",
        description="A test audience for the suite.",
        rubric=(
            "Relevant means an item about the thing this test audience is configured to "
            "care about, and nothing else at all."
        ),
        topics=("testing",),
        trusted_sources=("gov.example",),
        blocked_sources=("blocked.example",),
    )


@pytest.fixture
def store() -> Iterator[Store]:
    with Store.memory() as opened:
        yield opened


@pytest.fixture
def context() -> Iterator[FetchContext]:
    """A context whose client has no transport to the outside world."""
    with httpx.Client(transport=httpx.MockTransport(_refuse)) as client:
        yield FetchContext(client=client, gate=gate(), robots=AllowAll(), now=NOW)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"the test suite made a real request to {request.url}")


def raw(
    url: str,
    title: str = "A headline",
    *,
    summary: str = "",
    source_key: str = "gov.example",
    published_at: datetime | None = None,
) -> RawItem:
    return RawItem(
        source_key=source_key,
        source_kind="rss",
        url=url,
        title=title,
        summary=summary,
        published_at=published_at or NOW,
        origin="https://gov.example/feed",
    )


def item(
    item_id: str,
    title: str = "A headline",
    *,
    summary: str = "",
    domain: str = "gov.example",
    published_at: datetime | None = None,
) -> Item:
    published = published_at or NOW
    return Item(
        id=item_id,
        source_key=domain,
        source_kind="rss",
        url=f"https://{domain}/{item_id}",
        original_url=f"https://{domain}/{item_id}",
        domain=domain,
        title=title,
        summary=summary,
        published_at=published,
        fetched_at=published,
        origin="https://gov.example/feed",
    )
