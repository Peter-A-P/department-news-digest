"""The Bluesky pick: only posts with no news story, popular enough, and wanted by the rubric."""

from __future__ import annotations

from clippings.config.audience import Audience
from clippings.gateway import ModelCall, ModelCallFailed, ModelReply, ScriptedClient
from clippings.models import Cluster, Item
from clippings.rank.spotlight import MIN_LIKES, candidates, pick, quote
from tests.conftest import item


def post(item_id: str, likes: int, text: str = "A post about the budget vote") -> Item:
    return item(item_id, text, summary=text, domain="bsky.app").model_copy(
        update={"source_kind": "bluesky", "score": likes, "comments": 1, "author": item_id}
    )


def story(cluster_id: str, *members: Item) -> Cluster:
    return Cluster(
        id=cluster_id,
        audience_id="test-audience",
        day="2026-09-12",
        representative_id=members[0].id,
        item_ids=tuple(m.id for m in members),
    )


def test_candidates_are_unattached_popular_posts_most_engaged_first() -> None:
    news, attached = item("n", "Council passes budget"), post("p0", 500)
    quiet, popular, busier = post("p1", MIN_LIKES - 1), post("p2", 40), post("p3", 90)
    items = {i.id: i for i in (news, attached, quiet, popular, busier)}
    clusters = [
        story("k0", news, attached),  # inside a news story: commentary, not a pick
        story("k1", quiet),
        story("k2", popular),
        story("k3", busier),
    ]
    assert [p.id for p in candidates(clusters, items)] == ["p3", "p2"]


def test_the_pick_is_the_most_engaged_post_the_rubric_wants(audience: Audience) -> None:
    first, second = post("p1", 90), post("p2", 40)
    items = {i.id: i for i in (first, second)}
    clusters = [story("k1", first), story("k2", second)]
    reply = (
        '{"id": "c01", "score": 1, "reason": "a joke"}\n{"id": "c02", "score": 2, "reason": "r"}'
    )
    chosen = pick(audience, clusters, items, ScriptedClient(lambda call: reply), run_id="r")
    assert chosen.item is not None and chosen.item.id == "p2" and chosen.score == 2


def test_nothing_qualifies_and_nothing_is_shown(audience: Audience) -> None:
    only = post("p1", 90)
    reply = '{"id": "c01", "score": 1, "reason": "marginal"}'
    chosen = pick(
        audience, [story("k1", only)], {"p1": only}, ScriptedClient(lambda c: reply), run_id="r"
    )
    assert chosen.item is None and chosen.reply is not None


class Failing:
    name = "failing"

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply:
        raise ModelCallFailed("upstream 529")


def test_a_failed_call_leaves_the_section_out(audience: Audience) -> None:
    only = post("p1", 90)
    chosen = pick(audience, [story("k1", only)], {"p1": only}, Failing(), run_id="r")
    assert chosen.item is None and "529" in chosen.error


def test_the_quote_is_the_post_s_own_words_and_at_most_twenty_five() -> None:
    text = " ".join(f"word{n}" for n in range(40))
    shown = quote(text)
    assert shown.endswith(" ...")
    words = shown.removesuffix(" ...").split()
    assert len(words) == 25 and " ".join(words) in text
