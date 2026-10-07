"""The terms record is the gate, not a document about a gate."""

from __future__ import annotations

import re
from datetime import date

import pytest

from clippings.config.load import EXAMPLES, load_audiences
from clippings.sources.terms import (
    SOURCES_DOC,
    TermsGate,
    TermsRecordError,
    load_terms,
    parse_terms,
)

TABLE = """
| Key | Source | Terms | Date read | Status | Notes |
|---|---|---|---|---|---|
| good.example | Good (RSS) | https://good.example/terms | 2026-09-12 | allowed | |
| later.example | Later (RSS) | https://later.example/terms | - | pending | not read yet |
| gone.example | Gone (RSS) | https://gone.example/terms | 2026-09-12 | dropped | changed their terms |
"""


def test_a_pending_source_is_refused() -> None:
    gate = TermsGate(parse_terms(TABLE))
    with pytest.raises(TermsRecordError, match="not read yet"):
        gate.check("later.example")
    assert gate.allows("later.example") is False


def test_a_dropped_source_is_refused_with_the_reason() -> None:
    gate = TermsGate(parse_terms(TABLE))
    with pytest.raises(TermsRecordError, match="changed their terms"):
        gate.check("gone.example")


def test_a_source_with_no_row_at_all_is_refused() -> None:
    gate = TermsGate(parse_terms(TABLE))
    with pytest.raises(TermsRecordError, match=re.escape("no row in docs/sources.md")):
        gate.check("never.example")


def test_an_allowed_source_passes_and_carries_its_date() -> None:
    gate = TermsGate(parse_terms(TABLE))
    row = gate.check("good.example")
    assert row.allowed
    assert row.date_read == date(2026, 9, 12)


def test_allowed_without_a_date_read_is_an_error() -> None:
    """The date is the point of the record; a row without one is not a record."""
    table = (
        "| Key | Source | Terms | Date read | Status | Notes |\n"
        "|---|---|---|---|---|---|\n"
        "| x.example | X | https://x.example/terms | - | allowed | |\n"
    )
    with pytest.raises(TermsRecordError, match="no date read is recorded"):
        parse_terms(table)


def test_an_unknown_status_is_an_error() -> None:
    table = (
        "| Key | Source | Terms | Date read | Status | Notes |\n"
        "|---|---|---|---|---|---|\n"
        "| x.example | X | https://x.example/terms | 2026-09-12 | probably fine | |\n"
    )
    with pytest.raises(TermsRecordError, match="expected one of"):
        parse_terms(table)


def test_the_shipped_record_parses() -> None:
    rows = load_terms(SOURCES_DOC)
    assert rows, "docs/sources.md has no rows"


def test_every_source_in_every_example_audience_has_a_row() -> None:
    """An audience cannot name a source the terms record has never heard of.

    This is the check that keeps `clippings sources check` honest: the row may say pending,
    and then the fetcher refuses it, but it must exist.
    """
    rows = load_terms(SOURCES_DOC)
    for audience in load_audiences(EXAMPLES):
        keys = {feed.terms for feed in audience.sources.feeds}
        if audience.sources.gdelt.queries:
            keys.add("gdelt")
        if audience.sources.reddit.subreddits:
            keys.add("reddit")
        if audience.sources.bluesky.queries:
            keys.add("bluesky")
        missing = keys - set(rows)
        assert not missing, f"{audience.id} uses sources with no row in docs/sources.md: {missing}"


def test_recording_a_reading_changes_one_row_and_nothing_else() -> None:
    """Find-and-replace of `pending` broke the legend and left no date, twice."""
    from datetime import date

    import pytest

    from clippings.sources.terms import TermsRecordError, parse_terms, record_reading

    text = "\n".join(
        [
            "| Status | Meaning |",
            "|---|---|",
            "| `pending` | Not read yet. |",
            "",
            "| Key | Source | Terms | Date read | Status | Notes |",
            "|---|---|---|---|---|---|",
            "| a.example | A | https://a.example/terms | - | pending | first |",
            "| b.example | B | https://b.example/terms | - | pending | |",
            "",
            "Prose that says `pending` stays as it is.",
        ]
    )
    updated = record_reading(text, "a.example", "allowed", date(2026, 10, 7), "Read by Peter")
    rows = parse_terms(updated)
    assert rows["a.example"].allowed and rows["a.example"].date_read == date(2026, 10, 7)
    assert rows["a.example"].notes == "first. Read by Peter"
    assert rows["b.example"].status == "pending"
    assert "| `pending` | Not read yet. |" in updated
    assert "says `pending` stays" in updated
    with pytest.raises(TermsRecordError, match="no row"):
        record_reading(text, "c.example", "allowed", date(2026, 10, 7))
