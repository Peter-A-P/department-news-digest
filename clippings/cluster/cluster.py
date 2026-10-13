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

Posts do not chain. Only news items form the components; a post then joins the one story
whose news item it is closest to, and only if it clears the threshold against that news
item itself. On 2026-10-08 chaining through posts turned OpenAI's mathematics announcement
into a twenty-item story: posts about AI regulation were within 0.82 of other posts, each
of which was within 0.82 of the next, and an off-topic post was listed as a source. Directly
against the announcement those posts scored 0.57 to 0.71. A post near no news item stays out
of every news story (with any posts it matches), and a story of posts alone is never a
candidate (PLAN.md section 2.3).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
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
from clippings.models import SOCIAL_KINDS, Cluster, Item

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
    outlet's summary of it. A news item before any post, whatever its time: the headline a
    story is shown under is a publisher's, and a post is commentary on the story.
    """
    return min(
        items,
        key=lambda item: (
            item.source_kind in SOCIAL_KINDS,
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
    components = _components(by_id, vectors, duplicates, stories)
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


def _components(
    by_id: dict[str, Item],
    vectors: dict[str, Vector],
    duplicates: set[tuple[str, str]],
    stories: set[tuple[str, str]],
) -> list[list[str]]:
    """News items chain into stories; each post joins at most one, by its own closest link."""
    is_post = {key: item.source_kind in SOCIAL_KINDS for key, item in by_id.items()}
    edges = duplicates | stories
    news = [key for key in by_id if not is_post[key]]
    news_edges = [(a, b) for a, b in edges if not is_post[a] and not is_post[b]]
    groups = connected_components(news, news_edges)
    group_of = {key: index for index, group in enumerate(groups) for key in group}

    # Each post's links to news items, scored: a near-duplicate is a perfect match, an
    # embedding link counts by its cosine. The best link decides the story, so a post close
    # to two stories joins one of them rather than merging them.
    best: dict[str, tuple[float, str]] = {}
    for a, b in edges:
        if is_post[a] == is_post[b]:
            continue
        post, news_item = (a, b) if is_post[a] else (b, a)
        score = 1.0 if (a, b) in duplicates else cosine(vectors[post], vectors[news_item])
        if post not in best or (score, news_item) > best[post]:
            best[post] = (score, news_item)
    for post, (_, news_item) in sorted(best.items()):
        groups[group_of[news_item]].append(post)

    orphans = [key for key in by_id if is_post[key] and key not in best]
    orphan_set = set(orphans)
    orphan_edges = [(a, b) for a, b in edges if a in orphan_set and b in orphan_set]
    return groups + connected_components(orphans, orphan_edges)


def collapse_rate(items_ingested: int, stories: int) -> float:
    """Items ingested per story shown: the headline deduplication number.

    One means nothing collapsed. Three means the average story arrived from three places.
    """
    return items_ingested / stories if stories else 0.0


def fresh_stories(
    clusters: Sequence[Cluster],
    items: Mapping[str, Item],
    audience: Audience,
    since: datetime | None,
) -> tuple[list[Cluster], set[str]]:
    """The day's stories with yesterday's taken out, and the ids of those taken out.

    The pool reaches back forty-eight hours, so that a report today joins the story it
    continues. Without this, a story built only of articles an earlier digest could already
    have shown came back the next morning (Peter, 2026-10-12: "old articles popping up in new
    days"): 69 of the 130 stories shown from 2026-10-08 to 2026-10-12 had nothing fetched
    since the previous digest. So a news story counts as today's only if at least one of its
    news items was first fetched after `since`, the previous digest's time. A story that
    gained a new report stays, headed by the new report, so the headline is what is new. A
    story of posts alone is left as it is: it is never a candidate, and the post pick reads it.
    """
    if since is None:
        return list(clusters), set()
    kept: list[Cluster] = []
    stale: set[str] = set()
    for cluster in clusters:
        news = [
            items[item_id]
            for item_id in cluster.item_ids
            if item_id in items and items[item_id].source_kind not in SOCIAL_KINDS
        ]
        if not news:
            kept.append(cluster)
            continue
        new = [item for item in news if item.fetched_at > since]
        if not new:
            stale.add(cluster.id)
            kept.append(cluster)
            continue
        if cluster.representative_id not in {item.id for item in new}:
            cluster = cluster.model_copy(
                update={"representative_id": representative(new, audience).id}
            )
        kept.append(cluster)
    return kept, stale
