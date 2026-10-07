"""The model re-ranker: the only stage that reads the audience's rubric.

The first live ranking showed why this exists (see the commit that built `rank/`): the
pre-filter ranked a fatal collision first and a film interview sixth in a municipal digest,
both of which the rubric excludes in so many words. Nothing that runs on CPU reads a
sentence like "it excludes routine crime and court reports", and the exclusions are exactly
what pollutes the top of a regional pool.

So the top candidates, and only those, go to a small model with the rubric, in one call per
audience per day. PLAN.md section 2.3: the model never sees the whole pool. The slice is
taken in `select.candidates_for_rerank` and its length is fixed by the audience file, so the
cost of this call cannot drift upward as the pool grows.

What the model is shown per candidate is what the publisher put in the feed: the headline,
the outlet and the first words of the feed summary. Not the article text: a relevance
judgement does not need it, and sending it would multiply the cost of the one call whose
input grows with the candidate count.

The model's answer is a score from 0 to 3 per candidate. A 0 means not relevant or excluded
by the rubric, and a story scored 0 is never selected, however well it did on the
pre-filter. The rest are ordered by a blend in which the model dominates and the pre-filter
breaks near-ties, and the blend's weight is a prior to be measured in week 3, like the
pre-filter's weights.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace

from clippings.config.audience import Audience
from clippings.gateway import ModelCall, ModelCallFailed, ModelClient, ModelReply, Purpose
from clippings.rank.score import ScoredStory

# The scale, as the model is told it. Kept small on purpose: a four-point scale is one a
# model applies consistently, and one a person can check against the rubric by eye.
MAX_SCORE = 3

# How much of the final order is the model's. A prior, not a finding: the model is the only
# stage that reads the rubric, so it decides, and the pre-filter separates two stories the
# model scored the same. Measured against the labelled week in week 3.
MODEL_WEIGHT = 0.8

# Feed summaries run from a sentence to a whole article. The first words carry what the
# item is about, and the call's cost is linear in them.
SUMMARY_WORDS = 60

# Enough for one short line per candidate at the largest candidate count an audience file
# allows (200), with room for a model that writes slightly longer reasons than asked.
MAX_TOKENS = 8000

SYSTEM = """You rank news items for one audience's morning digest.

You are given the audience, its rubric (what counts as relevant and what does not), and a
numbered list of candidate items. Judge each candidate against the rubric only. Do not
reward an item for being recent, popular, dramatic or local unless the rubric asks for that.
Apply the rubric's exclusions strictly: an excluded kind of item scores 0 however prominent.

Score every candidate:
3 = the audience must read this today
2 = relevant, belongs in the digest if there is room
1 = marginal: touches the audience's concerns but changes nothing for them
0 = not relevant, or excluded by the rubric

Answer with one JSON object per line and nothing else, one line per candidate, in the order
given:
{"id": "c01", "score": 2, "reason": "at most twelve words"}"""


@dataclass(frozen=True)
class RerankScore:
    """What the model said about one candidate, kept beside what it was combined with."""

    story_id: str
    local_id: str
    prefilter: float
    # None when the model gave no usable score for this candidate; the story then keeps its
    # pre-filter score alone, and the digest says how many candidates that happened to.
    model_score: int | None
    reason: str
    final: float

    @property
    def excluded(self) -> bool:
        return self.model_score == 0


@dataclass(frozen=True)
class Rerank:
    """The re-ranked candidates, best first, and what it cost to get them."""

    stories: tuple[ScoredStory, ...]
    scores: tuple[RerankScore, ...]
    reply: ModelReply | None
    # Empty when the call succeeded. When it failed the digest is built from the pre-filter
    # order and says so, rather than not being built at all.
    error: str = ""

    @property
    def reranked(self) -> bool:
        return self.reply is not None and not self.error

    @property
    def unscored(self) -> int:
        return sum(1 for score in self.scores if score.model_score is None)

    @property
    def excluded(self) -> int:
        return sum(1 for score in self.scores if score.excluded)

    def selectable(self) -> tuple[ScoredStory, ...]:
        """The stories the digest may be chosen from: everything not scored 0."""
        excluded = {score.story_id for score in self.scores if score.excluded}
        return tuple(story for story in self.stories if story.id not in excluded)


def local_ids(count: int) -> list[str]:
    """Short ids the model echoes back. Shorter than a cluster id and impossible to confuse
    with one, so a model that invents an id is caught rather than matched to the wrong story."""
    width = max(2, len(str(count)))
    return [f"c{index:0{width}d}" for index in range(1, count + 1)]


def candidate_line(local_id: str, story: ScoredStory) -> str:
    item = story.representative
    words = item.summary.split()
    summary = " ".join(words[:SUMMARY_WORDS]) + (" ..." if len(words) > SUMMARY_WORDS else "")
    outlets = f" (+{story.cluster.size - 1} other outlets)" if story.cluster.size > 1 else ""
    line = f"{local_id} | {item.domain}{outlets} | {item.title.strip()}"
    return f"{line} | {summary}" if summary else line


def build_call(audience: Audience, candidates: Sequence[ScoredStory]) -> ModelCall:
    """The one re-ranking request for one audience's day."""
    ids = local_ids(len(candidates))
    lines = "\n".join(candidate_line(ids[i], story) for i, story in enumerate(candidates))
    user = (
        f"Audience: {audience.name}\n"
        f"About: {audience.description.strip()}\n\n"
        f"Rubric: {audience.rubric.strip()}\n\n"
        f"Candidates ({len(candidates)}), one per line as id | outlet | headline | summary:\n"
        f"{lines}"
    )
    return ModelCall(
        purpose=Purpose.RERANK,
        audience_id=audience.id,
        system=SYSTEM,
        user=user,
        max_tokens=MAX_TOKENS,
    )


