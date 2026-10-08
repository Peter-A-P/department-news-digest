"""Article text, fetched only where the publisher allows it, kept thirty days.

PLAN.md section 2.2. The text is what the summariser reads and what the verifier checks a
quote against; it is never republished, and retention deletes it at thirty days.

Three gates before a request leaves, in order of how cheap they are to check: the item's
source must be allowed in the terms record, the item's own domain must not be blocked for
this audience, and robots.txt must permit the path. A page behind any of them has no text,
and an item with no text can still reach a digest on its title and summary alone, quoted
from what the publisher put in the feed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import trafilatura

from clippings.config.audience import Audience
from clippings.ingest.normalise import is_blocked
from clippings.models import SOCIAL_KINDS, Item, ItemText
from clippings.sources.base import FetchContext

# Below this the extractor found a navigation page, a consent wall or a stub, not an
# article. Storing it would give the summariser something to quote that is not the story.
MIN_WORDS = 60

# Posts are their own text: the title and body arrived with the item, and fetching the page
# would be fetching a discussion platform's rendering of what is already in hand.
SELF_DESCRIBING = SOCIAL_KINDS


@dataclass(frozen=True)
class ExtractOutcome:
    """What happened to one item, so the run can report why text is missing."""

    item_id: str
    text: ItemText | None
    reason: str = ""

    @property
    def extracted(self) -> bool:
        return self.text is not None


def extract_one(item: Item, audience: Audience, context: FetchContext) -> ExtractOutcome:
    """Fetch and extract one item's article text, or say why not."""
    if item.source_kind in SELF_DESCRIBING:
        return ExtractOutcome(item.id, None, "post carries its own text")
    if not context.permitted(item.source_key):
        return ExtractOutcome(item.id, None, "terms do not allow it")
    if item.source_kind in {"rss", "sitemap"} and not _feed_allows_extraction(item, audience):
        return ExtractOutcome(item.id, None, "feed cleared for its summary only")
    if is_blocked(item.domain, audience):
        return ExtractOutcome(item.id, None, "blocked source")
    if not context.robots.allows(item.url):
        return ExtractOutcome(item.id, None, "robots.txt disallows it")
    try:
        response = context.client.get(item.url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return ExtractOutcome(item.id, None, f"{type(exc).__name__}: {exc}")
    text = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if not text:
        return ExtractOutcome(item.id, None, "no article found on the page")
    words = len(text.split())
    if words < MIN_WORDS:
        return ExtractOutcome(item.id, None, f"only {words} words extracted")
    return ExtractOutcome(
        item.id,
        ItemText(item_id=item.id, text=text, extracted_at=datetime.now(UTC), words=words),
    )


def _feed_allows_extraction(item: Item, audience: Audience) -> bool:
    """False when the feed this item came from is marked `extract: false`.

    An RSS item's origin is the feed URL it was read from. An origin that matches no
    configured feed (the audience file changed since the item was stored) is refused rather
    than allowed: the flag exists to keep a request from leaving, so not knowing is a no.
    """
    flags = {feed.url: feed.extract for feed in audience.sources.feeds}
    flags |= {sitemap.url: sitemap.extract for sitemap in audience.sources.sitemaps}
    return flags.get(item.origin, False)
