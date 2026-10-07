"""The source adapters, against mocked transports. No test reaches a publisher."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from clippings.config.audience import Audience, Feed
from clippings.constants import USER_AGENT
from clippings.sources.base import FetchContext, FetchResult
from clippings.sources.bluesky import BlueskySource, parse_posts, post_url
from clippings.sources.gdelt import MIN_INTERVAL_SECONDS, GdeltSource, parse_articles
from clippings.sources.reddit import RedditSource, parse_listing
from clippings.sources.robots import AllowAll, RobotsCache
from clippings.sources.rss import RssSource, parse_feed
from tests.conftest import NOW, gate

FEED = Feed(url="https://gov.example/feed", publisher="Gov", terms="gov.example")

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Gov news</title>
  <item>
    <title>Consultation opens</title>
    <link>https://gov.example/news/1</link>
    <description>&lt;p&gt;The regulator opened a consultation.&lt;/p&gt;</description>
    <pubDate>Sat, 12 Sep 2026 09:00:00 +0000</pubDate>
  </item>
  <item>
    <title>An older notice</title>
    <link>https://gov.example/news/0</link>
    <pubDate>Wed, 09 Sep 2026 09:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Gov news</title>
  <entry>
    <title>An atom entry</title>
    <link href="https://gov.example/news/2"/>
    <updated>2026-09-12T09:00:00Z</updated>
    <content type="html">Some content.</content>
  </entry>
</feed>
"""


def audience_with(sources: object, languages: tuple[str, ...] = ("en",)) -> Audience:
    """A minimal audience carrying only the sources a test is about."""
    return Audience(
        id="a",
        name="A",
        description="d",
        rubric="Relevant means the one thing this audience is configured to care about here.",
        topics=("t",),
        languages=languages,
        sources=sources,
    )


def context_with(handler, **statuses: str) -> FetchContext:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FetchContext(client=client, gate=gate(**statuses), robots=AllowAll(), now=NOW)


# -- RSS ---------------------------------------------------------------------------------


def test_a_feed_is_parsed_into_items() -> None:
    items = parse_feed(RSS, FEED, since=NOW - timedelta(days=7))
    assert [one.title for one in items] == ["Consultation opens", "An older notice"]
    assert items[0].url == "https://gov.example/news/1"
    assert items[0].published_at == datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def test_the_watermark_excludes_what_was_already_seen() -> None:
    items = parse_feed(RSS, FEED, since=datetime(2026, 9, 10, tzinfo=UTC))
    assert [one.title for one in items] == ["Consultation opens"]


def test_atom_feeds_work_too() -> None:
    items = parse_feed(ATOM, FEED, since=NOW - timedelta(days=7))
    assert items[0].url == "https://gov.example/news/2"


def test_an_entry_with_no_link_is_skipped() -> None:
    feed = b'<?xml version="1.0"?><rss version="2.0"><channel><item><title>No link</title></item></channel></rss>'
    assert parse_feed(feed, FEED, since=NOW - timedelta(days=7)) == ()


def test_a_source_whose_terms_are_not_read_is_never_requested() -> None:
    """The whole point of the terms gate: no request leaves for a pending source."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a request was sent to {request.url} for a pending source")

    audience = audience_with({"feeds": [FEED]})
    results = list(RssSource().fetch(audience, context_with(handler, **{"gov.example": "pending"})))
    assert len(results) == 1
    assert results[0].ok is False
    assert "not read yet" in results[0].detail


def test_a_dropped_source_is_never_requested() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a request was sent for a dropped source")

    audience = audience_with({"feeds": [FEED]})
    results = list(RssSource().fetch(audience, context_with(handler, **{"gov.example": "dropped"})))
    assert results[0].ok is False
    assert "dropped" in results[0].detail


def test_an_allowed_feed_is_fetched() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == FEED.url
        assert "clippings" in request.headers["User-Agent"]
        return httpx.Response(200, content=RSS)

    audience = audience_with({"feeds": [FEED]})
    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    context = FetchContext(
        client=client, gate=gate(**{"gov.example": "allowed"}), robots=AllowAll(), now=NOW
    )
    results = list(RssSource().fetch(audience, context))
    assert results[0].ok is True
    # One of the feed's two entries. The other was published three days ago, and a source
    # with no watermark is read back only as far as the cold-start window.
    assert [one.title for one in results[0].items] == ["Consultation opens"]


def test_a_failing_feed_is_recorded_rather_than_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    audience = audience_with({"feeds": [FEED]})
    results = list(RssSource().fetch(audience, context_with(handler, **{"gov.example": "allowed"})))
    assert results[0].ok is False
    assert "503" in results[0].detail


# -- robots ------------------------------------------------------------------------------


def test_robots_disallow_stops_a_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /feed\n")
        raise AssertionError("fetched a path robots.txt disallows")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    robots = RobotsCache(client)
    assert robots.allows("https://gov.example/feed") is False
    assert robots.allows("https://gov.example/allowed") is True


def test_a_host_with_no_robots_file_allows_everything() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    assert RobotsCache(client).allows("https://gov.example/feed") is True


def test_a_host_whose_robots_file_cannot_be_read_is_not_fetched() -> None:
    """The cautious default: a host that will not tell us is not asked again."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert RobotsCache(client).allows("https://gov.example/feed") is False


