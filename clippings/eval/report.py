"""The numbers in the README, computed from the run's store and the labellers' files.

PLAN.md section 1 lists what a stranger can check; this module is the only thing that writes
them. The README's result tables sit between markers and are replaced whole, so no number in
them is typed by hand. A number that needs labels nobody has given yet, or a study nobody has
run, is printed as "not yet" with what it is waiting for, never as a zero.

Every figure carries a 95% interval from the 03 gate's own statistics
(`drift.analysis.stats`): a percentile bootstrap for means and ratios, the Jeffreys interval
for a share that came out at none or all, so "100%" of 40 is never printed as a certainty.

Recall is a ratio estimate over a stratified sample (PLAN.md section 2.6). The top stratum is
a census of the stories the system ranked highest, the random stratum a sample of the rest in
which each label stands for `weight` stories. The interval resamples each day's random
stratum with replacement; the top stratum, being a census, is not resampled. It is printed as
an importance-weighted estimate, because that is what it is.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from drift.analysis.stats import Estimate, bootstrap_mean, jeffreys_proportion, percentile
from gate.judge.calibration import cohens_kappa

from clippings.assemble.digest import Digest
from clippings.config.audience import Audience
from clippings.eval.labels import ranked_ids_for_day
from clippings.eval.sample import stratified_sample
from clippings.ingest.store import Store
from clippings.models import Label

RESAMPLES = 2000
NOT_YET = "_not yet_"

README_START = "<!-- report:start -->"
README_END = "<!-- report:end -->"


# -- the estimators --------------------------------------------------------------------------


@dataclass(frozen=True)
class DayLabels:
    """One fully labelled day of one audience, as the recall estimate needs it."""

    day: str
    shown_relevant: int
    top: tuple[bool, ...]
    random: tuple[bool, ...]
    # How many unlabelled stories each random-stratum label stands for.
    weight: float


def _ratio(days: Sequence[DayLabels], randoms: Sequence[Sequence[bool]]) -> float:
    shown = sum(day.shown_relevant for day in days)
    total = sum(
        sum(day.top) + day.weight * sum(drawn) for day, drawn in zip(days, randoms, strict=True)
    )
    return shown / total if total else float("nan")


def recall(days: Sequence[DayLabels], *, resamples: int = RESAMPLES, seed: int = 0) -> Estimate:
    """Relevant stories the digests showed, over the relevant stories estimated in the pools."""
    n = sum(len(day.top) + len(day.random) for day in days)
    point = _ratio(days, [day.random for day in days])
    if not days or math.isnan(point):
        return Estimate(point, float("nan"), float("nan"), n)
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        randoms = [[day.random[rng.randrange(len(day.random))] for _ in day.random] for day in days]
        value = _ratio(days, randoms)
        if not math.isnan(value):
            draws.append(value)
    draws.sort()
    if not draws:
        return Estimate(point, float("nan"), float("nan"), n)
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return Estimate(point, lo, hi, n)


def share(flags: Sequence[bool]) -> Estimate:
    """A share of yes/no units, with the gate's interval (Jeffreys at none or all)."""
    return bootstrap_mean([1.0 if flag else 0.0 for flag in flags])


def counted_share(successes: int, n: int) -> Estimate:
    return jeffreys_proportion(successes, n)


def quantile(
    values: Sequence[float], q: float, *, resamples: int = RESAMPLES, seed: int = 0
) -> Estimate:
    """A percentile with a percentile-bootstrap interval."""
    n = len(values)
    if n == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    rng = random.Random(seed)
    draws = sorted(
        percentile([values[rng.randrange(n)] for _ in range(n)], q) for _ in range(resamples)
    )
    return Estimate(
        percentile(values, q),
        draws[int(0.025 * resamples)],
        draws[min(resamples - 1, int(0.975 * resamples))],
        n,
    )


