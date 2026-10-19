"""The reader study and uptime: who reads what, what a session records, and how both are
reported."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

import pytest

from clippings.config.audience import Audience
from clippings.eval.reader_study import Condition, Study, application, condition_for, study_days
from clippings.eval.report import NOT_YET, build_report, reader_times, readme_tables
from clippings.eval.uptime import unattended, uptime_days
from clippings.ingest.pipeline import new_run_id
from clippings.ingest.store import Store
from clippings.models import Cluster, ReaderSession
from tests.conftest import NOW, item
from tests.test_faithfulness import _digest, _story

DAY = NOW.date().isoformat()


def test_every_day_is_read_both_ways_and_no_reader_reads_a_day_twice() -> None:
    for index in range(5):
        assert {condition_for(1, index), condition_for(2, index)} == {"digest", "sources"}
        assert condition_for(3, index) == condition_for(1, index)
    assert [condition_for(1, i) for i in range(5)].count("sources") == 3


@pytest.fixture
def study(store: Store, audience: Audience) -> Study:
    store.add_items(
        [
            item("a1", "Council passes budget"),
            item("a2", "Budget passes council"),
            item("b1", "Library hours extended"),
        ],
        audience.id,
    )
    store.save_clusters(
        [
            Cluster(
                id="A",
                audience_id=audience.id,
                day=DAY,
                representative_id="a1",
                item_ids=("a1", "a2"),
            ),
            Cluster(
                id="B", audience_id=audience.id, day=DAY, representative_id="b1", item_ids=("b1",)
            ),
        ]
    )
    store.save_digest(_digest(DAY, (_story("A", ["The council passed it."], "a1"),)))
    return Study(store=store, sessions=Store.memory(), audience=audience, reader_number=1)


def test_the_study_days_are_digest_days_with_a_story(study: Study, store: Store) -> None:
    empty = (NOW + timedelta(days=1)).date().isoformat()
    store.save_digest(_digest(empty, ()))
    assert study_days(store, study.audience) == [DAY]


def test_a_sources_session_records_its_time_and_which_picks_the_digest_showed(
    study: Study,
) -> None:
    def go(method: str, path: str, body: object = None) -> tuple[str, bytes]:
        raw = json.dumps(body).encode() if body is not None else b""
        path, _, query = path.partition("?")
        seen: dict[str, str] = {}
        out = application(study)(
            {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "CONTENT_LENGTH": str(len(raw)),
                "wsgi.input": io.BytesIO(raw),
            },
            lambda status, headers: seen.update(status=status),
        )
        return seen["status"], b"".join(out)

    # Reader 1 has the first day from the sources: every news item, and no digest to open.
    status, page = go("GET", f"/session?day={DAY}")
    assert status.startswith("200") and page.count(b'class="pick"') == 3
    assert go("GET", f"/digest?day={DAY}")[0].startswith("403")
    done = {"token": study.token, "day": DAY, "seconds_active": 300, "seconds_wall": 320}
    picks = ["https://gov.example/a2", "https://gov.example/b1"]
    assert go("POST", "/done", {**done, "picks": picks})[0].startswith("400")  # not started
    assert go("POST", "/start", {"token": study.token, "day": DAY})[0].startswith("200")
    assert go("POST", "/done", {**done, "picks": ["https://elsewhere.example/"]})[0].startswith(
        "400"
    )
    status, reply = go("POST", "/done", {**done, "picks": picks})
    assert status.startswith("200"), reply
    (session,) = study.sessions.reader_sessions("reader-1")
    assert session.condition == "sources" and session.shown == 3
    assert session.seconds_active == 300 and session.picks_in_digest == 1


def _session(reader: str, condition: Condition, minutes: float, day: str = DAY) -> ReaderSession:
    return ReaderSession(
        reader=reader,
        audience_id="test-audience",
        day=day,
        condition=condition,
        seconds_active=minutes * 60,
        seconds_wall=minutes * 60,
        shown=10,
        picks=("u1", "u2") if condition == "sources" else (),
        picks_in_digest=1 if condition == "sources" else 0,
        started_at=NOW,
        finished_at=NOW,
    )


def test_reader_times_compare_the_conditions_with_an_interval() -> None:
    sessions = [
        _session("reader-1", "digest", 2),
        _session("reader-2", "digest", 4),
        _session("reader-1", "sources", 10, "d2"),
        _session("reader-2", "sources", 14, "d2"),
    ]
    times = reader_times(sessions)
    assert times.digest.point == pytest.approx(3) and times.sources.point == pytest.approx(12)
    assert times.ratio.point == pytest.approx(4)
    assert times.ratio.lo < times.ratio.point < times.ratio.hi
    assert (times.picks, times.picks_in_digest) == (4, 2)


def test_the_report_fills_the_reader_cell(store: Store, audience: Audience) -> None:
    assert f"{NOT_YET} (reader study)" in readme_tables(build_report(store, [], [audience], "p"))
    sessions = [_session("reader-1", "digest", 2), _session("reader-2", "sources", 12)]
    tables = readme_tables(build_report(store, [], [audience], "p", reader_sessions=sessions))
    assert "(reader study)" not in tables and "2.0 on all 1 vs 12.0 on all 1, 2 sessions" in tables
    assert "6.0 (interval undefined, one session of a kind) times as long" in tables


# -- uptime -----------------------------------------------------------------------------------


def test_only_the_scheduled_run_or_its_retry_is_unattended() -> None:
    assert unattended("20261009T090023Z-0c94ac", "2026-10-09")
    assert not unattended("20261008T094759Z-2c3ef4", "2026-10-08")  # started by hand
    assert unattended("20261008T094759Z-2c3ef4-retry1", "2026-10-08")
    assert not unattended("20261009T090023Z-0c94ac", "2026-10-10")  # another day's run


def test_a_retry_is_marked_in_the_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RUN_TASK_ATTEMPT", "1")
    assert new_run_id(NOW).endswith("-retry1")
    monkeypatch.setenv("CLOUD_RUN_TASK_ATTEMPT", "0")
    assert "-retry" not in new_run_id(NOW)


def test_a_day_rescued_by_hand_or_missing_an_audience_is_down(store: Store) -> None:
    def save(day: str, audience_id: str, run_id: str) -> None:
        store.save_digest(_digest(day, (), audience_id).model_copy(update={"run_id": run_id}))

    save("2026-10-08", "a", "20261008T094759Z-2c3ef4")  # by hand after a failure
    save("2026-10-08", "b", "20261008T094759Z-2c3ef4")
    for audience_id in ("a", "b"):
        save("2026-10-09", audience_id, "20261009T090023Z-0c94ac")
        save("2026-10-09", audience_id, "20261009T130000Z-ffffff")  # a later rerun by hand
    save("2026-10-10", "a", "20261010T090025Z-b6b9dd")  # b's digest never came
    # The 11th's run has not had time to finish, so it is not judged yet.
    now = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
    days = uptime_days(store, ["a", "b"], now)
    assert [(day.day, day.up, day.missing) for day in days] == [
        ("2026-10-08", False, ("a", "b")),
        ("2026-10-09", True, ()),
        ("2026-10-10", False, ("b",)),
    ]
