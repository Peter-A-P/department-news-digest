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
which each label stands for `weight` stories. The interval resamples the labelled days, then
each drawn day's random stratum as a binomial (Jeffreys at none or all); within a day the top
stratum, being a census, is not resampled. It is printed as an importance-weighted estimate,
because that is what it is.

Precision resamples whole days too. Stories from one morning's digest share a pool and a
news cycle, so they are not independent evidence; until 2026-10-17 both intervals treated
them as if they were, and recall's reflected only the random strata, not how much the
digest varied from one day to the next.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from drift.analysis.stats import (
    Estimate,
    bootstrap_mean,
    bootstrap_mean_by_cluster,
    jeffreys_proportion,
    percentile,
)
from gate.judge.calibration import cohens_kappa
from gate.stats import rate_draw

from clippings.assemble.digest import Digest
from clippings.config.audience import Audience
from clippings.constants import CAD_PER_USD, MEASUREMENT_FROM, MEASUREMENT_TO, UPTIME_FROM, cad
from clippings.eval.bills import Bill
from clippings.eval.labels import ranked_ids_for_day
from clippings.eval.sample import DEFAULT_TOP, stratified_sample
from clippings.eval.uptime import UptimeDay, uptime_days
from clippings.ingest.store import Store
from clippings.models import FaithLabel, Label, PairLabel, PurityLabel, ReaderSession

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


def _ratio(days: Sequence[DayLabels], buried: Sequence[float]) -> float:
    shown = sum(day.shown_relevant for day in days)
    total = sum(sum(day.top) + extra for day, extra in zip(days, buried, strict=True))
    return shown / total if total else float("nan")


def recall(days: Sequence[DayLabels], *, resamples: int = RESAMPLES, seed: int = 0) -> Estimate:
    """Relevant stories the digests showed, over the relevant stories estimated in the pools.

    Each replicate draws the days with replacement, then redraws every drawn day's random
    stratum as a binomial at the 03 gate's `rate_draw`: the observed share, or at none or all
    the Jeffreys posterior. A plain resample of a stratum with no relevant story in it redraws
    nothing every time and prints a zero-width interval, as if "none found in 18" meant "none
    there" (the first labelled days, 2026-10-10, did exactly that).

    Without the draw over days, the only uncertainty left was the random strata's, and in a
    week where no random stratum held a must-read story the Jeffreys draws could only add
    buried stories: the point was the top of its own interval, which said nothing about how
    the digest did on a day not labelled (found 2026-10-17: AI must-read recall printed 83%,
    63% to 83%; drawn over days it is 57% to 100%).
    """
    n = sum(len(day.top) + len(day.random) for day in days)
    point = _ratio(days, [day.weight * sum(day.random) for day in days])
    if not days or math.isnan(point):
        return Estimate(point, float("nan"), float("nan"), n, len(days))
    if len(days) == 1 and not days[0].random:
        # One census day: nothing to resample, so no interval is invented.
        return Estimate(point, float("nan"), float("nan"), n, 1)
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        drawn = [days[rng.randrange(len(days))] for _ in days]
        buried = []
        for day in drawn:
            size = len(day.random)
            rate = rate_draw(rng, sum(day.random), size)
            buried.append(day.weight * sum(1 for _ in range(size) if rng.random() < rate))
        value = _ratio(drawn, buried)
        if not math.isnan(value):
            draws.append(value)
    draws.sort()
    if not draws:
        return Estimate(point, float("nan"), float("nan"), n, len(days))
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return Estimate(point, lo, hi, n, len(days))


def share(flags: Sequence[bool]) -> Estimate:
    """A share of yes/no units, with the gate's interval (Jeffreys at none or all)."""
    return bootstrap_mean([1.0 if flag else 0.0 for flag in flags])


def share_by_day(flags: Sequence[bool], days: Sequence[str]) -> Estimate:
    """A share of yes/no units that come in days, resampled a whole day at a time."""
    return bootstrap_mean_by_cluster([1.0 if flag else 0.0 for flag in flags], days)


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


@dataclass(frozen=True)
class PairDay:
    """One audience-day's labelled pairs, as the deduplication estimates need them."""

    day: str
    together: tuple[bool, ...]
    together_weight: float
    near: tuple[bool, ...]
    near_weight: float


