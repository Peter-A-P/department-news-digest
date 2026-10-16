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
    assert [(one.item.id, one.score) for one in chosen.picks] == [("p2", 2)]


def test_nothing_qualifies_and_nothing_is_shown(audience: Audience) -> None:
    only = post("p1", 90)
    reply = '{"id": "c01", "score": 1, "reason": "marginal"}'
    chosen = pick(
        audience, [story("k1", only)], {"p1": only}, ScriptedClient(lambda c: reply), run_id="r"
    )
    assert chosen.picks == () and chosen.reply is not None


class Failing:
    name = "failing"

    def complete(self, call: ModelCall, *, run_id: str) -> ModelReply:
        raise ModelCallFailed("upstream 529")


def test_a_failed_call_leaves_the_section_out(audience: Audience) -> None:
    only = post("p1", 90)
    chosen = pick(audience, [story("k1", only)], {"p1": only}, Failing(), run_id="r")
    assert chosen.picks == () and "529" in chosen.error


def test_the_quote_is_the_post_s_own_words_and_at_most_twenty_five() -> None:
    text = " ".join(f"word{n}" for n in range(40))
    shown = quote(text)
    assert shown.endswith(" ...")
    words = shown.removesuffix(" ...").split()
    assert len(words) == 25 and " ".join(words) in text


def test_several_picks_are_the_most_engaged_wanted_posts_one_per_author() -> None:
    from clippings.rank.spotlight import Scored

    scored = Scored(((3, "a"), (2, "b"), (1, "c"), (2, "d"), (3, "e")), None)
    # The second post is by the first post's author, so it is one voice and is passed over.
    assert scored.best(["ana", "ana", "bo", "cy", "dee"], count=2) == [0, 3]
    assert scored.best(["ana", "bo", "cy", "dee", "eve"], count=1) == [0]


def test_a_digest_stored_with_one_pick_of_each_loads_as_a_list_of_one() -> None:
    from clippings.assemble.digest import Digest
    from tests.test_deletions import pick as bluesky_pick
    from tests.test_delivery import digest

    stored = digest().model_dump(mode="json")
    del stored["spotlights"], stored["x_picks"]
    stored["spotlight"] = bluesky_pick().model_dump(mode="json")
    stored["x_pick"] = None
    loaded = Digest.model_validate(stored)
    assert len(loaded.spotlights) == 1 and loaded.x_picks == ()
