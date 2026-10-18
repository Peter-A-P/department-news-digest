"""Which pairs of items a labeller is asked about, for the deduplication numbers.

PLAN.md section 1 reports deduplication as pairwise precision and recall on a labelled
sample of item pairs. A day's pool of a hundred news items holds about five thousand pairs,
and nearly all of them are two different stories, so a uniform sample would spend the
labeller's time on obvious "no"s and almost never meet a pair the clustering wrongly kept
apart. Each audience-day is sampled in three strata instead:

- **together**: pairs the clustering put in one story. Precision comes from these.
- **near**: pairs it kept apart whose words overlap the most, the day's top `NEAR_FACTOR`
  pairs per news item by word overlap, less those put together. A missed duplicate is
  almost always here, so recall is estimated as together-and-same over together-and-same
  plus near-and-same, each weighted by the pairs its labels stand for.
- **check**: a few pairs from everything else. They are not weighted into recall, which
  would let one chance "same" among thousands of pairs decide the number; they are
  reported on their own, as a test of the assumption that a same-story pair shares words.

So recall is measured within the pairs that share words, and says so. Over the 43
audience-days in the store on 2026-10-17, the top three pairs per item by word overlap held
843 of the 846 pairs the clustering had put together: overlap finds same-story pairs, which
is what the "near" stratum needs. Word overlap is deliberately not the clustering's own signal, so it can
find what the embeddings missed.

The same module lists the stories the clustering made of several news items, which is what
the purity question (is each item in the right story?) is asked of.

Only news items are paired. Posts never head a story (PLAN.md section 2.3) and join one
only by nearness to a news item; whether a reprint was collapsed is a question about news.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

from clippings.cluster.metrics import Pair, ordered, pairs_within
from clippings.ingest.store import Store
from clippings.models import SOCIAL_KINDS, Cluster, Item

PairStratum = Literal["together", "near", "check"]

TOGETHER_N = 5
NEAR_N = 6
CHECK_N = 2
# The "near" population is the day's top NEAR_FACTOR x (news items) pairs by word overlap.
NEAR_FACTOR = 3
# Enough of the feed summary to compare by, as on the relevance page.
SUMMARY_WORDS = 30

# Words too common to say two items are about the same thing.
COMMON_WORDS = (
    "a an the of to in on for and or is are was were be been by with at from as it its this "
    "that these those after over new says said say will would has have had not but than into "
    "about up out more who what how why can could may also just one two his her their they "
    "our you we he she all any some first last year years"
)
STOPWORDS = frozenset(COMMON_WORDS.split())


@dataclass(frozen=True)
class PairUnit:
    """One pair to judge, and what its label stands for."""

    left_id: str
    right_id: str
    stratum: PairStratum
    weight: float
    together: bool


@dataclass(frozen=True)
class PairSample:
    audience_id: str
    day: str
    units: tuple[PairUnit, ...]
    # The size of each stratum's population, for the report and for checking the weights.
    population: dict[str, int]


def words(item: Item) -> frozenset[str]:
    """The content words of an item's title and the start of its summary."""
    text = f"{item.title} {' '.join(item.summary.split()[:SUMMARY_WORDS])}".lower()
    return frozenset(
        word for word in re.findall(r"[a-z0-9']+", text) if len(word) > 2 and word not in STOPWORDS
    )


def overlap(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def news_items(clusters: Sequence[Cluster], items: dict[str, Item]) -> list[str]:
    return sorted(
        {
            item_id
            for cluster in clusters
            for item_id in cluster.item_ids
            if item_id in items and items[item_id].source_kind not in SOCIAL_KINDS
        }
    )


def _seed(audience_id: str, day: str) -> int:
    # A fixed hash, as in eval/sample.py: the same day asks for the same pairs every time.
    digest = hashlib.blake2b(f"{audience_id}|{day}|pairs".encode(), digest_size=4).digest()
    return int.from_bytes(digest, "big") % (2**31)


def pair_sample(
    clusters: Sequence[Cluster],
    items: dict[str, Item],
    audience_id: str,
    day: str,
    *,
    together_n: int = TOGETHER_N,
    near_n: int = NEAR_N,
    check_n: int = CHECK_N,
) -> PairSample:
    ids = news_items(clusters, items)
    together = {pair for pair in pairs_within(clusters) if pair[0] in ids and pair[1] in ids}
    vocab = {item_id: words(items[item_id]) for item_id in ids}
    scored = sorted(
        (
            (overlap(vocab[left], vocab[right]), (left, right))
            for left, right in combinations(ids, 2)
        ),
        key=lambda entry: (-entry[0], entry[1]),
    )
    top = [pair for score, pair in scored[: NEAR_FACTOR * len(ids)] if score > 0]
    near = [pair for pair in top if pair not in together]
    near_set = set(near)
    rest = [pair for _, pair in scored if pair not in together and pair not in near_set]

    rng = random.Random(_seed(audience_id, day))
    units: list[PairUnit] = []
    strata: tuple[tuple[PairStratum, list[Pair], int], ...] = (
        ("together", sorted(together), together_n),
        ("near", sorted(near), near_n),
        ("check", sorted(rest), check_n),
    )
    for stratum, population, n in strata:
        drawn = rng.sample(population, min(n, len(population)))
        weight = len(population) / len(drawn) if drawn else 0.0
        units += [
            PairUnit(
                left_id=left,
                right_id=right,
                stratum=stratum,
                weight=weight,
                together=stratum == "together",
            )
            for left, right in (ordered(*pair) for pair in drawn)
        ]
    return PairSample(
        audience_id=audience_id,
        day=day,
        units=tuple(units),
        population={"together": len(together), "near": len(near), "check": len(rest)},
    )


@dataclass(frozen=True)
class JoinedStory:
    """A story the clustering made of more than one news item, for the purity question."""

    cluster_id: str
    item_ids: tuple[str, ...]


def joined_stories(
    clusters: Sequence[Cluster], items: dict[str, Item]
) -> tuple[list[JoinedStory], int]:
    """The day's stories of two or more news items, and the day's count of news items.

    Purity (PLAN.md section 1) is asked only of these: an item alone in its story is in the
    right one by construction. In the week to 2026-10-17 that was 5 to 8 stories and 11 to 21
    items an audience-day, out of 43 to 76 news items.
    """
    ids = set(news_items(clusters, items))
    stories = []
    for cluster in clusters:
        members = tuple(sorted(item_id for item_id in cluster.item_ids if item_id in ids))
        if len(members) > 1:
            stories.append(JoinedStory(cluster.id, members))
    return sorted(stories, key=lambda story: story.cluster_id), len(ids)


def joined_stories_for_day(
    store: Store, audience_id: str, day: str
) -> tuple[list[JoinedStory], int]:
    items = {item.id: item for item in store.items_for(audience_id)}
    return joined_stories(store.clusters_for(audience_id, day), items)


def pair_sample_for_day(store: Store, audience_id: str, day: str) -> PairSample:
    items = {item.id: item for item in store.items_for(audience_id)}
    return pair_sample(store.clusters_for(audience_id, day), items, audience_id, day)
