"""What a story is scored on, before any model sees it.

PLAN.md section 2.3: ranking is hybrid, and only the top candidates go to a model
re-ranker. Everything here runs on CPU in the job and costs nothing, which is what makes a
digest cost cents rather than dollars: the pre-filter does the bulk of the work and the
model is asked only about what survived it.

Every feature is kept on the result rather than collapsed into the score. A digest that
cannot say why an item is in it is a black box with a citation, and both the page and the
labelling CLI show the breakdown.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from clippings.cluster.embed import Embedder, Vector, cosine
from clippings.config.audience import Audience
from clippings.ingest.normalise import is_trusted
from clippings.models import Cluster, Item

# How fast a story goes stale. A daily digest at 07:00 covers roughly the last day, so a
# story from yesterday morning should still rank and one from last week should not. Twelve
# hours halves the recency term; at 48 hours it is down to about a sixteenth.
RECENCY_HALF_LIFE_HOURS = 12.0

# A story carried by several outlets is more likely to matter. The term saturates fast,
# because the difference between one outlet and three is real and the difference between
# eight and twelve is not.
CORROBORATION_SATURATION = 3.0

# A source the audience named as trusted is worth more than one it did not, but not so much
# more that a trusted source's routine notice outranks everybody else's important one.
TRUSTED_WEIGHT = 1.0
UNTRUSTED_WEIGHT = 0.6

WORD = re.compile(r"[a-z0-9]+")

# Words that carry no topic signal. A topic like "transit service and expansion" is about
# transit, service and expansion; "and" matches everything and means nothing.
STOP_WORDS = frozenset(
    {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
)


@dataclass(frozen=True)
class Features:
    """One story's features, each in [0, 1]."""

    audience_similarity: float
    entity_hits: float
    topic_hits: float
    source_trust: float
    recency: float
    corroboration: float

    def as_dict(self) -> dict[str, float]:
        return {
            "audience_similarity": self.audience_similarity,
            "entity_hits": self.entity_hits,
            "topic_hits": self.topic_hits,
            "source_trust": self.source_trust,
            "recency": self.recency,
            "corroboration": self.corroboration,
        }


def normalise_text(text: str) -> str:
    """Lower-case words separated by single spaces, so phrase matching is not fooled by
    punctuation or by a line break in the middle of an organisation's name."""
    return " ".join(WORD.findall(text.lower()))


class Informativeness:
    """How much each word tells you, measured on the day's own pool.

    The third defect the first live run exposed. An audience for Toronto lists "Toronto" as
    a place and writes topics like "Toronto city council", and every single item in a
    Toronto feed contains the word "Toronto". Matching on it scored almost every story
    identically and near the top: the entity feature saturated at 1.00 on 20 stories out of
    23, which is the same as having no feature.

    A word that appears in every document distinguishes nothing, and a word that appears in
    two documents out of two hundred distinguishes a great deal. That is inverse document
    frequency, computed here over the day's pool rather than a fixed corpus, so it adapts to
    each audience without anybody maintaining a stop list per department: "Toronto" is
    uninformative in the Toronto audience and informative in the national one, and nothing
    has to be configured for that to be true.
    """

    def __init__(self, documents: Sequence[str]) -> None:
        self._total = len(documents)
        frequency: dict[str, int] = {}
        for document in documents:
            for word in frozenset(WORD.findall(document.lower())):
                frequency[word] = frequency.get(word, 0) + 1
        self._frequency = frequency

    def weight(self, word: str) -> float:
        """The word's inverse document frequency, floored at zero.

        A word in every document scores zero. An unseen word is treated as maximally
        informative, which is right: it is not in the pool, so it cannot be boilerplate.
        """
        if self._total == 0:
            return 1.0
        seen = self._frequency.get(word, 0)
        if seen >= self._total:
            return 0.0
        return math.log(self._total / (1 + seen))

    def uniform(self) -> bool:
        """True when there is nothing to learn from, so callers can fall back."""
        return self._total < 2


def content_words(phrase: str) -> frozenset[str]:
    """The words in a phrase that carry its meaning."""
    return frozenset(WORD.findall(phrase.lower())) - STOP_WORDS


