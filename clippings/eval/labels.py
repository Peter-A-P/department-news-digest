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
from clippings.models import Item, Label
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
    """The day's pool in the order the system put it.

    With an audience and an embedder this is the real ranking: stories best first, each
    represented by the item the digest would link to, then the rest of each story's items.
    That is the order the sampler calls "top thirty", so precision at K is measured against
    what the system would actually have shown.

    Without them it falls back to cluster order, largest story first. The fallback exists so
    the labelling CLI still works on a store whose audience file is not to hand, and a label
    taken that way measures the clustering rather than the ranking. The two must not be
    mixed in one week's numbers.
    """
    clusters = store.clusters_for(audience_id, day)
    if not clusters:
        return [item.id for item in store.items_for(audience_id)]

    if audience is not None and embedder is not None:
        items = {item.id: item for item in store.items_for(audience_id)}
        scored = score_stories(clusters, items, audience, embedder, now or datetime.now(UTC))
        ordered = [story.representative.id for story in scored]
        seen = set(ordered)
        for story in scored:
            ordered.extend(item_id for item_id in story.cluster.item_ids if item_id not in seen)
            seen.update(story.cluster.item_ids)
        return ordered

    ordered = [cluster.representative_id for cluster in clusters]
    seen = set(ordered)
    for cluster in clusters:
        ordered.extend(item_id for item_id in cluster.item_ids if item_id not in seen)
        seen.update(cluster.item_ids)
    return ordered


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
) -> LabellingQueue:
    """The items this labeller still has to judge for this day, in order.

    Items already labelled by this person are dropped, so the command resumes; the sample
    itself does not change, because its seed is derived from the audience and the day.
    """
    ranked = ranked_ids_for_day(
        store, audience_id, day, audience=audience, embedder=embedder, now=now
    )
    sample = stratified_sample(ranked, audience_id, day, top_k=top_k, random_n=random_n, seed=seed)
    done = store.labelled_ids(audience_id, day, labeller)
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
