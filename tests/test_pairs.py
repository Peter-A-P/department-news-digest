"""Deduplication pairs: what is sampled, how the numbers are estimated, and the page that asks."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from clippings.cluster.metrics import pairs_within
from clippings.config.audience import Audience
from clippings.eval.label_ui import Workspace
from clippings.eval.pairs import overlap, pair_sample, pair_sample_for_day, words
from clippings.eval.report import NOT_YET, PairDay, build_report, dedup_scores, readme_tables
from clippings.ingest.store import Store
from clippings.models import Cluster, Item
from tests.conftest import NOW, item
from tests.test_label_ui import call

DAY = NOW.date().isoformat()

TITLES = {
    "a1": "Council passes transit budget, fares frozen for 2027",
    "a2": "Transit budget passes council with fares frozen",
    "b1": "Hospital opens new emergency wing in the east end",
    "b2": "New emergency wing opens at east end hospital",
    "c1": "Library extends weekend hours",
    "c2": "Snow plough contract awarded to local firm",
    "c3": "Water main break closes downtown street",
    "c4": "Ferry schedule changes for the winter season",
    "c5": "Province names new deputy health minister",
    "c6": "Arts grant program opens applications",
}


def _cluster(cluster_id: str, *item_ids: str) -> Cluster:
    return Cluster(
        id=cluster_id,
        audience_id="test-audience",
        day=DAY,
        representative_id=item_ids[0],
        item_ids=item_ids,
    )


# The clustering kept a1 and a2 together, and missed that b1 and b2 are one story.
CLUSTERS = [
    _cluster("A", "a1", "a2"),
    _cluster("B", "b1"),
    _cluster("C", "b2"),
    *(_cluster(f"C{n}", f"c{n}") for n in range(1, 7)),
]


def _items() -> dict[str, Item]:
    return {item_id: item(item_id, title) for item_id, title in TITLES.items()}


@pytest.fixture
def pair_store(store: Store) -> Store:
    store.add_items(_items().values(), "test-audience")
    store.save_clusters(CLUSTERS)
    return store


def test_strata_are_disjoint_and_each_is_what_it_says() -> None:
    items = _items()
    sample = pair_sample(CLUSTERS, items, "test-audience", DAY)
    together = pairs_within(CLUSTERS)
    seen = set()
    for unit in sample.units:
        pair = (unit.left_id, unit.right_id)
        assert unit.left_id < unit.right_id and pair not in seen
        seen.add(pair)
        assert unit.together == (pair in together)
        assert (unit.stratum == "together") == (pair in together)
    near = [unit for unit in sample.units if unit.stratum == "near"]
    assert near and all(
        overlap(words(items[u.left_id]), words(items[u.right_id])) > 0 for u in near
    )
    # The missed duplicate shares more words than any unrelated pair: it is in "near".
    assert sample.population["near"] >= 1
    all_near = pair_sample(CLUSTERS, items, "test-audience", DAY, near_n=100)
    assert ("b1", "b2") in {(u.left_id, u.right_id) for u in all_near.units if u.stratum == "near"}


def test_weights_are_population_over_drawn_and_the_sample_is_stable() -> None:
    items = _items()
    sample = pair_sample(CLUSTERS, items, "test-audience", DAY)
    for stratum, population in sample.population.items():
        drawn = [unit for unit in sample.units if unit.stratum == stratum]
        if drawn:
            assert drawn[0].weight == pytest.approx(population / len(drawn))
    assert sum(sample.population.values()) == len(items) * (len(items) - 1) // 2
    assert pair_sample(CLUSTERS, items, "test-audience", DAY) == sample


def test_posts_are_not_paired() -> None:
    items = _items()
    post = items["c1"].model_copy(update={"id": "p1", "source_kind": "bluesky"})
    items["p1"] = post
    clusters = [*CLUSTERS[:-1], _cluster("C6", "c6", "p1")]
    sample = pair_sample(clusters, items, "test-audience", DAY, near_n=100, check_n=100)
    assert all("p1" not in (unit.left_id, unit.right_id) for unit in sample.units)


def test_dedup_scores_against_hand_worked_numbers() -> None:
    """Day one: 4 of 5 together pairs are one story, each standing for 2; 1 of 6 near pairs
    is, each standing for 10. Found 8 of 10 put together; missed 10. Precision 0.8, recall
    8 / 18."""
    day = PairDay(
        day="d",
        together=(True, True, True, True, False),
        together_weight=2.0,
        near=(True, False, False, False, False, False),
        near_weight=10.0,
    )
    precision, recall = dedup_scores([day, day])
    assert precision.point == pytest.approx(0.8)
    assert recall.point == pytest.approx(8 / 18)
    assert recall.lo < recall.point < recall.hi


def test_no_missed_pair_found_is_not_recall_of_certainty() -> None:
    day = PairDay(
        "d", together=(True,) * 5, together_weight=1.0, near=(False,) * 6, near_weight=20.0
    )
    _, recall = dedup_scores([day])
    assert recall.point == 1.0 and recall.lo < 0.9


def test_saving_a_day_of_pairs_records_every_pair_with_what_it_stands_for(
    pair_store: Store, audience: Audience
) -> None:
    ws = Workspace(
        store=pair_store, labels=Store.memory(), labeller="peter", audiences={audience.id: audience}
    )
    status, page = call(ws, "GET", f"/pairs/day?audience={audience.id}&day={DAY}")
    assert status.startswith("200")
    text = page.decode()
    # The clustering's decision and the strata are not shown.
    assert "together" not in text and "near" not in text.replace("nearest", "")
    keys = [part.split('"', 1)[0] for part in text.split('data-id="')[1:]]
    sample = pair_sample_for_day(pair_store, audience.id, DAY)
    assert len(keys) == len(sample.units)
    status, reply = call(
        ws,
        "POST",
        "/pairs/save",
        {"token": ws.token, "audience": audience.id, "day": DAY, "same": keys[:1], "shown": keys},
    )
    assert status.startswith("200"), reply
    assert json.loads(reply)["next"] == "/pairs"
    labels = ws.labels.pair_labels_for(audience.id, DAY, "peter")
    assert len(labels) == len(sample.units)
    assert sum(label.same_story for label in labels) == 1
    first = next(label for label in labels if label.same_story)
    # The titles outlive the items, as relevance labels do.
    assert first.left_title == TITLES[first.left_id] and first.right_url.startswith("https://")


def test_a_partial_or_tokenless_save_of_pairs_is_refused(
    pair_store: Store, audience: Audience
) -> None:
    ws = Workspace(
        store=pair_store, labels=Store.memory(), labeller="peter", audiences={audience.id: audience}
    )
    _, page = call(ws, "GET", f"/pairs/day?audience={audience.id}&day={DAY}")
    keys = [part.split('"', 1)[0] for part in page.decode().split('data-id="')[1:]]
    base = {"audience": audience.id, "day": DAY, "same": []}
    assert call(ws, "POST", "/pairs/save", {**base, "shown": keys})[0].startswith("403")
    partial = {**base, "token": ws.token, "shown": keys[1:]}
    assert call(ws, "POST", "/pairs/save", partial)[0].startswith("400")
    assert ws.labels.pair_labels_for(audience.id) == []


def test_the_report_fills_the_deduplication_cell_from_labelled_pairs(
    pair_store: Store, audience: Audience
) -> None:
    ws = Workspace(
        store=pair_store, labels=Store.memory(), labeller="peter", audiences={audience.id: audience}
    )
    before = readme_tables(build_report(pair_store, [], [audience], "peter"))
    assert f"{NOT_YET} (pair labels)" in before
    _, page = call(ws, "GET", f"/pairs/day?audience={audience.id}&day={DAY}")
    keys = [part.split('"', 1)[0] for part in page.decode().split('data-id="')[1:]]
    together = {f"{a}|{b}" for a, b in pairs_within(CLUSTERS)}
    call(
        ws,
        "POST",
        "/pairs/save",
        {
            "token": ws.token,
            "audience": audience.id,
            "day": DAY,
            "same": [key for key in keys if key in together],
            "shown": keys,
        },
    )
    report = build_report(
        pair_store, [], [audience], "peter", pair_labels=ws.labels.pair_labels_for()
    )
    assert report.dedup_precision is not None and report.dedup_precision.point == 1.0
    assert report.pair_days == 1
    assert "(pair labels)" not in readme_tables(report)


def test_a_labels_file_from_before_pair_strata_opens_and_gains_the_columns(tmp_path: Path) -> None:
    path = tmp_path / "old.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        "CREATE TABLE pair_labels (audience_id TEXT NOT NULL, day TEXT NOT NULL, "
        "left_id TEXT NOT NULL, right_id TEXT NOT NULL, labeller TEXT NOT NULL, "
        "same_story BOOLEAN NOT NULL, labelled_at TIMESTAMPTZ NOT NULL, "
        "PRIMARY KEY (audience_id, day, left_id, right_id, labeller))"
    )
    connection.close()
    with Store.open(path) as store:
        assert store.pair_labels_for() == []
        columns = {row[0] for row in store._connection.execute("DESCRIBE pair_labels").fetchall()}
    assert {"stratum", "weight", "together", "left_title", "right_url"} <= columns
