"""The store: retention, watermarks, and one item seen by two audiences."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from clippings.ingest.store import Store
from clippings.models import ItemText
from tests.conftest import NOW, item


def test_retention_deletes_items_past_thirty_days_and_their_text(store: Store) -> None:
    """Article text is kept thirty days and never republished."""
    old = item("old", published_at=NOW - timedelta(days=31))
    recent = item("recent", published_at=NOW - timedelta(days=29))
    store.add_items([old, recent], "an-audience")
    for one in (old, recent):
        store.add_text(ItemText(item_id=one.id, text="the article", extracted_at=NOW, words=100))

    deleted = store.retention(now=NOW)

    assert deleted == {"items": 1, "texts": 1}
    assert store.item_ids() == {"recent"}
    assert store.text_for("old") is None
    assert store.text_for("recent") is not None


def test_retention_on_the_boundary_keeps_the_item(store: Store) -> None:
    store.add_items(
        [item("edge", published_at=NOW - timedelta(days=30) + timedelta(seconds=1))], "a"
    )
    assert store.retention(now=NOW)["items"] == 0


def test_an_item_seen_by_two_audiences_is_one_row(store: Store) -> None:
    shared = item("shared")
    store.add_items([shared], "audience-one")
    store.add_items([shared], "audience-two")
    assert store.count_items() == 1
    assert [one.id for one in store.items_for("audience-one")] == ["shared"]
    assert [one.id for one in store.items_for("audience-two")] == ["shared"]


def test_re_adding_an_item_does_not_count_as_new(store: Store) -> None:
    first = store.add_items([item("a"), item("b")], "an-audience")
    second = store.add_items([item("a"), item("c")], "an-audience")
    assert (first, second) == (2, 1)


def test_a_watermark_never_moves_backwards(store: Store) -> None:
    """A source that republishes an old item must not rewind the window."""
    later = NOW
    earlier = NOW - timedelta(days=3)
    store.set_watermark("an-audience", "gov.example", "https://gov.example/feed", later)
    store.set_watermark("an-audience", "gov.example", "https://gov.example/feed", earlier)
    assert store.watermark("an-audience", "gov.example", "https://gov.example/feed") == later


def test_watermarks_are_per_audience_and_per_origin(store: Store) -> None:
    store.set_watermark("one", "gov.example", "https://gov.example/feed", NOW)
    assert store.watermark("two", "gov.example", "https://gov.example/feed") is None
    assert store.watermark("one", "gov.example", "https://gov.example/other") is None


def test_items_are_returned_newest_first(store: Store) -> None:
    store.add_items(
        [
            item("older", published_at=NOW - timedelta(hours=5)),
            item("newest", published_at=NOW),
            item("middle", published_at=NOW - timedelta(hours=2)),
        ],
        "an-audience",
    )
    assert [one.id for one in store.items_for("an-audience")] == ["newest", "middle", "older"]


def test_the_since_window_filters_the_pool(store: Store) -> None:
    store.add_items(
        [item("in", published_at=NOW), item("out", published_at=NOW - timedelta(days=4))],
        "an-audience",
    )
    pool = store.items_for("an-audience", since=NOW - timedelta(days=2))
    assert [one.id for one in pool] == ["in"]


def test_the_database_survives_being_closed_and_reopened(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "nested" / "clippings.duckdb"
    with Store.open(path) as opened:
        opened.add_items([item("kept")], "an-audience")
    with Store.open(path) as reopened:
        assert reopened.item_ids() == {"kept"}


def test_the_fetch_log_records_a_failure(store: Store) -> None:
    """A source that failed must be countable, or uptime and source yield both flatter."""
    store.log_fetch(
        run_id="r1",
        audience_id="an-audience",
        source_key="gov.example",
        origin="https://gov.example/feed",
        started_at=datetime.now(UTC),
        items=0,
        ok=False,
        detail="ConnectTimeout",
    )
    rows = store._connection.execute("SELECT ok, detail FROM fetch_log").fetchall()
    assert rows == [(False, "ConnectTimeout")]


def test_times_come_back_in_utc_whatever_the_machine_says() -> None:
    """DuckDB returns TIMESTAMPTZ in the session zone, which defaults to the machine's."""
    from datetime import UTC, timedelta

    from clippings.ingest.store import Store
    from tests.conftest import NOW, item

    with Store.memory() as store:
        store.add_items([item("a")], "test-audience")
        published = store.items_for("test-audience")[0].published_at
    assert published == NOW
    assert published.utcoffset() == timedelta(0)
    assert published.tzinfo is not None and published.astimezone(UTC).hour == NOW.hour


def test_a_checkpointed_file_copied_mid_run_holds_what_was_written(tmp_path: Path) -> None:
    """The daily job uploads the database after each audience while it is still open."""
    import shutil

    from clippings.ingest.store import Store
    from tests.conftest import item

    path = tmp_path / "live.duckdb"
    with Store.open(path) as store:
        store.add_items([item("a")], "test-audience")
        store.checkpoint()
        shutil.copy(path, tmp_path / "copy.duckdb")
    with Store.open(tmp_path / "copy.duckdb") as copy:
        assert copy.count_items() == 1
