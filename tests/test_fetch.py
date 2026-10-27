"""`clippings fetch`: one source for every audience, stored and nothing else."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from clippings import cli
from clippings.config.audience import Audience
from clippings.ingest.remote import LocalRunLock
from clippings.ingest.store import Store
from clippings.models import SourceKind
from clippings.sources.base import FetchContext, FetchResult
from tests.test_pipeline import raw_item, result


class Gdelt:
    """Stands in for GDELT: one instance, so the test sees it was shared."""

    kind: SourceKind = "gdelt"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        self.asked.append(audience.id)
        yield result(raw_item(f"https://gov.example/{audience.id}", f"News for {audience.id}"))


@pytest.fixture
def two(audience: Audience) -> list[Audience]:
    return [audience, audience.model_copy(update={"id": "second-audience"})]


def _invoke(tmp_path: Path, *args: str) -> Result:
    return CliRunner().invoke(
        cli.app,
        ["fetch", *args, "--db", str(tmp_path / "c.duckdb"), "--lock", str(tmp_path / "run.lock")],
        env={"CLIPPINGS_BUCKET": None},
    )


def test_a_fetch_stores_every_audiences_items_and_builds_nothing(
    tmp_path: Path, two: list[Audience], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Gdelt()
    monkeypatch.setattr(cli, "default_sources", lambda: (source,))
    monkeypatch.setattr(cli, "load_audiences", lambda _: two)
    outcome = _invoke(tmp_path, "gdelt")
    assert outcome.exit_code == 0, outcome.output
    assert source.asked == ["test-audience", "second-audience"]
    with Store.open(tmp_path / "c.duckdb") as store:
        for one in two:
            assert [item.title for item in store.items_for(one.id)] == [f"News for {one.id}"]
            assert store.cluster_days(one.id) == [] and store.digest_days(one.id) == []


def test_a_fetch_steps_aside_while_the_daily_run_holds_the_lock(
    tmp_path: Path, two: list[Audience], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Gdelt()
    monkeypatch.setattr(cli, "default_sources", lambda: (source,))
    monkeypatch.setattr(cli, "load_audiences", lambda _: two)
    LocalRunLock(tmp_path / "run.lock").acquire("the daily run")
    outcome = _invoke(tmp_path, "gdelt")
    assert outcome.exit_code == 0 and "steps aside" in outcome.output
    assert source.asked == []


def test_an_unknown_source_is_refused(tmp_path: Path) -> None:
    outcome = _invoke(tmp_path, "teletext")
    assert outcome.exit_code == 2
