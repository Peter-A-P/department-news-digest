"""The audience file is the product, so a bad one fails at load."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from clippings.config.audience import Audience
from clippings.config.load import EXAMPLES, AudienceFileError, load_audience, load_audiences

MINIMAL = {
    "id": "an-audience",
    "name": "An audience",
    "description": "What this audience is.",
    "rubric": (
        "Relevant means an item this audience would need before its next meeting, and "
        "nothing that merely mentions the topic."
    ),
    "topics": ["a topic"],
}


def test_an_unknown_field_is_rejected() -> None:
    """A typo must not silently change what a department reads."""
    with pytest.raises(ValidationError, match="topic"):
        Audience.model_validate(MINIMAL | {"topic": ["a topic"]})


def test_an_unknown_field_deep_in_the_file_is_rejected() -> None:
    with pytest.raises(ValidationError, match="max_storys"):
        Audience.model_validate(MINIMAL | {"digest": {"max_storys": 5}})


def test_an_audience_needs_at_least_one_topic() -> None:
    with pytest.raises(ValidationError, match="at least one topic"):
        Audience.model_validate(MINIMAL | {"topics": []})


def test_a_placeholder_rubric_is_rejected() -> None:
    """The rubric is published with the numbers; 'stuff we care about' is not a rubric."""
    with pytest.raises(ValidationError, match="at least ten words"):
        Audience.model_validate(MINIMAL | {"rubric": "things we care about"})


def test_a_domain_cannot_be_both_trusted_and_blocked() -> None:
    with pytest.raises(ValidationError, match="both trusted and blocked"):
        Audience.model_validate(
            MINIMAL | {"trusted_sources": ["a.example"], "blocked_sources": ["a.example"]}
        )


def test_a_source_must_be_a_bare_domain() -> None:
    with pytest.raises(ValidationError, match="not a bare domain"):
        Audience.model_validate(MINIMAL | {"trusted_sources": ["https://a.example/news"]})


def test_a_feed_must_be_https() -> None:
    with pytest.raises(ValidationError, match="must be https"):
        Audience.model_validate(
            MINIMAL
            | {
                "sources": {
                    "feeds": [
                        {"url": "http://a.example/rss", "publisher": "A", "terms": "a.example"}
                    ]
                }
            }
        )


def test_the_digest_cannot_ask_for_more_stories_than_the_model_ever_sees() -> None:
    with pytest.raises(ValidationError, match="at least max_stories"):
        Audience.model_validate(MINIMAL | {"digest": {"max_stories": 40, "rerank_candidates": 10}})


def test_an_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown timezone"):
        Audience.model_validate(MINIMAL | {"delivery": {"timezone": "Mars/Olympus_Mons"}})


def test_the_file_name_must_match_the_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "something-else.yaml"
    path.write_text(yaml.safe_dump(MINIMAL), encoding="utf-8")
    with pytest.raises(AudienceFileError, match="the file name is the audience id"):
        load_audience(path)


def test_the_example_audiences_load() -> None:
    audiences = load_audiences(EXAMPLES)
    assert {audience.id for audience in audiences} == {
        "ai",
        "public-health-canada",
        "municipal-toronto",
        "newfoundland-labrador",
    }


def test_every_example_audience_has_a_rubric_and_sources() -> None:
    for audience in load_audiences(EXAMPLES):
        assert len(audience.rubric.split()) >= 30, f"{audience.id}: rubric is too thin to label by"
        assert audience.sources.feeds, f"{audience.id}: no feeds"
        for feed in audience.sources.feeds:
            # Every feed in the repository has been fetched at least once and returned
            # entries; `clippings sources probe` is what checks that, and six of the
            # original thirteen did not. A URL nobody has fetched is a guess.
            assert feed.url.startswith("https://"), f"{audience.id}: {feed.url}"
        assert audience.profile_text(), f"{audience.id}: nothing to embed as a profile"


@pytest.mark.parametrize(
    "query",
    ['"large language model" OR "generative AI"', 'Canada outbreak OR "public health"'],
)
def test_a_gdelt_or_outside_parentheses_is_rejected_at_load(query: str) -> None:
    from clippings.config.audience import GdeltSource

    with pytest.raises(ValidationError, match="parentheses"):
        GdeltSource(queries=(query,))


def test_a_gdelt_or_inside_parentheses_or_quotes_is_accepted() -> None:
    from clippings.config.audience import GdeltSource

    GdeltSource(queries=('("large language model" OR "generative AI")', '"rock OR roll" band'))
