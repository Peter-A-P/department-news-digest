"""A Bluesky pick is shown in full only while it exists, and only for thirty days."""

from __future__ import annotations

from datetime import timedelta

import httpx

from clippings.assemble.deletions import updated_pick
from clippings.assemble.digest import Spotlight
from clippings.assemble.render import html_page, markdown
from clippings.sources.bluesky import post_exists
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
    )
    return base.model_copy(update=changes)


def test_the_full_post_is_behind_a_button_on_the_page() -> None:
    page = html_page(digest().model_copy(update={"spotlight": pick()}))
    assert "Show full post" in page and "Second line." in page


def test_a_deleted_post_s_words_are_removed_and_the_page_says_so() -> None:
    day = digest().model_copy(update={"spotlight": pick(), "generated_at": NOW})
    gone = updated_pick(day, NOW + timedelta(days=1), lambda url: False)
    assert gone is not None and gone.spotlight is not None and gone.spotlight.deleted
    page, text = html_page(gone), markdown(gone)
    assert "deleted by its author" in page and "first words" not in page
    assert "deleted by its author" in text and "first words" not in text


def test_an_unknown_answer_changes_nothing() -> None:
    day = digest().model_copy(update={"spotlight": pick(), "generated_at": NOW})
    assert updated_pick(day, NOW + timedelta(days=1), lambda url: None) is None
    assert updated_pick(day, NOW + timedelta(days=1), lambda url: True) is None


def test_after_thirty_days_only_the_quote_is_kept() -> None:
    day = digest().model_copy(update={"spotlight": pick(), "generated_at": NOW})
    aged = updated_pick(day, NOW + timedelta(days=31), lambda url: True)
    assert aged is not None and aged.spotlight is not None
    assert aged.spotlight.full_text == "" and aged.spotlight.quote
    assert "Show full post" not in html_page(aged)


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
