"""The trend view: what an audience's news was about this week, against the week before.

PLAN.md section 4 names it: weekly entity and topic deltas with the items behind them. The
terms are the audience's own, from its file (organisations, people, places and topics), so
the page answers "is there more about Metrolinx this week?" for the things the audience said
it follows, and invents no subject of its own.

A term is counted in the news articles its sources published in each seven-day week, by
publication date: an article counts once for a term if its title or feed summary names it.
Reprints count, because this is coverage, not stories. An organisation, person or place is
matched as a whole phrase; a topic, which an audience writes as "transit service and
expansion" and no headline contains, when two thirds of its content words appear.

A count moving from 6 to 9 is noise. A term is said to have risen or fallen only when the
change is larger than the change in all coverage would explain: given the term's articles in
the two weeks, the share in this week is tested against this week's share of all articles,
with an exact two-sided binomial test at 5%. Everything else is "about the same". The page
shows both weeks' totals, so a week with more sources is visible as such.

Two weeks are fourteen days, inside the thirty for which items are kept; the page shows titles
and links, never article text.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from clippings.config.audience import Audience
from clippings.ingest.store import Store
from clippings.models import SOCIAL_KINDS, Item
from clippings.rank.features import WORD, content_words

WEEK = 7
# The articles shown under a term, newest first; the count says how many there were.
SHOWN_ITEMS = 8
SIGNIFICANCE = 0.05

Kind = Literal["organisation", "person", "place", "topic"]
Change = Literal["rose", "fell", "about the same"]


@dataclass(frozen=True)
class TrendItem:
    title: str
    url: str
    domain: str
    published_at: datetime
    in_digest: bool


@dataclass(frozen=True)
class Term:
    label: str
    kind: Kind
    this_week: int
    last_week: int
    change: Change
    items: tuple[TrendItem, ...]


@dataclass(frozen=True)
class Trends:
    audience_id: str
    # The last day of this week, and the first days of this week and the one before.
    end: date
    this_total: int
    last_total: int
    terms: tuple[Term, ...]
    unseen: tuple[str, ...]
    # The week before began before the audience's first digest, so it holds only what the
    # feeds still carried on the first day, and its counts are low for that reason.
    partial_last: bool = False

    @property
    def start(self) -> date:
        return self.end - timedelta(days=WEEK - 1)

    @property
    def last_end(self) -> date:
        return self.start - timedelta(days=1)

    @property
    def last_start(self) -> date:
        return self.end - timedelta(days=2 * WEEK - 1)


def _entity_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)


def mentions(kind: Kind, phrase: str, text: str) -> bool:
    if kind != "topic":
        return bool(_entity_pattern(phrase).search(text))
    words = content_words(phrase)
    if not words:
        return False
    present = frozenset(WORD.findall(text.lower()))
    return len(words & present) >= math.ceil(2 * len(words) / 3)


def binomial_p(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial test: the chance of an outcome as unlikely as `k` in `n`."""
    if n == 0 or p <= 0.0 or p >= 1.0:
        return 1.0

    def log_pmf(i: int) -> float:
        return (
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * math.log(p)
            + (n - i) * math.log(1 - p)
        )

    observed = log_pmf(k)
    # A small tolerance, so outcomes exactly as likely as the observed one are counted.
    return min(
        1.0, sum(math.exp(lp) for i in range(n + 1) if (lp := log_pmf(i)) <= observed + 1e-9)
    )


def change(this_week: int, last_week: int, this_total: int, last_total: int) -> Change:
    if not this_total or not last_total:
        return "about the same"
    share = this_total / (this_total + last_total)
    n = this_week + last_week
    if binomial_p(this_week, n, share) >= SIGNIFICANCE:
        return "about the same"
    return "rose" if this_week > n * share else "fell"


def terms_of(audience: Audience) -> list[tuple[str, Kind]]:
    entities = audience.entities
    out: list[tuple[str, Kind]] = []
    out += [(name, "organisation") for name in entities.organisations]
    out += [(name, "person") for name in entities.people]
    out += [(name, "place") for name in entities.places]
    out += [(topic, "topic") for topic in audience.topics]
    return out


def trends(store: Store, audience: Audience, end: date) -> Trends:
    """The week to `end` against the week before, from the news items the store holds."""
    first = datetime.combine(end - timedelta(days=2 * WEEK - 1), datetime.min.time(), UTC)
    last = datetime.combine(end + timedelta(days=1), datetime.min.time(), UTC)
    split = datetime.combine(end - timedelta(days=WEEK - 1), datetime.min.time(), UTC)
    news = [
        item
        for item in store.items_for(audience.id, since=first)
        if item.source_kind not in SOCIAL_KINDS and item.published_at < last
    ]
    this = [item for item in news if item.published_at >= split]
    before = [item for item in news if item.published_at < split]
    shown = _shown_ids(store, audience.id, split.date(), end)
    terms = []
    unseen = []
    for phrase, kind in terms_of(audience):
        now_hits = [item for item in this if mentions(kind, phrase, _text(item))]
        then_hits = sum(mentions(kind, phrase, _text(item)) for item in before)
        if not now_hits and not then_hits:
            unseen.append(phrase)
            continue
        terms.append(
            Term(
                label=phrase,
                kind=kind,
                this_week=len(now_hits),
                last_week=then_hits,
                change=change(len(now_hits), then_hits, len(this), len(before)),
                items=tuple(
                    TrendItem(
                        title=item.title,
                        url=item.url,
                        domain=item.domain,
                        published_at=item.published_at,
                        in_digest=item.id in shown,
                    )
                    for item in sorted(now_hits, key=lambda i: i.published_at, reverse=True)[
                        :SHOWN_ITEMS
                    ]
                ),
            )
        )
    terms.sort(key=lambda term: (-term.this_week, -term.last_week, term.label.lower()))
    return Trends(
        audience_id=audience.id,
        end=end,
        this_total=len(this),
        last_total=len(before),
        terms=tuple(terms),
        unseen=tuple(unseen),
        partial_last=min(store.digest_days(audience.id), default=end.isoformat())
        > (end - timedelta(days=2 * WEEK - 1)).isoformat(),
    )


def latest_trends(store: Store, audience: Audience) -> Trends | None:
    """The trends for the week to the audience's latest digest day, if it has one."""
    days = store.digest_days(audience.id)
    return trends(store, audience, date.fromisoformat(max(days))) if days else None


def _text(item: Item) -> str:
    return f"{item.title}\n{item.summary}"


def _shown_ids(store: Store, audience_id: str, start: date, end: date) -> set[str]:
    """Every news item cited by a story a digest of the week showed."""
    shown: set[str] = set()
    for day in store.digest_days(audience_id):
        if start.isoformat() <= day <= end.isoformat():
            digest = store.digest_for(audience_id, day)
            if digest is not None:
                shown |= {link.item_id for story in digest.stories for link in story.sources}
    return shown


def describe(terms: Sequence[Term]) -> str:
    """One line for the top of the page: what rose and what fell."""
    rose = [term.label for term in terms if term.change == "rose"]
    fell = [term.label for term in terms if term.change == "fell"]
    parts = []
    if rose:
        parts.append(f"More coverage than the week before: {', '.join(rose)}.")
    if fell:
        parts.append(f"Less: {', '.join(fell)}.")
    return " ".join(parts) or "No term's share of coverage changed by more than chance would."
