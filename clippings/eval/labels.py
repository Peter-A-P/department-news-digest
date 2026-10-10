"""Building a day's labelling queue and recording what a labeller says.

The interactive part lives in the CLI; everything that decides what is asked, in what
order, and what a label means lives here, so the labelled week can be rebuilt from the
store without a person in the loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from clippings.cluster.embed import Embedder
from clippings.config.audience import Audience
from clippings.eval.sample import DaySample, SampleUnit, stratified_sample
from clippings.ingest.store import Store
from clippings.models import SOCIAL_KINDS, Cluster, Item, Label
from clippings.rank.score import score_stories

Answer = Literal["yes", "no", "skip"]


@dataclass(frozen=True)
class Question:
    """One item put to a labeller, with everything needed to judge it and nothing more."""

    unit: SampleUnit
    item: Item

    @property
    def prompt(self) -> str:
        return f"{self.item.title}\n  {self.item.domain}  {self.item.url}"


@dataclass
class LabellingQueue:
    """A day's work for one labeller, in the order it is put to them."""

    audience_id: str
    day: str
    labeller: str
    sample: DaySample
    questions: tuple[Question, ...]

    @property
    def remaining(self) -> int:
        return len(self.questions)


def ranked_ids_for_day(
    store: Store,
    audience_id: str,
    day: str,
    *,
    audience: Audience | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
) -> list[str]:
    """The day's news stories in the order the system put them, each as its representative.

    When the day's run saved its ranking (the re-ranked candidates, then the rest of the pool
    in pre-filter order), that is the order used, because it is what the digest was actually
    chosen from. Otherwise, with an audience and an embedder, the pre-filter ranking is
    recomputed. Without them it falls back to cluster order, largest story first; a label
    taken that way measures the clustering rather than the ranking, and the two must not be
    mixed in one week's numbers.

    One entry per story, the item the digest would link to, and only stories headed by a
    news item: the other items of a story are reprints of it, and a story of posts alone is
    never a candidate (PLAN.md section 2.3). Labelling either would spend the labeller's time
    on judgements no number uses.
    """
    items = {item.id: item for item in store.items_for(audience_id)}
    clusters = store.clusters_for(audience_id, day)
    saved = store.ranking_for(audience_id, day)
    by_cluster = {cluster.id: cluster for cluster in clusters}
    ordered: list[Cluster]
    if saved and all(cluster_id in by_cluster for cluster_id in saved):
        ordered = [by_cluster[cluster_id] for cluster_id in saved]
        ordered += [cluster for cluster in clusters if cluster.id not in set(saved)]
    elif clusters and audience is not None and embedder is not None:
        scored = score_stories(clusters, items, audience, embedder, now or datetime.now(UTC))
        ordered = [story.cluster for story in scored]
    else:
        ordered = list(clusters)
    # The stories the digest showed come first, so precision at K always has its labels: the
    # digest is chosen from the re-ranked candidates with diversity, and a shown story can sit
    # below thirtieth in the saved order (none has yet; 22nd is the lowest seen by 2026-10-10).
    digest = store.digest_for(audience_id, day)
    shown = [story.story_id for story in digest.stories] if digest else []
    position = {cluster_id: index for index, cluster_id in enumerate(shown)}
    ordered.sort(key=lambda cluster: position.get(cluster.id, len(position)))
    return [
        cluster.representative_id
        for cluster in ordered
        if cluster.representative_id in items
        and items[cluster.representative_id].source_kind not in SOCIAL_KINDS
    ]


def build_queue(
    store: Store,
    audience_id: str,
    day: str,
    labeller: str,
    *,
    audience: Audience | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
    top_k: int = 30,
    random_n: int = 30,
    seed: int | None = None,
    labels: Store | None = None,
    include_done: bool = False,
) -> LabellingQueue:
    """The items this labeller still has to judge for this day, in order.

    Items already labelled by this person are dropped, so the command resumes; the sample
    itself does not change, because its seed is derived from the audience and the day.
    `labels` is where this labeller's labels are kept, when that is not the run's store, and
    `include_done` keeps the labelled items in, so a finished day can be reopened.
    """
    ranked = ranked_ids_for_day(
        store, audience_id, day, audience=audience, embedder=embedder, now=now
    )
    sample = stratified_sample(ranked, audience_id, day, top_k=top_k, random_n=random_n, seed=seed)
    done = set() if include_done else (labels or store).labelled_ids(audience_id, day, labeller)
    by_id = {item.id: item for item in store.items_for(audience_id)}
    questions = tuple(
        Question(unit=unit, item=by_id[unit.item_id])
        for unit in sample.units
        if unit.item_id not in done and unit.item_id in by_id
    )
    return LabellingQueue(
        audience_id=audience_id, day=day, labeller=labeller, sample=sample, questions=questions
    )


def record(
    store: Store,
    queue: LabellingQueue,
    question: Question,
    relevant: bool,
    *,
    labeller: str | None = None,
) -> Label:
    """Write one label, copying the item's URL and title so it outlives retention."""
    labeller = labeller or queue.labeller
    label = Label(
        audience_id=queue.audience_id,
        day=queue.day,
        item_id=question.unit.item_id,
        labeller=labeller,
        relevant=relevant,
        stratum=question.unit.stratum,
        rank=question.unit.rank,
        weight=question.unit.weight,
        url=question.item.url,
        title=question.item.title,
        labelled_at=datetime.now(UTC),
    )
    store.add_label(label)
    return label
