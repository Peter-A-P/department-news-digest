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
) -> Selection:
    """Choose up to `k` stories, penalising resemblance to what is already chosen."""
    by_score_alone = tuple(scored)
    if k <= 0 or not scored:
        return Selection(stories=(), by_score_alone=by_score_alone)

    remaining = list(scored)
    chosen: list[ScoredStory] = []
    per_domain: dict[str, int] = {}

    while remaining and len(chosen) < k:
        best: ScoredStory | None = None
        best_value = float("-inf")
        for story in remaining:
            domain = story.representative.domain
            if per_domain.get(domain, 0) >= max_per_domain:
                continue
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
