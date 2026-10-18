"""The objects that move through the pipeline.

An adapter yields `RawItem`. Normalisation turns it into `Item`, which is what the store
holds and everything downstream reads.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["rss", "sitemap", "gdelt", "reddit", "bluesky"]

# Discussion platforms. Their items are posts, not reports: they carry their own text, and
# since 2026-10-08 they reach a digest only inside a story that a news source also carries
# (`rank.score.has_news`), where they count as corroboration. Peter's decision, after Toronto
# commentary posts filled six of ten slots on the first day Bluesky was on.
SOCIAL_KINDS: frozenset[str] = frozenset({"reddit", "bluesky"})


class RawItem(BaseModel):
    """What a source adapter yields, before normalisation.

    The adapter does no cleaning beyond what its own format requires: normalisation is one
    place, so the rules are the same for every source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_key: str
    source_kind: SourceKind
    url: str
    title: str
    summary: str = ""
    author: str | None = None
    published_at: datetime | None = None
    # Where this item came from within the source: a feed URL, a subreddit, a query.
    origin: str = ""
    # Public engagement counts where the source publishes them, for the ranking features.
    score: int | None = None
    comments: int | None = None


class Item(BaseModel):
    """A normalised item in the store.

    `id` is derived from the canonical URL, so the same article arriving from a feed and
    from GDELT is one row, seen by both.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_key: str
    source_kind: SourceKind
    url: str
    original_url: str
    domain: str
    title: str
    summary: str = ""
    author: str | None = None
    language: str | None = None
    published_at: datetime
    fetched_at: datetime
    origin: str = ""
    score: int | None = None
    comments: int | None = None

    @staticmethod
    def id_for(canonical_url: str) -> str:
        """A stable id for a canonical URL: the first sixteen hex characters of its digest."""
        return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]


class ItemText(BaseModel):
    """Extracted article text, kept thirty days and never republished.

    Held apart from `Item` so retention deletes it on its own schedule and so no code path
    that renders a digest has the full text in hand by accident.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    text: str
    extracted_at: datetime
    # The extractor's own view of whether it found an article rather than a navigation page.
    words: int


class Cluster(BaseModel):
    """One story: the items that report it, for one audience on one day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    audience_id: str
    day: str
    # The item chosen to represent the story: earliest published among the most trusted.
    representative_id: str
    item_ids: tuple[str, ...] = Field(min_length=1)

    @property
    def size(self) -> int:
        return len(self.item_ids)


class Label(BaseModel):
    """One relevance judgement, by one labeller, on one item.

    The item's URL and title are copied here rather than referenced. A label outlives the
    item it was made on: retention deletes the item at thirty days, and the labelled week
    has to remain publishable as ids, URLs and labels after that (PLAN.md section 3).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audience_id: str
    day: str
    item_id: str
    labeller: str
    relevant: bool
    # Which stratum of the day's sample this came from, and what it stands for. Recall is
    # estimated from these weights, so a label without them cannot be used.
    # "spotlight" is the day's Bluesky pick (rank/spotlight.py) and "x_pick" the day's X pick
    # (rank/x_pick.py), each judged on its own and kept out of the sample's estimates.
    stratum: Literal["top", "random", "spotlight", "x_pick"]
    rank: int
    weight: float
    url: str
    title: str
    labelled_at: datetime
    # The stories the labeller would put in the digest first: relevant, and among the most
    # important of the day. A digest has room for ten, so "did it pick the most important
    # ten" is the recall that matters, not "did it show every relevant story" (Peter,
    # 2026-10-10). `graded` says the page offered the choice; labels from before it did not,
    # and their must_read is unknown rather than false.
    must_read: bool = False
    graded: bool = False


class PairLabel(BaseModel):
    """One judgement of whether two news items of a day's pool are the same story.

    Like a relevance label it copies both items' URLs and titles, so the labelled pairs stay
    publishable after retention deletes the items, and it records what the clustering decided
    when the pair was drawn, so the deduplication numbers do not depend on clusters that are
    deleted with them. `left_id` sorts before `right_id`: a pair has no order.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audience_id: str
    day: str
    left_id: str
    right_id: str
    labeller: str
    same_story: bool
    # "together": the clustering put the two in one story. "near": it kept them apart, but
    # their words overlap enough that they might be one. "check": apart, drawn from the rest,
    # and reported on its own as a test of the "near" boundary (eval/pairs.py).
    stratum: Literal["together", "near", "check"]
    # How many of the day's pairs in this stratum the label stands for.
    weight: float
    together: bool
    left_url: str
    left_title: str
    right_url: str
    right_title: str
    labelled_at: datetime
