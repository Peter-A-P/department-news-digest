"""Whether the daily run did its job without a person, day by day.

PLAN.md section 1 publishes the uptime of the daily run: the share of days on which the run
the scheduler started (or Cloud Run's automatic retry of it) published a digest for every
audience. A day rescued by a run started by hand is a day down, because the claim is "it
runs without a person". It is computed from the store alone, from the run id of every
digest kept, so a stranger with the database gets the same number.

A run id begins with its start time in UTC (`ingest.pipeline.new_run_id`), and a retry is
marked `-retry<n>`. Checked against Cloud Run's own execution list on 2026-10-18: the
scheduled executions were created at 09:00:01 every day; on 2026-10-08 the scheduled run
failed (out of memory) and the digests came from a run started by hand at 09:47, which this
counts as down; on 2026-10-10 the scheduled run published all four before later runs by hand
replaced some of them, which this counts as up.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from clippings.constants import SCHEDULED_GRACE_MINUTES, SCHEDULED_RUN_UTC, UPTIME_FROM
from clippings.ingest.store import Store

# How long after the scheduled start a day is judged: the job's own timeout (an hour, in
# deploy/deploy.sh) and its one retry. Before that a missing digest may still be coming.
SETTLE = timedelta(hours=2, minutes=30)


@dataclass(frozen=True)
class UptimeDay:
    day: str
    up: bool
    # The audiences with no digest from the scheduled run or its retry.
    missing: tuple[str, ...]


def started(run_id: str) -> datetime | None:
    try:
        return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def scheduled_start(day: str) -> datetime:
    hour, minute = SCHEDULED_RUN_UTC
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=UTC)


def unattended(run_id: str, day: str) -> bool:
    """The scheduled run of `day`, or an automatic retry of it."""
    start = started(run_id)
    if start is None or start.date().isoformat() != day:
        return False
    if "-retry" in run_id:
        return True
    window = scheduled_start(day)
    return window <= start < window + timedelta(minutes=SCHEDULED_GRACE_MINUTES)


def uptime_days(
    store: Store, audience_ids: Sequence[str], now: datetime | None = None
) -> list[UptimeDay]:
    """Every day from `UPTIME_FROM` whose scheduled run has had time to finish."""
    moment = now or datetime.now(UTC)
    days = []
    day = date.fromisoformat(UPTIME_FROM)
    while scheduled_start(day.isoformat()) + SETTLE <= moment:
        key = day.isoformat()
        missing = tuple(
            audience_id
            for audience_id in audience_ids
            if not any(unattended(d.run_id, key) for d in store.digest_runs(audience_id, key))
        )
        days.append(UptimeDay(key, not missing, missing))
        day += timedelta(days=1)
    return days
