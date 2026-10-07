"""Repair once, then drop.

PLAN.md section 2.4: a sentence the verifier refuses is rewritten once, with the failure
named, and dropped if the rewrite fails too. Once is structural here, not a counter someone
can raise: `repair_story` takes a first-pass check and returns a draft, and the pipeline
verifies that draft and keeps what passes. There is no function that takes a repaired draft
and repairs it again.

The rewrite is asked for the failed sentences only, each with its reasons. The sentences
that passed are not sent back to be "improved": a sentence that has been verified is not put
at risk for the sake of style.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from clippings.config.audience import Audience
from clippings.gateway import ModelCall, ModelCallFailed, ModelClient, ModelReply, Purpose
from clippings.summarise.cite import CitedSentence, Source, StoryDraft, parse_draft
from clippings.summarise.prompt import MAX_TOKENS, SYSTEM, render_sources
from clippings.summarise.verify import StoryCheck


def build_call(audience: Audience, sources: Sequence[Source], check: StoryCheck) -> ModelCall:
    failed = [
        {
            "text": item.sentence.text,
            "sources": list(item.sentence.cites),
            "refused_because": [finding.describe() for finding in item.findings],
        }
        for item in check.failed
    ]
    user = (
        f"Audience: {audience.name}\n\n"
        "These sentences from your summary were refused by the checker, for the reasons "
        "given. Rewrite each one so it keeps every rule, or leave it out if the sources do "
        "not support it. Return only the rewritten sentences, in the same JSON shape.\n\n"
        f"Refused:\n{json.dumps(failed, indent=2)}\n\n"
        f"Sources:\n\n{render_sources(sources)}"
    )
    return ModelCall(
        purpose=Purpose.REPAIR,
        audience_id=audience.id,
        system=SYSTEM,
        user=user,
        max_tokens=MAX_TOKENS,
    )


def repair_story(
    audience: Audience,
    sources: Sequence[Source],
    check: StoryCheck,
    client: ModelClient,
    *,
    run_id: str,
) -> tuple[StoryDraft, ModelReply | None, str]:
    """The draft to verify a second time: what passed, plus the rewrites in their place.

    Returns the draft, the reply (for the cost record) and an error, empty on success. On a
    failed call the draft is what passed the first time, so the refused sentences are
    dropped, which is what happens to a sentence whose repair fails.
    """
    passed = check.kept
    if not check.failed:
        return StoryDraft(check.story_id, passed), None, ""
    try:
        reply = client.complete(build_call(audience, sources, check), run_id=run_id)
    except ModelCallFailed as exc:
        return StoryDraft(check.story_id, passed), None, str(exc)
    budget = audience.digest.max_sentences_per_story
    rewritten = parse_draft(check.story_id, reply.text, max_sentences=len(check.failed))
    merged = _in_place(check, rewritten.sentences)[:budget]
    return StoryDraft(check.story_id, tuple(merged)), reply, rewritten.parse_error


def _in_place(check: StoryCheck, rewrites: Sequence[CitedSentence]) -> list[CitedSentence]:
    """Each rewrite where the sentence it replaces stood, so the summary still reads in order.

    A rewrite that repeats a sentence already in the summary is left out: asked to fix an
    unsupported sentence, a model will often restate one that passed, and the same sentence
    twice is not a repair.
    """
    passed = {item.sentence.text.casefold() for item in check.checks if item.passed}
    queue = [rewrite for rewrite in rewrites if rewrite.text.casefold() not in passed]
    merged: list[CitedSentence] = []
    for item in check.checks:
        if item.passed:
            merged.append(item.sentence)
        elif queue:
            merged.append(queue.pop(0))
    return merged
