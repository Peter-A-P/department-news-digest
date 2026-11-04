"""The faithfulness check: which sentences are drawn, what the checker is shown, what a saved
day records and how the report scores it."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clippings.assemble.digest import (
    Digest,
    DigestSentence,
    DigestStory,
    SourceLink,
    VerificationCounts,
)
from clippings.config.audience import Audience
from clippings.eval.faithfulness import DAYS, PER_DAY, sample_days, sentence_sample
from clippings.eval.label_ui import Workspace
from clippings.eval.report import NOT_YET, build_report, detail, faithfulness, readme_tables
from clippings.ingest.store import Store
from clippings.models import FaithLabel, ItemText, Verdict
from tests.conftest import NOW, item
from tests.test_label_ui import call

DAY = NOW.date().isoformat()

ARTICLE = (
    "The council voted 9 to 4 on Tuesday to freeze fares for 2027. The mayor said the budget "
    '"keeps the city moving" and the vote ends a month of debate.'
)


def _story(
    story_id: str, sentences: list[str], item_id: str, *, extracted: bool = True
) -> DigestStory:
    link = SourceLink(
        sid="s1",
        item_id=item_id,
        domain="gov.example",
        title=f"Headline {story_id}",
        url=f"https://gov.example/{item_id}",
        published_at=NOW,
        extracted=extracted,
    )
    return DigestStory(
        story_id=story_id,
        position=1,
        headline=f"Headline {story_id}",
        url=link.url,
        domain="gov.example",
        published_at=NOW,
        outlets=1,
        sentences=tuple(DigestSentence(text=text, cites=("s1",)) for text in sentences),
        sources=(link,),
        status="verified",
        prefilter_score=0.5,
        rerank_score=3,
        rerank_reason="",
        final_score=0.9,
        why="",
    )


def _digest(
    day: str, stories: tuple[DigestStory, ...], audience_id: str = "test-audience"
) -> Digest:
    return Digest(
        audience_id=audience_id,
        audience_name="Test audience",
        day=day,
        run_id="r1",
        generated_at=NOW,
        stories=stories,
        counts=VerificationCounts(),
        calls=(),
        pool_items=10,
        pool_stories=8,
        candidates=8,
        reranked=True,
        rerank_error="",
        rerank_unscored=0,
        rerank_excluded=0,
        embedder="hashing",
        model_client="scripted",
    )


SENTENCES = [
    'The council voted 9 to 4 to freeze fares, and the mayor said it "keeps the city moving".',
    "The vote ends a month of debate.",
    "Fares will rise in 2028.",
]


@pytest.fixture
def faith_ws(store: Store, audience: Audience) -> Workspace:
    store.add_items([item("a", "Council freezes fares", summary="Fares frozen.")], audience.id)
    store.add_text(ItemText(item_id="a", text=ARTICLE, extracted_at=NOW, words=30))
    stories = (
        _story("k1", SENTENCES, "a"),
        # Its source was deleted after thirty days.
        _story("k2", ["A second story's only sentence.", "And its second."], "gone"),
    )
    store.save_digest(_digest(DAY, stories))
    return Workspace(
        store=store, labels=Store.memory(), labeller="peter", audiences={audience.id: audience}
    )


def test_the_sample_is_drawn_from_shown_sentences_stably_with_its_weight() -> None:
    stories = tuple(_story(f"k{n}", [f"s{n}a", f"s{n}b", f"s{n}c"], "a") for n in range(4))
    digest = _digest(DAY, stories)
    sample = sentence_sample(digest)
    assert len(sample.units) == PER_DAY and sample.shown == 12
    assert all(unit.weight == pytest.approx(12 / PER_DAY) for unit in sample.units)
    assert len({unit.key for unit in sample.units}) == PER_DAY
    assert sentence_sample(digest) == sample
    short = sentence_sample(_digest(DAY, (_story("k1", ["only"], "a"),)))
    assert [(unit.key, unit.weight) for unit in short.units] == [("k1|0", 1.0)]


def test_the_days_are_the_first_week_of_digests_with_sentences_from_measure_from(
    store: Store,
) -> None:
    days = [(NOW + timedelta(days=n)).date().isoformat() for n in range(10)]
    for day in days:
        # The fourth day's digest was empty: nothing passed the rubric.
        stories = () if day == days[3] else (_story("k1", ["one"], "a"),)
        store.save_digest(_digest(day, stories))
    assert sample_days(store, "test-audience", days[2]) == [days[2], *days[4 : 4 + DAYS - 1]]
    assert sample_days(store, "test-audience", None) == [*days[:3], *days[4 : 4 + DAYS - 3]]


def test_the_page_shows_what_the_summariser_read_with_the_quote_and_numbers_marked(
    faith_ws: Workspace, audience: Audience
) -> None:
    status, page = call(faith_ws, "GET", f"/faithfulness/day?audience={audience.id}&day={DAY}")
    text = page.decode()
    assert status.startswith("200"), text
    # This fixture's draw holds k1's first sentence and k2's, whose source is gone.
    assert "k1|0" in text and "k2|0" in text
    assert "<mark>keeps the city moving</mark>" in text
    assert "<mark>9</mark> to <mark>4</mark>" in text
    # The 9 and the 4 of the sentence are not marked inside other numbers.
    assert "<mark>2027</mark>" not in text and "202<mark>" not in text
    assert "Deleted after thirty days" in text


def _keys(page: bytes) -> list[str]:
    return [part.split('"', 1)[0] for part in page.decode().split('data-id="')[1:]]


def test_saving_records_a_verdict_for_every_sentence_with_its_words_and_links(
    faith_ws: Workspace, audience: Audience
) -> None:
    _, page = call(faith_ws, "GET", f"/faithfulness/day?audience={audience.id}&day={DAY}")
    keys = _keys(page)
    assert len(keys) == PER_DAY
    verdicts = {key: "supported" for key in keys}
    verdicts[keys[0]] = "unsupported"
    payload = {"token": faith_ws.token, "audience": audience.id, "day": DAY, "verdicts": verdicts}
    status, reply = call(faith_ws, "POST", "/faithfulness/save", payload)
    assert status.startswith("200"), reply
    labels = faith_ws.labels.faith_labels_for(audience.id, DAY, "peter")
    assert {f"{label.story_id}|{label.sentence}": label.verdict for label in labels} == verdicts
    assert all(label.text and label.headline and label.cited_urls for label in labels)
    assert all(label.weight == pytest.approx(5 / PER_DAY) for label in labels)
    assert faith_ws.next_open_faith_day() is None


def test_a_partial_tokenless_or_unanswered_save_is_refused(
    faith_ws: Workspace, audience: Audience
) -> None:
    _, page = call(faith_ws, "GET", f"/faithfulness/day?audience={audience.id}&day={DAY}")
    keys = _keys(page)
    base = {"audience": audience.id, "day": DAY}
    whole = {key: "supported" for key in keys}
    assert call(faith_ws, "POST", "/faithfulness/save", {**base, "verdicts": whole})[0].startswith(
        "403"
    )
    for verdicts in ({key: "supported" for key in keys[1:]}, {**whole, keys[0]: ""}):
        payload = {**base, "token": faith_ws.token, "verdicts": verdicts}
        assert call(faith_ws, "POST", "/faithfulness/save", payload)[0].startswith("400")
    assert faith_ws.labels.faith_labels_for() == []


def _label(day: str, n: int, verdict: Verdict, weight: float = 1.0) -> FaithLabel:
    return FaithLabel(
        audience_id="a",
        day=day,
        story_id="k",
        sentence=n,
        labeller="peter",
        verdict=verdict,
        weight=weight,
        text=f"Sentence {n}.",
        headline="Headline",
        cited_urls=("https://gov.example/a",),
        labelled_at=NOW,
    )


def test_faithfulness_weights_days_by_their_sentences_and_leaves_out_cant_tell() -> None:
    # Day 1: 4 judged of 12 shown, all supported. Day 2: 2 judged of 4 shown, one supported,
    # and a third it was not possible to check.
    labels = [_label("d1", n, "supported", 3.0) for n in range(4)]
    labels += [
        _label("d2", 0, "supported", 2.0),
        _label("d2", 1, "unsupported", 2.0),
        _label("d2", 2, "unclear", 2.0),
    ]
    estimate = faithfulness(labels, "peter")
    # (3 x 4 + 2 x 1) / (3 x 4 + 2 x 2): 14 of 16 weighted sentences.
    assert estimate.point == pytest.approx(14 / 16)
    assert estimate.n == 6 and estimate.clusters == 2
    assert estimate.lo < estimate.point <= estimate.hi


def test_all_supported_is_not_printed_as_a_certainty() -> None:
    labels = [_label(f"d{day}", n, "supported") for day in range(5) for n in range(4)]
    estimate = faithfulness(labels, "peter")
    assert estimate.point == 1.0 and estimate.lo < 1.0


def test_the_report_fills_the_faithfulness_cell_and_lists_what_was_not_supported(
    faith_ws: Workspace, audience: Audience
) -> None:
    before = build_report(faith_ws.store, [], [audience], "peter")
    assert f"{NOT_YET} (hand check)" in readme_tables(before)
    labels = [
        _label(DAY, 0, "supported").model_copy(update={"audience_id": audience.id}),
        _label(DAY, 1, "unsupported").model_copy(update={"audience_id": audience.id}),
        _label(DAY, 2, "unclear").model_copy(update={"audience_id": audience.id}),
    ]
    report = build_report(faith_ws.store, [], [audience], "peter", faith_labels=labels)
    tables = readme_tables(report)
    assert "(hand check)" not in tables and "50% (" in tables and ", 2 sentences" in tables
    assert "1 more could not be checked" in tables
    assert "1 of 2 were judged not supported" in tables
    assert "Sentence 1. Cited: <https://gov.example/a>" in detail(report)
