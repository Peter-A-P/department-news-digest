"""Turning features into one number, and saying what the number was made of.

The weights below are a prior, not a result. They are a starting point chosen from what the
features mean, and week 3 measures them against the hand-labelled week: precision at K under
these weights, against the alternatives, with intervals. Until that happens they are stated
here as an assumption rather than presented as a finding, and the README says so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from clippings.cluster.embed import Embedder, Vector
from clippings.config.audience import Audience
from clippings.models import Cluster, Item
from clippings.rank.features import (
    Features,
    Informativeness,
    audience_vectors,
    embed_stories,
    features_for,
    story_text,
)

# Weights sum to one, so a score is in [0, 1] and two audiences' scores mean the same thing.
#
# Similarity carries the most because it is the only feature that reads the whole audience
# description rather than a list. Entities and topics are next and are deliberately split:
# an item naming the regulator matters even when it uses none of the audience's topic words,
# and the reverse is also true. Recency is worth less than any of those on purpose, because
# a digest that ranks by freshness is a feed reader, and the product is not a feed reader.
# Corroboration is the smallest because it is the easiest to game and the slowest to move:
# the story every outlet carries is usually the one the reader already knows.
WEIGHTS: dict[str, float] = {
    "audience_similarity": 0.34,
    "entity_hits": 0.20,
    "topic_hits": 0.18,
    "recency": 0.14,
    "source_trust": 0.08,
    "corroboration": 0.06,
}


@dataclass(frozen=True)
class ScoredStory:
    """A story with its score and the features that produced it."""

    cluster: Cluster
    representative: Item
    features: Features
    score: float

    @property
    def id(self) -> str:
        return self.cluster.id

    def why(self, top: int = 3) -> str:
        """The features that contributed most, for the page and the labelling CLI."""
        contributions = {
            name: value * WEIGHTS[name] for name, value in self.features.as_dict().items()
        }
        ranked = sorted(contributions.items(), key=lambda pair: -pair[1])[:top]
        return ", ".join(f"{name.replace('_', ' ')} {value:.2f}" for name, value in ranked)


def combine(features: Features) -> float:
    """The weighted sum. Weights sum to one and every feature is in [0, 1]."""
    return sum(value * WEIGHTS[name] for name, value in features.as_dict().items())


def score_stories(
    clusters: Sequence[Cluster],
    items: Mapping[str, Item],
    audience: Audience,
    embedder: Embedder,
    now: datetime,
    *,
    profile: Sequence[Vector] | None = None,
) -> list[ScoredStory]:
    """Score every story for one audience, best first.

    The audience is embedded once per run, not once per story: it does not change within a
    run, and embedding it repeatedly would be the most obvious waste in the loop.
    """
    if not clusters:
        return []
    if profile is None:
        profile = audience_vectors(audience, embedder)
    story_vectors = embed_stories(clusters, items, embedder)
    # Measured on this day's pool for this audience, so no stop list is maintained per
    # department and a word's weight follows what that audience actually receives.
    informativeness = Informativeness([story_text(cluster, items) for cluster in clusters])
    scored = []
    for cluster in clusters:
        if cluster.representative_id not in items:
            # The representative was deleted by retention between clustering and ranking.
            continue
        features = features_for(
            cluster, items, audience, profile, story_vectors, now, informativeness
        )
        scored.append(
            ScoredStory(
                cluster=cluster,
                representative=items[cluster.representative_id],
                features=features,
                score=combine(features),
            )
        )
    # Ties broken by cluster id so a rerun produces the same order, which the labelling
    # sample depends on.
    scored.sort(key=lambda story: (-story.score, story.cluster.id))
    return scored
