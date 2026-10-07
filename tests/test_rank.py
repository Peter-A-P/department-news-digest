"""Ranking: the features, the score they combine into, and what gets selected."""

from __future__ import annotations

from datetime import timedelta

import pytest

from clippings.cluster.cluster import build_clusters
from clippings.cluster.embed import Hashing
from clippings.config.audience import Audience
from clippings.models import Cluster
from clippings.rank.features import (
    RECENCY_HALF_LIFE_HOURS,
    audience_vectors,
    corroboration,
    embed_stories,
    features_for,
    phrase_hits,
    recency,
    story_text,
)
from clippings.rank.score import WEIGHTS, ScoredStory, combine, score_stories
from clippings.rank.select import candidates_for_rerank, select
from tests.conftest import NOW, item


def cluster(*item_ids: str, cluster_id: str = "c1", audience_id: str = "test-audience") -> Cluster:
    return Cluster(
        id=cluster_id,
        audience_id=audience_id,
        day="2026-09-13",
        representative_id=item_ids[0],
        item_ids=item_ids,
    )


# -- features -----------------------------------------------------------------------------


def test_phrase_hits_scores_the_best_matching_phrase() -> None:
    """A story is relevant because it is about one concern, not slightly about all of them.

    An average over topics would score a story that nails one topic at a tenth, which is
    indistinguishable from one that grazes several and is about none.
    """
    text = "The House of Assembly met to discuss the fishery."
    assert phrase_hits(text, ("House of Assembly", "Memorial University")) == 1.0
    assert phrase_hits(text, ("House of Assembly",)) == 1.0
    assert phrase_hits(text, ()) == 0.0


def test_a_phrase_gets_partial_credit_for_the_words_it_shares() -> None:
    """Exact phrase matching scored zero on 23 of 23 stories in the first live run."""
    # "transit service and expansion" against a headline about transit service changes:
    # two of the three content words are present.
    assert phrase_hits(
        "TTC service changes announced", ("transit service and expansion",)
    ) == pytest.approx(1 / 3)
    assert phrase_hits("A story about nothing relevant", ("municipal budget",)) == 0.0


def test_stop_words_are_not_what_makes_a_phrase_match() -> None:
    """'and' appears in everything and means nothing.

    Counting them would let a phrase match on its connectives: "transit and housing" would
    be half-matched by any text containing the word "and", which is all of them.
    """
    # Only the content word is missing, so the phrase does not match at all, even though
    # every one of its stop words is present in the text.
    assert phrase_hits("the news of the week and of the year", ("the budget of the day",)) == 0.0
    # A phrase made entirely of stop words has nothing to match on.
    assert phrase_hits("any text at all", ("and the of",)) == 0.0


def test_phrase_matching_survives_punctuation_and_case() -> None:
    assert phrase_hits("the HOUSE OF ASSEMBLY, yesterday", ("house of assembly",)) == 1.0


def test_word_order_does_not_matter() -> None:
    """Publishers write "the budget for the municipality", not the audience's phrasing."""
    assert phrase_hits("the municipal budget", ("budget municipal",)) == 1.0


def test_a_phrase_only_matches_whole_words() -> None:
    """'fish' must not match inside 'fisheries'."""
    assert phrase_hits("fisheries policy", ("fish",)) == 0.0
    assert phrase_hits("the fish quota", ("fish",)) == 1.0


def test_recency_halves_at_the_half_life() -> None:
    assert recency(NOW - timedelta(hours=RECENCY_HALF_LIFE_HOURS), NOW) == pytest.approx(0.5)
    assert recency(NOW, NOW) == 1.0


def test_recency_never_exceeds_one_for_a_future_date() -> None:
    """A publisher's clock can be wrong, and an undated feed is dated at fetch time."""
    assert recency(NOW + timedelta(hours=6), NOW) == 1.0


def test_recency_decays_but_stays_positive() -> None:
    week_old = recency(NOW - timedelta(days=7), NOW)
    assert 0.0 < week_old < 0.01


def test_corroboration_saturates() -> None:
    assert corroboration(1) == 0.0
    assert corroboration(3) > corroboration(2)
    assert corroboration(12) - corroboration(8) < corroboration(3) - corroboration(2)
    assert corroboration(100) < 1.0


