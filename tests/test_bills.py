"""The bills the gateway's ledger does not see: how they are read and what the report says."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from clippings.config.audience import Audience
from clippings.eval.bills import BILLS, Bill, load_bills
from clippings.eval.report import build_report, readme_tables
from clippings.ingest.store import Store


def _bill(**update: object) -> Bill:
    values: dict[str, object] = {
        "name": "X API",
        "first_day": date(2026, 10, 12),
        "last_day": date(2026, 11, 8),
        "amount": 8.01,
        "currency": "USD",
        "source": "X Developer Console",
        "read_on": date(2026, 11, 8),
    }
    return Bill.model_validate(values | update)


def test_a_bill_is_spread_over_the_days_it_ran_both_ends_counted() -> None:
    bill = _bill()
    assert bill.days == 28
    assert bill.cad_per_day == pytest.approx(8.01 * 1.35 / 28)
    assert _bill(currency="CAD", amount=28.0).cad_per_day == pytest.approx(1.0)


def test_a_bill_that_ends_before_it_starts_or_is_negative_is_refused() -> None:
    with pytest.raises(ValidationError):
        _bill(last_day=date(2026, 10, 1))
    with pytest.raises(ValidationError):
        _bill(amount=-1.0)


def test_the_recorded_bills_load() -> None:
    bills = load_bills(BILLS)
    assert {bill.name for bill in bills} == {"Google Cloud", "X API"}
    assert load_bills(Path("no-such-file.yaml")) == []


def test_the_report_adds_the_bills_to_the_model_cost(store: Store, audience: Audience) -> None:
    without = readme_tables(build_report(store, [], [audience], "peter"))
    assert "billed" not in without
    tables = readme_tables(build_report(store, [], [audience], "peter", bills=[_bill()]))
    assert "X API billed US$8.01 from 2026-10-12 to 2026-11-08, CA$0.386 a day" in tables