def _stratum_draws(
    rng: random.Random, drawn: Sequence[Sequence[bool]], pooled: Sequence[Sequence[bool]]
) -> list[int]:
    """Each drawn day's count of yeses in one stratum, for one bootstrap replicate.

    When the stratum, pooled over every labelled day, holds both answers, each drawn day's
    labels are resampled with replacement: a two-stage bootstrap, days and then the pairs
    drawn within them, so a day with none stays at none. When it holds only one (no
    missed duplicate in any day's "near" pairs, say), one rate is drawn for the replicate at
    the gate's `rate_draw`, Jeffreys at none or all, and every drawn day is redrawn at it, so
    "none in 160" is not printed as a certainty.

    Until 2026-10-25 every day was redrawn at its own Jeffreys rate. Over 27 labelled days,
    22 of whose six "near" pairs held no duplicate, that treated each of them as evidence of
    a rate near 7% and put dedup recall at 85% with an interval of 40% to 84%, the point
    above its own interval; precision, from days with five of five, was pulled down the same
    way.
    """
    k = sum(sum(flags) for flags in pooled)
    n = sum(len(flags) for flags in pooled)
    if 0 < k < n:
        return [sum(rng.choice(flags) for _ in flags) if flags else 0 for flags in drawn]
    rate = rate_draw(rng, k, n)
    return [sum(1 for _ in flags if rng.random() < rate) for flags in drawn]


def dedup_scores(
    days: Sequence[PairDay], *, resamples: int = RESAMPLES, seed: int = 0
) -> tuple[Estimate, Estimate]:
    """Pairwise precision and recall of the clustering, from a stratified sample of pairs.

    Precision: of the pairs put in one story, the share that are one story, each day's
    labels weighted by the pairs they stand for. Recall: same-story pairs put together, over
    those plus the same-story pairs kept apart among the pairs whose words overlap
    (eval/pairs.py). The interval draws the days with replacement, and redraws a stratum
    as a binomial only when no labelled day holds the other answer (`_stratum_draws`).
    """

    def point(
        sample: Sequence[PairDay], same_t: Sequence[float], same_n: Sequence[float]
    ) -> tuple[float, float]:
        found = sum(day.together_weight * k for day, k in zip(sample, same_t, strict=True))
        put = sum(day.together_weight * len(day.together) for day in sample)
        missed = sum(day.near_weight * k for day, k in zip(sample, same_n, strict=True))
        precision = found / put if put else float("nan")
        recall = found / (found + missed) if found + missed else float("nan")
        return precision, recall

    n = sum(len(day.together) + len(day.near) for day in days)
    nan = Estimate(float("nan"), float("nan"), float("nan"), n, len(days))
    if not days:
        return nan, nan
    p, r = point(days, [sum(d.together) for d in days], [sum(d.near) for d in days])
    rng = random.Random(seed)
    p_draws: list[float] = []
    r_draws: list[float] = []
    for _ in range(resamples):
        drawn = [days[rng.randrange(len(days))] for _ in days]
        dp, dr = point(
            drawn,
            _stratum_draws(rng, [d.together for d in drawn], [d.together for d in days]),
            _stratum_draws(rng, [d.near for d in drawn], [d.near for d in days]),
        )
        if not math.isnan(dp):
            p_draws.append(dp)
        if not math.isnan(dr):
            r_draws.append(dr)

    def bounds(value: float, draws: list[float], units: int) -> Estimate:
        if math.isnan(value) or not draws:
            return Estimate(value, float("nan"), float("nan"), units, len(days))
        draws.sort()
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        return Estimate(value, lo, hi, units, len(days))

    together_n = sum(len(day.together) for day in days)
    return bounds(p, p_draws, together_n), bounds(r, r_draws, n)


def pair_days(labels: Iterable[PairLabel], labeller: str) -> list[PairDay]:
    """This labeller's pairs by audience-day. The page saves a day's pairs together, so a
    day with any label has them all."""
    grouped: dict[tuple[str, str], list[PairLabel]] = defaultdict(list)
    for label in labels:
        if label.labeller == labeller:
            grouped[(label.audience_id, label.day)].append(label)
    days = []
    for (_, day), day_labels in sorted(grouped.items()):
        together = [label for label in day_labels if label.stratum == "together"]
        near = [label for label in day_labels if label.stratum == "near"]
        days.append(
            PairDay(
                day=day,
                together=tuple(label.same_story for label in together),
                together_weight=together[0].weight if together else 0.0,
                near=tuple(label.same_story for label in near),
                near_weight=near[0].weight if near else 0.0,
            )
        )
    return days


