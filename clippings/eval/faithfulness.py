"""Which digest sentences a person checks against their sources, and what they are shown.

PLAN.md section 1 reports claim faithfulness on a 100-sentence sample: the share of digest
sentences whose cited sources support everything they say. The verifier already proves every
quote verbatim and every number present (summarise/verify.py); what it cannot check is a
paraphrase, which is what this sample is for.

The sample is drawn per audience-day, `PER_DAY` sentences uniformly from the sentences the
day's digest showed, over the first `DAYS` digest days with a sentence from the audience's
`measure_from`:
four audiences, seven days and four sentences make 112, the plan's hundred with room for a
day that showed fewer. Drawing by day rather than from one pool of every sentence keeps the
sample fixed as later digests arrive, and lets the interval redraw whole days, as every other
labelled number here does. Each judgement carries a weight, the day's shown sentences over
those drawn, so a day with many sentences counts for as many as it showed.

The checker is shown what the summariser read of each cited source, no more: the title, the
feed summary and the start of the article where it was extracted (`cite.source_text`). A
sentence that says something true that is not in those words is not supported.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from clippings.assemble.digest import Digest, DigestStory, SourceLink
from clippings.ingest.store import Store
from clippings.summarise.cite import source_text

PER_DAY = 4
DAYS = 7


@dataclass(frozen=True)
class SentenceUnit:
    """One sentence to judge, and how many of the day's shown sentences it stands for."""

    story_id: str
    sentence: int
    weight: float

    @property
    def key(self) -> str:
        return f"{self.story_id}|{self.sentence}"


@dataclass(frozen=True)
class SentenceSample:
    audience_id: str
    day: str
    units: tuple[SentenceUnit, ...]
    shown: int


def _seed(audience_id: str, day: str) -> int:
    # A fixed hash, as in eval/sample.py: the same day asks about the same sentences every time.
    digest = hashlib.blake2b(f"{audience_id}|{day}|faith".encode(), digest_size=4).digest()
    return int.from_bytes(digest, "big") % (2**31)


def sentence_sample(digest: Digest, *, per_day: int = PER_DAY) -> SentenceSample:
    population = [
        (story.story_id, index)
        for story in digest.stories
        for index, _ in enumerate(story.sentences)
    ]
    drawn = random.Random(_seed(digest.audience_id, digest.day)).sample(
        population, min(per_day, len(population))
    )
    weight = len(population) / len(drawn) if drawn else 0.0
    return SentenceSample(
        audience_id=digest.audience_id,
        day=digest.day,
        units=tuple(SentenceUnit(story_id, index, weight) for story_id, index in sorted(drawn)),
        shown=len(population),
    )


def sample_days(store: Store, audience_id: str, measure_from: str | None) -> list[str]:
    """The days sentences are drawn from: the first `DAYS` digest days from `measure_from`
    that showed a sentence. A day whose digest was empty (public health had three in its
    labelled week, when nothing passed the rubric) has nothing to check, so the next day
    stands in for it."""
    start = measure_from or ""
    days = []
    for day in sorted(day for day in store.digest_days(audience_id) if day >= start):
        digest = store.digest_for(audience_id, day)
        if digest is not None and any(story.sentences for story in digest.stories):
            days.append(day)
        if len(days) == DAYS:
            break
    return days


@dataclass(frozen=True)
class CitedSource:
    """One source a sentence cites, as the checker sees it."""

    link: SourceLink
    # What the summariser read, or "" when it is no longer on record.
    text: str
    # Said in place of, or after, the text: what was read, or why it cannot be shown.
    note: str


def cited_sources(
    store: Store, audience_id: str, story: DigestStory, sentence: int
) -> list[CitedSource]:
    by_sid = {link.sid: link for link in story.sources}
    links = [by_sid[sid] for sid in story.sentences[sentence].cites if sid in by_sid]
    items = {item.id: item for item in store.items_for(audience_id)}
    texts = store.texts_for(link.item_id for link in links)
    shown = []
    for link in links:
        item = items.get(link.item_id)
        if item is None:
            shown.append(
                CitedSource(
                    link,
                    "",
                    "Deleted after thirty days: open the article to check, or mark it unclear.",
                )
            )
            continue
        if link.extracted and link.item_id not in texts:
            shown.append(
                CitedSource(
                    link,
                    source_text(item, None),
                    "The article text the summariser read is deleted; only the title and "
                    "feed summary are left.",
                )
            )
            continue
        note = "" if link.extracted else "The summariser read only the title and feed summary."
        shown.append(
            CitedSource(
                link, source_text(item, texts.get(link.item_id) if link.extracted else None), note
            )
        )
    return shown