def phrase_hits(
    haystack: str, phrases: Sequence[str], informativeness: Informativeness | None = None
) -> float:
    """How well the text matches the best-matching phrase, in [0, 1].

    Two decisions here, both made after the first live run, where exact phrase matching
    scored zero on 23 stories out of 23 and left this feature contributing nothing at all.

    **Partial credit, not exact match.** An audience writes topics like "transit service and
    expansion", and no headline ever contains that string. A story is credited with the
    share of a phrase's content words it contains, so "TTC service changes" matches the
    transit topic in part rather than not at all.

    **The best phrase, not the average.** A story is relevant because it is about one of the
    audience's concerns, not because it is slightly about all of them. Averaging over ten
    topics would give a story that nails one topic a score of a tenth, which is
    indistinguishable from a story that grazes several and is about none of them.
    """
    if not phrases:
        return 0.0
    present = frozenset(WORD.findall(haystack.lower()))
    best = 0.0
    for phrase in phrases:
        words = content_words(phrase)
        if not words:
            continue
        if informativeness is None or informativeness.uniform():
            best = max(best, len(words & present) / len(words))
            continue
        weights = {word: informativeness.weight(word) for word in words}
        total = sum(weights.values())
        if total <= 0.0:
            # Every word in this phrase appears in every story today, so matching it says
            # nothing. Zero, rather than one, is the honest score.
            continue
        matched = sum(weight for word, weight in weights.items() if word in present)
        best = max(best, matched / total)
    return best


def recency(published_at: datetime, now: datetime) -> float:
    """Exponential decay on hours since publication, in [0, 1].

    An item dated in the future, which happens when a publisher's clock is wrong or a feed
    carries no date and normalisation used the fetch time, is treated as brand new rather
    than given a score above one.
    """
    hours = (now - published_at).total_seconds() / 3600
    if hours <= 0:
        return 1.0
    return float(2 ** (-hours / RECENCY_HALF_LIFE_HOURS))


def corroboration(cluster_size: int) -> float:
    """How many outlets carry this story, saturating in [0, 1]."""
    return 1.0 - math.exp(-(cluster_size - 1) / CORROBORATION_SATURATION)


def story_text(cluster: Cluster, items: Mapping[str, Item]) -> str:
    """Every title and summary in the story, which is what entities are matched against.

    The whole cluster rather than its representative: one outlet names the minister in the
    headline and another only in the third paragraph, and the story is the same story.
    """
    parts: list[str] = []
    for item_id in cluster.item_ids:
        item = items.get(item_id)
        if item is not None:
            parts.append(item.title)
            parts.append(item.summary)
    return " ".join(parts)


def audience_vectors(audience: Audience, embedder: Embedder) -> tuple[Vector, ...]:
    """The audience as several vectors, not one.

    Blending the description and every topic into a single vector produces a centroid that
    is close to everything the audience might read and sharp about nothing: on the first
    live run it ranked a car show and a home run into a municipal-affairs digest. An
    audience is a list of separate concerns, so it is embedded as one, and a story is scored
    against the concern it matches best.
    """
    texts = [audience.description, *audience.topics]
    return tuple(embedder.embed([text for text in texts if text.strip()]))


def features_for(
    cluster: Cluster,
    items: Mapping[str, Item],
    audience: Audience,
    profile: Sequence[Vector],
    story_vectors: Mapping[str, Vector],
    now: datetime,
    informativeness: Informativeness | None = None,
) -> Features:
    """Score one story against one audience."""
    representative = items[cluster.representative_id]
    text = story_text(cluster, items)
    story_vector = story_vectors.get(cluster.id)
    similarity = (
        max((cosine(vector, story_vector) for vector in profile), default=0.0)
        if story_vector is not None
        else 0.0
    )
    return Features(
        # Cosine over unit vectors is in [-1, 1]; anything below zero means unrelated, not
        # "negatively related", so the floor is zero.
        audience_similarity=max(0.0, similarity),
        entity_hits=phrase_hits(text, audience.entities.all(), informativeness),
        topic_hits=phrase_hits(text, audience.topics, informativeness),
        source_trust=(
            TRUSTED_WEIGHT if is_trusted(representative.domain, audience) else UNTRUSTED_WEIGHT
        ),
        recency=recency(representative.published_at, now),
        corroboration=corroboration(cluster.size),
    )


def embed_stories(
    clusters: Sequence[Cluster], items: Mapping[str, Item], embedder: Embedder
) -> dict[str, Vector]:
    """One vector per story, from every title and summary it contains."""
    if not clusters:
        return {}
    texts = [story_text(cluster, items) for cluster in clusters]
    return dict(zip((cluster.id for cluster in clusters), embedder.embed(texts), strict=True))