def purity_scores(labels: Iterable[PurityLabel], labeller: str) -> tuple[Estimate, Estimate, int]:
    """Cluster purity from this labeller's judgements: over the items of joined stories, and
    over every news item (an item alone in its story counts as in the right one). Both resample
    whole audience-days. Also returns how many audience-days were judged."""
    joined: list[bool] = []
    joined_days: list[str] = []
    every: list[bool] = []
    every_days: list[str] = []
    pools: dict[str, int] = {}
    for label in labels:
        if label.labeller != labeller:
            continue
        key = f"{label.audience_id}|{label.day}"
        joined.append(label.belongs)
        joined_days.append(key)
        pools[key] = label.pool_items
    every, every_days = list(joined), list(joined_days)
    for key, pool in pools.items():
        alone = pool - joined_days.count(key)
        every += [True] * alone
        every_days += [key] * alone
    return share_by_day(joined, joined_days), share_by_day(every, every_days), len(pools)


def faithfulness(
    labels: Iterable[FaithLabel], labeller: str, *, resamples: int = RESAMPLES, seed: int = 0
) -> Estimate:
    """Digest sentences their cited sources support, from this labeller's sampled sentences.

    Each judgement stands for `weight` of its day's shown sentences, so the point is a ratio
    over the days. "Can't tell" is left out of both sides and reported on its own, so a
    sentence nobody could check is never counted as supported. The interval draws the days
    with replacement, as `dedup_scores` does (`_stratum_draws`).
    """
    grouped: dict[tuple[str, str], list[FaithLabel]] = defaultdict(list)
    for label in labels:
        if label.labeller == labeller and label.verdict != "unclear":
            grouped[(label.audience_id, label.day)].append(label)
    days = [
        (tuple(label.verdict == "supported" for label in day), day[0].weight)
        for day in grouped.values()
    ]

    def ratio(sample: Sequence[tuple[tuple[bool, ...], float]], hits: Sequence[int]) -> float:
        judged = sum(weight * len(flags) for flags, weight in sample)
        found = sum(weight * k for (_, weight), k in zip(sample, hits, strict=True))
        return found / judged if judged else float("nan")

    n = sum(len(flags) for flags, _ in days)
    point = ratio(days, [sum(flags) for flags, _ in days])
    if not days or math.isnan(point):
        return Estimate(point, float("nan"), float("nan"), n, len(days))
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        drawn = [days[rng.randrange(len(days))] for _ in days]
        hits = _stratum_draws(rng, [flags for flags, _ in drawn], [flags for flags, _ in days])
        value = ratio(drawn, hits)
        if not math.isnan(value):
            draws.append(value)
    draws.sort()
    lo = draws[int(0.025 * len(draws))]
    hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
    return Estimate(point, lo, hi, n, len(days))


@dataclass(frozen=True)
class ReaderTimes:
    """The reader study's numbers: minutes per condition, and how many times as long."""

    digest: Estimate
    sources: Estimate
    ratio: Estimate
    sessions: int
    readers: int
    # From the sources: the items readers ticked, and of them, those in a story the digest
    # showed.
    picks: int
    picks_in_digest: int


