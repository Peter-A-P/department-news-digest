"""The "Sources checked" panel: every source an audience reads, and how its last check went.

A reader of a digest should be able to see where it came from without opening the
repository: each feed, sitemap, search and community, the date its terms were read, and
what happened the last time it was checked, failures included. It is built from the audience
file, the terms record and the run's fetch log, so it cannot list a source the run does not
read or hide one that failed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC
from html import escape

from clippings.config.audience import Audience
from clippings.ingest.store import FetchRecord, Store
from clippings.sources.bluesky import person_origin
from clippings.sources.terms import TermsRecordError, TermsRow, load_terms


@dataclass(frozen=True)
class SourceLine:
    kind: str
    name: str
    link: str
    terms_key: str
    origin_key: tuple[str, str]
    note: str = ""


def source_lines(audience: Audience) -> list[SourceLine]:
    """What the audience file says this audience reads, in the order a reader would scan it."""
    sources = audience.sources
    lines = [
        SourceLine(
            "News feed",
            feed.publisher,
            feed.url,
            feed.terms,
            (feed.terms, feed.url),
            "" if feed.extract else "headline and feed summary only",
        )
        for feed in sources.feeds
    ]
    lines += [
        SourceLine(
            "Publisher's site index",
            sitemap.publisher,
            sitemap.url,
            sitemap.terms,
            (sitemap.terms, sitemap.url),
            f"pages under {sitemap.include}",
        )
        for sitemap in sources.sitemaps
    ]
    lines += [
        SourceLine(
            "GDELT news index search",
            query,
            "https://www.gdeltproject.org/",
            "gdelt",
            ("gdelt", query),
        )
        for query in sources.gdelt.queries
    ]
    lines += [
        SourceLine(
            "Bluesky search",
            query,
            "https://bsky.app/",
            "bluesky",
            ("bluesky", query),
            "posts appear only inside news stories",
        )
        for query in sources.bluesky.queries
    ]
    lines += [
        SourceLine(
            "Bluesky account",
            f"@{handle}",
            f"https://bsky.app/profile/{handle}",
            "bluesky",
            ("bluesky", person_origin(handle)),
            "candidate for the day's post; otherwise only inside news stories",
        )
        for handle in sources.bluesky.people
    ]
    lines += [
        SourceLine(
            "X search" if query == sources.x.query else "X search by subject",
            query,
            "https://x.com/",
            "x",
            ("x", query),
            f"{count} posts read; one post a day, shown on its day only",
        )
        for query, count in sources.x.searches
    ]
    return lines


def _last_check(record: FetchRecord | None) -> str:
    if record is None:
        return "not checked yet"
    when = record.at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if record.ok:
        new = f"{record.items} new item{'s' if record.items != 1 else ''}"
        return f"{when}: {new}"
    detail = record.detail.lower()
    if detail.startswith("unavailable"):
        why = "not active yet (awaiting access)"
    elif "rate limited" in detail:
        why = "refused for asking too often"
    elif "robots" in detail:
        why = "the site's robots rules refuse it"
    elif detail.startswith("refused"):
        why = "refused"
    else:
        why = "failed"
    return f'{when}: <span class="failed">{why}</span>'


def sources_panel(
    audience: Audience,
    terms: Mapping[str, TermsRow],
    fetches: Mapping[tuple[str, str], FetchRecord],
) -> str:
    """The panel as HTML, folded under a "Sources checked" button."""
    rows = []
    for line in source_lines(audience):
        row = terms.get(line.terms_key)
        read = row.date_read.isoformat() if row and row.date_read else "not recorded"
        note = f'<span class="src-note">{escape(line.note)}</span>' if line.note else ""
        rows.append(
            "<tr>"
            f'<td><a href="{escape(line.link)}">{escape(line.name)}</a>{note}</td>'
            f"<td>{escape(line.kind)}</td>"
            f"<td>{escape(read)}</td>"
            f"<td>{_last_check(fetches.get(line.origin_key))}</td>"
            "</tr>"
        )
    count = len(rows)
    return (
        '<details class="src-panel"><summary><span class="more">Sources checked '
        f'({count})</span><span class="less">Hide sources</span></summary>'
        '<div class="src-body"><p class="note">Everything this digest reads, the date each '
        "source's terms of use were read, and how its most recent check went. A source "
        "whose terms do not permit this use is not read at all.</p>"
        '<div class="src-wrap"><table class="src-table"><thead><tr><th>Source</th>'
        "<th>Type</th><th>Terms read</th><th>Last check</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div></div></details>"
    )


def panel_for(audience: Audience, store: Store) -> str:
    """The panel for one audience from the run's store and the terms record on disk."""
    try:
        terms = load_terms()
    except TermsRecordError:
        terms = {}
    return sources_panel(audience, terms, store.last_fetches(audience.id))