def test_story_text_covers_every_item_not_just_the_representative(audience: Audience) -> None:
    """One outlet names the minister in the headline, another in the third paragraph."""
    items = {
        "a": item("a", "A headline"),
        "b": item("b", "Another headline", summary="Naming the regulator"),
    }
    text = story_text(cluster("a", "b"), items)
    assert "A headline" in text
    assert "Naming the regulator" in text


def test_features_are_all_within_range(audience: Audience) -> None:
    items = {"a": item("a", "A headline about testing", summary="Some words.")}
    embedder = Hashing()
    profile = audience_vectors(audience, embedder)
    one = cluster("a")
    features = features_for(
        one, items, audience, profile, embed_stories([one], items, embedder), NOW
    )
    for name, value in features.as_dict().items():
        assert 0.0 <= value <= 1.0, f"{name} out of range: {value}"


def test_a_trusted_source_scores_higher_than_an_untrusted_one(audience: Audience) -> None:
    embedder = Hashing()
    profile = audience_vectors(audience, embedder)
    scores = {}
    for domain in ("gov.example", "random.example"):
        items = {"a": item("a", "A headline", domain=domain)}
        one = cluster("a")
        scores[domain] = features_for(
            one, items, audience, profile, embed_stories([one], items, embedder), NOW
        ).source_trust
    assert scores["gov.example"] > scores["random.example"]


# -- score --------------------------------------------------------------------------------


def test_the_weights_sum_to_one() -> None:
    """So a score is in [0, 1] and two audiences' scores mean the same thing."""
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_every_feature_has_a_weight(audience: Audience) -> None:
    items = {"a": item("a")}
    embedder = Hashing()
    one = cluster("a")
    features = features_for(
        one,
        items,
        audience,
        audience_vectors(audience, embedder),
        embed_stories([one], items, embedder),
        NOW,
    )
    assert set(features.as_dict()) == set(WEIGHTS), "a feature with no weight is dead code"


def test_recency_is_worth_less_than_relevance() -> None:
    """A digest that ranks by freshness is a feed reader, and this is not a feed reader."""
    assert WEIGHTS["recency"] < WEIGHTS["audience_similarity"]
    assert WEIGHTS["recency"] < WEIGHTS["entity_hits"]


def test_a_more_relevant_story_outranks_a_fresher_irrelevant_one(audience: Audience) -> None:
    on_topic = item(
        "on",
        "Testing the thing this audience cares about",
        summary="testing testing",
        published_at=NOW - timedelta(hours=20),
    )
    off_topic = item("off", "An unrelated matter entirely", published_at=NOW)
    items = {"on": on_topic, "off": off_topic}
    clusters = [cluster("on", cluster_id="c-on"), cluster("off", cluster_id="c-off")]
    ranked = score_stories(clusters, items, audience, Hashing(), NOW)
    assert ranked[0].representative.id == "on"


def test_scoring_is_stable_across_runs(audience: Audience) -> None:
    """The labelling sample depends on the order not moving between runs."""
    items = {f"i{n}": item(f"i{n}", f"Headline {n}") for n in range(8)}
    clusters = [cluster(f"i{n}", cluster_id=f"c{n}") for n in range(8)]
    first = score_stories(clusters, items, audience, Hashing(), NOW)
    second = score_stories(clusters, items, audience, Hashing(), NOW)
    assert [s.id for s in first] == [s.id for s in second]


def test_a_story_whose_representative_was_deleted_is_skipped(audience: Audience) -> None:
    """Retention can remove an item between clustering and ranking."""
    ranked = score_stories([cluster("gone")], {}, audience, Hashing(), NOW)
    assert ranked == []


def test_an_empty_day_ranks_to_nothing(audience: Audience) -> None:
    assert score_stories([], {}, audience, Hashing(), NOW) == []


def test_why_names_the_features_that_mattered(audience: Audience) -> None:
    items = {"a": item("a", "Testing")}
    ranked = score_stories([cluster("a")], items, audience, Hashing(), NOW)
    explanation = ranked[0].why()
    assert explanation
    assert any(name.replace("_", " ") in explanation for name in WEIGHTS)


