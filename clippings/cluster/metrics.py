"""Measuring the clustering against labelled pairs.

PLAN.md section 1: deduplication is reported as pairwise precision and recall on a labelled
sample of item pairs, cluster purity, and the collapse rate. Labelling every pair in a day
is quadratic and pointless; a sample of pairs, labelled the same way for every
configuration, is what these functions score.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from clippings.models import Cluster

Pair = tuple[str, str]


def ordered(left: str, right: str) -> Pair:
    """Pairs are unordered; storing them one way round makes them comparable."""
    return (left, right) if left < right else (right, left)


def pairs_within(clusters: Iterable[Cluster]) -> set[Pair]:
    """Every pair of items the clustering placed in the same story."""
    pairs: set[Pair] = set()
    for cluster in clusters:
        members = sorted(cluster.item_ids)
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                pairs.add((left, right))
    return pairs


@dataclass(frozen=True)
class PairScores:
    """Pairwise agreement between the clustering and the labels, on the labelled sample."""

    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

    @property
    def labelled(self) -> int:
        return (
            self.true_positives + self.false_positives + self.false_negatives + self.true_negatives
        )

    @property
    def precision(self) -> float:
        """Of the pairs put together, how many belong together."""
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else 0.0

    @property
    def recall(self) -> float:
        """Of the pairs that belong together, how many were put together."""
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else 0.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    def outcomes(self) -> list[int]:
        """One 1 or 0 per labelled pair, for bootstrapping an interval over the sample."""
        return (
            [1] * self.true_positives
            + [0] * self.false_positives
            + [0] * self.false_negatives
            + [1] * self.true_negatives
        )


def score_pairs(clusters: Sequence[Cluster], labels: Mapping[Pair, bool]) -> PairScores:
    """Score the clustering against a labelled sample of pairs.

    `labels` maps an ordered pair to whether the two items are the same story. Only pairs in
    the sample are scored: everything else is unlabelled, not negative.
    """
    predicted = pairs_within(clusters)
    true_positives = false_positives = false_negatives = true_negatives = 0
    for pair, same_story in labels.items():
        key = ordered(*pair)
        together = key in predicted
        if same_story and together:
            true_positives += 1
        elif same_story:
            false_negatives += 1
        elif together:
            false_positives += 1
        else:
            true_negatives += 1
    return PairScores(true_positives, false_positives, false_negatives, true_negatives)


def purity(clusters: Sequence[Cluster], truth: Mapping[str, str]) -> float:
    """Share of clustered items that sit in a cluster with their own story's majority.

    `truth` maps an item id to the id of the story a labeller says it belongs to. Items
    without a label are skipped, not counted against the clustering.
    """
    total = 0
    correct = 0
    for cluster in clusters:
        stories = [truth[item_id] for item_id in cluster.item_ids if item_id in truth]
        if not stories:
            continue
        total += len(stories)
        correct += max(stories.count(story) for story in set(stories))
    return correct / total if total else 0.0
