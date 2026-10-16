"""The day's most discussed Bluesky post that the audience's rubric would want: one, or none.

Posts are not stories (PLAN.md section 2.3): inside a news story a post is commentary, and a
story of posts alone is never one of the digest's stories. This is the one place a post with
no news story under it reaches the digest, as its own section below the stories, marked as a
post and never in a story's slot (Peter, 2026-10-10).

The candidates are posts that joined no news story, with at least `MIN_LIKES` likes, most
engaged first. One model call scores them against the rubric, with a rule set for posts on
top: no jokes, insults, personal attacks, posts about private individuals, or posts that are
only a link. The pick is the most engaged post the model scored at least 2. Nothing the model
writes is shown as fact: the page shows the post's own words, cut to twenty-five, its
counts and a link, and the model's twelve-word reason as the reason it was picked.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from clippings.config.audience import Audience
from clippings.gateway import ModelCall, ModelCallFailed, ModelClient, ModelReply, Purpose
from clippings.models import Cluster, Item
from clippings.rank.rerank import local_ids, parse_scores

# Below this a post is one person's aside, not a conversation. Measured on 2026-10-10: the
# post-only stories that day ran from 0 to 171 likes, and the ones a reader would call a
# conversation started in the tens.
MIN_LIKES = 10
# How many posts the model is shown: the most engaged, so the call stays a few hundred
# tokens. Sixteen since the people lists (2026-10-13): a reporter's or researcher's most
# liked post of the day is often off the audience's topic, and eight could all be that.
CANDIDATES = 16
MIN_SCORE = 2
QUOTE_WORDS = 25
# Eight short lines, plus Haiku 5.5's thinking, which counts against the limit.
MAX_TOKENS = 4000

SYSTEM = """You judge public social media posts for one audience's morning digest.

You are given the audience, its rubric (what counts as relevant and what does not), and a
numbered list of posts. Each post is commentary, not reporting: judge whether what it is
about is something the rubric says this audience should know, and whether the post itself is
worth a busy reader's attention. Score 0 for jokes, insults, personal attacks, posts about a
private individual, posts that are only a link or a headline with no comment, promotion, and
anything the rubric excludes.

Score every post:
3 = the audience should see this conversation today
2 = relevant and worth showing
1 = marginal
0 = not relevant, or excluded by the rules above

Answer with one JSON object per line and nothing else, for example:
{"id": "c01", "score": 2, "reason": "at most twelve words"}"""


@dataclass(frozen=True)
class Pick:
    """The post chosen, or None, and what the call cost."""

    item: Item | None
    score: int | None
    reason: str
    reply: ModelReply | None
    error: str = ""
    # Every post the model scored, for the run log: why a day has no pick is then on record.
    considered: tuple[str, ...] = ()


def engagement(item: Item) -> int:
    return (item.score or 0) + (item.comments or 0)


def candidates(clusters: Sequence[Cluster], items: Mapping[str, Item]) -> list[Item]:
    """Bluesky posts that joined no news story, popular enough, most engaged first."""
    posts = []
    for cluster in clusters:
        members = [items[item_id] for item_id in cluster.item_ids if item_id in items]
        if not members or any(item.source_kind != "bluesky" for item in members):
            continue
        best = max(members, key=lambda item: (engagement(item), item.id))
        if (best.score or 0) >= MIN_LIKES:
            posts.append(best)
    posts.sort(key=lambda item: (-engagement(item), item.id))
    return posts[:CANDIDATES]


@dataclass(frozen=True)
class PostLine:
    """What the model is shown of one post, from Bluesky or from X (rank/x_pick.py)."""

    author: str
    likes: int
    replies: int
    text: str


def line_for(post: Item) -> PostLine:
    return PostLine(post.author or "", post.score or 0, post.comments or 0, post.summary)


def build_call(audience: Audience, posts: Sequence[PostLine]) -> ModelCall:
    ids = local_ids(len(posts))
    lines = "\n".join(
        f"{ids[index]} | @{post.author} | {post.likes} likes, {post.replies} replies"
        f" | {' '.join(post.text.split())[:400]}"
        for index, post in enumerate(posts)
    )
    user = (
        f"Audience: {audience.name}\n"
        f"About: {audience.description.strip()}\n\n"
        f"Rubric: {audience.rubric.strip()}\n\n"
        f"Posts ({len(posts)}), one per line as id | author | engagement | text:\n{lines}"
    )
    return ModelCall(
        purpose=Purpose.SPOTLIGHT,
        audience_id=audience.id,
        system=SYSTEM,
        user=user,
        max_tokens=MAX_TOKENS,
    )


@dataclass(frozen=True)
class Scored:
    """The model's score and reason for each post, in the order given, and the call."""

    scores: tuple[tuple[int, str], ...]
    reply: ModelReply | None
    error: str = ""

    def first(self, minimum: int = MIN_SCORE) -> int | None:
        """The index of the first post scored at least `minimum`: the most engaged, when the
        posts were given most engaged first."""
        for index, (score, _) in enumerate(self.scores):
            if score >= minimum:
                return index
        return None


def considered(labels: Sequence[str], likes: Sequence[int], scored: Scored) -> tuple[str, ...]:
    """One run-log line per scored post: where it is, its likes, the model's score and
    reason. Not the post's text, which the log has no business keeping."""
    return tuple(
        f"{label}, {count} likes: {score} {reason}".rstrip()
        for label, count, (score, reason) in zip(labels, likes, scored.scores, strict=False)
    )


def score_posts(
    audience: Audience, posts: Sequence[PostLine], client: ModelClient, *, run_id: str
) -> Scored:
    """One call that scores every post against the rubric. A failed call scores nothing."""
    ids = local_ids(len(posts))
    try:
        reply = client.complete(build_call(audience, posts), run_id=run_id)
    except ModelCallFailed as exc:
        return Scored((), None, error=str(exc))
    scores = parse_scores(reply.text, set(ids))
    return Scored(tuple(scores.get(local_id, (0, "")) for local_id in ids), reply)


def pick(
    audience: Audience,
    clusters: Sequence[Cluster],
    items: Mapping[str, Item],
    client: ModelClient,
    *,
    run_id: str,
) -> Pick:
    posts = candidates(clusters, items)
    if not posts:
        return Pick(None, None, "", None)
    scored = score_posts(audience, [line_for(post) for post in posts], client, run_id=run_id)
    if scored.reply is None:
        # No pick is the safe answer: the section is simply left out.
        return Pick(None, None, "", None, error=scored.error)
    seen = considered([post.url for post in posts], [post.score or 0 for post in posts], scored)
    chosen = scored.first()
    if chosen is None:
        return Pick(None, None, "", scored.reply, considered=seen)
    score, reason = scored.scores[chosen]
    return Pick(posts[chosen], score, reason, scored.reply, considered=seen)


def quote(text: str, words: int = QUOTE_WORDS) -> str:
    """The post's own words, cut at a word boundary: verbatim by construction."""
    parts = " ".join(text.split()).split(" ")
    return " ".join(parts[:words]) + (" ..." if len(parts) > words else "")
