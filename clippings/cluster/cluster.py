"""Grouping a day's items into stories.

Two passes, cheapest first. MinHash collapses the same text reprinted; embeddings then join
what is the same story told in different words. Both are thresholds over a graph, and the
clusters are the connected components of the union: the wire copy and the local write-up of
one announcement end up in one story, and so does the follow-up that quotes them both.

Connected components rather than a centroid method because a story genuinely chains: A is
the announcement, B reports A, C reports B with new detail. A threshold that joins each
link joins the chain, which is what a reader means by one story. The cost is that a bad
threshold merges two stories through one ambiguous item, which is why the deduplication
numbers are measured on labelled pairs rather than asserted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime

from clippings.cluster.embed import Embedder, Vector, cosine
from clippings.cluster.shingles import (
    DEFAULT_THRESHOLD as DUPLICATE_THRESHOLD,
)
from clippings.cluster.shingles import (
    connected_components,
    near_duplicates,
)
from clippings.config.audience import Audience
from clippings.ingest.normalise import is_trusted
from clippings.models import Cluster, Item

# Two items whose embeddings agree this much are the same story. Lower than the
# near-duplicate threshold because these are different words about one event; measured
# against the labelled pairs in week 3 and recorded there, not tuned by eye.
STORY_THRESHOLD = 0.82


# Below this a summary is a teaser rather than a lead, and the title has to carry the
# duplicate signal on its own.
MIN_SUMMARY_WORDS = 12


def duplicate_text(item: Item) -> str:
    """What the near-duplicate check compares: the body, where a reprint shows.

    Two outlets running the same wire copy share the lead almost word for word while
    rewriting the headline, so the title is deliberately left out where there is enough
    body to work with. Measured on the fixtures in the suite: the same wire story scores
    0.75 on the body alone and 0.51 once the weighted title is mixed in, on either side of
    the 0.7 threshold.
    """
    if len(item.summary.split()) >= MIN_SUMMARY_WORDS:
        return item.summary
    return f"{item.title} {item.summary}".strip()


def story_text(item: Item) -> str:
    """What the embedding compares: the title, weighted, plus the body.

    The opposite weighting to `duplicate_text`, and for the opposite reason. Two reports of
    one event share a subject rather than a sentence, and the headline is where the subject
    is stated.
    """
    return f"{item.title} {item.title} {item.summary}".strip()


def story_pairs(
    items: Sequence[Item], vectors: dict[str, Vector], threshold: float = STORY_THRESHOLD
) -> set[tuple[str, str]]:
    """Every pair of items whose embeddings put them in the same story.

    All-pairs over a day's pool for one audience: a few hundred items is tens of thousands
    of dot products, well under a second, and an index would be machinery with no payoff at
    this size.
    """
    pairs: set[tuple[str, str]] = set()
    ids = [item.id for item in items if item.id in vectors]
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            if cosine(vectors[left], vectors[right]) >= threshold:
                pairs.add((left, right) if left < right else (right, left))
    return pairs


def cluster_id(item_ids: Sequence[str]) -> str:
    """A stable id for a set of items, so the same story keeps its id across a rerun."""
    joined = "|".join(sorted(item_ids))
    return hashlib.blake2b(joined.encode("utf-8"), digest_size=8).hexdigest()


def representative(items: Sequence[Item], audience: Audience) -> Item:
    """The item that stands for the story: earliest, preferring a trusted source.

    Earliest because the digest links to the report that broke it, and trusted first
    because a department would rather be linked to the regulator's own notice than to an
    outlet's summary of it.
    """
    return min(
        items,
        key=lambda item: (
            not is_trusted(item.domain, audience),
            item.published_at,
            item.id,
        ),
    )


def build_clusters(
    items: Sequence[Item],
    audience: Audience,
    embedder: Embedder,
    day: str | datetime,
    *,
    duplicate_threshold: float = DUPLICATE_THRESHOLD,
    story_threshold: float = STORY_THRESHOLD,
) -> list[Cluster]:
    """Cluster a day's items for one audience, largest story first."""
    if not items:
        return []
    day_key = day if isinstance(day, str) else day.date().isoformat()
    by_id = {item.id: item for item in items}
    duplicates = near_duplicates(
        {item.id: duplicate_text(item) for item in items}, threshold=duplicate_threshold
    )
    vectors = dict(
        zip(by_id, embedder.embed([story_text(by_id[key]) for key in by_id]), strict=True)
    )
    stories = story_pairs(list(items), vectors, threshold=story_threshold)

    components = connected_components(by_id, duplicates | stories)
    clusters = [
        Cluster(
            id=cluster_id(members),
            audience_id=audience.id,
            day=day_key,
            representative_id=representative([by_id[key] for key in members], audience).id,
            item_ids=tuple(members),
        )
        for members in components
    ]
    clusters.sort(key=lambda cluster: (-cluster.size, cluster.id))
    return clusters


def collapse_rate(items_ingested: int, stories: int) -> float:
    """Items ingested per story shown: the headline deduplication number.

    One means nothing collapsed. Three means the average story arrived from three places.
    """
    return items_ingested / stories if stories else 0.0
