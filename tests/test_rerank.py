"""The re-ranker: it reads the rubric, it sees only the slice, and it fails safe."""

from __future__ import annotations

from datetime import timedelta

from clippings.config.audience import Audience
from clippings.gateway import ModelCall, ModelCallFailed, ModelReply, ScriptedClient
from clippings.models import Cluster
from clippings.rank.features import Features
from clippings.rank.rerank import blend, build_call, local_ids, parse_scores, rerank
from clippings.rank.score import ScoredStory
from tests.conftest import NOW, item


def story(index: int, score: float, title: str = "") -> ScoredStory:
    rep = item(f"i{index}", title or f"Headline {index}", published_at=NOW - timedelta(hours=index))
    features = Features(0.5, 0.5, 0.5, 0.6, 0.5, 0.0)
    cluster = Cluster(
        id=f"k{index:02d}",
        audience_id="test-audience",
        day="2026-09-12",
        representative_id=rep.id,
        item_ids=(rep.id,),
    )
    return ScoredStory(cluster=cluster, representative=rep, features=features, score=score)


def lines(*scores: tuple[str, int]) -> str:
    return "\n".join(f'{{"id": "{i}", "score": {s}, "reason": "r"}}' for i, s in scores)


def test_the_model_is_shown_the_rubric_and_only_the_slice(audience: Audience) -> None:
    candidates = [story(index, 0.9 - index / 100) for index in range(5)]
    call = build_call(audience, candidates[:3])
    assert audience.rubric.strip() in call.user
    assert "Headline 2" in call.user
    assert "Headline 3" not in call.user
    assert sum(1 for line in call.user.splitlines() if line.startswith("c0")) == 3


def test_a_story_the_rubric_excludes_is_never_selectable(audience: Audience) -> None:
    candidates = [story(0, 0.9, "Fatal collision"), story(1, 0.5, "Council budget")]
    client = ScriptedClient(lambda call: lines(("c01", 0), ("c02", 3)))
    result = rerank(audience, candidates, client, run_id="r")
    assert result.reranked
    assert [s.representative.title for s in result.stories] == ["Council budget", "Fatal collision"]
    assert [s.representative.title for s in result.selectable()] == ["Council budget"]
    assert result.excluded == 1


def test_the_model_decides_and_the_prefilter_breaks_ties(audience: Audience) -> None:
    candidates = [story(0, 0.9), story(1, 0.4), story(2, 0.6)]
    client = ScriptedClient(lambda call: lines(("c01", 1), ("c02", 2), ("c03", 2)))
    result = rerank(audience, candidates, client, run_id="r")
    assert [s.id for s in result.stories] == ["k02", "k01", "k00"]


def test_unknown_ids_bad_scores_and_repeats_are_ignored() -> None:
    text = "\n".join(
        [
            '{"id": "c01", "score": 3}',
            '{"id": "c01", "score": 0}',  # a second score for the same id: the first wins
            '{"id": "c99", "score": 3}',  # not offered
            '{"id": "c02", "score": 7}',  # off the scale
            '{"id": "c03", "score": true}',  # not a number
            '{"id": "c04", "score": 2.5}',  # not on the scale
            "not json at all {",
        ]
    )
    assert parse_scores(text, set(local_ids(4))) == {"c01": (3, "")}


def test_a_candidate_the_model_skipped_keeps_its_place_below_the_relevant(
    audience: Audience,
) -> None:
    candidates = [story(0, 0.95), story(1, 0.2), story(2, 0.9)]
    client = ScriptedClient(lambda call: lines(("c02", 2), ("c03", 0)))
    result = rerank(audience, candidates, client, run_id="r")
    assert [s.id for s in result.stories] == ["k01", "k00", "k02"]
    assert result.unscored == 1
    assert blend(None, 0.95) < blend(1, 0.0)


class FailingClient:
    name = "failing"

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply:
        raise ModelCallFailed("upstream 529")


def test_a_failed_call_falls_back_to_the_prefilter_and_says_so(audience: Audience) -> None:
    candidates = [story(0, 0.9), story(1, 0.5)]
    result = rerank(audience, candidates, FailingClient(), run_id="r")
    assert not result.reranked
    assert "529" in result.error
    assert [s.id for s in result.selectable()] == ["k00", "k01"]


def test_a_reply_with_no_usable_scores_is_a_failure_not_an_empty_digest(
    audience: Audience,
) -> None:
    candidates = [story(0, 0.9)]
    result = rerank(audience, candidates, ScriptedClient(lambda call: "I cannot help"), run_id="r")
    assert not result.reranked
    assert [s.id for s in result.selectable()] == ["k00"]


def test_a_minimum_score_leaves_out_the_marginal_and_the_unscored(audience: Audience) -> None:
    candidates = [story(0, 0.9), story(1, 0.8), story(2, 0.7), story(3, 0.6)]
    client = ScriptedClient(lambda call: lines(("c01", 3), ("c02", 1), ("c03", 2)))
    result = rerank(audience, candidates, client, run_id="r")
    assert result.reranked
    assert {s.id for s in result.selectable(2)} == {"k00", "k02"}
    # At the default, marginal and unscored stay in, as before.
    assert {s.id for s in result.selectable()} == {"k00", "k01", "k02", "k03"}