def reader_times(
    sessions: Sequence[ReaderSession], *, resamples: int = RESAMPLES, seed: int = 0
) -> ReaderTimes:
    """Minutes with the page in view, from the digest and from the sources.

    The ratio's interval resamples the sessions within each condition. With three readers the
    sessions are not independent of who read them, and the interval does not pretend to know
    how much: the conditions alternate within every reader, so a slow reader slows both.
    """
    minutes = {
        condition: [s.seconds_active / 60 for s in sessions if s.condition == condition]
        for condition in ("digest", "sources")
    }
    digest, sources = minutes["digest"], minutes["sources"]
    nan = float("nan")
    ratio = Estimate(nan, nan, nan, len(sessions), len({s.reader for s in sessions}))
    if digest and sources:
        # One session of either kind: a ratio, but nothing to resample.
        point = (sum(sources) / len(sources)) / (sum(digest) / len(digest))
        ratio = Estimate(point, nan, nan, len(sessions), len({s.reader for s in sessions}))
    if len(digest) > 1 and len(sources) > 1:
        point = (sum(sources) / len(sources)) / (sum(digest) / len(digest))
        rng = random.Random(seed)
        draws = []
        for _ in range(resamples):
            d = [digest[rng.randrange(len(digest))] for _ in digest]
            o = [sources[rng.randrange(len(sources))] for _ in sources]
            if sum(d):
                draws.append((sum(o) / len(o)) / (sum(d) / len(d)))
        draws.sort()
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        ratio = Estimate(point, lo, hi, len(sessions), len({s.reader for s in sessions}))
    return ReaderTimes(
        digest=bootstrap_mean(digest) if digest else Estimate(nan, nan, nan, 0, 0),
        sources=bootstrap_mean(sources) if sources else Estimate(nan, nan, nan, 0, 0),
        ratio=ratio,
        sessions=len(sessions),
        readers=len({s.reader for s in sessions}),
        picks=sum(len(s.picks) for s in sessions),
        picks_in_digest=sum(s.picks_in_digest for s in sessions),
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
    # Estimated relevant stories in a day's pool: the top stratum's plus the random stratum's,
    # weighted. Beside the digest's length it says how much recall a digest of that length
    # could reach at best.
    relevant_per_day: Estimate | None = None
    # The same two over must-read stories, on the days labelled with that choice: whether the
    # digest picked the most important stories, which is its job when it has ten slots.
    must_recall: Estimate | None = None
    must_per_day: Estimate | None = None
    graded_days: int = 0
    # The Bluesky pick (rank/spotlight.py), judged on its own: was it worth showing.
    spotlight: Estimate | None = None
    # The X pick (rank/x_pick.py), judged the same way.
    x_pick: Estimate | None = None
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
    # What the cloud and X billed, read from their own pages (eval/bills.py).
    bills: list[Bill]
    # Deduplication against labelled pairs: precision and recall, the audience-days they
    # come from, and the "check" pairs found to be one story, of those judged.
    dedup_precision: Estimate | None
    dedup_recall: Estimate | None
    pair_days: int
    check_same: int
    check_n: int
    # Cluster purity: over the items of stories with several news items, and over every
    # news item, from the audience-days judged.
    purity_joined: Estimate | None
    purity_all: Estimate | None
    purity_days: int
    # Claim faithfulness on the sampled sentences: the weighted share supported, the
    # sentences that were judged and could not be, and the ones judged not supported.
    faith: Estimate | None
    faith_unclear: int
    faith_unsupported: list[FaithLabel]
    # The reader study, once a session is done.
    readers: ReaderTimes | None
    # The scheduled run, day by day since UPTIME_FROM.
    uptime: list[UptimeDay]
    sources: list[SourceYield]


def _complete_days(
    store: Store, labels: list[Label], audience_id: str, labeller: str
) -> dict[str, list[Label]]:
    """This labeller's labels by day, for the days whose whole sample they judged.

    While the store holds every item the day's labels name, the sample is drawn again and
    must be covered. Once retention has deleted some of them it cannot be drawn again, and
    the labels stand on their own record: a day was saved only as a whole sample
    (`label_ui.save_day`), so it counts if its top stratum runs unbroken from rank 1. Without
    this, each labelled day left the results thirty days after it was fetched (found
    2026-11-07, when Newfoundland and Labrador's 2026-10-09 dropped out).
    """
    by_day: dict[str, list[Label]] = defaultdict(list)
    for label in labels:
        if label.audience_id == audience_id and label.labeller == labeller:
            by_day[label.day].append(label)
    held = {item.id for item in store.items_for(audience_id)}
    complete = {}
    for day, day_labels in by_day.items():
        sampled = [label for label in day_labels if label.stratum in ("top", "random")]
        if not {label.item_id for label in sampled} <= held:
            if _whole_sample(sampled):
                complete[day] = day_labels
            continue
        sample = stratified_sample(ranked_ids_for_day(store, audience_id, day), audience_id, day)
        if {unit.item_id for unit in sample.units} <= {label.item_id for label in day_labels}:
            complete[day] = day_labels
    return complete


def _whole_sample(sampled: Sequence[Label]) -> bool:
    """Whether a day's saved labels hold a whole sample as `stratified_sample` draws one: every
    top rank from 1 with no gap, and a random stratum only once the top one is full. A day
    labelled again after its run was redone (Newfoundland and Labrador's 2026-10-10) holds
    two samples' labels, so a rank may appear twice."""
    top = {label.rank for label in sampled if label.stratum == "top"}
    has_random = any(label.stratum == "random" for label in sampled)
    return (
        bool(top)
        and top == set(range(1, len(top) + 1))
        and (not has_random or len(top) == DEFAULT_TOP)
    )


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
    pair_labels: Sequence[PairLabel] = (),
    purity_labels: Sequence[PurityLabel] = (),
    faith_labels: Sequence[FaithLabel] = (),
    reader_sessions: Sequence[ReaderSession] = (),
    bills: Sequence[Bill] = (),
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
        start = audience.measure_from or ""
        complete = {
            day: day_labels
            for day, day_labels in _complete_days(store, labels, audience.id, labeller).items()
            if day >= start
        }
        result.labelled_days = sorted(complete)
        if complete:
            shown_flags: list[bool] = []
            shown_days: list[str] = []
            days: list[DayLabels] = []
            must_days: list[DayLabels] = []
            for day, day_labels in sorted(complete.items()):
                by_item = {label.item_id: label for label in day_labels}
                digest = next((d for d in mine if d.day == day), None)
                shown = _shown_items(store, digest) if digest else []
                flags = [by_item[item_id].relevant for item_id in shown if item_id in by_item]
                shown_flags += flags
                shown_days += [day] * len(flags)
                random_labels = [label for label in day_labels if label.stratum == "random"]
                if all(label.graded for label in day_labels):
                    must_days.append(
                        DayLabels(
                            day=day,
                            shown_relevant=sum(
                                by_item[item_id].must_read
                                for item_id in shown
                                if item_id in by_item
                            ),
                            top=tuple(one.must_read for one in day_labels if one.stratum == "top"),
                            random=tuple(label.must_read for label in random_labels),
                            weight=random_labels[0].weight if random_labels else 0.0,
                        )
                    )
                days.append(
                    DayLabels(
                        day=day,
                        shown_relevant=sum(flags),
                        top=tuple(label.relevant for label in day_labels if label.stratum == "top"),
                        random=tuple(label.relevant for label in random_labels),
                        weight=random_labels[0].weight if random_labels else 0.0,
                    )
                )
            result.precision = share_by_day(shown_flags, shown_days)
            result.recall = recall(days)
            result.relevant_per_day = bootstrap_mean(
                [sum(day.top) + day.weight * sum(day.random) for day in days]
            )
            if must_days:
                result.graded_days = len(must_days)
                result.must_recall = recall(must_days)
                result.must_per_day = bootstrap_mean(
                    [sum(day.top) + day.weight * sum(day.random) for day in must_days]
                )
        picks = [
            label.relevant
            for label in labels
            if label.audience_id == audience.id
            and label.labeller == labeller
            and label.stratum == "spotlight"
            and label.day >= start
        ]
        if picks:
            result.spotlight = share(picks)
        x_picks = [
            label.relevant
            for label in labels
            if label.audience_id == audience.id
            and label.labeller == labeller
            and label.stratum == "x_pick"
            and label.day >= start
        ]
        if x_picks:
            result.x_pick = share(x_picks)
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
    audience_ids = {audience.id for audience in audiences}
    own_pairs = [pair for pair in pair_labels if pair.audience_id in audience_ids]
    judged = pair_days(own_pairs, labeller)
    dedup_precision, dedup_recall = dedup_scores(judged) if judged else (None, None)
    own_purity = [label for label in purity_labels if label.audience_id in audience_ids]
    purity_joined, purity_all, purity_days = (
        purity_scores(own_purity, labeller)
        if any(label.labeller == labeller for label in own_purity)
        else (None, None, 0)
    )
    own_faith = [
        label
        for label in faith_labels
        if label.audience_id in audience_ids and label.labeller == labeller
    ]
    own_sessions = [session for session in reader_sessions if session.audience_id in audience_ids]
    checks = [
        pair.same_story
        for pair in own_pairs
        if pair.labeller == labeller and pair.stratum == "check"
    ]
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
        bills=list(bills),
        dedup_precision=dedup_precision,
        dedup_recall=dedup_recall,
        pair_days=len(judged),
        check_same=sum(checks),
        check_n=len(checks),
        purity_joined=purity_joined,
        purity_all=purity_all,
        purity_days=purity_days,
        faith=faithfulness(own_faith, labeller) if own_faith else None,
        faith_unclear=sum(label.verdict == "unclear" for label in own_faith),
        faith_unsupported=[label for label in own_faith if label.verdict == "unsupported"],
        readers=reader_times(own_sessions) if own_sessions else None,
        uptime=uptime_days(store, [audience.id for audience in audiences], now),
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


def cad_money(estimate: Estimate) -> str:
    if math.isnan(estimate.point):
        return NOT_YET
    point, lo, hi = (cad(value) for value in (estimate.point, estimate.lo, estimate.hi))
    return f"CA${point:.3f} (CA${lo:.3f} to CA${hi:.3f})"


def _month_days(days: Sequence[UptimeDay]) -> list[UptimeDay]:
    return [day for day in days if MEASUREMENT_FROM <= day.day <= MEASUREMENT_TO]


def readme_tables(report: Report) -> str:
    labelled = sum(len(result.labelled_days) for result in report.audiences)
    lines = [
        f"Measured over {report.digests} digests from {report.first_day} to {report.last_day}, "
        f"by `clippings report` on {report.generated_at:%Y-%m-%d}. 95% intervals throughout. "
        f"{labelled} audience-days hand-labelled"
        + (
            ": every audience has its labelled week."
            if all(len(result.labelled_days) >= 7 for result in report.audiences)
            else " so far; the relevance columns fill as the labelled week does."
        ),
        "",
        "**Relevance, per audience, against a hand-labelled week**",
        "",
        "| Audience | Precision at K (95% CI) | Recall of must-read stories, "
        "importance-weighted (95% CI) | Must-read stories per day "
        "| Recall of all relevant stories | Relevant stories per day | Labeller kappa "
        "| Stories per day | Cost per digest |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for result in report.audiences:
        days = (
            f", {len(result.labelled_days)} day{'s' if len(result.labelled_days) != 1 else ''}"
            if result.labelled_days
            else ""
        )
        lines.append(
            f"| {result.name} | {pct(result.precision)}{days} | {pct(result.must_recall)} "
            f"| {num(result.must_per_day, '.1f')} | {pct(result.recall)} "
            f"| {num(result.relevant_per_day, '.1f')} | {num(result.kappa)} | {num(result.stories_per_day, '.1f')} "
            f"| {cad_money(result.cost)} |"
        )
    pairs = (
        NOT_YET + " (pair labels)"
        if report.dedup_precision is None
        else f"{pct(report.dedup_precision)} / {pct(report.dedup_recall)}, "
        f"{report.pair_days} audience-days"
    )
    purity = (
        NOT_YET + " (story checks)"
        if report.purity_joined is None
        else f"{pct(report.purity_joined)}, {report.purity_days} audience-days"
    )
    faith = (
        NOT_YET + " (hand check)"
        if report.faith is None
        else f"{pct(report.faith)}, {report.faith.n} sentences"
    )
    readers = (
        NOT_YET + " (reader study)"
        if report.readers is None
        else f"{num(report.readers.digest, '.1f')} vs {num(report.readers.sources, '.1f')}, "
        f"{report.readers.sessions} sessions"
    )
    month = _month_days(report.uptime)
    up = sum(day.up for day in report.uptime)
    if month:
        month_up = sum(day.up for day in month)
        uptime = (
            f"{pct(counted_share(month_up, len(month)))}, {month_up} of {len(month)} days of the "
            f"measurement month, {MEASUREMENT_FROM} to {MEASUREMENT_TO}"
        )
    elif report.uptime:
        uptime = (
            f"{pct(counted_share(up, len(report.uptime)))}, {up} of {len(report.uptime)} "
            f"days since {UPTIME_FROM}"
        )
    else:
        uptime = NOT_YET
    lines += [
        "",
        "**Pipeline properties**",
        "",
        "| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, "
        "stories of several articles | Quotes verbatim, before / "
        "after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) "
        "| Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) "
        "| Uptime of the scheduled daily run |",
        "|---|---|---|---|---|---|---|---|---|",
        f"| {pairs} | {num(report.collapse)} items per story | {purity} "
        f"| {pct(report.quotes_first)} / "
        f"{pct(report.quotes_after_repair)} | {pct(report.citation_first)} "
        f"| {faith} | {num(report.lag_p50, '.0f', ' h')} / "
        f"{num(report.lag_p90, '.0f', ' h')} | {readers} "
        f"| {uptime} |",
        "",
    ]
    if report.purity_days:
        lines += [
            "Cluster purity is the share of articles in a story of several that a labeller "
            "judged to belong with the rest; over every news article, stories of one "
            f"included, it is {pct(report.purity_all)}.",
            "",
        ]
    if report.faith is not None:
        unclear = (
            f" {report.faith_unclear} more could not be checked, because what the summariser "
            "read was no longer on record, and are left out."
            if report.faith_unclear
            else ""
        )
        lines += [
            "Faithfulness is the share of sampled digest sentences that say only what the "
            "sources they cite say, hand-checked against what the summariser read, weighted by "
            "the sentences each day's digest showed. "
            f"{len(report.faith_unsupported)} of {report.faith.n} were judged not supported, "
            f"listed in [docs/report.md](docs/report.md).{unclear}",
            "",
        ]
    if report.readers is not None:
        r = report.readers
        ratio = (
            NOT_YET
            if math.isnan(r.ratio.point)
            else f"{r.ratio.point:.1f} (interval undefined, one session of a kind)"
            if math.isnan(r.ratio.lo)
            else num(r.ratio, ".1f")
        )
        picked = (
            f" Of the {r.picks} items readers ticked as worth a briefing when working from the "
            f"sources, {pct(counted_share(r.picks_in_digest, r.picks))} were in a story the "
            "digest showed."
            if r.picks
            else ""
        )
        lines += [
            f"Reader minutes are minutes with the page in view, from {r.readers} "
            f"reader{'s' if r.readers != 1 else ''} briefed on a morning either from the digest "
            "or from the news items it was made from; from the sources they took "
            f"{ratio} times as long.{picked}",
            "",
        ]
    missed = [day for day in report.uptime if not day.up]
    if report.uptime:
        lines += [
            "Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or "
            "Cloud Run's automatic retry of it, published every audience's digest; a day "
            "rescued by a run started by hand is down"
            + (f" ({', '.join(day.day for day in missed)})." if missed else ".")
            + (
                f" Since {UPTIME_FROM}, the first scheduled morning: "
                f"{pct(counted_share(up, len(report.uptime)))}, {up} of {len(report.uptime)} days."
                if month
                else f" The measurement month runs from {MEASUREMENT_FROM} to {MEASUREMENT_TO}."
            ),
            "",
        ]
    if report.pair_days:
        lines += [
            "Deduplication recall is over the pairs whose words overlap most, where a missed "
            "duplicate almost always is; of "
            f"{report.check_n} pairs drawn from outside them as a check, {report.check_same} "
            f"{'was' if report.check_same == 1 else 'were'} the same story.",
            "",
        ]
    lines += [
        "Most discussed on Bluesky, judged worth showing: "
        + "; ".join(f"{r.name} {pct(r.spotlight)}" for r in report.audiences)
        + ". A separate section below the stories, not counted in precision or recall.",
        "",
        "Most discussed on X, judged worth showing: "
        + "; ".join(f"{r.name} {pct(r.x_pick)}" for r in report.audiences)
        + ". The same kind of section, from X's paid API.",
        "",
        f"All four digests together cost {cad_money(report.cost_per_day)} a day in model calls, from "
        f"the gateway's ledger, converted from US dollars at {CAD_PER_USD} CAD per USD"
        + (f" ({report.uncosted_calls} calls uncosted)" if report.uncosted_calls else "")
        + "."
        + _bills_text(report)
        + " Details, per source and per day: [docs/report.md](docs/report.md).",
    ]
    return "\n".join(lines)


def _bill_amount(bill: Bill) -> str:
    return f"{'US' if bill.currency == 'USD' else 'CA'}${bill.amount:.2f}"


def _bills_text(report: Report) -> str:
    """The bills the ledger does not see, and everything together. A bill is a total, not a
    sample, so the interval of the whole is the model cost's, moved by the bills."""
    if not report.bills:
        return ""
    parts = [
        f"{bill.name} billed {_bill_amount(bill)} from {bill.first_day} to {bill.last_day}, "
        f"CA${bill.cad_per_day:.3f} a day"
        for bill in report.bills
    ]
    extra = sum(bill.cad_per_day for bill in report.bills)
    whole = report.cost_per_day
    if math.isnan(whole.point):
        return " " + "; ".join(parts) + "."
    point, lo, hi = (cad(value) + extra for value in (whole.point, whole.lo, whole.hi))
    return (
        " "
        + "; ".join(parts)
        + ", read from their own billing pages ([docs/bills.yaml](docs/bills.yaml)). "
        f"Everything together: CA${point:.3f} (CA${lo:.3f} to CA${hi:.3f}) a day, "
        f"about CA${point * 30.4:.0f} a month."
    )


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
    if report.faith is not None:
        lines += [
            "",
            "## Sentences judged not supported",
            "",
            "From the faithfulness sample: each sentence as the digest showed it, its story, "
            "and the sources it cited.",
            "",
        ]
        for label in report.faith_unsupported:
            cited = ", ".join(f"<{url}>" for url in label.cited_urls) or "no source on record"
            lines.append(
                f'- {label.audience_id}, {label.day}, "{label.headline}": {label.text} '
                f"Cited: {cited}"
            )
        if not report.faith_unsupported:
            lines.append("None so far.")
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


def _triple(estimate: Estimate | None) -> list[float] | None:
    """An estimate as [point, low, high] for a chart, or None when it does not exist yet."""
    if estimate is None or math.isnan(estimate.point):
        return None
    return [estimate.point, estimate.lo, estimate.hi]


def site_values(report: Report) -> dict[str, object]:
    """What the site's front page shows, from the same run as the README's tables.

    Written to `clippings/assemble/results.json` by `clippings report` and read by
    `assemble/about.py`, so no measured number is ever typed into the page. Strings are
    already formatted the way the README prints them; triples feed the chart."""
    precision = [r.precision.point for r in report.audiences if r.precision]
    must = [r.must_recall.point for r in report.audiences if r.must_recall]
    kappa = next((r for r in report.audiences if r.kappa is not None), None)
    extra = sum(bill.cad_per_day for bill in report.bills)
    whole = cad(report.cost_per_day.point) + extra
    readers = report.readers
    month = _month_days(report.uptime)
    days = month or report.uptime
    up = sum(day.up for day in days)
    return {
        "as_of": report.generated_at.date().isoformat(),
        "first_day": report.first_day,
        "last_day": report.last_day,
        "digests": report.digests,
        "labelled_days": sum(len(r.labelled_days) for r in report.audiences),
        "precision_range": (
            f"{min(precision):.0%} to {max(precision):.0%}" if precision else NOT_YET
        ),
        "must_recall_range": f"{min(must):.0%} to {max(must):.0%}" if must else NOT_YET,
        "audiences": [
            {
                "name": r.name,
                "days": len(r.labelled_days),
                "precision": _triple(r.precision),
                "must_recall": _triple(r.must_recall),
                "recall": _triple(r.recall),
                "precision_text": pct(r.precision),
                "must_recall_text": pct(r.must_recall),
            }
            for r in report.audiences
        ],
        "kappa": num(kappa.kappa) if kappa else NOT_YET,
        "kappa_audience": kappa.name if kappa else "",
        "dedup": f"{pct(report.dedup_precision)} / {pct(report.dedup_recall)}",
        "purity": pct(report.purity_joined),
        "quotes": pct(report.quotes_after_repair),
        "quotes_first": pct(report.quotes_first),
        "faith": pct(report.faith),
        "faith_point": f"{report.faith.point:.0%}" if report.faith else NOT_YET,
        "faith_n": report.faith.n if report.faith else 0,
        "faith_unsupported": len(report.faith_unsupported),
        "reader_digest": num(readers.digest, ".1f") if readers else NOT_YET,
        "reader_sources": num(readers.sources, ".1f") if readers else NOT_YET,
        "reader_ratio": f"{readers.ratio.point:.1f}" if readers else NOT_YET,
        "reader_ratio_text": num(readers.ratio, ".1f") if readers else NOT_YET,
        "reader_sessions": readers.sessions if readers else 0,
        "reader_count": readers.readers if readers else 0,
        "lag_p50": num(report.lag_p50, ".0f", " h"),
        "cost_day": f"CA${whole:.2f}",
        "cost_month": f"CA${whole * 30.4:.0f}",
        "cost_models_day": cad_money(report.cost_per_day),
        "uptime": (
            f"{pct(counted_share(up, len(days)))}, {up} of {len(days)} days"
            + (" of the measurement month" if month else f" since {UPTIME_FROM}")
            if days
            else NOT_YET
        ),
        "measurement_from": MEASUREMENT_FROM,
        "measurement_to": MEASUREMENT_TO,
    }
