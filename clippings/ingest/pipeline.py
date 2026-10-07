"""One audience, one day: fetch, normalise, store, extract, cluster.

Plain functions, because week 2 wraps them in a LangGraph graph and a node should be a
call, not a reimplementation. Everything that decides anything lives here; the graph
decides only what runs next.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from clippings.cluster.cluster import build_clusters, collapse_rate
from clippings.cluster.embed import Embedder, backend_name
from clippings.config.audience import Audience
from clippings.ingest.extract import extract_one
from clippings.ingest.normalise import normalise
from clippings.ingest.store import Store
from clippings.models import Cluster, Item
from clippings.rank.features import embed_stories
from clippings.rank.score import ScoredStory, score_stories
from clippings.rank.select import Selection, candidates_for_rerank, select
from clippings.sources.base import FetchContext, FetchResult, Source
from clippings.sources.bluesky import BlueskySource
from clippings.sources.gdelt import GdeltSource
from clippings.sources.reddit import RedditSource
from clippings.sources.rss import RssSource


def default_sources() -> tuple[Source, ...]:
    """Every adapter. Which ones do anything is decided by the audience file."""
    return (RssSource(), GdeltSource(), RedditSource(), BlueskySource())


@dataclass(frozen=True)
class SourceReport:
    """What one origin produced, for the source-yield table and for uptime."""

    source_key: str
    origin: str
    fetched: int
    stored: int
    ok: bool
    detail: str


@dataclass
class RunReport:
    """Everything the run did, in a shape the CLI prints and week 3 measures from."""

    audience_id: str
    run_id: str
    day: str
    started_at: datetime
    finished_at: datetime | None = None
    sources: list[SourceReport] = field(default_factory=list)
    new_items: int = 0
    extracted: int = 0
    extraction_skipped: dict[str, int] = field(default_factory=dict)
    clusters: int = 0
    clustered_items: int = 0
    embedder: str = ""
    # The ranked stories, best first, and the K chosen for the digest. Week 2 hands the
    # candidates to the gateway re-ranker; nothing here calls a model.
    ranked: list[ScoredStory] = field(default_factory=list)
    selected: list[ScoredStory] = field(default_factory=list)
    displaced: int = 0

    @property
    def fetched(self) -> int:
        return sum(source.fetched for source in self.sources)

    @property
    def sources_ok(self) -> int:
        return sum(1 for source in self.sources if source.ok)

    @property
    def collapse_rate(self) -> float:
        return collapse_rate(self.clustered_items, self.clusters)

    def failures(self) -> list[SourceReport]:
        return [source for source in self.sources if not source.ok]


def new_run_id(now: datetime | None = None) -> str:
    """A run id that sorts by time and is unique per container."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def ingest(
    audience: Audience,
    store: Store,
    context: FetchContext,
    *,
    run_id: str,
    sources: Sequence[Source] | None = None,
    report: RunReport | None = None,
) -> RunReport:
    """Fetch every source for this audience and store what is new."""
    report = report or RunReport(
        audience_id=audience.id,
        run_id=run_id,
        day=context.now.date().isoformat(),
        started_at=context.now,
    )
    context.watermarks = _watermarks(store, audience)
    for source in sources or default_sources():
        for result in source.fetch(audience, context):
            report.sources.append(_absorb(result, audience, store, run_id, context))
    report.new_items = sum(source.stored for source in report.sources)
    return report


def _watermarks(store: Store, audience: Audience) -> dict[tuple[str, str], datetime]:
    marks: dict[tuple[str, str], datetime] = {}
    for feed in audience.sources.feeds:
        mark = store.watermark(audience.id, feed.terms, feed.url)
        if mark:
            marks[(feed.terms, feed.url)] = mark
    for key, origins in (
        ("gdelt", audience.sources.gdelt.queries),
        ("reddit", audience.sources.reddit.subreddits),
        ("bluesky", audience.sources.bluesky.queries),
    ):
        for origin in origins:
            mark = store.watermark(audience.id, key, origin)
            if mark:
                marks[(key, origin)] = mark
    return marks