def test_combine_is_bounded(audience: Audience) -> None:
    items = {"a": item("a", "Testing " * 20, summary="testing")}
    embedder = Hashing()
    one = cluster("a")
    features = features_for(
        one,
        items,
        audience,
        audience_vectors(audience, embedder),
        embed_stories([one], items, embedder),
        NOW,
    )
    assert 0.0 <= combine(features) <= 1.0


# -- selection ----------------------------------------------------------------------------


def scored(story_id: str, score: float, domain: str = "a.example") -> ScoredStory:
    from clippings.rank.features import Features

    one = item(story_id, f"Headline {story_id}", domain=domain)
    return ScoredStory(
        cluster=cluster(story_id, cluster_id=story_id),
        representative=one,
        features=Features(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        score=score,
    )


def test_selection_takes_the_best_first() -> None:
    stories = [scored("a", 0.9), scored("b", 0.5), scored("c", 0.1)]
    chosen = select(stories, {}, k=2, diversity=0.0)
    assert [s.id for s in chosen.stories] == ["a", "b"]


def test_selection_never_returns_more_than_k() -> None:
    stories = [scored(f"s{n}", 1.0 - n / 100) for n in range(20)]
    assert len(select(stories, {}, k=5).stories) == 5


def test_k_larger_than_the_pool_returns_the_pool() -> None:
    stories = [scored("a", 0.9), scored("b", 0.5)]
    assert len(select(stories, {}, k=10).stories) == 2


def test_a_redundant_story_is_pushed_out_by_a_different_one() -> None:
    """The top scores on a day are often several angles on one event."""
    stories = [scored("a", 0.90), scored("b", 0.89), scored("c", 0.60)]
    vectors = {
        "a": (1.0, 0.0),
        "b": (1.0, 0.0),  # identical to a
        "c": (0.0, 1.0),  # unrelated
    }
    chosen = select(stories, vectors, k=2, diversity=0.5)
    assert [s.id for s in chosen.stories] == ["a", "c"]
    assert [s.id for s in chosen.displaced] == ["b"]


def test_zero_diversity_is_plain_top_k() -> None:
    stories = [scored("a", 0.90), scored("b", 0.89), scored("c", 0.60)]
    vectors = {"a": (1.0, 0.0), "b": (1.0, 0.0), "c": (0.0, 1.0)}
    chosen = select(stories, vectors, k=2, diversity=0.0)
    assert [s.id for s in chosen.stories] == ["a", "b"]
    assert chosen.displaced == ()


def test_one_publisher_cannot_crowd_out_the_others_when_there_is_a_choice() -> None:
    """The cap binds whenever there is something else to take."""
    stories = [scored(f"loud{n}", 1.0 - n / 100, domain="loud.example") for n in range(6)]
    stories += [scored(f"quiet{n}", 0.5 - n / 100, domain="quiet.example") for n in range(3)]
    chosen = select(stories, {}, k=4, diversity=0.0, max_per_domain=2)
    domains = [s.representative.domain for s in chosen.stories]
    assert domains.count("loud.example") == 2
    assert domains.count("quiet.example") == 2


def test_the_domain_cap_lifts_rather_than_shortening_the_digest() -> None:
    """A thin day is a real day.

    On a quiet Sunday one local outlet may be the only one publishing. Showing three
    stories out of eight available, because of a diversity rule, serves the reader worse
    than showing eight from one outlet: `max_stories` is a ceiling, and the cap is there to
    stop crowding out, not to ration a day that has only one source.
    """
    stories = [scored(f"s{n}", 1.0 - n / 100, domain="only.example") for n in range(5)]
    chosen = select(stories, {}, k=4, diversity=0.0, max_per_domain=2)
    assert len(chosen.stories) == 4
    assert {s.representative.domain for s in chosen.stories} == {"only.example"}


def test_the_cap_only_lifts_once_the_alternatives_are_exhausted() -> None:
    """It is a last resort, not a suggestion: the other publisher is taken first."""
    stories = [scored(f"loud{n}", 1.0 - n / 100, domain="loud.example") for n in range(6)]
    stories.append(scored("other", 0.01, domain="quiet.example"))
    chosen = select(stories, {}, k=4, diversity=0.0, max_per_domain=2)
    domains = [s.representative.domain for s in chosen.stories]
    assert len(chosen.stories) == 4
    assert "quiet.example" in domains
    assert domains.index("quiet.example") < 3, "the cap lifted before the alternative was used"


def test_the_rerank_slice_is_fixed_by_the_audience_file() -> None:
    """The cost control: model calls per day cannot drift upward as the pool grows."""
    stories = [scored(f"s{n}", 1.0 - n / 1000) for n in range(500)]
    assert len(candidates_for_rerank(stories, 60)) == 60
    assert len(candidates_for_rerank(stories[:10], 60)) == 10


def test_selection_of_an_empty_pool_is_empty() -> None:
    assert select([], {}, k=10).stories == ()


def test_clustered_stories_rank_and_select_end_to_end(audience: Audience) -> None:
    items = [
        item("a", "Testing the thing", summary="A long summary about testing the thing here."),
        item("b", "An unrelated bus route", summary="A transit agency named a new route today."),
        item("c", "Another testing matter", summary="More about testing, in different words."),
    ]
    by_id = {one.id: one for one in items}
    embedder = Hashing()
    clusters = build_clusters(items, audience, embedder, "2026-09-13")
    ranked = score_stories(clusters, by_id, audience, embedder, NOW)
    assert len(ranked) == len(clusters)
    chosen = select(ranked, embed_stories(clusters, by_id, embedder), k=2)
    assert 1 <= len(chosen.stories) <= 2
    assert all(s.representative.id in by_id for s in chosen.stories)


def test_diversity_reorders_within_a_rubric_tier_and_never_across_one() -> None:
    """First live run, 2026-10-07: two stories scored 1 by the re-ranker were placed above
    four it scored 2, because resemblance to a chosen story cost more than a rubric point."""
    from clippings.models import Cluster
    from clippings.rank.features import Features
    from clippings.rank.score import ScoredStory
    from clippings.rank.select import select
    from tests.conftest import item

    def story(name: str, score: float) -> ScoredStory:
        rep = item(name, domain=f"{name}.example")
        cluster = Cluster(
            id=name, audience_id="a", day="d", representative_id=rep.id, item_ids=(rep.id,)
        )
        return ScoredStory(cluster, rep, Features(0, 0, 0, 0, 0, 0), score)

    must, alike, unalike = story("must", 0.9), story("alike", 0.6), story("unalike", 0.4)
    vectors = {"must": (1.0, 0.0), "alike": (1.0, 0.0), "unalike": (0.0, 1.0)}
    tiers = {"must": 3.0, "alike": 2.0, "unalike": 1.0}

    untiered = select([must, alike, unalike], vectors, 2)
    assert [s.id for s in untiered.stories] == ["must", "unalike"]
    tiered = select([must, alike, unalike], vectors, 2, tiers=tiers)
    assert [s.id for s in tiered.stories] == ["must", "alike"]


def test_the_outlet_cap_does_not_pull_a_marginal_story_above_a_relevant_one() -> None:
    from clippings.models import Cluster
    from clippings.rank.features import Features
    from clippings.rank.score import ScoredStory
    from clippings.rank.select import select
    from tests.conftest import item

    def story(name: str, domain: str) -> ScoredStory:
        rep = item(name, domain=domain)
        cluster = Cluster(
            id=name, audience_id="a", day="d", representative_id=rep.id, item_ids=(rep.id,)
        )
        return ScoredStory(cluster, rep, Features(0, 0, 0, 0, 0, 0), 0.5)

    stories = [story(f"cbc{i}", "cbc.ca") for i in range(4)] + [story("other", "ntv.ca")]
    tiers = {"cbc0": 3.0, "cbc1": 3.0, "cbc2": 3.0, "cbc3": 2.0, "other": 1.0}
    vectors = {s.id: (1.0, 0.0) for s in stories}
    chosen = select(stories, vectors, 5, tiers=tiers, diversity=0.0, max_per_domain=3)
    assert [s.id for s in chosen.stories] == ["cbc0", "cbc1", "cbc2", "cbc3", "other"]
