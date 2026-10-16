"""The day's most discussed X post that the audience's rubric would want: one, or none.

The same judgement as the Bluesky pick (rank/spotlight.py), from a different pool: X's ten
most relevant posts of the last day for the audience's query, read through the paid API
(sources/x.py). Posts with fewer than `MIN_LIKES` likes are not a conversation and are not
shown to the model. One model call scores the rest against the rubric with the rules for
posts; the pick is the most engaged post scored at least 2. Only then is its author looked
up, the one user read a day, because X's display rules require the author's name, handle
and picture beside the post.

Every request is logged to the fetch log, which is what the monthly cap is checked against
and what the "Sources checked" panel shows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from clippings.assemble.digest import Digest, XPick, call_cost
from clippings.config.audience import Audience
from clippings.constants import X_POST_SHOWN_HOURS
from clippings.gateway import ModelClient, ModelReply, Purpose
from clippings.ingest.store import Store
from clippings.rank.spotlight import MIN_LIKES, PostLine, considered, score_posts
from clippings.sources.base import FetchContext
from clippings.sources.x import (
    AUTHOR_ORIGIN,
    MONTHLY_CAP_USD,
    PRICE_POST_USD,
    PRICE_USER_USD,
    SOURCE_KEY,
    XAuthor,
    XPost,
    XUnavailable,
    author,
    headroom,
    link_keys,
    post_url,
    search,
    spent_usd,
)


@dataclass(frozen=True)
class XChoice:
    """The post chosen and its author, or why there is none, and what it cost."""

    post: XPost | None = None
    author: XAuthor | None = None
    score: int | None = None
    reason: str = ""
    reply: ModelReply | None = None
    # This run's reads at X's list price, for the run log and the page.
    reads_usd: float = 0.0
    detail: str = ""
    # Every post the model scored, for the run log (rank/spotlight.considered).
    considered: tuple[str, ...] = ()


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def pick_x(
    audience: Audience,
    context: FetchContext,
    store: Store,
    client: ModelClient,
    *,
    run_id: str,
    covered: frozenset[str] = frozenset(),
) -> XChoice:
    """`covered` is the day's digest's sources as `link_keys`: a post that links to one of
    them repeats a story the reader already has, and is not a candidate."""
    config = audience.sources.x
    if not config.searches:
        return XChoice(detail="off for this audience")

    def log(origin: str, items: int, ok: bool, detail: str = "") -> None:
        store.log_fetch(
            run_id=run_id,
            audience_id=audience.id,
            source_key=SOURCE_KEY,
            origin=origin,
            started_at=context.now,
            items=items,
            ok=ok,
            detail=detail,
        )

    if not context.permitted(SOURCE_KEY):
        for query, _ in config.searches:
            refused = context.refusal(SOURCE_KEY, query).detail
            log(query, 0, False, refused)
        return XChoice(detail=refused)
    spent = spent_usd(store.reads_since(SOURCE_KEY, month_start(context.now)))
    if not headroom(spent, config.reads):
        detail = f"refused: the monthly cap of US${MONTHLY_CAP_USD:.2f} is reached"
        for query, _ in config.searches:
            log(query, 0, False, detail)
        return XChoice(detail=detail)
    # People first, then the subject search; a post both find is read once here, though X
    # bills it in each search that returns it.
    by_id: dict[str, XPost] = {}
    read = 0
    failed = ""
    for query, count in config.searches:
        try:
            found, billed_posts = search(audience, context, query, count)
        except XUnavailable as exc:
            log(query, 0, False, str(exc))
            failed = str(exc)
            continue
        log(query, billed_posts, True)
        read += billed_posts
        for post in found:
            by_id.setdefault(post.id, post)
    if failed and not by_id:
        return XChoice(detail=failed)
    posts = list(by_id.values())
    cost = read * PRICE_POST_USD

    new = [post for post in posts if not link_keys(post.links) & covered]
    eligible = sorted(
        (post for post in new if post.likes >= MIN_LIKES),
        key=lambda post: (-post.engagement, post.id),
    )
    if not eligible:
        dropped = len(posts) - len(new)
        repeats = f", {dropped} linked a story in the digest" if dropped else ""
        return XChoice(reads_usd=cost, detail=f"no new post with {MIN_LIKES} likes{repeats}")
    lines = [
        PostLine(f"user {post.author_id}", post.likes, post.replies, post.text) for post in eligible
    ]
    scored = score_posts(audience, lines, client, run_id=run_id)
    # The status link works without the author's handle, which would cost a user read each.
    seen = considered(
        [f"https://x.com/i/status/{post.id}" for post in eligible],
        [post.likes for post in eligible],
        scored,
    )
    index = scored.first()
    if index is None:
        detail = scored.error or f"no post the rubric wants, of {len(eligible)} scored"
        return XChoice(reply=scored.reply, reads_usd=cost, detail=detail, considered=seen)
    chosen = eligible[index]
    score, reason = scored.scores[index]
    try:
        who = author(context, chosen.author_id)
    except XUnavailable as exc:
        # Without its author the post cannot be shown the way X requires, so it is not shown.
        log(AUTHOR_ORIGIN, 0, False, str(exc))
        return XChoice(reply=scored.reply, reads_usd=cost, detail=str(exc))
    log(AUTHOR_ORIGIN, 1, True)
    return XChoice(chosen, who, score, reason, scored.reply, cost + PRICE_USER_USD, considered=seen)


def shown(chosen: XChoice | None) -> XPick | None:
    """The pick as the digest keeps it, or None when there is no pick."""
    if chosen is None or chosen.post is None or chosen.author is None or chosen.score is None:
        return None
    post, who = chosen.post, chosen.author
    return XPick(
        post_id=post.id,
        url=post_url(who.username, post.id),
        username=who.username,
        name=who.name,
        image_url=who.image_url,
        text=post.text,
        posted_at=post.created_at,
        likes=post.likes,
        reposts=post.reposts,
        replies=post.replies,
        rubric_score=chosen.score,
        reason=chosen.reason,
        reads_usd=chosen.reads_usd,
    )


def still_showing(digest: Digest, now: datetime) -> bool:
    """Whether a digest is young enough that an X pick added now would still be shown."""
    return now - digest.generated_at < timedelta(hours=X_POST_SHOWN_HOURS)


def added_to(digest: Digest, chosen: XChoice) -> Digest:
    """A published digest with the X pick added after the fact (`clippings x-pick`).

    The model call is added to the digest's costs. `generated_at` is kept, so the words
    still go with the next daily run, as if the pick had been made with the digest.
    """
    calls = digest.calls
    if chosen.reply is not None:
        calls = (*calls, call_cost(Purpose.SPOTLIGHT, "", chosen.reply))
    return digest.model_copy(update={"x_pick": shown(chosen), "calls": calls})
