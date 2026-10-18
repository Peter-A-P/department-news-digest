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
    share_by_day,
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


def test_recall_interval_reflects_days_that_went_differently() -> None:
    """Two census days, one where the digest showed every relevant story and one where it
    showed a quarter. Nothing in either random stratum to resample, so only the draw over
    days can give an interval; without it this printed a zero-width one."""
    good = DayLabels("a", shown_relevant=4, top=(True,) * 4, random=(), weight=0.0)
    poor = DayLabels("b", shown_relevant=1, top=(True,) * 4, random=(), weight=0.0)
    estimate = recall([good, poor])
    assert estimate.point == pytest.approx(5 / 8)
    assert estimate.lo < estimate.point < estimate.hi
    assert estimate.clusters == 2


def test_recall_point_is_not_the_top_of_its_interval_when_no_must_read_was_buried() -> None:
    """The week found on 2026-10-17: every random stratum empty of must-read stories, so the
    Jeffreys draws can only add buried ones. Days that differ must still reach above it."""
    days = [
        DayLabels("a", shown_relevant=2, top=(True,) * 2, random=(False,) * 30, weight=1.5),
        DayLabels("b", shown_relevant=3, top=(True,) * 6, random=(False,) * 30, weight=1.4),
        DayLabels("c", shown_relevant=5, top=(True,) * 5, random=(False,) * 9, weight=1.0),
    ]
    estimate = recall(days)
    assert estimate.hi > estimate.point


def test_one_census_day_has_no_interval_rather_than_a_zero_width_one() -> None:
    day = DayLabels("d", shown_relevant=3, top=(True,) * 4, random=(), weight=0.0)
    estimate = recall([day])
    assert estimate.point == pytest.approx(3 / 4) and math.isnan(estimate.lo)


def test_precision_resamples_whole_days() -> None:
    """Ten stories from a perfect day and ten from a poor one are two days of evidence, not
    twenty stories: the day-level interval is wider than the story-level one."""
    flags = [True] * 10 + [True, True] + [False] * 8
    days = ["a"] * 10 + ["b"] * 10
    by_day, by_story = share_by_day(flags, days), share(flags)
    assert by_day.point == pytest.approx(by_story.point)
    assert by_day.hi - by_day.lo > by_story.hi - by_story.lo
    assert by_day.clusters == 2


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
