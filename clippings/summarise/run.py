"""Summarise, verify, repair, verify: the stages the graph runs over the chosen stories.

Each function takes every story at once and does one thing to each, so a graph node is one
call and the order of operations is the graph's, not hidden in a loop here. A story's state
lives in a `StoryWork` and nothing in it is overwritten: the first draft and its check stay
beside the repaired draft and its check, because the published counts are the difference
between them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from clippings.config.audience import Audience
from clippings.gateway import ModelCallFailed, ModelClient, ModelReply, Purpose
from clippings.models import Item, ItemText
from clippings.rank.score import ScoredStory
from clippings.summarise import prompt, repair
from clippings.summarise.cite import CitedSentence, Source, StoryDraft, parse_draft, story_sources
from clippings.summarise.verify import StoryCheck, verify_story


@dataclass
class StoryWork:
    """One chosen story on its way through the summariser and the verifier."""

    story: ScoredStory
    sources: tuple[Source, ...]
    draft: StoryDraft | None = None
    first: StoryCheck | None = None
    repaired: StoryDraft | None = None
    final: StoryCheck | None = None
    replies: list[tuple[Purpose, ModelReply]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.story.id

    @property
    def needs_repair(self) -> bool:
        return self.first is not None and bool(self.first.failed) and self.repaired is None

    @property
    def kept(self) -> tuple[CitedSentence, ...]:
        """What the digest shows: the second check's survivors if there was a repair, the
        first's otherwise. A sentence reaches here only by passing a check."""
        if self.final is not None:
            return self.final.kept
        if self.first is not None:
            return self.first.kept
        return ()

    @property
    def status(self) -> str:
        if not self.kept and self.draft is not None and not self.draft.sentences and self.errors:
            # Nothing was drafted because the call failed or its answer did not parse: a
            # different fact from a summary the verifier refused, and the page says which.
            return "summary failed"
        if not self.kept:
            return "no verified summary"
        return "repaired" if self.repaired is not None else "verified"


def prepare(
    stories: Sequence[ScoredStory],
    items: Mapping[str, Item],
    texts: Mapping[str, ItemText],
    audience: Audience,
) -> list[StoryWork]:
    return [
        StoryWork(story=story, sources=story_sources(story.cluster, items, texts, audience))
        for story in stories
    ]


def draft_all(
    works: Sequence[StoryWork], audience: Audience, client: ModelClient, *, run_id: str
) -> None:
    """One summary call per story. A failed call leaves that story with no summary."""
    for work in works:
        try:
            reply = client.complete(prompt.build_call(audience, work.sources), run_id=run_id)
        except ModelCallFailed as exc:
            work.errors.append(str(exc))
            work.draft = StoryDraft(work.id, (), parse_error="the summary call failed")
            continue
        work.replies.append((Purpose.SUMMARISE, reply))
        work.draft = parse_draft(work.id, reply.text, audience.digest.max_sentences_per_story)
        if work.draft.parse_error:
            work.errors.append(work.draft.parse_error)


def verify_all(works: Sequence[StoryWork]) -> None:
    """Check whatever was last written for each story: the first draft, or its repair."""
    for work in works:
        if work.repaired is not None:
            work.final = verify_story(work.repaired, work.sources)
        elif work.draft is not None and work.first is None:
            work.first = verify_story(work.draft, work.sources)


def repair_all(
    works: Sequence[StoryWork], audience: Audience, client: ModelClient, *, run_id: str
) -> None:
    """One rewrite for each story with a refused sentence, and never a second."""
    for work in works:
        if not work.needs_repair or work.first is None:
            continue
        draft, reply, error = repair.repair_story(
            audience, work.sources, work.first, client, run_id=run_id
        )
        work.repaired = draft
        if reply is not None:
            work.replies.append((Purpose.REPAIR, reply))
        if error:
            work.errors.append(f"repair: {error}")


def any_need_repair(works: Sequence[StoryWork]) -> bool:
    return any(work.needs_repair for work in works)