def test_robots_is_fetched_once_per_host() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="User-agent: *\nAllow: /\n")

    robots = RobotsCache(httpx.Client(transport=httpx.MockTransport(handler)))
    robots.allows("https://gov.example/a")
    robots.allows("https://gov.example/b")
    assert calls == 1


# -- GDELT -------------------------------------------------------------------------------


def test_gdelt_articles_are_parsed() -> None:
    payload = {
        "articles": [
            {
                "url": "https://news.example/story",
                "title": "A story",
                "seendate": "20260912T090000Z",
                "domain": "news.example",
                "language": "English",
            }
        ]
    }
    items = parse_articles(payload, "a query", since=NOW - timedelta(days=1))
    assert items[0].url == "https://news.example/story"
    assert items[0].published_at == datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def test_gdelt_text_response_is_a_failure_carrying_gdelt_s_own_words() -> None:
    """GDELT answers a rejected query with plain text and a 200.

    What it says is the useful part, so the recorded detail is its sentence rather than the
    JSON parser's complaint about column one.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Your query was too short.")

    audience = audience_with({"gdelt": {"queries": ["x"]}})
    results = list(
        GdeltSource(min_interval=0.0).fetch(audience, context_with(handler, gdelt="allowed"))
    )
    assert results[0].ok is False
    assert "Your query was too short." in results[0].detail


def test_gdelt_restricts_the_query_to_the_audience_languages() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["query"])
        return httpx.Response(200, json={"articles": []})

    audience = audience_with({"gdelt": {"queries": ["transit"]}})
    list(GdeltSource(min_interval=0.0).fetch(audience, context_with(handler, gdelt="allowed")))
    assert seen == ["transit sourcelang:english"]


# -- Reddit ------------------------------------------------------------------------------


def test_reddit_posts_are_parsed_as_the_post_not_the_link_target() -> None:
    payload = {
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "permalink": "/r/toronto/comments/abc/council_votes/",
                        "title": "Council votes",
                        "selftext": "Some discussion.",
                        "author": "someone",
                        "created_utc": 1789000000,
                        "score": 42,
                        "num_comments": 7,
                        "url": "https://news.example/elsewhere",
                    },
                }
            ]
        }
    }
    items = parse_listing(payload, "toronto", since=datetime(2020, 1, 1, tzinfo=UTC))
    assert items[0].url == "https://www.reddit.com/r/toronto/comments/abc/council_votes/"
    assert items[0].score == 42


def test_a_comment_in_a_listing_is_ignored() -> None:
    payload = {"data": {"children": [{"kind": "t1", "data": {"body": "a comment"}}]}}
    assert parse_listing(payload, "toronto", since=datetime(2020, 1, 1, tzinfo=UTC)) == ()


def test_reddit_without_credentials_reports_itself_unavailable() -> None:
    """The pipeline runs with any subset of sources."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a token request was sent with no credentials")

    audience = audience_with({"reddit": {"subreddits": ["toronto"]}})
    results = list(RedditSource().fetch(audience, context_with(handler, reddit="allowed")))
    assert results[0].ok is False
    assert "REDDIT_CLIENT_ID" in results[0].detail


# -- Bluesky -----------------------------------------------------------------------------


def test_a_bluesky_post_url_is_built_from_the_uri_and_handle() -> None:
    url = post_url("at://did:plc:xyz/app.bsky.feed.post/3abc", "someone.bsky.social")
    assert url == "https://bsky.app/profile/someone.bsky.social/post/3abc"


def test_bluesky_posts_are_parsed() -> None:
    payload = {
        "posts": [
            {
                "uri": "at://did:plc:xyz/app.bsky.feed.post/3abc",
                "author": {"handle": "someone.bsky.social"},
                "record": {"text": "First line\nSecond line", "createdAt": "2026-09-12T09:00:00Z"},
                "likeCount": 3,
                "replyCount": 1,
            }
        ]
    }
    items = parse_posts(payload, "a query", since=NOW - timedelta(days=1))
    assert items[0].title == "First line"
    assert items[0].summary == "First line\nSecond line"
    assert items[0].author == "someone.bsky.social"


def test_bluesky_refuses_a_source_whose_terms_are_not_read() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a search request was sent for a pending source")

    audience = audience_with({"bluesky": {"queries": ["transit"]}})
    results = list(BlueskySource().fetch(audience, context_with(handler, bluesky="pending")))
    assert results[0].ok is False
    assert "not read yet" in results[0].detail


