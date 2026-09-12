"""The week-one pipeline end to end, against a source that yields fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

from clippings.cluster.embed import Hashing
from clippings.config.audience import Audience
from clippings.eval.labels import build_queue, record
from clippings.ingest.pipeline import ingest, run_audience
from clippings.ingest.store import Store
from clippings.models import RawItem, SourceKind
from clippings.sources.base import FetchContext, FetchResult
from tests.conftest import NOW

WIRE = (
    "The regulator said on Tuesday it would open a consultation on automated decision "
    "systems used by federal departments, with submissions closing in November."
)
WIRE_REPRINTED = (
    "The regulator said on Tuesday it would open a consultation on automated decision "
    "systems used by federal departments."
)


class FixtureSource:
    """A source that yields what the test gives it, and never touches the network."""

    kind: SourceKind = "rss"

    def __init__(self, *results: FetchResult) -> None:
        self._results = results

    def fetch(self, audience: Audience, context: FetchContext) -> Iterator[FetchResult]:
        yield from self._results


def raw_item(url: str, title: str, summary: str = "", **kwargs: object) -> RawItem:
    return RawItem(
        source_key="gov.example",
        source_kind="rss",
        url=url,
        title=title,
        summary=summary,
        published_at=NOW,
        origin="https://gov.example/feed",
        **kwargs,
    )


def result(*items: RawItem, ok: bool = True, detail: str = "") -> FetchResult:
    return FetchResult(
        source_key="gov.example",
        origin="https://gov.example/feed",
        items=items,
        ok=ok,
        detail=detail,
    )


def test_a_day_runs_end_to_end(audience: Audience, store: Store, context: FetchContext) -> None:
    source = FixtureSource(
        result(
            raw_item("https://gov.example/1", "Regulator opens consultation", WIRE),
            raw_item("https://news.example/1", "Consultation to open", WIRE_REPRINTED),
            raw_item("https://news.example/2", "New bus route", "A transit agency named a route."),
        )
    )
    report = run_audience(audience, store, context, Hashing(), sources=[source], extract=False)

    assert report.fetched == 3
    assert report.new_items == 3
    assert report.clusters == 2, "the reprinted wire copy should collapse into one story"
    assert report.clustered_items == 3
    assert report.collapse_rate == 1.5
    assert report.embedder == "hashing"
    assert report.failures() == []


def test_a_blocked_source_never_reaches_the_store(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    """The blocked item is fetched by the adapter and dropped before it is written."""
    source = FixtureSource(
        result(
            raw_item("https://gov.example/1", "Kept"),
            raw_item("https://blocked.example/1", "Dropped"),
        )
    )
    report = ingest(audience, store, context, run_id="r1", sources=[source])

    assert report.fetched == 2
    assert report.new_items == 1
    assert [one.title for one in store.items_for(audience.id)] == ["Kept"]


def test_a_rerun_stores_nothing_new(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    source = FixtureSource(result(raw_item("https://gov.example/1", "A headline", WIRE)))
    first = ingest(audience, store, context, run_id="r1", sources=[source])
    second = ingest(audience, store, context, run_id="r2", sources=[source])
    assert (first.new_items, second.new_items) == (1, 0)


def test_the_watermark_moves_to_the_newest_item_seen(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    older = raw_item("https://gov.example/1", "Older").model_copy(
        update={"published_at": NOW - timedelta(hours=6)}
    )
    newer = raw_item("https://gov.example/2", "Newer")
    ingest(audience, store, context, run_id="r1", sources=[FixtureSource(result(older, newer))])
    assert store.watermark(audience.id, "gov.example", "https://gov.example/feed") == NOW


def test_a_failed_source_does_not_move_the_watermark(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    """A source that failed must be retried over the same window, not skipped past."""
    failed = FetchResult.failure("gov.example", "https://gov.example/feed", "503")
    ingest(audience, store, context, run_id="r1", sources=[FixtureSource(failed)])
    assert store.watermark(audience.id, "gov.example", "https://gov.example/feed") is None


def test_a_failure_is_reported_rather_than_hidden(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    source = FixtureSource(
        result(raw_item("https://gov.example/1", "Kept")),
        FetchResult.failure("gdelt", "a query", "ConnectTimeout"),
    )
    report = ingest(audience, store, context, run_id="r1", sources=[source])
    assert report.sources_ok == 1
    assert [failure.source_key for failure in report.failures()] == ["gdelt"]
    assert report.new_items == 1, "one source failing must not cost the others their items"


def test_the_run_report_names_which_embedder_produced_the_clusters(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    """A number produced with the hashing fallback must say so."""
    report = run_audience(
        audience,
        store,
        context,
        Hashing(),
        sources=[FixtureSource(result(raw_item("https://gov.example/1", "A headline")))],
        extract=False,
    )
    assert report.embedder == "hashing"


def test_labelling_a_day_records_labels_that_outlive_the_item(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    run_audience(
        audience,
        store,
        context,
        Hashing(),
        sources=[
            FixtureSource(
                result(
                    raw_item("https://gov.example/1", "Regulator opens consultation", WIRE),
                    raw_item("https://news.example/2", "New bus route", "A transit agency."),
                )
            )
        ],
        extract=False,
    )
    day = NOW.date().isoformat()
    queue = build_queue(store, audience.id, day, "peter")
    assert queue.remaining == 2

    for question in queue.questions:
        record(store, queue, question, relevant=question.item.domain == "gov.example")

    labels = store.labels_for(audience.id, day)
    assert len(labels) == 2
    assert {label.relevant for label in labels} == {True, False}
    # The URL and title are copied in, so the label survives retention.
    assert all(label.url for label in labels)

    store.retention(now=NOW + timedelta(days=31))
    assert store.count_items() == 0
    assert len(store.labels_for(audience.id, day)) == 2


def test_labelling_resumes_where_it_stopped(
    audience: Audience, store: Store, context: FetchContext
) -> None:
    run_audience(
        audience,
        store,
        context,
        Hashing(),
        sources=[
            FixtureSource(
                result(
                    raw_item("https://gov.example/1", "One", WIRE),
                    raw_item("https://news.example/2", "Two", "Something else entirely."),
                )
            )
        ],
        extract=False,
    )
    day = NOW.date().isoformat()
    queue = build_queue(store, audience.id, day, "peter")
    record(store, queue, queue.questions[0], relevant=True)

    assert build_queue(store, audience.id, day, "peter").remaining == 1
    # A second labeller starts from the beginning: kappa needs both to see the same items.
    assert build_queue(store, audience.id, day, "someone-else").remaining == 2
