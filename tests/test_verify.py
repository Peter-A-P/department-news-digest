"""The verifier against altered quotes, wrong citations and uncited sentences.

PLAN.md section 4's tests that matter: a quote altered by one word, a citation to an id
outside the cluster, and an uncited sentence are each refused. Each test below is built so
that it would pass if the check it names were removed, which is what makes it a test of that
check rather than of the fixture.
"""

from __future__ import annotations

import pytest

from clippings.constants import QUOTE_MAX_WORDS
from clippings.summarise.cite import CitedSentence, Source, StoryDraft, parse_draft
from clippings.summarise.verify import (
    Failure,
    contains_verbatim,
    numbers,
    verify_sentence,
    verify_story,
)
from tests.conftest import item

COUNCIL = (
    "Council voted 9-4 on Tuesday to approve the harbour plan. The mayor said the vote was "
    "\u201ca turning point for the waterfront\u201d and that work would start in spring. "
    "The plan costs $1,200,000 over three years."
)
FERRY = "Marine Atlantic said the crossing\u2019s schedule would return to normal on Friday."


def sources() -> dict[str, Source]:
    return {
        "s1": Source(
            sid="s1", item=item("a", "Council approves harbour plan"), text=COUNCIL, extracted=True
        ),
        "s2": Source(sid="s2", item=item("b", "Ferry schedule"), text=FERRY, extracted=False),
    }


def failures(text: str, *cites: str) -> set[Failure]:
    check = verify_sentence(CitedSentence(text=text, cites=cites), sources())
    return {finding.failure for finding in check.findings}


def test_a_verbatim_quote_with_its_citation_passes() -> None:
    assert failures('The mayor called it "a turning point for the waterfront".', "s1") == set()


def test_a_quote_altered_by_one_word_is_refused() -> None:
    assert failures('The mayor called it "a turning point for the harbour".', "s1") == {
        Failure.QUOTE_NOT_VERBATIM
    }


@pytest.mark.parametrize(
    "quote",
    [
        "a turning point for waterfront",  # a word dropped
        "a major turning point for the waterfront",  # a word added
        "a point turning for the waterfront",  # two words swapped
        "a turning point ... waterfront",  # an ellipsis: words left out
    ],
)
def test_any_change_inside_the_quotation_marks_is_refused(quote: str) -> None:
    assert Failure.QUOTE_NOT_VERBATIM in failures(f'He said "{quote}".', "s1")


def test_punctuation_shape_and_case_do_not_count_as_a_change() -> None:
    """Normalisation forgives a curly apostrophe, a line break and a capital, nothing more."""
    assert (
        failures('The operator said "the crossing\'s schedule would return\nto normal".', "s2")
        == set()
    )
    assert contains_verbatim(COUNCIL, "A Turning Point for the Waterfront")


def test_a_real_quote_attributed_to_the_wrong_source_is_refused() -> None:
    """The words exist in s1, but the sentence cites s2: that is a wrong citation."""
    assert failures('The mayor said "a turning point for the waterfront".', "s2") == {
        Failure.QUOTE_NOT_VERBATIM
    }


def test_a_citation_outside_the_story_is_refused() -> None:
    assert Failure.UNKNOWN_CITATION in failures("Council approved the harbour plan.", "s1", "s7")


def test_an_uncited_sentence_is_refused() -> None:
    assert failures("Council approved the harbour plan.") == {Failure.UNCITED}


def test_a_quote_over_twenty_five_words_is_refused_even_when_verbatim() -> None:
    long_source = " ".join(f"word{index}" for index in range(40))
    source = Source(sid="s1", item=item("c"), text=long_source, extracted=True)
    quote = " ".join(f"word{index}" for index in range(QUOTE_MAX_WORDS + 1))
    check = verify_sentence(
        CitedSentence(text=f'It read "{quote}".', cites=("s1",)), {"s1": source}
    )
    assert {finding.failure for finding in check.findings} == {Failure.QUOTE_TOO_LONG}

    exactly = " ".join(f"word{index}" for index in range(QUOTE_MAX_WORDS))
    check = verify_sentence(
        CitedSentence(text=f'It read "{exactly}".', cites=("s1",)), {"s1": source}
    )
    assert check.passed


def test_an_unpaired_quotation_mark_is_refused() -> None:
    assert Failure.UNBALANCED_QUOTES in failures('The mayor said "a turning point.', "s1")


def test_a_number_not_in_the_cited_source_is_refused() -> None:
    assert failures("Council voted 9-4 to approve the plan.", "s1") == set()
    assert failures("Council voted 8-4 to approve the plan.", "s1") == {
        Failure.NUMBER_NOT_IN_SOURCE
    }


def test_numbers_compare_without_their_separators() -> None:
    assert failures("The plan costs $1200000.", "s1") == set()
    assert numbers("1,200 people and 3.5 per cent in 2026.") == {"1200", "3.5", "2026"}


def test_the_story_check_counts_quotes_before_anything_is_dropped() -> None:
    draft = StoryDraft(
        "story",
        (
            CitedSentence('He said "a turning point for the waterfront".', ("s1",)),
            CitedSentence('He said "a turning point for the harbour".', ("s1",)),
            CitedSentence("No citation here.", ()),
        ),
    )
    check = verify_story(draft, list(sources().values()))
    assert (check.quotes, check.quotes_verbatim) == (2, 1)
    assert len(check.kept) == 1
    assert check.cited == 2


def test_the_parser_keeps_an_uncited_sentence_for_the_verifier_to_refuse() -> None:
    """A parser that silently dropped uncited sentences would hide the failure count."""
    draft = parse_draft(
        "story",
        'Here you go:\n```json\n{"sentences": [{"text": "One."}, {"text": "Two.", "sources": ["s1"]}]}\n```',
        max_sentences=3,
    )
    assert [sentence.cites for sentence in draft.sentences] == [(), ("s1",)]


def test_the_parser_cuts_to_the_length_budget_and_says_so() -> None:
    body = ", ".join(f'{{"text": "S{index}.", "sources": ["s1"]}}' for index in range(5))
    draft = parse_draft("story", f'{{"sentences": [{body}]}}', max_sentences=3)
    assert (len(draft.sentences), draft.over_budget) == (3, 2)


def test_curly_quotes_from_the_model_are_read_as_quotes() -> None:
    draft = parse_draft(
        "story",
        '{"sentences": [{"text": "He said \u201ca turning point for the harbour\u201d.", "sources": ["s1"]}]}',
        max_sentences=3,
    )
    check = verify_story(draft, list(sources().values()))
    assert [f.failure for f in check.checks[0].findings] == [Failure.QUOTE_NOT_VERBATIM]