def kappa(
    pairs: Sequence[tuple[bool, bool]], *, resamples: int = RESAMPLES, seed: int = 0
) -> Estimate:
    """Cohen's kappa between two labellers on the stories both judged, bootstrapped over them."""
    n = len(pairs)
    point = cohens_kappa(pairs)
    if n == 0 or math.isnan(point):
        return Estimate(point, float("nan"), float("nan"), n)
    rng = random.Random(seed)
    draws = sorted(
        value
        for value in (
            cohens_kappa([pairs[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples)
        )
        if not math.isnan(value)
    )
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return Estimate(point, lo, hi, n)


# -- what is measured, per audience and overall -----------------------------------------------


@dataclass
class AudienceResult:
    audience_id: str
    name: str
    digests: int
    stories_per_day: Estimate
    cost: Estimate
    labelled_days: list[str] = field(default_factory=list)
    precision: Estimate | None = None
    recall: Estimate | None = None
    kappa: Estimate | None = None
    kappa_with: str = ""


@dataclass
class SourceYield:
    audience_id: str
    source: str
    ingested: int
    in_digest: int
    labelled: int
    relevant: int


@dataclass
class Report:
    generated_at: datetime
    first_day: str
    last_day: str
    labeller: str
    audiences: list[AudienceResult]
    digests: int
    collapse: Estimate
    quotes_first: Estimate
    quotes_after_repair: Estimate
    citation_first: Estimate
    lag_p50: Estimate
    lag_p90: Estimate
    cost_per_day: Estimate
    uncosted_calls: int
    pair_labels: int
    sources: list[SourceYield]


def _complete_days(
    store: Store, labels: list[Label], audience_id: str, labeller: str
) -> dict[str, list[Label]]:
    """This labeller's labels by day, for the days whose whole sample they judged."""
    by_day: dict[str, list[Label]] = defaultdict(list)
    for label in labels:
        if label.audience_id == audience_id and label.labeller == labeller:
            by_day[label.day].append(label)
    complete = {}
    for day, day_labels in by_day.items():
        sample = stratified_sample(ranked_ids_for_day(store, audience_id, day), audience_id, day)
        if {unit.item_id for unit in sample.units} <= {label.item_id for label in day_labels}:
            complete[day] = day_labels
    return complete


def _shown_items(store: Store, digest: Digest) -> list[str]:
    clusters = {
        cluster.id: cluster for cluster in store.clusters_for(digest.audience_id, digest.day)
    }
    return [
        clusters[story.story_id].representative_id
        for story in digest.stories
        if story.story_id in clusters
    ]


def build_report(
    store: Store,
    labels: list[Label],
    audiences: Sequence[Audience],
    labeller: str,
    *,
    now: datetime | None = None,
) -> Report:
    digests = [
        digest
        for audience in audiences
        for day in sorted(store.digest_days(audience.id))
        if (digest := store.digest_for(audience.id, day)) is not None
    ]
    results = []
    for audience in audiences:
        mine = [digest for digest in digests if digest.audience_id == audience.id]
        result = AudienceResult(
            audience_id=audience.id,
            name=audience.name,
            digests=len(mine),
            stories_per_day=bootstrap_mean([float(len(d.stories)) for d in mine]),
            cost=bootstrap_mean([d.cost_usd for d in mine]),
        )
        complete = _complete_days(store, labels, audience.id, labeller)
        result.labelled_days = sorted(complete)
        if complete:
            shown_flags: list[bool] = []
            days: list[DayLabels] = []
            for day, day_labels in sorted(complete.items()):
                by_item = {label.item_id: label for label in day_labels}
                digest = next((d for d in mine if d.day == day), None)
                shown = _shown_items(store, digest) if digest else []
                flags = [by_item[item_id].relevant for item_id in shown if item_id in by_item]
                shown_flags += flags
                random_labels = [label for label in day_labels if label.stratum == "random"]
                days.append(
                    DayLabels(
                        day=day,
                        shown_relevant=sum(flags),
                        top=tuple(label.relevant for label in day_labels if label.stratum == "top"),
                        random=tuple(label.relevant for label in random_labels),
                        weight=random_labels[0].weight if random_labels else 0.0,
                    )
                )
            result.precision = share(shown_flags)
            result.recall = recall(days)
        others = {
            label.labeller
            for label in labels
            if label.audience_id == audience.id and label.labeller != labeller
        }
        mine_by_key = {
            (label.day, label.item_id): label.relevant
            for label in labels
            if label.audience_id == audience.id and label.labeller == labeller
        }
        for other in sorted(others):
            pairs = [
                (mine_by_key[(label.day, label.item_id)], label.relevant)
                for label in labels
                if label.audience_id == audience.id
                and label.labeller == other
                and (label.day, label.item_id) in mine_by_key
            ]
            if pairs:
                result.kappa, result.kappa_with = kappa(pairs), other
                break
        results.append(result)

    totals: Counter[str] = Counter()
    lags: list[float] = []
    for digest in digests:
        c = digest.counts
        totals["quotes_first"] += c.quotes_first
        totals["quotes_verbatim_first"] += c.quotes_verbatim_first
        totals["quotes_after_repair"] += c.quotes_after_repair
        totals["quotes_verbatim_after_repair"] += c.quotes_verbatim_after_repair
        totals["drafted"] += c.sentences_drafted
        totals["cited_first"] += c.sentences_cited_first
        totals["uncosted"] += digest.uncosted_calls
        for story in digest.stories:
            hours = (digest.generated_at - story.published_at).total_seconds() / 3600
            lags.append(max(0.0, hours))
    by_day: dict[str, float] = defaultdict(float)
    for digest in digests:
        by_day[digest.day] += digest.cost_usd

    days_seen = sorted({digest.day for digest in digests})
    return Report(
        generated_at=now or datetime.now(UTC),
        first_day=days_seen[0] if days_seen else "",
        last_day=days_seen[-1] if days_seen else "",
        labeller=labeller,
        audiences=results,
        digests=len(digests),
        collapse=bootstrap_mean([d.pool_items / d.pool_stories for d in digests if d.pool_stories]),
        quotes_first=counted_share(totals["quotes_verbatim_first"], totals["quotes_first"]),
        quotes_after_repair=counted_share(
            totals["quotes_verbatim_after_repair"], totals["quotes_after_repair"]
        ),
        citation_first=counted_share(totals["cited_first"], totals["drafted"]),
        lag_p50=quantile(lags, 0.5),
        lag_p90=quantile(lags, 0.9),
        cost_per_day=bootstrap_mean(list(by_day.values())),
        uncosted_calls=totals["uncosted"],
        pair_labels=sum(len(store.pair_labels_for(a.id)) for a in audiences),
        sources=source_yield(store, labels, audiences, digests, labeller),
    )


def source_yield(
    store: Store,
    labels: list[Label],
    audiences: Sequence[Audience],
    digests: Sequence[Digest],
    labeller: str,
) -> list[SourceYield]:
    """Per source: items held, items a digest showed or cited, and labelled relevance."""
    rows = []
    for audience in audiences:
        items = {item.id: item for item in store.items_for(audience.id)}
        ingested = Counter(item.source_key for item in items.values())
        used = {
            link.item_id
            for digest in digests
            if digest.audience_id == audience.id
            for story in digest.stories
            for link in story.sources
        }
        in_digest = Counter(items[i].source_key for i in used if i in items)
        judged = [
            label
            for label in labels
            if label.audience_id == audience.id
            and label.labeller == labeller
            and label.item_id in items
        ]
        labelled = Counter(items[label.item_id].source_key for label in judged)
        relevant = Counter(items[label.item_id].source_key for label in judged if label.relevant)
        rows += [
            SourceYield(
                audience.id, source, count, in_digest[source], labelled[source], relevant[source]
            )
            for source, count in ingested.most_common()
        ]
    return rows


# -- writing it down --------------------------------------------------------------------------


def pct(estimate: Estimate | None) -> str:
    if estimate is None or math.isnan(estimate.point):
        return NOT_YET
    if math.isnan(estimate.lo):
        return f"{estimate.point:.0%} (interval undefined, n={estimate.n})"
    return f"{estimate.point:.0%} ({estimate.lo:.0%} to {estimate.hi:.0%})"


def num(estimate: Estimate | None, fmt: str = ".2f", unit: str = "") -> str:
    if estimate is None or math.isnan(estimate.point):
        return NOT_YET
    if estimate.lo == estimate.hi == estimate.point:
        # Every unit had the same value: a count, not an estimate, so no interval is invented.
        return f"{estimate.point:{fmt}}{unit} on all {estimate.n}"
    return f"{estimate.point:{fmt}}{unit} ({estimate.lo:{fmt}} to {estimate.hi:{fmt}})"


def usd(estimate: Estimate) -> str:
    if math.isnan(estimate.point):
        return NOT_YET
    return f"US${estimate.point:.3f} (US${estimate.lo:.3f} to US${estimate.hi:.3f})"


def readme_tables(report: Report) -> str:
    labelled = sum(len(result.labelled_days) for result in report.audiences)
    lines = [
        f"Measured over {report.digests} digests from {report.first_day} to {report.last_day}, "
        f"by `clippings report` on {report.generated_at:%Y-%m-%d}. 95% intervals throughout. "
        f"{labelled} audience-days hand-labelled so far; the relevance columns fill as the "
        "labelled week does.",
        "",
        "**Relevance, per audience, against a hand-labelled week**",
        "",
        "| Audience | Precision at K (95% CI) | Recall, importance-weighted (95% CI) "
        "| Labeller kappa | Stories per day | Cost per digest |",
        "|---|---|---|---|---|---|",
    ]
    for result in report.audiences:
        days = f", {len(result.labelled_days)} days" if result.labelled_days else ""
        lines.append(
            f"| {result.name} | {pct(result.precision)}{days} | {pct(result.recall)} "
            f"| {num(result.kappa)} | {num(result.stories_per_day, '.1f')} "
            f"| {usd(result.cost)} |"
        )
    pairs = (
        NOT_YET + " (pair labels)"
        if report.pair_labels == 0
        else f"{report.pair_labels} pairs labelled"
    )
    lines += [
        "",
        "**Pipeline properties**",
        "",
        "| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / "
        "after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) "
        "| Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) "
        "| Uptime, measurement month |",
        "|---|---|---|---|---|---|---|---|",
        f"| {pairs} | {num(report.collapse)} items per story | {pct(report.quotes_first)} / "
        f"{pct(report.quotes_after_repair)} | {pct(report.citation_first)} "
        f"| {NOT_YET} (hand check) | {num(report.lag_p50, '.0f', ' h')} / "
        f"{num(report.lag_p90, '.0f', ' h')} | {NOT_YET} (reader study) "
        f"| {NOT_YET} (measurement month) |",
        "",
        f"All four digests together cost {usd(report.cost_per_day)} a day in model calls, from "
        "the gateway's ledger"
        + (f" ({report.uncosted_calls} calls uncosted)" if report.uncosted_calls else "")
        + ". Details, per source and per day: [docs/report.md](docs/report.md).",
    ]
    return "\n".join(lines)


def detail(report: Report) -> str:
    lines = [
        "# Report",
        "",
        "Written by `clippings report`; do not edit by hand. 95% intervals throughout.",
        "",
        readme_tables(report),
        "",
        "## Labelled days",
        "",
        f"Labeller for precision and recall: `{report.labeller}`. A day counts once its whole "
        "sample is labelled.",
        "",
    ]
    for result in report.audiences:
        days = ", ".join(result.labelled_days) or "none yet"
        extra = f"; kappa against `{result.kappa_with}`" if result.kappa_with else ""
        lines.append(f"- {result.name}: {days}{extra}")
    lines += [
        "",
        "## Source yield",
        "",
        "Items held (thirty days), items a digest showed or cited, and, once labelled, the share "
        "of each source's labelled stories judged relevant.",
        "",
        "| Audience | Source | Items held | In a digest | Share in a digest (95% CI) "
        "| Relevant of labelled |",
        "|---|---|---|---|---|---|",
    ]
    for row in report.sources:
        relevant = (
            f"{row.relevant} of {row.labelled}, {pct(counted_share(row.relevant, row.labelled))}"
            if row.labelled
            else NOT_YET
        )
        lines.append(
            f"| {row.audience_id} | {row.source} | {row.ingested} | {row.in_digest} "
            f"| {pct(counted_share(row.in_digest, row.ingested))} | {relevant} |"
        )
    return "\n".join(lines) + "\n"


def replace_between_markers(text: str, block: str) -> str:
    """The README with its result block replaced; the markers must already be there."""
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.S)
    if not pattern.search(text):
        raise ValueError(f"the README has no {README_START} ... {README_END} block")
    return pattern.sub(lambda _: f"{README_START}\n{block}\n{README_END}", text, count=1)


def all_labels(stores: Iterable[Store]) -> list[Label]:
    return [label for store in stores for label in store.all_labels()]
