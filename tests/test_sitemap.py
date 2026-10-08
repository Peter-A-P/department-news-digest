"""The sitemap source: new news pages only, by the page's own publication date."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from clippings.config.audience import Audience, Sitemap, Sources
from clippings.sources.base import FetchContext, FetchResult
from clippings.sources.robots import AllowAll
from clippings.sources.sitemap import MAX_PAGES, Entry, candidates, page_meta, parse_sitemap
from tests.conftest import gate

SITEMAP = Sitemap(
    url="https://lab.example/sitemap.xml", publisher="Lab", terms="lab.example", include="/news/"
)
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


def urlset(*entries: tuple[str, str | None]) -> bytes:
    rows = "".join(
        f"<url><loc>{loc}</loc>{f'<lastmod>{mod}</lastmod>' if mod else ''}</url>"
        for loc, mod in entries
    )
    return (
        '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{rows}</urlset>"
    ).encode()


def page(title: str, published: str | None) -> str:
    meta = f'<meta property="article:published_time" content="{published}"/>' if published else ""
    return (
        f"<html><head><title>{title} \\ Lab</title>"
        f'<meta property="og:title" content="{title}"/>'
        f'<meta property="og:description" content="About {title}."/>{meta}</head></html>'
    )


def test_only_news_pages_changed_since_the_watermark_newest_first() -> None:
    entries, children = parse_sitemap(
        urlset(
            ("https://lab.example/news", "2026-10-08T08:00:00Z"),  # the index page itself
            ("https://lab.example/news/new", "2026-10-08T07:00:00Z"),
            ("https://lab.example/news/newer", "2026-10-08T08:30:00Z"),
            ("https://lab.example/news/old", "2026-09-01T00:00:00Z"),
            ("https://lab.example/careers/job", "2026-10-08T08:00:00Z"),
            ("https://lab.example/news/undated", None),
        )
    )
    assert children == []
    chosen = candidates(entries, SITEMAP, NOW - timedelta(days=2))
    assert [entry.url.rsplit("/", 1)[1] for entry in chosen] == ["newer", "new"]


def test_the_number_of_pages_read_is_bounded() -> None:
    entries = [Entry(f"https://lab.example/news/{i}", NOW) for i in range(50)]
    assert len(candidates(entries, SITEMAP, NOW - timedelta(days=1))) == MAX_PAGES


def test_page_metadata_prefers_the_publishers_own_fields() -> None:
    meta = page_meta(page("Claude discovers an enzyme", "2026-10-07T16:06:00.000Z"))
    assert meta.title == "Claude discovers an enzyme"
    assert meta.description == "About Claude discovers an enzyme."
    assert meta.published == datetime(2026, 10, 7, 16, 6, tzinfo=UTC)
    structured = page_meta(
        '<title>T</title><script>{"datePublished":"2026-10-01T00:00:00Z"}</script>'
    )
    assert structured.published == datetime(2026, 10, 1, tzinfo=UTC)


def fetch(pages: dict[str, httpx.Response], allowed: bool = True) -> list[FetchResult]:
    from clippings.sources.sitemap import SitemapSource

    def respond(request: httpx.Request) -> httpx.Response:
        return pages.get(str(request.url), httpx.Response(404))

    audience = Audience(
        id="lab",
        name="Lab",
        description="d",
        topics=("ai",),
        rubric="Relevant means an item whose primary subject is the lab and nothing else at all.",
        sources=Sources(sitemaps=(SITEMAP,)),
    )
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        context = FetchContext(
            client=client,
            gate=gate(**{"lab.example": "allowed" if allowed else "pending"}),
            robots=AllowAll(),
            now=NOW,
        )
        return list(SitemapSource().fetch(audience, context))


def test_an_edited_old_post_is_not_news_and_a_new_one_is() -> None:
    """Measured on anthropic.com: a post published 2026-09-23 carried a lastmod of 2026-10-07."""
    results = fetch(
        {
            "https://lab.example/sitemap.xml": httpx.Response(
                200,
                content=urlset(
                    ("https://lab.example/news/edited", "2026-10-08T08:00:00Z"),
                    ("https://lab.example/news/fresh", "2026-10-08T07:00:00Z"),
                    ("https://lab.example/news/undated", "2026-10-08T06:00:00Z"),
                ),
            ),
            "https://lab.example/news/edited": httpx.Response(
                200, text=page("Old", "2026-09-23T16:06:00Z")
            ),
            "https://lab.example/news/fresh": httpx.Response(
                200, text=page("Fresh", "2026-10-08T06:30:00Z")
            ),
            "https://lab.example/news/undated": httpx.Response(200, text=page("Undated", None)),
        }
    )
    (result,) = results
    assert result.ok
    assert [item.title for item in result.items] == ["Fresh"]
    item = result.items[0]
    assert (item.source_kind, item.summary) == ("sitemap", "About Fresh.")
    assert "1 edited, not new" in result.detail and "1 with no publication date" in result.detail


def test_a_pending_sitemap_is_never_requested() -> None:
    (result,) = fetch({}, allowed=False)
    assert not result.ok
    assert "refused" in result.detail
