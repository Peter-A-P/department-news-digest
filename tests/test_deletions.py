"""A Bluesky pick is shown in full only while it exists, and only for thirty days."""

from __future__ import annotations

from datetime import timedelta

import httpx

from clippings.assemble.deletions import updated_pick
from clippings.assemble.digest import Spotlight
from clippings.assemble.render import html_page, markdown
from clippings.sources.bluesky import PostView, post_exists
from tests.conftest import NOW
from tests.test_delivery import digest

URL = "https://bsky.app/profile/a.bsky.social/post/3abc"


def pick(**changes: object) -> Spotlight:
    base = Spotlight(
        item_id="p",
        url=URL,
        author="a.bsky.social",
        quote="The first words of a long post",
        likes=99,
        replies=3,
        posted_at=NOW,
        rubric_score=2,
        reason="r",
        full_text="The first words of a long post, and then the rest of it.\nSecond line.",
        name="Ana Author",
        image_url="https://cdn.bsky.app/img/avatar/plain/did:plc:x/abc@jpeg",
        reposts=4,
    )
    return base.model_copy(update=changes)


def test_the_whole_post_is_shown_as_a_card_with_its_author() -> None:
    page = html_page(digest().model_copy(update={"spotlights": (pick(),)}))
    assert "Second line." in page and "Show full post" not in page
    name, text = page.index("Ana Author"), page.index("The first words")
    assert name < text and 'href="https://bsky.app/profile/a.bsky.social"' in page
    assert 'src="https://cdn.bsky.app/img/avatar/plain/did:plc:x/abc@jpeg"' in page
    assert 'aria-label="View on Bluesky"' in page and "99 likes, 4 reposts, 3 replies" in page


def test_a_pick_from_before_the_card_shows_its_handle_alone() -> None:
    old = pick(name="", image_url="", reposts=0)
    page = html_page(digest().model_copy(update={"spotlights": (old,)}))
    assert (
        "@a.bsky.social" in page
        and 'class="pc-avatar"' not in page
        and 'class="pc-name"' not in page
    )


def test_a_deleted_post_s_words_are_removed_and_the_page_says_so() -> None:
    day = digest().model_copy(update={"spotlights": (pick(),), "generated_at": NOW})
    gone = updated_pick(day, NOW + timedelta(days=1), lambda url: PostView(False))
    assert gone is not None and gone.spotlights and gone.spotlights[0].deleted
    page, text = html_page(gone), markdown(gone)
    assert "deleted by its author" in page and "first words" not in page
    assert "Ana Author" not in page and "cdn.bsky.app" not in page
    assert "deleted by its author" in text and "first words" not in text


def test_an_unknown_answer_changes_nothing() -> None:
    day = digest().model_copy(update={"spotlights": (pick(),), "generated_at": NOW})
    assert updated_pick(day, NOW + timedelta(days=1), lambda url: PostView(None)) is None
    assert updated_pick(day, NOW + timedelta(days=1), lambda url: PostView(True)) is None


def test_after_thirty_days_only_the_quote_is_kept() -> None:
    day = digest().model_copy(update={"spotlights": (pick(),), "generated_at": NOW})
    aged = updated_pick(day, NOW + timedelta(days=31), lambda url: PostView(True))
    assert aged is not None and aged.spotlights
    assert aged.spotlights[0].full_text == "" and aged.spotlights[0].quote
    page = html_page(aged)
    assert "Second line." not in page and "The first words" in page
    assert "Ana Author" not in page and "cdn.bsky.app" not in page


def respond(*answers: httpx.Response) -> httpx.Client:
    queue = list(answers)
    return httpx.Client(transport=httpx.MockTransport(lambda request: queue.pop(0)))


def test_post_exists_reads_bluesky_s_public_api() -> None:
    resolved = httpx.Response(200, json={"did": "did:plc:x"})
    assert post_exists(respond(resolved, httpx.Response(200, json={"posts": [{}]})), URL)
    assert post_exists(respond(resolved, httpx.Response(200, json={"posts": []})), URL) is False
    # A handle that no longer resolves: the account is gone or renamed.
    assert post_exists(respond(httpx.Response(400, json={})), URL) is False
    # A server error is not evidence of deletion.
    assert post_exists(respond(httpx.Response(503)), URL) is None


def test_the_author_s_name_and_picture_come_from_bluesky_s_public_api() -> None:
    from clippings.sources.bluesky import post_view

    resolved = httpx.Response(200, json={"did": "did:plc:x"})
    post = {
        "author": {"displayName": " Ana Author ", "avatar": "https://cdn.bsky.app/img/a.jpg"},
        "likeCount": 9,
        "repostCount": 2,
        "replyCount": 1,
    }
    view = post_view(respond(resolved, httpx.Response(200, json={"posts": [post]})), URL)
    assert view.found and view.name == "Ana Author" and view.reposts == 2
    assert view.image_url == "https://cdn.bsky.app/img/a.jpg"
    # A picture from anywhere else is not shown: the page's policy would refuse it anyway.
    elsewhere = {**post, "author": {"avatar": "https://tracker.example/a.jpg"}}
    view = post_view(respond(resolved, httpx.Response(200, json={"posts": [elsewhere]})), URL)
    assert view.image_url == "" and view.name == ""


def test_a_pick_from_before_the_card_gains_its_author_on_the_next_check() -> None:
    old = pick(name="", image_url="", reposts=0)
    day = digest().model_copy(update={"spotlights": (old,), "generated_at": NOW})
    seen = PostView(True, name="Ana Author", image_url="https://cdn.bsky.app/a.jpg", reposts=5)
    named = updated_pick(day, NOW + timedelta(days=1), lambda url: seen)
    assert named is not None and named.spotlights
    assert named.spotlights[0].name == "Ana Author" and named.spotlights[0].reposts == 5
    # Once it has them, the next check changes nothing.
    assert updated_pick(named, NOW + timedelta(days=2), lambda url: seen) is None
