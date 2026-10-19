"""What a story is summarised from, and what the summariser's answer is parsed into.

A story's sources are its items, each given a short id (`s1`, `s2`, ...) that the model
cites. The id is local to the story on purpose: a citation can only resolve to an item in
this cluster, so "a citation to an id outside the cluster" is a parse result the verifier
can see, not a lookup that might quietly succeed against some other story.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from clippings.config.audience import Audience
from clippings.ingest.normalise import is_trusted
from clippings.models import Cluster, Item, ItemText

# How many of a story's items the summariser reads. The representative first, then the
# most trusted and the earliest: past four, another outlet's copy of the same wire story adds
# tokens and nothing to say.
MAX_SOURCES = 4

# Words of article text per source. Enough for the lead and the first quotes, which is where
# a news story puts what matters, and it keeps a story's call near PLAN.md section 6's
# 3,000 input tokens.
TEXT_WORDS = 450

# Straight double quotes are the only quotation marks the summariser is asked to use; curly
# ones are folded to straight before parsing, so a model that types them is still read.
CURLY_DOUBLE = str.maketrans({"“": '"', "”": '"', "„": '"', "«": '"', "»": '"'})
QUOTE = re.compile(r'"([^"]*)"')


@dataclass(frozen=True)
class Source:
    """One item as the summariser sees it."""

    sid: str
    item: Item
    # What the model may draw on and what a quote is checked against: the publisher's title
    # and feed summary, then the extracted article text where the terms allowed extraction.
    text: str
    extracted: bool

    @property
    def domain(self) -> str:
        return self.item.domain


def story_sources(
    cluster: Cluster,
    items: Mapping[str, Item],
    texts: Mapping[str, ItemText],
    audience: Audience,
    *,
    limit: int = MAX_SOURCES,
) -> tuple[Source, ...]:
    """The items a story is summarised from, in the order they are shown to the model."""
    members = [items[item_id] for item_id in cluster.item_ids if item_id in items]
    members.sort(
        key=lambda item: (
            item.id != cluster.representative_id,
            not is_trusted(item.domain, audience),
            item.published_at,
            item.id,
        )
    )
    return tuple(
        Source(
            sid=f"s{index}",
            item=item,
            text=source_text(item, texts.get(item.id)),
            extracted=item.id in texts,
        )
        for index, item in enumerate(members[:limit], start=1)
    )


def source_text(item: Item, extracted: ItemText | None) -> str:
    """What the summariser reads of one item: the title, the feed summary, then the start of
    the article where it was extracted. The faithfulness check shows a person the same."""
    parts = [item.title.strip(), item.summary.strip()]
    if extracted is not None:
        parts.append(" ".join(extracted.text.split()[:TEXT_WORDS]))
    return "\n\n".join(part for part in parts if part)


@dataclass(frozen=True)
class CitedSentence:
    """One sentence of a summary and the sources it says it draws on."""

    text: str
    cites: tuple[str, ...]

    @property
    def quotes(self) -> tuple[str, ...]:
        """Every span the sentence puts in quotation marks."""
        return tuple(match.group(1) for match in QUOTE.finditer(self.text))

    @property
    def balanced(self) -> bool:
        """An odd number of quotation marks leaves a quote whose extent is unknowable."""
        return self.text.count('"') % 2 == 0


@dataclass(frozen=True)
class StoryDraft:
    """The summariser's answer for one story, parsed."""

    story_id: str
    sentences: tuple[CitedSentence, ...]
    # Sentences past the audience's length budget, cut before verification.
    over_budget: int = 0
    parse_error: str = ""


def parse_draft(story_id: str, text: str, max_sentences: int) -> StoryDraft:
    """Read `{"sentences": [{"text": ..., "sources": [...]}, ...]}` out of a reply.

    The first JSON object in the text is used, so a reply wrapped in a code fence or with a
    line of preamble still parses. Anything that is not a sentence with a string text is
    skipped; a sentence with no sources list is kept with no citations, so the verifier
    refuses it for being uncited rather than the parser hiding it.
    """
    loaded = _first_object(text)
    if loaded is None:
        return StoryDraft(story_id, (), parse_error="no JSON object in the reply")
    raw = loaded.get("sentences")
    if not isinstance(raw, list):
        return StoryDraft(story_id, (), parse_error="the reply has no sentences list")
    sentences: list[CitedSentence] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        body = entry.get("text")
        if not isinstance(body, str) or not body.strip():
            continue
        cites = entry.get("sources", [])
        cited = tuple(str(cite).strip() for cite in cites) if isinstance(cites, list) else ()
        # Curly quotation marks become straight ones here, after JSON parsing, where they are
        # inside a string and cannot break the document.
        clean = " ".join(body.translate(CURLY_DOUBLE).split())
        sentences.append(CitedSentence(text=clean, cites=cited))
    kept = sentences[:max_sentences]
    return StoryDraft(story_id, tuple(kept), over_budget=len(sentences) - len(kept))


def _first_object(text: str) -> dict[str, object] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            loaded, _ = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


def source_map(sources: Sequence[Source]) -> dict[str, Source]:
    return {source.sid: source for source in sources}