def _absorb(
    result: FetchResult,
    audience: Audience,
    store: Store,
    run_id: str,
    context: FetchContext,
) -> SourceReport:
    """Normalise one fetch result into the store and move its watermark."""
    items: list[Item] = []
    for raw in result.items:
        item = normalise(raw, audience, fetched_at=context.now)
        if item is not None:
            items.append(item)
    stored = store.add_items(items, audience.id) if items else 0
    store.log_fetch(
        run_id=run_id,
        audience_id=audience.id,
        source_key=result.source_key,
        origin=result.origin,
        started_at=context.now,
        items=len(items),
        ok=result.ok,
        detail=result.detail,
    )
    if result.ok and items:
        # The watermark follows the newest item actually seen, not the clock: a source that
        # publishes with a delay would otherwise have its next window skip over the gap.
        store.set_watermark(
            audience.id,
            result.source_key,
            result.origin,
            max(item.published_at for item in items),
        )
    return SourceReport(
        source_key=result.source_key,
        origin=result.origin,
        fetched=len(result.items),
        stored=stored,
        ok=result.ok,
        detail=result.detail,
    )


def extract_texts(
    items: Sequence[Item],
    audience: Audience,
    store: Store,
    context: FetchContext,
    report: RunReport,
) -> None:
    """Fetch and store article text for items that do not have it yet."""
    for item in items:
        if store.text_for(item.id) is not None:
            continue
        outcome = extract_one(item, audience, context)
        if outcome.text is not None:
            store.add_text(outcome.text)
            report.extracted += 1
        else:
            reason = outcome.reason.split(":")[0]
            report.extraction_skipped[reason] = report.extraction_skipped.get(reason, 0) + 1


def cluster_day(
    audience: Audience,
    store: Store,
    embedder: Embedder,
    *,
    items: Sequence[Item],
    day: str,
) -> list[Cluster]:
    """Cluster the day's pool for one audience and save the result."""
    clusters = build_clusters(items, audience, embedder, day)
    store.save_clusters(clusters)
    return clusters


def run_audience(
    audience: Audience,
    store: Store,
    context: FetchContext,
    embedder: Embedder,
    *,
    run_id: str | None = None,
    sources: Sequence[Source] | None = None,
    extract: bool = True,
    window_hours: int = 48,
) -> RunReport:
    """Every stage that costs nothing, for one audience: fetch, store, extract, cluster,
    rank, and choose from the pre-filter's order. The graph runs the same stages and then
    hands the candidates to the re-ranker; this is what runs when no model may be called."""
    run_id = run_id or new_run_id(context.now)
    report = ingest(audience, store, context, run_id=run_id, sources=sources)
    pool = rank_day(
        audience, store, context, embedder, report, extract=extract, window_hours=window_hours
    )
    # The re-ranker only ever sees this slice, and the digest is chosen from it.
    candidates = candidates_for_rerank(report.ranked, audience.digest.rerank_candidates)
    selection = choose(candidates, pool, embedder, audience.digest.max_stories)
    report.selected = list(selection.stories)
    report.displaced = len(selection.displaced)

    report.finished_at = datetime.now(UTC)
    return report


def rank_day(
    audience: Audience,
    store: Store,
    context: FetchContext,
    embedder: Embedder,
    report: RunReport,
    *,
    extract: bool = True,
    window_hours: int = 48,
) -> dict[str, Item]:
    """Extract, cluster and score the day's pool. Returns the pool by item id."""
    since = context.now.replace(microsecond=0) - timedelta(hours=window_hours)
    pool = store.items_for(audience.id, since=since)
    if extract:
        extract_texts(pool, audience, store, context, report)

    day = context.now.date().isoformat()
    clusters = cluster_day(audience, store, embedder, items=pool, day=day)
    report.clusters = len(clusters)
    report.clustered_items = len(pool)
    report.embedder = backend_name(embedder)

    by_id = {item.id: item for item in pool}
    report.ranked = score_stories(clusters, by_id, audience, embedder, context.now)
    return by_id


def choose(
    stories: Sequence[ScoredStory],
    pool: dict[str, Item],
    embedder: Embedder,
    k: int,
    *,
    tiers: Mapping[str, float] | None = None,
) -> Selection:
    """The digest's K stories from an ordered list, with the diversity penalty applied within
    the re-ranker's tiers when there are any."""
    vectors = embed_stories([story.cluster for story in stories], pool, embedder)
    return select(stories, vectors, k, tiers=tiers)
