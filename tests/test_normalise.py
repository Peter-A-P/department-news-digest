"""Normalisation: canonical URLs, the dedup key, and the blocked-source rule."""

from __future__ import annotations

from clippings.config.audience import Audience
from clippings.ingest.normalise import (
    canonical_url,
    dedup_key,
    domain_of,
    is_blocked,
    is_trusted,
    normalise,
)
from clippings.models import Item
from tests.conftest import raw


def test_tracking_parameters_are_stripped_but_real_ones_are_kept() -> None:
    url = "https://news.example/story?id=42&utm_source=newsletter&utm_medium=email&fbclid=abc"
    assert canonical_url(url) == "https://news.example/story?id=42"


def test_the_fragment_is_dropped() -> None:
    assert canonical_url("https://news.example/story#section-3") == "https://news.example/story"


def test_a_trailing_slash_is_dropped_but_the_root_keeps_its_own() -> None:
    assert canonical_url("https://news.example/story/") == "https://news.example/story"
    assert canonical_url("https://news.example/") == "https://news.example/"


def test_the_dedup_key_collapses_scheme_and_www_but_the_link_does_not() -> None:
    """A reader gets the link as published; deduplication is stricter than display."""
    published = "http://www.news.example/story"
    assert canonical_url(published) == "http://www.news.example/story"
    assert dedup_key(published) == "https://news.example/story"
    assert dedup_key("https://news.example/story") == dedup_key(published)


def test_the_same_article_from_two_sources_gets_one_id() -> None:
    from_feed = "https://www.news.example/story?utm_source=rss"
    from_gdelt = "http://news.example/story"
    assert Item.id_for(dedup_key(from_feed)) == Item.id_for(dedup_key(from_gdelt))


def test_the_domain_drops_www() -> None:
    assert domain_of("https://www.news.example/story") == "news.example"


def test_blocking_covers_subdomains(audience: Audience) -> None:
    blocking = audience.model_copy(update={"blocked_sources": ("example.org",)})
    assert is_blocked("news.example.org", blocking) is True
    assert is_blocked("example.org", blocking) is True
    assert is_blocked("notexample.org", blocking) is False


def test_trust_covers_subdomains(audience: Audience) -> None:
    trusting = audience.model_copy(update={"trusted_sources": ("ontario.ca",)})
    assert is_trusted("news.ontario.ca", trusting) is True


def test_a_blocked_source_never_becomes_an_item(audience: Audience) -> None:
    """The check is here, not at render time: a blocked source never reaches the store."""
    assert normalise(raw("https://blocked.example/story"), audience) is None


def test_a_blocked_subdomain_never_becomes_an_item(audience: Audience) -> None:
    assert normalise(raw("https://www.news.blocked.example/story"), audience) is None


def test_an_item_from_a_permitted_source_is_normalised(audience: Audience) -> None:
    one = normalise(raw("https://gov.example/story?utm_source=x", "  A   headline "), audience)
    assert one is not None
    assert one.url == "https://gov.example/story"
    assert one.title == "A headline"
    assert one.domain == "gov.example"


def test_html_in_a_feed_summary_becomes_plain_text(audience: Audience) -> None:
    one = normalise(
        raw("https://gov.example/story", summary="<p>Two  <b>words</b></p>\n"), audience
    )
    assert one is not None
    assert one.summary == "Two words"


def test_an_item_with_no_title_is_dropped(audience: Audience) -> None:
    assert normalise(raw("https://gov.example/story", title="  "), audience) is None


def test_a_non_http_url_is_dropped(audience: Audience) -> None:
    assert normalise(raw("mailto:someone@example.org"), audience) is None
    assert normalise(raw("ftp://files.example/story"), audience) is None


def test_an_item_with_no_date_is_dated_at_the_fetch_time(audience: Audience) -> None:
    """Common in the wild. The fetch time is an upper bound on publication, recorded as one."""
    from tests.conftest import NOW

    undated = raw("https://gov.example/story").model_copy(update={"published_at": None})
    one = normalise(undated, audience, fetched_at=NOW)
    assert one is not None
    assert one.published_at == NOW
