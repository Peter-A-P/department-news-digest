"""The digest as data: what is shown, why, what it cost, and what the verifier refused.

A `Digest` is what the store keeps and every renderer reads. It holds no article text: the
summary sentences (the only words a model wrote, every one verified), quotes of at most
twenty-five words inside them, and each source's title, outlet and link. So it is safe to
keep after the thirty-day deletion of the items it was built from, and the archive and the
week-3 measurements are built from it.

The counts go with the digest rather than into a log, because the README's quote and
citation columns are sums over stored digests, and a number that can be recomputed from the
store is one a stranger can check.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from clippings.config.audience import Audience
from clippings.gateway import ModelReply, Purpose
from clippings.rank.rerank import Rerank, RerankScore
from clippings.summarise.run import StoryWork


class Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceLink(Frozen):
    sid: str
    item_id: str
    domain: str
    title: str
    url: str
    published_at: datetime
    # Whether the summariser read the article or only the feed's title and summary.
    extracted: bool


class DigestSentence(Frozen):
    text: str
    cites: tuple[str, ...]


class DigestStory(Frozen):
    story_id: str
    position: int
    headline: str
    url: str
    domain: str
    published_at: datetime
    outlets: int
    sentences: tuple[DigestSentence, ...]
    sources: tuple[SourceLink, ...]
    status: str
    prefilter_score: float
    rerank_score: int | None
    rerank_reason: str
    final_score: float
    why: str


class Spotlight(Frozen):
    """The day's most discussed Bluesky post the rubric wanted (rank/spotlight.py).

    Shown below the stories as a post card, not reporting: its author, its own words (whole
    while it exists and for thirty days, then cut to twenty-five), its counts and a link.
    Nothing here is model-written except `reason`, shown as the reason it was picked.
    """

    item_id: str
    url: str
    author: str
    quote: str
    likes: int
    replies: int
    posted_at: datetime
    rubric_score: int
    reason: str
    # The whole post, shown in the post card while it exists and for thirty days, then
    # cleared (assemble/deletions.py). Bluesky only: a Reddit post is never shown beyond its
    # quote, as the access request to Reddit promised.
    full_text: str = ""
    # Set when a later run found the post deleted: its words are then no longer shown at all.
    deleted: bool = False
    # The author's display name and picture and the repost count, from Bluesky's public API
    # when the post was picked, for the post card. Cleared with the words. Empty on picks
    # made before the card (2026-10-13), which then show the handle alone.
    name: str = ""
    image_url: str = ""
    reposts: int = 0


class XPick(Frozen):
    """The day's most discussed X post the rubric wanted (rank/x_pick.py).

    Shown whole, with the author's name, handle and picture, a timestamp linking to the post,
    the X logo and the reply, repost and like links, because X's display rules allow nothing
    less (Peter, 2026-10-10). Shown on the day it was picked only: the next run removes the
    words, the name and the picture from every stored copy and its page
    (assemble/deletions.py), which keeps the store current with X without paying to ask X
    whether the post still exists.
    """

    post_id: str
    url: str
    username: str
    name: str
    image_url: str
    text: str
    posted_at: datetime
    likes: int
    reposts: int
    replies: int
    rubric_score: int
    reason: str
    # The run's X reads at list price, in US dollars: the search and the author lookup.
    reads_usd: float
    # Set once the words, the name and the picture have been removed.
    expired: bool = False


class VerificationCounts(Frozen):
    """What the verifier saw, summed over the digest's stories.

    "First" is the summariser's own draft. "After repair" is what was verified the second
    time. Shown sentences passed one check or the other, so every quote shown is verbatim
    by construction, and the useful numbers are the first two quote figures: how often the
    model tried to put words in a source's mouth, before and after being told it had.
    """

    stories: int = 0
    sentences_drafted: int = 0
    sentences_cited_first: int = 0
    sentences_passed_first: int = 0
    sentences_repaired_ok: int = 0
    sentences_dropped: int = 0
    sentences_shown: int = 0
    over_budget_cut: int = 0
    quotes_first: int = 0
    quotes_verbatim_first: int = 0
    quotes_after_repair: int = 0
    quotes_verbatim_after_repair: int = 0
    quotes_shown: int = 0
    stories_repaired: int = 0
    stories_without_summary: int = 0
    refusals: dict[str, int] = {}


class CallCost(Frozen):
    purpose: str
    story_id: str
    model: str
    call_uid: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class Digest(Frozen):
    audience_id: str
    audience_name: str
    day: str
    run_id: str
    generated_at: datetime
    stories: tuple[DigestStory, ...]
    counts: VerificationCounts
    calls: tuple[CallCost, ...]
    # Pool and pipeline facts the page states, so a reader sees what the digest was chosen
    # from and by what.
    pool_items: int
    pool_stories: int
    candidates: int
    reranked: bool
    rerank_error: str
    rerank_unscored: int
    rerank_excluded: int
    embedder: str
    model_client: str
    # None when no post qualified, the call failed, or the digest predates the section.
    spotlight: Spotlight | None = None
    # The same for X, also None when X is off for the audience (sources.x.query empty).
    x_pick: XPick | None = None

    @property
    def cost_usd(self) -> float:
        """The digest's model cost from the gateway's own figures. Uncosted rows count zero
        here and are reported separately, because the gateway never guesses a price."""
        return sum(call.cost_usd or 0.0 for call in self.calls)

    @property
    def uncosted_calls(self) -> int:
        return sum(1 for call in self.calls if call.cost_usd is None)


def counts_for(works: Sequence[StoryWork]) -> VerificationCounts:
    refusals: Counter[str] = Counter()
    c: Counter[str] = Counter()
    for work in works:
        c["stories"] += 1
        if work.draft is not None:
            c["over_budget_cut"] += work.draft.over_budget
        if work.first is not None:
            c["sentences_drafted"] += len(work.first.checks)
            c["sentences_cited_first"] += work.first.cited
            c["sentences_passed_first"] += len(work.first.kept)
            c["quotes_first"] += work.first.quotes
            c["quotes_verbatim_first"] += work.first.quotes_verbatim
            for check in work.first.failed:
                for finding in check.findings:
                    refusals[finding.failure.value] += 1
        last = work.final or work.first
        if last is not None:
            c["quotes_after_repair"] += last.quotes
            c["quotes_verbatim_after_repair"] += last.quotes_verbatim
        if work.repaired is not None and work.first is not None:
            c["stories_repaired"] += 1
            c["sentences_repaired_ok"] += max(0, len(work.kept) - len(work.first.kept))
        shown = work.kept
        c["sentences_shown"] += len(shown)
        c["quotes_shown"] += sum(len(sentence.quotes) for sentence in shown)
        if not shown:
            c["stories_without_summary"] += 1
    c["sentences_dropped"] = (
        c["sentences_drafted"] - c["sentences_passed_first"] - c["sentences_repaired_ok"]
    )
    return VerificationCounts.model_validate({**c, "refusals": dict(refusals)})


def _story(position: int, work: StoryWork, score: RerankScore | None) -> DigestStory:
    rep = work.story.representative
    return DigestStory(
        story_id=work.id,
        position=position,
        headline=rep.title.strip(),
        url=rep.url,
        domain=rep.domain,
        published_at=rep.published_at,
        outlets=work.story.cluster.size,
        sentences=tuple(
            DigestSentence(text=sentence.text, cites=sentence.cites) for sentence in work.kept
        ),
        sources=tuple(
            SourceLink(
                sid=source.sid,
                item_id=source.item.id,
                domain=source.domain,
                title=source.item.title.strip(),
                url=source.item.url,
                published_at=source.item.published_at,
                extracted=source.extracted,
            )
            for source in work.sources
        ),
        status=work.status,
        prefilter_score=score.prefilter if score else work.story.score,
        rerank_score=score.model_score if score else None,
        rerank_reason=score.reason if score else "",
        final_score=work.story.score,
        why=work.story.why(),
    )


def call_cost(purpose: Purpose, story_id: str, reply: ModelReply) -> CallCost:
    """One model call as the digest records it, with the gateway's own price."""
    return CallCost(
        purpose=purpose.value,
        story_id=story_id,
        model=reply.model,
        call_uid=reply.call_uid,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cost_usd=reply.cost_usd,
    )


