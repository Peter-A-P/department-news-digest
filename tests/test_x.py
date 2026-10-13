"""The X pick: refused unless allowed, capped before a request, shown whole, gone after a day."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from clippings.assemble.deletions import expire_x_picks, expired_x_pick
from clippings.assemble.digest import XPick
from clippings.assemble.publish import LocalSite
from clippings.assemble.render import html_page, markdown
from clippings.config.audience import Audience, XSource
from clippings.constants import X_POST_SHOWN_HOURS
from clippings.gateway import ScriptedClient
from clippings.ingest.store import Store
from clippings.rank.x_pick import month_start, pick_x, shown
from clippings.serve.app import SECURITY_HEADERS
from clippings.sources.base import FetchContext
from clippings.sources.robots import AllowAll
from clippings.sources.x import (
    AUTHOR_ORIGIN,
    MONTHLY_CAP_USD,
    PRICE_POST_USD,
    PRICE_USER_USD,
    parse_search,
    query_for,
)
from tests.conftest import NOW, gate
from tests.test_delivery import digest

QUERY = '"city council" OR budget'


@pytest.fixture
def on(audience: Audience) -> Audience:
    return audience.model_copy(
        update={"sources": audience.sources.model_copy(update={"x": XSource(query=QUERY)})}
    )


def raw_post(post_id: str, likes: int, text: str = "A post about the vote") -> dict[str, Any]:
    return {
        "id": post_id,
        "author_id": f"u{post_id}",
        "text": text,
        "created_at": "2026-09-12T10:00:00.000Z",
        "public_metrics": {"like_count": likes, "retweet_count": 2, "reply_count": 1},
    }


def x_api(posts: list[dict[str, Any]], user_status: int = 200) -> Callable[..., httpx.Response]:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer token"
        if request.url.path == "/2/tweets/search/recent":
            return httpx.Response(200, json={"data": posts, "meta": {"result_count": len(posts)}})
        author_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            user_status,
            json={
                "data": {
                    "id": author_id,
                    "username": f"handle_{author_id}",
                    "name": "Ana Author",
                    "profile_image_url": "https://pbs.twimg.com/profile_images/1/a_normal.jpg",
                }
            },
        )

    return answer


def context_for(
    answer: Callable[[httpx.Request], httpx.Response],
    *,
    status: str = "allowed",
    secrets: dict[str, str] | None = None,
) -> tuple[FetchContext, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    context = FetchContext(
        client=client,
        gate=gate(x=status),
        robots=AllowAll(),
        now=NOW,
        secrets={"X_BEARER_TOKEN": "token"} if secrets is None else secrets,
    )
    return context, seen


def scores(*lines: tuple[int, str]) -> ScriptedClient:
    reply = "\n".join(
        f'{{"id": "c{n:02d}", "score": {score}, "reason": "{reason}"}}'
        for n, (score, reason) in enumerate(lines, start=1)
    )
    return ScriptedClient(lambda call: reply)


def never(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"no request should have been sent: {request.url}")


# -- the adapter ------------------------------------------------------------------------------


def test_the_query_leaves_out_reposts_and_replies_and_keeps_the_language(on: Audience) -> None:
    assert query_for(on) == f"({QUERY}) -is:retweet -is:reply lang:en"


def test_a_long_post_is_read_whole_unescaped_and_a_sensitive_one_is_skipped() -> None:
    long = raw_post("1", 50, text="Cut short by X")
    long["note_tweet"] = {"text": "The whole long post &amp; the rest of it"}
    sensitive = raw_post("2", 900) | {"possibly_sensitive": True}
    posts = parse_search({"data": [long, sensitive]})
    assert [post.id for post in posts] == ["1"]
    assert posts[0].text == "The whole long post & the rest of it"
    assert posts[0].engagement == 53


# -- the pick ---------------------------------------------------------------------------------


def test_nothing_is_requested_until_the_terms_are_allowed(on: Audience, store: Store) -> None:
    context, _ = context_for(never, status="pending")
    chosen = pick_x(on, context, store, scores(), run_id="r")
    assert chosen.post is None and chosen.detail.startswith("refused")
    assert store.last_fetches(on.id)[("x", QUERY)].ok is False


def test_without_a_token_it_is_unavailable_and_nothing_is_sent(on: Audience, store: Store) -> None:
    context, _ = context_for(never, secrets={})
    chosen = pick_x(on, context, store, scores(), run_id="r")
    assert chosen.post is None and "X_BEARER_TOKEN" in chosen.detail


def test_the_monthly_cap_refuses_before_any_request(on: Audience, store: Store) -> None:
    reads = int(MONTHLY_CAP_USD / PRICE_POST_USD) - 5
    store.log_fetch("old", on.id, "x", QUERY, month_start(NOW), reads, True)
    context, _ = context_for(never)
    chosen = pick_x(on, context, store, scores(), run_id="r")
    assert chosen.post is None and "monthly cap" in chosen.detail


def test_last_month_s_reads_do_not_count_against_this_month(on: Audience, store: Store) -> None:
    store.log_fetch("old", on.id, "x", QUERY, month_start(NOW) - timedelta(days=1), 5000, True)
    context, seen = context_for(x_api([raw_post("1", 50)]))
    pick_x(on, context, store, scores((2, "r")), run_id="r")
    assert seen


def test_no_credits_is_reported_not_raised(on: Audience, store: Store) -> None:
    context, _ = context_for(lambda request: httpx.Response(402, json={}))
    chosen = pick_x(on, context, store, scores(), run_id="r")
    assert chosen.post is None and "402" in chosen.detail


def test_the_pick_is_the_most_engaged_post_the_rubric_wants_and_one_author_is_read(
    on: Audience, store: Store
) -> None:
    posts = [raw_post("quiet", 3), raw_post("joke", 900), raw_post("good", 80), raw_post("ok", 40)]
    context, seen = context_for(x_api(posts))
    client = scores((0, "a joke"), (2, "council vote"), (3, "also fine"))
    chosen = pick_x(on, context, store, client, run_id="r")

    assert chosen.post is not None and chosen.post.id == "good"
    assert chosen.author is not None and chosen.author.username == "handle_ugood"
    # The model saw only posts with enough likes, most engaged first; a three-like post is
    # not a conversation.
    assert "quiet" not in client.calls[0].user and client.calls[0].user.count(" likes, ") == 3
    # One search and one author lookup: no user is read for a post that was not picked.
    assert [request.url.path for request in seen] == [
        "/2/tweets/search/recent",
        "/2/users/ugood",
    ]
    assert chosen.reads_usd == pytest.approx(4 * PRICE_POST_USD + PRICE_USER_USD)
    assert store.reads_since("x", month_start(NOW)) == {QUERY: 4, AUTHOR_ORIGIN: 1}


def test_a_post_whose_author_cannot_be_read_is_not_shown(on: Audience, store: Store) -> None:
    context, _ = context_for(x_api([raw_post("1", 50)], user_status=503))
    chosen = pick_x(on, context, store, scores((2, "r")), run_id="r")
    assert chosen.post is None and chosen.reply is not None


def test_x_is_off_unless_the_audience_has_a_query(audience: Audience, store: Store) -> None:
    context, _ = context_for(never)
    assert pick_x(audience, context, store, scores(), run_id="r").detail == "off for this audience"
    assert "x" not in audience.terms_keys()
    with pytest.raises(ValidationError):
        XSource(query="a" * 461)
    with pytest.raises(ValidationError):
        XSource(query="a", candidates=5)


# -- the page ---------------------------------------------------------------------------------


def x_pick(**changes: object) -> XPick:
    base = XPick(
        post_id="123",
        url="https://x.com/ana/status/123",
        username="ana",
        name="Ana Author",
        image_url="https://pbs.twimg.com/profile_images/1/a_normal.jpg",
        text='Line one with <b>markup</b> & "quotes"\nLine two, and well past twenty-five '
        + " ".join(f"w{n}" for n in range(40)),
        posted_at=NOW,
        likes=120,
        reposts=7,
        replies=9,
        rubric_score=2,
        reason="Council vote on the budget",
        reads_usd=0.06,
    )
    return base.model_copy(update=changes)


def test_the_post_is_shown_whole_the_way_x_asks() -> None:
    pick = x_pick()
    page = html_page(digest().model_copy(update={"x_pick": pick}))
    assert "Most discussed on X" in page
    # The whole text, unaltered but escaped: no cut at twenty-five words.
    assert "Line one with &lt;b&gt;markup&lt;/b&gt; &amp; &quot;quotes&quot;" in page
    assert "w39" in page and "<b>markup</b>" not in page
    # Name and handle above the text, both to the profile; the picture; the logo; the
    # timestamp to the post; the three actions.
    name, handle, text = page.index("Ana Author"), page.index("@ana"), page.index("Line one")
    assert name < text and handle < text
    assert page.count('href="https://x.com/ana"') == 3
    assert 'src="https://pbs.twimg.com/profile_images/1/a_normal.jpg"' in page
    assert 'aria-label="View on X"' in page
    assert re.search(r'<a href="https://x.com/ana/status/123">2026-09-12 12:00 UTC</a>', page)
    for intent in ("tweet?in_reply_to=123", "retweet?tweet_id=123", "like?tweet_id=123"):
        assert f"https://x.com/intent/{intent}" in page


def test_the_markdown_and_draft_link_to_the_post_rather_than_show_it() -> None:
    text = markdown(digest().model_copy(update={"x_pick": x_pick()}))
    assert "[A post by @ana](https://x.com/ana/status/123)" in text
    assert "Line one" not in text


def test_the_only_outside_images_the_policy_allows_are_the_platforms_own() -> None:
    policy = dict(SECURITY_HEADERS)["Content-Security-Policy"]
    assert "img-src 'self' https://pbs.twimg.com https://cdn.bsky.app" in policy
    assert policy.count("https://") == 2 and "script-src" not in policy


# -- after its day ----------------------------------------------------------------------------


def test_the_words_stay_for_the_day_and_go_by_the_next_run() -> None:
    day = digest().model_copy(update={"x_pick": x_pick(), "generated_at": NOW})
    early = NOW + timedelta(hours=X_POST_SHOWN_HOURS) - timedelta(minutes=1)
    assert expired_x_pick(day, early) is None
    gone = expired_x_pick(day, NOW + timedelta(hours=X_POST_SHOWN_HOURS))
    assert gone is not None and gone.x_pick is not None and gone.x_pick.expired
    assert gone.x_pick.text == gone.x_pick.name == gone.x_pick.image_url == ""
    page = html_page(gone)
    assert "Line one" not in page and "Ana Author" not in page and "pbs.twimg.com" not in page
    assert "https://x.com/ana/status/123" in page and "only on the day" in page


def test_every_stored_run_and_the_page_lose_the_words(
    audience: Audience, store: Store, tmp_path: Path
) -> None:
    first = digest().model_copy(update={"x_pick": x_pick(), "run_id": "r1"})
    rerun = first.model_copy(update={"run_id": "r2", "generated_at": NOW + timedelta(hours=1)})
    store.save_digest(first)
    store.save_digest(rerun)
    site = LocalSite(tmp_path)
    later = NOW + timedelta(days=1)

    changed = expire_x_picks(store, site, [audience], later, {})

    assert changed == [f"{audience.id}/{first.day}"]
    runs = store.digest_runs(audience.id, first.day)
    assert len(runs) == 2 and all(run.x_pick and run.x_pick.expired for run in runs)
    for name in ("index.html", "digest.md", "digest.eml"):
        written = site.read(f"{audience.id}/{first.day}/{name}")
        assert written is not None and b"Line one" not in written
    # Nothing left to do on the run after.
    assert expire_x_picks(store, site, [audience], later + timedelta(days=1), {}) == []


def test_the_digest_carries_the_pick_with_its_author_and_cost(on: Audience, store: Store) -> None:
    context, _ = context_for(x_api([raw_post("7", 50)]))
    chosen = pick_x(on, context, store, scores((3, "the vote")), run_id="r")
    kept = shown(chosen)
    assert kept is not None and kept.url == "https://x.com/handle_u7/status/7"
    assert kept.name == "Ana Author" and kept.rubric_score == 3 and kept.reads_usd > 0
    assert shown(None) is None


def test_a_pick_added_later_keeps_the_digest_s_day_and_counts_its_call(
    on: Audience, store: Store
) -> None:
    from clippings.gateway import ModelReply
    from clippings.rank.x_pick import added_to, still_showing

    context, _ = context_for(x_api([raw_post("7", 50)]))
    reply = ModelReply(text='{"id": "c01", "score": 2, "reason": "r"}', model="m", cost_usd=0.001)
    chosen = pick_x(on, context, store, ScriptedClient(lambda call: reply.text), run_id="r")
    chosen = chosen.__class__(**{**chosen.__dict__, "reply": reply})
    published = digest().model_copy(update={"generated_at": NOW})

    updated = added_to(published, chosen)
    assert updated.x_pick is not None and updated.generated_at == NOW
    assert len(updated.calls) == len(published.calls) + 1
    assert updated.cost_usd == pytest.approx(published.cost_usd + 0.001)
    # The words still go with the next morning's run, as if picked with the digest.
    assert expired_x_pick(updated, NOW + timedelta(hours=X_POST_SHOWN_HOURS)) is not None
    assert still_showing(published, NOW + timedelta(hours=X_POST_SHOWN_HOURS - 1))
    assert not still_showing(published, NOW + timedelta(hours=X_POST_SHOWN_HOURS))


def test_a_post_sharing_a_story_already_in_the_digest_is_not_a_candidate(
    on: Audience, store: Store
) -> None:
    from clippings.sources.x import link_keys

    shared = raw_post("shared", 900) | {
        "entities": {"urls": [{"expanded_url": "https://www.gov.example/a?utm_source=x"}]}
    }
    photo = raw_post("photo", 60) | {
        "entities": {"urls": [{"expanded_url": "https://x.com/a/status/1/photo/1"}]}
    }
    assert parse_search({"data": [photo]})[0].links == ()
    context, _ = context_for(x_api([shared, photo]))
    client = scores((2, "new"))
    covered = link_keys(["https://gov.example/a"])
    chosen = pick_x(on, context, store, client, run_id="r", covered=covered)
    # The story's own link, however X wrote it, takes the busier post out of the running.
    assert chosen.post is not None and chosen.post.id == "photo"
    assert "shared" not in client.calls[0].user and "900 likes" not in client.calls[0].user


def test_when_every_busy_post_repeats_the_digest_there_is_no_pick(
    on: Audience, store: Store
) -> None:
    from clippings.sources.x import link_keys

    shared = raw_post("shared", 900) | {
        "entities": {"urls": [{"unwound_url": "https://gov.example/a"}]}
    }
    context, _ = context_for(x_api([shared, raw_post("quiet", 2)]))
    covered = link_keys(["https://gov.example/a"])
    chosen = pick_x(on, context, store, scores(), run_id="r", covered=covered)
    assert chosen.post is None and "1 linked a story in the digest" in chosen.detail
