"""The summariser: a few cited sentences per story, with any quotes marked.

One call per story. The story's sources are numbered `s1` to `s4`, and the model answers with
sentences that each name the sources they draw on. Everything it writes goes to the verifier,
so the prompt's job is to make the verifier's rules easy to keep rather than to enforce them:
nothing in this file decides whether a sentence is shown.

The headline is not the model's. A story is headed by its representative item's own title and
links to it, so the only words in a digest that no publisher wrote are the summary sentences,
and every one of those is checked.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC

from clippings.config.audience import Audience
from clippings.constants import QUOTE_MAX_WORDS
from clippings.gateway import ModelCall, Purpose
from clippings.summarise.cite import Source

MAX_TOKENS = 700

SYSTEM = f"""You write one story's entry in a morning news digest for a named audience.

You are given the story's sources, each with an id (s1, s2, ...): the outlet, the headline,
the feed summary and, where available, the start of the article. Write a short summary of
what happened and why it matters to this audience.

Rules, all of which are checked mechanically and a sentence that breaks one is deleted:
- Every sentence names, in "sources", the ids of the sources it draws on. At least one.
- Say only what the cited sources say. No background from memory, no speculation.
- Every number you write must appear in a source the sentence cites.
- Quotes are optional. If you quote, use straight double quotes, copy the words exactly as
  they appear in a source the sentence cites, with no ellipses or changes, and quote at most
  {QUOTE_MAX_WORDS} words. Do not use double quotes for anything else.
- Plain punctuation: no em dashes or en dashes.
- Write for the audience: lead with what changed for them.

Answer with one JSON object and nothing else:
{{"sentences": [{{"text": "...", "sources": ["s1"]}}, {{"text": "...", "sources": ["s1", "s2"]}}]}}"""


def render_sources(sources: Sequence[Source]) -> str:
    blocks = []
    for source in sources:
        published = source.item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
        blocks.append(f"[{source.sid}] {source.domain}, published {published}\n{source.text}")
    return "\n\n---\n\n".join(blocks)


def build_call(audience: Audience, sources: Sequence[Source]) -> ModelCall:
    """The summary request for one story."""
    n = audience.digest.max_sentences_per_story
    user = (
        f"Audience: {audience.name}\n"
        f"About: {audience.description.strip()}\n\n"
        f"Write at most {n} sentence{'s' if n != 1 else ''}.\n\n"
        f"Sources:\n\n{render_sources(sources)}"
    )
    return ModelCall(
        purpose=Purpose.SUMMARISE,
        audience_id=audience.id,
        system=SYSTEM,
        user=user,
        max_tokens=MAX_TOKENS,
    )