def _calls(
    rerank: Rerank | None, works: Sequence[StoryWork], extra: Sequence[ModelReply] = ()
) -> tuple[CallCost, ...]:
    cost = call_cost
    calls = []
    if rerank is not None and rerank.reply is not None:
        calls.append(cost(Purpose.RERANK, "", rerank.reply))
    for work in works:
        calls.extend(cost(purpose, work.id, reply) for purpose, reply in work.replies)
    calls.extend(cost(Purpose.SPOTLIGHT, "", reply) for reply in extra)
    return tuple(calls)


def build_digest(
    audience: Audience,
    *,
    day: str,
    run_id: str,
    generated_at: datetime,
    works: Sequence[StoryWork],
    rerank: Rerank | None,
    pool_items: int,
    pool_stories: int,
    embedder: str,
    model_client: str,
    spotlight: Spotlight | None = None,
    spotlight_reply: ModelReply | None = None,
    x_pick: XPick | None = None,
    x_pick_reply: ModelReply | None = None,
) -> Digest:
    scores = {score.story_id: score for score in rerank.scores} if rerank else {}
    return Digest(
        audience_id=audience.id,
        audience_name=audience.name,
        day=day,
        run_id=run_id,
        generated_at=generated_at,
        stories=tuple(
            _story(position, work, scores.get(work.id))
            for position, work in enumerate(works, start=1)
        ),
        counts=counts_for(works),
        calls=_calls(rerank, works, [r for r in (spotlight_reply, x_pick_reply) if r]),
        pool_items=pool_items,
        pool_stories=pool_stories,
        candidates=len(rerank.scores) if rerank else 0,
        reranked=rerank.reranked if rerank else False,
        rerank_error=rerank.error if rerank else "not run",
        rerank_unscored=rerank.unscored if rerank else 0,
        rerank_excluded=rerank.excluded if rerank else 0,
        embedder=embedder,
        model_client=model_client,
        spotlight=spotlight,
        x_pick=x_pick,
    )
