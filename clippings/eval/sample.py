"""What a labeller is shown, and the weights that make recall estimable.

PLAN.md section 2.6. Labelling a day's whole pool is thousands of labels per audience and
will not happen, so each day is sampled in two strata: the thirty stories the system ranked
highest, and a random thirty from the rest. The unit is a news story, shown by the item the
digest would link to: a digest misses stories, not reprints of them, and a post is never a
candidate (PLAN.md section 2.3), so neither is put to the labeller.

Precision at K comes from the top stratum directly. Recall cannot: the relevant items the
system buried are, by definition, not in the top stratum. They are estimated from the
random stratum, where each labelled item stands for many unlabelled ones, and the weight is
how many. That is why every recall number this project publishes is labelled an
importance-weighted estimate rather than a measurement.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Stratum = Literal["top", "random"]

DEFAULT_TOP = 30
DEFAULT_RANDOM = 30


@dataclass(frozen=True)
class SampleUnit:
    """One thing to label, and what it stands for in the estimate."""

    item_id: str
    stratum: Stratum
    rank: int
    # How many pool items this label represents. One in the top stratum, which is a census;
    # more in the random stratum, which is a sample.
    weight: float


@dataclass(frozen=True)
class DaySample:
    """A day's labelling work for one audience."""

    audience_id: str
    day: str
    units: tuple[SampleUnit, ...]
    pool_size: int
    seed: int

    @property
    def top(self) -> tuple[SampleUnit, ...]:
        return tuple(unit for unit in self.units if unit.stratum == "top")

    @property
    def tail(self) -> tuple[SampleUnit, ...]:
        return tuple(unit for unit in self.units if unit.stratum == "random")


def stratified_sample(
    ranked_ids: Sequence[str],
    audience_id: str,
    day: str,
    *,
    top_k: int = DEFAULT_TOP,
    random_n: int = DEFAULT_RANDOM,
    seed: int | None = None,
) -> DaySample:
    """Take the top `top_k` by rank, then `random_n` at random from the rest.

    `seed` defaults to a value derived from the audience and the day, so re-running the
    sampler for a day that has already been labelled asks for the same items rather than a
    fresh set nobody has labelled.
    """
    if seed is None:
        # Derived with a fixed hash, not `hash()`: Python salts `hash()` per process, so the
        # seed, and with it the random stratum, changed every time the command started and a
        # half-labelled day came back with different items (found 2026-10-10).
        digest = hashlib.blake2b(f"{audience_id}|{day}".encode(), digest_size=4).digest()
        seed = int.from_bytes(digest, "big") % (2**31)
    head = list(ranked_ids[:top_k])
    tail = list(ranked_ids[top_k:])
    drawn = random.Random(seed).sample(tail, min(random_n, len(tail)))
    # Each drawn item stands for this many of the items that were not drawn.
    weight = len(tail) / len(drawn) if drawn else 0.0
    units = [
        SampleUnit(item_id=item_id, stratum="top", rank=index + 1, weight=1.0)
        for index, item_id in enumerate(head)
    ]
    units += [
        SampleUnit(
            item_id=item_id,
            stratum="random",
            rank=ranked_ids.index(item_id) + 1,
            weight=weight,
        )
        for item_id in drawn
    ]
    return DaySample(
        audience_id=audience_id,
        day=day,
        units=tuple(units),
        pool_size=len(ranked_ids),
        seed=seed,
    )