def test_an_empty_post_is_skipped() -> None:
    payload = {
        "posts": [
            {
                "uri": "at://x/app.bsky.feed.post/1",
                "author": {"handle": "a.bsky.social"},
                "record": {"text": "   ", "createdAt": "2026-09-12T09:00:00Z"},
            }
        ]
    }
    assert parse_posts(payload, "q", since=NOW - timedelta(days=1)) == ()


def test_a_malformed_payload_yields_nothing_rather_than_raising() -> None:
    payloads: list[object] = [None, [], {"posts": "not a list"}, {}]
    for payload in payloads:
        assert parse_posts(payload, "q", since=NOW) == ()
        assert parse_articles(payload, "q", since=NOW) == ()


# -- the shared result shape --------------------------------------------------------------


def test_a_failure_result_carries_no_items() -> None:
    result = FetchResult.failure("gov.example", "https://gov.example/feed", "503")
    assert result.items == ()
    assert result.ok is False


def test_refusal_on_a_permitted_source_is_a_programming_error() -> None:
    context = context_with(lambda request: httpx.Response(200), **{"gov.example": "allowed"})
    with pytest.raises(AssertionError):
        context.refusal("gov.example", "https://gov.example/feed")


def test_gdelt_waits_between_requests() -> None:
    """GDELT asks for one request every five seconds, and that is the whole of its price."""
    stamps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        stamps.append(time.monotonic())
        return httpx.Response(200, json={"articles": []})

    audience = audience_with({"gdelt": {"queries": ["one", "two"]}})
    source = GdeltSource(min_interval=0.25)
    list(source.fetch(audience, context_with(handler, gdelt="allowed")))

    assert len(stamps) == 2
    assert stamps[1] - stamps[0] >= 0.25, "the second request did not wait its turn"


def test_the_default_gdelt_interval_is_what_gdelt_asked_for() -> None:
    assert MIN_INTERVAL_SECONDS >= 5.0


def test_gdelt_rate_limiting_is_reported_not_retried() -> None:
    """Asking twice for what we were told to ask once is not a fix."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="Please limit requests to one every 5 seconds.")

    audience = audience_with({"gdelt": {"queries": ["one"]}})
    results = list(
        GdeltSource(min_interval=0.0).fetch(audience, context_with(handler, gdelt="allowed"))
    )
    assert calls == 1
    assert results[0].ok is False
    assert "rate limited" in results[0].detail


def test_bluesky_without_credentials_reports_itself_unavailable() -> None:
    """Search needs a session now; without an app password the run continues without it."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a request was sent with no app password")

    audience = audience_with({"bluesky": {"queries": ["transit"]}})
    results = list(BlueskySource().fetch(audience, context_with(handler, bluesky="allowed")))
    assert results[0].ok is False
    assert "BLUESKY_HANDLE" in results[0].detail


def test_bluesky_searches_with_the_token_it_was_given() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "a-token"})
        seen.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"posts": []})

    audience = audience_with({"bluesky": {"queries": ["transit"]}})
    context = context_with(handler, bluesky="allowed")
    context.secrets = {"BLUESKY_HANDLE": "someone.bsky.social", "BLUESKY_APP_PASSWORD": "x"}
    results = list(BlueskySource().fetch(audience, context))
    assert results[0].ok is True
    assert seen == ["Bearer a-token"]


def test_the_user_agent_identifies_the_project_without_carrying_a_url() -> None:
    """The product token is what robots.txt addresses, and it has to stay.

    The URL is deliberately absent: CBC's edge drops any user agent containing one, which is
    the convention meant to make a crawler identifiable. See clippings/constants.py for the
    measurement and docs/sources.md for the reasoning.
    """
    assert USER_AGENT.startswith("clippings/")
    assert "://" not in USER_AGENT, (
        "a URL in the user agent gets this project refused by at least one publisher; "
        "robots.txt addresses the 'clippings' product token instead"
    )


def test_reddit_gets_the_user_agent_its_rules_ask_for() -> None:
    import httpx

    from clippings.sources.base import FetchContext
    from clippings.sources.reddit import user_agent
    from clippings.sources.robots import AllowAll
    from tests.conftest import gate

    with httpx.Client() as client:
        context = FetchContext(client=client, gate=gate(), robots=AllowAll())
        assert user_agent(context) == {}
        context.secrets = {"REDDIT_CLIENT_ID": "abc", "REDDIT_USERNAME": "someone"}
        agent = user_agent(context)["User-Agent"]
    assert agent == "python:clippings:abc:0.1 (by /u/someone)"
    assert "http" not in agent.split("(")[0], "no URL: CBC-style edges refuse one"
