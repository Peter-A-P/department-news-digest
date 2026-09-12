"""The run lock: a second job does not write."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from clippings.ingest.remote import LocalObjectStore, LocalRunLock, RunLockHeld


def test_a_second_run_cannot_take_the_lock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Cloud Run retries a failed job; two containers can be alive at once."""
    first = LocalRunLock(tmp_path / "run.lock")
    first.acquire("container-one")
    second = LocalRunLock(tmp_path / "run.lock")
    with pytest.raises(RunLockHeld, match="container-one"):
        second.acquire("container-two")


def test_the_lock_is_released_and_can_be_retaken(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "run.lock"
    with LocalRunLock(path):
        assert path.exists()
    assert not path.exists()
    LocalRunLock(path).acquire("the next run")


def test_the_lock_is_released_even_when_the_run_fails(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "run.lock"
    with pytest.raises(ValueError, match="the run failed"), LocalRunLock(path):
        raise ValueError("the run failed")
    assert not path.exists()


def test_a_stale_lock_is_broken(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A container killed mid-run must not block every run after it."""
    path = tmp_path / "run.lock"
    path.write_text(
        json.dumps(
            {
                "holder": "a container that died",
                "taken_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    lock = LocalRunLock(path, ttl=timedelta(hours=2))
    lock.acquire("the next run")
    assert json.loads(path.read_text(encoding="utf-8"))["holder"] == "the next run"


def test_a_fresh_lock_is_not_broken(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "run.lock"
    LocalRunLock(path).acquire("the running job")
    with pytest.raises(RunLockHeld):
        LocalRunLock(path, ttl=timedelta(hours=2)).acquire("an impatient job")


def test_an_unreadable_lock_file_is_treated_as_broken(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "run.lock"
    path.write_text("not json at all", encoding="utf-8")
    LocalRunLock(path).acquire("the next run")


def test_releasing_a_lock_this_process_does_not_hold_does_nothing(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A second job exiting must not delete the first job's lock on its way out."""
    path = tmp_path / "run.lock"
    holder = LocalRunLock(path)
    holder.acquire("container-one")
    loser = LocalRunLock(path)
    with pytest.raises(RunLockHeld):
        loser.acquire("container-two")
    loser.release()
    assert path.exists(), "the losing run deleted the winner's lock"


def test_the_object_store_round_trips_the_database_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bucket = LocalObjectStore(tmp_path / "bucket")
    source = tmp_path / "clippings.duckdb"
    source.write_bytes(b"a database")
    bucket.upload(source, "state/clippings.duckdb")

    destination = tmp_path / "restored" / "clippings.duckdb"
    assert bucket.download("state/clippings.duckdb", destination) is True
    assert destination.read_bytes() == b"a database"


def test_downloading_a_database_that_is_not_there_yet_is_not_an_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The first run of a new environment has no file in the bucket."""
    bucket = LocalObjectStore(tmp_path / "bucket")
    assert bucket.download("state/clippings.duckdb", tmp_path / "x.duckdb") is False
