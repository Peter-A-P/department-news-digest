"""Turning a `RawItem` from any source into the one shape the store holds.

Two different URLs for the same article is the commonest duplicate there is, and it costs
nothing to collapse before clustering does the expensive work. The canonical URL is what a
reader is linked to; the dedup key is a stricter form used only to give an item its id, so
`http://www.example.org/a?utm_source=x` and `https://example.org/a` are one item.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from clippings.config.audience import Audience
from clippings.models import Item, RawItem

# Campaign and click identifiers: they identify the referral, never the article.
TRACKING_PARAMS = frozenset(
    {
        "cmp",
        "cmpid",
        "email_source",
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "msclkid",
        "ncid",
        "ref",
        "referrer",
        "s_cid",
        "smid",
        "sref",
        "twclid",
        "wtmc",
        "yclid",
    }
)
TRACKING_PREFIXES = ("utm_", "at_", "ito", "cmpid_", "spm_")

WHITESPACE = re.compile(r"\s+")
TAG = re.compile(r"<[^>]+>")


class NormaliseError(ValueError):
    """An item that cannot be normalised, and so is dropped rather than stored half-formed."""


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_PARAMS or lowered.startswith(TRACKING_PREFIXES)


def canonical_url(url: str) -> str:
    """The link a reader is given: the same article, without the referral noise."""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise NormaliseError(f"not an http(s) URL: {url!r}")
    host = parts.hostname or ""
    netloc = host.lower()
    if parts.port and parts.port not in {80, 443}:
        netloc = f"{netloc}:{parts.port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not _is_tracking(key)
        ]
    )
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # The fragment is dropped: it addresses a position in the page, not a document.
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def dedup_key(url: str) -> str:
    """The stricter form an item's id is derived from.

    Scheme and a leading `www.` are collapsed here and nowhere else: a publisher serving
    both is one article, but the reader still gets the link as published.
    """
    parts = urlsplit(canonical_url(url))
    host = parts.netloc.removeprefix("www.")
    return urlunsplit(("https", host, parts.path, parts.query, ""))


def domain_of(url: str) -> str:
    """The bare host, for trust, blocking and source yield."""
    return urlsplit(canonical_url(url)).netloc.removeprefix("www.")


def registrable_suffixes(domain: str) -> tuple[str, ...]:
    """`news.ontario.ca` matches a rule written as `ontario.ca` or as itself.

    Trust and blocking are written as bare domains in the audience file, and a department
    writing `cbc.ca` means the subdomains too.
    """
    labels = domain.split(".")
    return tuple(".".join(labels[index:]) for index in range(len(labels) - 1))


def is_blocked(domain: str, audience: Audience) -> bool:
    """Whether this domain is blocked for this audience, subdomains included."""
    candidates = {domain, *registrable_suffixes(domain)}
    return bool(candidates & set(audience.blocked_sources))


def is_trusted(domain: str, audience: Audience) -> bool:
    candidates = {domain, *registrable_suffixes(domain)}
    return bool(candidates & set(audience.trusted_sources))


def clean_text(value: str) -> str:
    """Feed summaries arrive as HTML fragments; the store holds plain text."""
    return WHITESPACE.sub(" ", TAG.sub(" ", value)).strip()


def normalise(
    raw: RawItem,
    audience: Audience,
    *,
    language: str | None = None,
    fetched_at: datetime | None = None,
) -> Item | None:
    """Normalise one raw item, or return None if it must not be stored.

    Returns None rather than raising for the ordinary reasons an item is dropped: a blocked
    source, or a URL that is not a fetchable article. A blocked source never reaches the
    store, which is the point of checking here rather than at render time.
    """
    try:
        canonical = canonical_url(raw.url)
    except NormaliseError:
        return None
    domain = domain_of(canonical)
    if is_blocked(domain, audience):
        return None
    title = clean_text(raw.title)
    if not title:
        return None
    published = raw.published_at
    now = fetched_at or datetime.now(UTC)
    if published is None:
        # A feed without a date is common. The fetch time is an upper bound on publication
        # and is recorded as such; timeliness excludes these and says how many it excluded.
        published = now
    if published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    return Item(
        id=Item.id_for(dedup_key(canonical)),
        source_key=raw.source_key,
        source_kind=raw.source_kind,
        url=canonical,
        original_url=raw.url,
        domain=domain,
        title=title,
        summary=clean_text(raw.summary),
        author=raw.author,
        language=language,
        published_at=published.astimezone(UTC),
        fetched_at=now,
        origin=raw.origin,
        score=raw.score,
        comments=raw.comments,
    )
