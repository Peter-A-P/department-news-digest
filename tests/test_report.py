"""The report: the estimators against hand-worked numbers, and the README block."""

from __future__ import annotations

import math

import pytest

from clippings.eval.report import (
    README_END,
    README_START,
    DayLabels,
    kappa,
    pct,
    quantile,
    recall,
    replace_between_markers,
    share,
)


def test_recall_weights_the_random_stratum_by_what_each_label_stands_for() -> None:
    """Top stratum: 3 relevant, 2 of them shown. Random: 1 of 4 relevant, each standing for
    5 stories, so an estimated 5 more relevant stories the system buried. 2 / (3 + 5)."""
    day = DayLabels(
        day="2026-10-08",
        shown_relevant=2,
        top=(True, True, True, False),
        random=(True, False, False, False),
        weight=5.0,
    )
    assert recall([day]).point == pytest.approx(2 / 8)


def test_recall_with_nothing_buried_is_the_share_of_the_top_that_was_shown() -> None:
    day = DayLabels("d", shown_relevant=3, top=(True,) * 4, random=(False,) * 10, weight=2.0)
    estimate = recall([day])
    assert estimate.point == pytest.approx(3 / 4)
    # None found in ten is not none there: the interval reaches below the point.
    assert estimate.lo < 0.75 and estimate.hi == pytest.approx(0.75)


def test_recall_interval_widens_with_what_the_random_stratum_might_have_missed() -> None:
    day = DayLabels("d", shown_relevant=5, top=(True,) * 6, random=(True, False) * 10, weight=3.0)
    estimate = recall([day])
    assert estimate.lo < estimate.point < estimate.hi


def test_a_share_of_all_yes_is_never_printed_as_a_certainty() -> None:
    estimate = share([True] * 20)
    assert estimate.point == 1.0 and estimate.lo < 0.95


def test_kappa_is_one_for_identical_labels_and_has_an_interval() -> None:
    pairs = [(True, True)] * 10 + [(False, False)] * 10 + [(True, False)] * 2
    estimate = kappa(pairs)
    assert 0.6 < estimate.point < 1.0
    assert estimate.lo <= estimate.point <= estimate.hi


def test_quantile_interval_contains_the_point() -> None:
    values = [float(v) for v in range(1, 101)]
    estimate = quantile(values, 0.9)
    assert estimate.lo <= estimate.point <= estimate.hi


def test_an_estimate_that_does_not_exist_yet_is_not_printed_as_zero() -> None:
    assert pct(None) == "_not yet_"
    assert pct(recall([])) == "_not yet_"
    assert not math.isnan(share([True, False]).point)


def test_the_readme_block_is_replaced_whole_and_nothing_else_moves() -> None:
    readme = f"# Title\n\nbefore\n{README_START}\nold table\n{README_END}\n\nafter\n"
    updated = replace_between_markers(readme, "new table")
    assert "old table" not in updated and "new table" in updated
    assert updated.startswith("# Title\n\nbefore\n") and updated.endswith("\n\nafter\n")


def test_a_readme_without_markers_is_refused_rather_than_appended_to() -> None:
    with pytest.raises(ValueError):
        replace_between_markers("# Title\n", "table")
