"""The labelling sample, and the weights recall is estimated from."""

from __future__ import annotations

from clippings.eval.sample import stratified_sample

POOL = [f"item-{index:03d}" for index in range(200)]


def test_the_top_stratum_is_the_top_of_the_ranking() -> None:
    sample = stratified_sample(POOL, "a", "2026-09-12", top_k=30, random_n=30)
    assert [unit.item_id for unit in sample.top] == POOL[:30]
    assert all(unit.weight == 1.0 for unit in sample.top)


def test_the_random_stratum_is_drawn_from_everything_below_the_top() -> None:
    sample = stratified_sample(POOL, "a", "2026-09-12", top_k=30, random_n=30)
    assert len(sample.tail) == 30
    assert all(unit.item_id in POOL[30:] for unit in sample.tail)


def test_each_random_label_stands_for_the_items_that_were_not_drawn() -> None:
    """This weight is the whole basis of the recall estimate."""
    sample = stratified_sample(POOL, "a", "2026-09-12", top_k=30, random_n=30)
    assert all(unit.weight == (200 - 30) / 30 for unit in sample.tail)


def test_the_same_day_is_sampled_the_same_way_twice() -> None:
    """Re-running the sampler must not ask for a fresh set nobody has labelled."""
    first = stratified_sample(POOL, "a", "2026-09-12")
    second = stratified_sample(POOL, "a", "2026-09-12", seed=first.seed)
    assert [unit.item_id for unit in first.units] == [unit.item_id for unit in second.units]


def test_two_days_get_different_samples() -> None:
    first = stratified_sample(POOL, "a", "2026-09-12", seed=1)
    second = stratified_sample(POOL, "a", "2026-09-13", seed=2)
    assert {unit.item_id for unit in first.tail} != {unit.item_id for unit in second.tail}


def test_a_pool_smaller_than_the_sample_is_handled() -> None:
    """A quiet day for a narrow audience: everything is in the top stratum."""
    small = POOL[:10]
    sample = stratified_sample(small, "a", "2026-09-12", top_k=30, random_n=30)
    assert len(sample.top) == 10
    assert sample.tail == ()


def test_a_pool_with_a_short_tail_weights_what_it_has() -> None:
    pool = POOL[:40]
    sample = stratified_sample(pool, "a", "2026-09-12", top_k=30, random_n=30)
    assert len(sample.tail) == 10
    assert all(unit.weight == 1.0 for unit in sample.tail), (
        "when every tail item is drawn, each stands only for itself"
    )


def test_an_empty_pool_produces_an_empty_sample() -> None:
    sample = stratified_sample([], "a", "2026-09-12")
    assert sample.units == ()
    assert sample.pool_size == 0


def test_every_unit_knows_its_rank_in_the_full_ranking() -> None:
    sample = stratified_sample(POOL, "a", "2026-09-12", top_k=5, random_n=5)
    for unit in sample.units:
        assert POOL[unit.rank - 1] == unit.item_id
