"""Choosing the K stories that go in the digest.

Taking the top K by score is the obvious thing and it is wrong in a specific, repeatable
way: the highest-scoring stories on any given day are usually several angles on the same
event, because whatever makes one of them score well makes its neighbours score well too.
Clustering has already collapsed the same story told twice; this handles the different
stories that are all about the same thing, which clustering correctly keeps apart.

So selection is greedy with a redundancy penalty: take the best story, then repeatedly take
the story with the best score after subtracting how much it resembles what is already
chosen. That is maximal marginal relevance, and the one knob is how much resemblance costs.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from clippings.cluster.embed import Vector, cosine
from clippings.rank.score import ScoredStory

# How much resembling an already-chosen story costs. At zero this is top-K by score; at one
# a story that duplicates an earlier one is penalised by its full similarity. Chosen so a
# genuinely important second angle still gets in and a third does not, and measured in week
# 3 against the labelled week rather than left as a guess.
DEFAULT_DIVERSITY = 0.5

# Stories from one publisher crowding out the rest is the other way a digest gets narrow,
# and it is not visible to an embedding: two unrelated pieces from the same outlet look
# unrelated. At most this many stories per domain unless there is nothing else to take.
DEFAULT_MAX_PER_DOMAIN = 3


@dataclass(frozen=True)
class Selection:
    """What was chosen, and what it cost to choose it."""

    stories: tuple[ScoredStory, ...]
    # The order the scores alone would have given, so the effect of diversity is visible
    # rather than asserted.
    by_score_alone: tuple[ScoredStory, ...]

    @property
    def displaced(self) -> tuple[ScoredStory, ...]:
        """Stories top-K by score would have shown that diversity pushed out."""
        chosen = {story.id for story in self.stories}
        return tuple(
            story for story in self.by_score_alone[: len(self.stories)] if story.id not in chosen
        )


def select(
    scored: Sequence[ScoredStory],
    story_vectors: Mapping[str, Vector],
    k: int,
    *,
    diversity: float = DEFAULT_DIVERSITY,
    max_per_domain: int = DEFAULT_MAX_PER_DOMAIN,
    tiers: Mapping[str, float] | None = None,
) -> Selection:
    """Choose up to `k` stories, penalising resemblance to what is already chosen.

    `tiers`, when given, is the re-ranker's verdict per story id, and diversity and the
    per-outlet cap work within a tier, never across one: every story the model called a must-read is taken before any
    it called relevant, and so on down. Found on the first live run (2026-10-07), where two
    stories the model scored 1 were placed above four it scored 2, because the penalty for
    resembling an earlier story was larger than the gap between two rubric scores. The rubric
    is the audience's own statement of what matters; resemblance should reorder within it,
    not overrule it.
    """
    by_score_alone = tuple(scored)
    if k <= 0 or not scored:
        return Selection(stories=(), by_score_alone=by_score_alone)

    remaining = list(scored)
    chosen: list[ScoredStory] = []
    per_domain: dict[str, int] = {}

    while remaining and len(chosen) < k:
        best: ScoredStory | None = None
        best_value = float("-inf")
        pool = remaining
        if tiers is not None:
            # The tier comes first and the outlet cap applies inside it: a story the model
            # called marginal does not go above one it called relevant because the relevant
            # one is the fourth from CBC. Seen on the same run, where three CBC stories at
            # the top capped the outlet and pulled two 1s above four 2s.
            top = max(tiers.get(story.id, 0.0) for story in remaining)
            pool = [story for story in remaining if tiers.get(story.id, 0.0) == top]
        eligible = [
            story
            for story in pool
            if per_domain.get(story.representative.domain, 0) < max_per_domain
        ]
        if tiers is not None and not eligible:
            # Every story left in this tier is from a capped outlet: the tier wins.
            eligible = pool
        for story in eligible:
            value = story.score - diversity * _max_similarity(story, chosen, story_vectors)
            if value > best_value:
                best, best_value = story, value
        if best is None:
            # Every remaining story is from a domain already at its cap. Rather than show a
            # short digest, lift the cap for the rest: a thin day is a real day, and the
            # alternative is silently dropping stories the reader wanted.
            per_domain.clear()
            max_per_domain = k
            continue
        chosen.append(best)
        per_domain[best.representative.domain] = per_domain.get(best.representative.domain, 0) + 1
        remaining.remove(best)

    return Selection(stories=tuple(chosen), by_score_alone=by_score_alone)


def _max_similarity(
    story: ScoredStory, chosen: Sequence[ScoredStory], vectors: Mapping[str, Vector]
) -> float:
    """How much this story resembles the one it most resembles among those chosen."""
    vector = vectors.get(story.id)
    if vector is None or not chosen:
        return 0.0
    similarities = [cosine(vector, vectors[other.id]) for other in chosen if other.id in vectors]
    return max(similarities) if similarities else 0.0


def candidates_for_rerank(scored: Sequence[ScoredStory], limit: int) -> tuple[ScoredStory, ...]:
    """The only stories a model is ever shown.

    This is the cost control of the whole project, and it is a slice rather than a filter on
    purpose: the number of model calls per audience per day is fixed by the audience file
    and cannot drift upward as the pool grows (PLAN.md section 2.3).
    """
    return tuple(scored[:limit])
