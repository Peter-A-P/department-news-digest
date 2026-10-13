"""Clustering: near-duplicates, stories, and what the numbers mean."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import timedelta

from clippings.cluster.cluster import (
    build_clusters,
    cluster_id,
    collapse_rate,
    fresh_stories,
    representative,
)
from clippings.cluster.embed import Hashing, Vector, cosine
from clippings.cluster.metrics import pairs_within, purity, score_pairs
from clippings.cluster.shingles import (
    connected_components,
    near_duplicates,
    shingles,
    signature,
    similarity,
)
from clippings.config.audience import Audience
from clippings.models import Cluster, Item
from tests.conftest import NOW, item

WIRE = (
    "The regulator said on Tuesday it would open a consultation on automated decision "
    "systems used by federal departments, with submissions closing in November."
)
# The same wire copy with the lead rewritten and a clause cut, which is what an outlet does.
WIRE_REPRINTED = (
    "The regulator said on Tuesday it would open a consultation on automated decision "
    "systems used by federal departments."
)
UNRELATED = (
    "A municipal transit agency announced a new bus route serving the eastern suburbs "
    "from next spring, subject to budget approval."
)


def test_a_signature_is_stable_across_runs() -> None:
    """Stored clusters are meaningless if the hashing changes between runs."""
    assert signature(WIRE) == signature(WIRE)


def test_shingles_of_very_short_text_are_not_empty() -> None:
    assert shingles("two words") == frozenset({"two words"})
    assert shingles("") == frozenset()


def test_reprinted_wire_copy_is_a_near_duplicate() -> None:
    assert similarity(signature(WIRE), signature(WIRE_REPRINTED)) >= 0.7


def test_unrelated_text_is_not_a_near_duplicate() -> None:
    assert similarity(signature(WIRE), signature(UNRELATED)) < 0.3


def test_near_duplicates_finds_the_pair_and_nothing_else() -> None:
    pairs = near_duplicates({"a": WIRE, "b": WIRE_REPRINTED, "c": UNRELATED})
    assert pairs == {("a", "b")}


def test_connected_components_chains_transitively() -> None:
    """A reports the announcement, B reports A, C reports B: one story."""
    groups = connected_components(["a", "b", "c", "d"], [("a", "b"), ("b", "c")])
    assert sorted(groups, key=len) == [["d"], ["a", "b", "c"]]


def test_a_cluster_id_does_not_depend_on_the_order_of_its_items() -> None:
    assert cluster_id(["b", "a"]) == cluster_id(["a", "b"])


def test_the_representative_is_the_earliest_trusted_item(audience: Audience) -> None:
    """A department is linked to the regulator's own notice, not an outlet's summary."""
    trusted_later = item("trusted", domain="gov.example", published_at=NOW)
    untrusted_earlier = item("outlet", domain="news.example", published_at=NOW - timedelta(hours=3))
    assert representative([untrusted_earlier, trusted_later], audience).id == "trusted"


def test_the_representative_falls_back_to_the_earliest(audience: Audience) -> None:
    first = item("first", domain="news.example", published_at=NOW - timedelta(hours=3))
    second = item("second", domain="other.example", published_at=NOW)
    assert representative([second, first], audience).id == "first"


def test_reprinted_copy_lands_in_one_cluster(audience: Audience) -> None:
    items = [
        item("wire", "Regulator opens consultation", summary=WIRE),
        item("reprint", "Regulator to open consultation", summary=WIRE_REPRINTED),
        item("other", "New bus route announced", summary=UNRELATED),
    ]
    clusters = build_clusters(items, audience, Hashing(), "2026-09-12")
    sizes = sorted(cluster.size for cluster in clusters)
    assert sizes == [1, 2]
    biggest = max(clusters, key=lambda cluster: cluster.size)
    assert set(biggest.item_ids) == {"wire", "reprint"}


def test_an_empty_day_produces_no_clusters(audience: Audience) -> None:
    assert build_clusters([], audience, Hashing(), "2026-09-12") == []


def test_every_item_ends_up_in_exactly_one_cluster(audience: Audience) -> None:
    items = [item(f"i{index}", f"Headline number {index}") for index in range(12)]
    clusters = build_clusters(items, audience, Hashing(), "2026-09-12")
    assigned = [item_id for cluster in clusters for item_id in cluster.item_ids]
    assert sorted(assigned) == sorted(one.id for one in items)


def test_clusters_round_trip_through_the_store(audience: Audience, store) -> None:  # type: ignore[no-untyped-def]
    items = [item("a", summary=WIRE), item("b", summary=WIRE_REPRINTED)]
    clusters = build_clusters(items, audience, Hashing(), "2026-09-12")
    store.save_clusters(clusters)
    assert store.clusters_for(audience.id, "2026-09-12") == clusters


def test_saving_clusters_again_replaces_the_day_rather_than_appending(audience, store) -> None:  # type: ignore[no-untyped-def]
    store.save_clusters(build_clusters([item("a")], audience, Hashing(), "2026-09-12"))
    store.save_clusters(build_clusters([item("b")], audience, Hashing(), "2026-09-12"))
    saved = store.clusters_for(audience.id, "2026-09-12")
    assert [cluster.item_ids for cluster in saved] == [("b",)]


def test_the_hashing_embedder_returns_unit_vectors() -> None:
    vectors = Hashing().embed(["a headline about transit", "another about health"])
    for vector in vectors:
        assert abs(cosine(vector, vector) - 1.0) < 1e-9


def test_the_collapse_rate_is_items_per_story() -> None:
    assert collapse_rate(60, 20) == 3.0
    assert collapse_rate(0, 0) == 0.0


def test_pairwise_scores_against_labelled_pairs() -> None:
    clusters = [
        Cluster(
            id="c1", audience_id="a", day="2026-09-12", representative_id="x", item_ids=("x", "y")
        ),
        Cluster(id="c2", audience_id="a", day="2026-09-12", representative_id="z", item_ids=("z",)),
    ]
    labels = {
        ("x", "y"): True,  # together, and should be: a hit
        ("x", "z"): True,  # apart, and should be together: a miss
        ("y", "z"): False,  # apart, and should be: correct
    }
    scores = score_pairs(clusters, labels)
    assert (scores.true_positives, scores.false_negatives, scores.true_negatives) == (1, 1, 1)
    assert scores.precision == 1.0
    assert scores.recall == 0.5
    assert scores.labelled == 3


def test_unlabelled_pairs_are_not_counted_as_negatives() -> None:
    """Only the sample is scored; everything else is unlabelled, not wrong."""
    clusters = [
        Cluster(
            id="c1", audience_id="a", day="2026-09-12", representative_id="x", item_ids=("x", "y")
        )
    ]
    assert score_pairs(clusters, {}).labelled == 0


def test_pairs_within_enumerates_each_pair_once() -> None:
    clusters = [
        Cluster(
            id="c",
            audience_id="a",
            day="2026-09-12",
            representative_id="x",
            item_ids=("x", "y", "z"),
        )
    ]
    assert pairs_within(clusters) == {("x", "y"), ("x", "z"), ("y", "z")}


def test_purity_counts_the_majority_story_in_each_cluster() -> None:
    clusters = [
        Cluster(
            id="c",
            audience_id="a",
            day="2026-09-12",
            representative_id="x",
            item_ids=("x", "y", "z"),
        )
    ]
    assert purity(clusters, {"x": "s1", "y": "s1", "z": "s2"}) == 2 / 3
    assert purity(clusters, {}) == 0.0


class Placed:
    """An embedder that puts each text where the test says, by the first word of its title."""

    dimensions = 2

    def __init__(self, angles: dict[str, float]) -> None:
        self.angles = angles

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        return [
            (math.cos(self.angles[text.split()[0]]), math.sin(self.angles[text.split()[0]]))
            for text in texts
        ]


def post(item_id: str, title: str) -> Item:
    return item(item_id, title, domain="bsky.app").model_copy(update={"source_kind": "bluesky"})


def test_posts_do_not_chain_an_unrelated_post_into_a_story(audience: Audience) -> None:
    """News, a post close to it, and a post close only to that post: the second stays out.

    The shape of 2026-10-08, when posts about AI regulation reached OpenAI's mathematics
    story one post at a time and one was listed as its source.
    """
    # cos(0.5) = 0.88 between neighbours; cos(1.0) = 0.54 from the news item to the far post.
    embedder = Placed({"News": 0.0, "Near": 0.5, "Far": 1.0})
    items = [item("n", "News headline"), post("p1", "Near post"), post("p2", "Far post")]
    clusters = build_clusters(items, audience, embedder, "2026-09-12")
    groups = sorted(sorted(cluster.item_ids) for cluster in clusters)
    assert groups == [["n", "p1"], ["p2"]]


def test_a_post_close_to_two_stories_joins_one_and_does_not_merge_them(
    audience: Audience,
) -> None:
    # Two news items 0.80 apart (separate stories); the post sits between, nearer the first.
    embedder = Placed({"First": 0.0, "Second": 0.64, "Between": 0.30})
    items = [item("a", "First headline"), item("b", "Second headline"), post("p", "Between")]
    clusters = build_clusters(items, audience, embedder, "2026-09-12")
    groups = sorted(sorted(cluster.item_ids) for cluster in clusters)
    assert groups == [["a", "p"], ["b"]]


def _story(cluster_id_: str, *members: Item) -> Cluster:
    return Cluster(
        id=cluster_id_,
        audience_id="test",
        day="2026-10-12",
        representative_id=members[0].id,
        item_ids=tuple(member.id for member in members),
    )


def test_a_story_an_earlier_digest_could_show_is_left_out_and_a_new_report_heads_its_story(
    audience: Audience,
) -> None:
    yesterday = NOW - timedelta(hours=30)
    old = item("old", published_at=yesterday)
    follow_up = item("new", published_at=NOW)
    only_old = item("older", published_at=yesterday)
    post = item("post", published_at=yesterday).model_copy(update={"source_kind": "bluesky"})
    stories = [_story("continued", old, follow_up), _story("repeat", only_old), _story("p", post)]
    items = {member.id: member for member in (old, follow_up, only_old, post)}

    kept, stale = fresh_stories(stories, items, audience, since=NOW - timedelta(hours=24))

    assert stale == {"repeat"}
    by_id = {story.id: story for story in kept}
    # The story that gained a report is shown under the new report's headline, not yesterday's.
    assert by_id["continued"].representative_id == "new"
    # A story of posts alone is never a candidate either way, and the post pick still reads it.
    assert by_id["p"].representative_id == "post"
    # With no earlier digest, the first day shows everything.
    assert fresh_stories(stories, items, audience, since=None)[1] == set()
