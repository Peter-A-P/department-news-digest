"""The trend view: what counts as a mention, when a change is a change, and the page."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from clippings.assemble.publish import LocalSite, publish_indexes
from clippings.assemble.render import trends_page
from clippings.assemble.trends import SHOWN_ITEMS, binomial_p, change, mentions, trends
from clippings.config.audience import Audience, Entities
from clippings.ingest.store import Store
from tests.conftest import item
from tests.test_faithfulness import _digest, _story

END = date(2026, 10, 18)


def test_a_name_is_matched_whole_and_a_topic_by_most_of_its_words() -> None:
    assert mentions("organisation", "Meta", "Meta cuts AI staff")
    assert not mentions("organisation", "Meta", "metadata rules for archives")
    assert mentions("place", "St. John's", "Snow closes schools in St. John's today")
    assert mentions("topic", "transit service and expansion", "Transit service cut on Line 2")
    assert not mentions("topic", "transit service and expansion", "Transit fares frozen")


def test_the_binomial_test_against_hand_worked_values() -> None:
    assert binomial_p(5, 10, 0.5) == pytest.approx(1.0)
    assert binomial_p(0, 10, 0.5) == pytest.approx(2 / 1024)
    assert binomial_p(3, 0, 0.5) == 1.0


def test_a_change_is_only_a_change_beyond_what_all_coverage_did() -> None:
    # Twice the articles about it, in a week with twice the articles: the same share.
    assert change(20, 10, 200, 100) == "about the same"
    assert change(30, 2, 100, 100) == "rose"
    assert change(2, 30, 100, 100) == "fell"
    assert change(9, 6, 100, 100) == "about the same"
    # No week before to compare with.
    assert change(5, 0, 100, 0) == "about the same"


@pytest.fixture
def follower(audience: Audience) -> Audience:
    return audience.model_copy(
        update={
            "entities": Entities(organisations=("Metrolinx",), places=("Gander",)),
            "topics": ("transit service and expansion",),
        }
    )


def _at(days_before_end: int) -> datetime:
    return datetime.combine(END - timedelta(days=days_before_end), datetime.min.time(), UTC)


def test_two_weeks_are_counted_with_the_articles_behind_them(
    store: Store, follower: Audience
) -> None:
    this = [item(f"t{n}", "Metrolinx delays the line", published_at=_at(n % 7)) for n in range(12)]
    before = [item(f"b{n}", "Metrolinx opens a station", published_at=_at(8)) for n in range(2)]
    other = [item(f"o{n}", "Council votes", published_at=_at(n % 14)) for n in range(14)]
    post = item("p1", "Metrolinx is late again", published_at=_at(1)).model_copy(
        update={"source_kind": "bluesky"}
    )
    old = item("x1", "Metrolinx three weeks ago", published_at=_at(20))
    store.add_items([*this, *before, *other, post, old], follower.id)
    store.save_digest(_digest(END.isoformat(), (_story("k1", ["One."], "t0"),), follower.id))
    found = trends(store, follower, END)
    assert (found.this_total, found.last_total) == (12 + 7, 2 + 7)
    (metrolinx,) = found.terms
    assert (metrolinx.this_week, metrolinx.last_week) == (12, 2)
    assert len(metrolinx.items) == SHOWN_ITEMS
    assert [i.url for i in metrolinx.items if i.in_digest] == ["https://gov.example/t0"]
    assert found.unseen == ("Gander", "transit service and expansion")

    page = trends_page("Test audience", follower.id, found)
    assert "Metrolinx" in page and "in a digest" in page and "The 8 newest of 12" in page
    assert "Not named in either week: Gander" in page


def test_the_archive_links_its_trend_view(tmp_path: Path, store: Store, follower: Audience) -> None:
    store.add_items([item("t1", "Metrolinx", published_at=_at(0))], follower.id)
    site = LocalSite(tmp_path)
    page = trends_page(follower.name, follower.id, trends(store, follower, END))
    publish_indexes(
        site, [(follower.id, follower.name, "")], {follower.id: []}, trend_pages={follower.id: page}
    )
    assert (tmp_path / follower.id / "trends" / "index.html").exists()
    assert 'href="trends/"' in (tmp_path / follower.id / "index.html").read_text()