LINE = re.compile(r"\{[^{}]*\}")


def parse_scores(text: str, allowed: set[str]) -> dict[str, tuple[int, str]]:
    """Every usable `{"id", "score", "reason"}` object in the reply.

    Lenient about layout, strict about content: an object anywhere in the text is read, so a
    model that wraps its lines in a code fence or a list still parses; an id that was not
    offered, a score outside 0 to 3, or a second score for the same id is ignored rather
    than guessed at. The first score for an id wins.
    """
    scores: dict[str, tuple[int, str]] = {}
    for match in LINE.finditer(text):
        try:
            loaded = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not isinstance(loaded, dict):
            continue
        local_id = loaded.get("id")
        score = loaded.get("score")
        if not isinstance(local_id, str) or local_id not in allowed or local_id in scores:
            continue
        if isinstance(score, bool) or not isinstance(score, int | float):
            continue
        if score != int(score) or not 0 <= score <= MAX_SCORE:
            continue
        reason = loaded.get("reason")
        scores[local_id] = (int(score), reason.strip() if isinstance(reason, str) else "")
    return scores


def blend(model_score: int | None, prefilter: float) -> float:
    """The final order value, in [0, 1].

    A candidate the model gave no score keeps the place its pre-filter score would give it
    among the scored ones at the same pre-filter weight, which puts it below every scored
    candidate the model thought relevant and above the ones it excluded.
    """
    if model_score is None:
        return (1.0 - MODEL_WEIGHT) * prefilter
    return MODEL_WEIGHT * model_score / MAX_SCORE + (1.0 - MODEL_WEIGHT) * prefilter


def rerank(
    audience: Audience,
    candidates: Sequence[ScoredStory],
    client: ModelClient,
    *,
    run_id: str,
) -> Rerank:
    """Re-rank the candidate slice with one model call.

    A failed call is not a failed digest: the stories come back in pre-filter order with
    `error` set, and the page says the rubric was not applied that day.
    """
    if not candidates:
        return Rerank(stories=(), scores=(), reply=None)
    ids = local_ids(len(candidates))
    call = build_call(audience, candidates)
    try:
        reply = client.complete(call, run_id=run_id)
    except ModelCallFailed as exc:
        return _unreranked(candidates, ids, str(exc))

    parsed = parse_scores(reply.text, set(ids))
    if not parsed:
        return _unreranked(candidates, ids, "the re-ranker's reply held no usable scores", reply)

    scores: list[RerankScore] = []
    for local_id, story in zip(ids, candidates, strict=True):
        model_score, reason = parsed.get(local_id, (None, ""))
        scores.append(
            RerankScore(
                story_id=story.id,
                local_id=local_id,
                prefilter=story.score,
                model_score=model_score,
                reason=reason,
                final=blend(model_score, story.score),
            )
        )
    by_id = {score.story_id: score for score in scores}
    reordered = sorted(
        (replace(story, score=by_id[story.id].final) for story in candidates),
        key=lambda story: (-story.score, story.id),
    )
    order = {story.id: index for index, story in enumerate(reordered)}
    scores.sort(key=lambda score: order[score.story_id])
    return Rerank(stories=tuple(reordered), scores=tuple(scores), reply=reply)


def _unreranked(
    candidates: Sequence[ScoredStory],
    ids: Sequence[str],
    error: str,
    reply: ModelReply | None = None,
) -> Rerank:
    scores = tuple(
        RerankScore(
            story_id=story.id,
            local_id=local_id,
            prefilter=story.score,
            model_score=None,
            reason="",
            final=story.score,
        )
        for local_id, story in zip(ids, candidates, strict=True)
    )
    return Rerank(stories=tuple(candidates), scores=scores, reply=reply, error=error)
