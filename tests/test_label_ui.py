"""The labelling page: what it shows, and that saving a day records every story on it."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from clippings.cluster.embed import Hashing
from clippings.config.audience import Audience
from clippings.eval.label_ui import Workspace, application
from clippings.ingest.pipeline import run_audience
from clippings.ingest.store import Store
from clippings.sources.base import FetchContext
from tests.conftest import NOW
from tests.test_pipeline import FixtureSource, raw_item, result

DAY = NOW.date().isoformat()


@pytest.fixture
def workspace(audience: Audience, store: Store, context: FetchContext) -> Workspace:
    run_audience(
        audience,
        store,
        context,
        Hashing(),
        sources=[
            FixtureSource(
                result(
                    raw_item("https://gov.example/1", "Regulator opens consultation", "A."),
                    raw_item("https://news.example/2", "New bus route", "B."),
                    raw_item("https://news.example/3", "Council passes budget", "C."),
                )
            )
        ],
        extract=False,
    )
    pushed: list[int] = []
    ws = Workspace(
        store=store,
        labels=Store.memory(),
        labeller="peter",
        audiences={audience.id: audience},
        push=lambda: pushed.append(1),
    )
    ws.pushed = pushed  # type: ignore[attr-defined]
    return ws


def call(ws: Workspace, method: str, path: str, body: Any = None) -> tuple[str, bytes]:
    raw = json.dumps(body).encode() if body is not None else b""
    path, _, query = path.partition("?")
    captured: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status

    out = application(ws)(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        },
        start_response,
    )
    return captured["status"], b"".join(out)


def ids_on(page: bytes) -> list[str]:
    text = page.decode()
    return [part.split('"', 1)[0] for part in text.split('data-id="')[1:]]


def test_saving_a_day_records_an_answer_for_every_story_shown(workspace: Workspace) -> None:
    audience_id = next(iter(workspace.audiences))
    status, page = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    assert status.startswith("200")
    shown = ids_on(page)
    assert len(shown) == 3
    payload = {
        "token": workspace.token,
        "audience": audience_id,
        "day": DAY,
        "relevant": shown[:1],
        "shown": shown,
    }
    status, reply = call(workspace, "POST", "/save", payload)
    assert status.startswith("200"), reply
    labels = workspace.labels.labels_for(audience_id, DAY, "peter")
    # Unmarked stories are recorded as "no": the labeller saw them.
    assert sorted(label.relevant for label in labels) == [False, False, True]
    assert workspace.pushed == [1]  # type: ignore[attr-defined]
    assert json.loads(reply)["next"] == "/"


def test_a_save_without_the_page_token_is_refused(workspace: Workspace) -> None:
    audience_id = next(iter(workspace.audiences))
    _, page = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    payload = {"audience": audience_id, "day": DAY, "relevant": [], "shown": ids_on(page)}
    status, _ = call(workspace, "POST", "/save", payload)
    assert status.startswith("403")
    assert workspace.labels.labels_for(audience_id, DAY, "peter") == []


def test_a_save_that_did_not_show_the_whole_sample_is_refused(workspace: Workspace) -> None:
    audience_id = next(iter(workspace.audiences))
    _, page = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    payload = {
        "token": workspace.token,
        "audience": audience_id,
        "day": DAY,
        "relevant": [],
        "shown": ids_on(page)[:2],
    }
    assert call(workspace, "POST", "/save", payload)[0].startswith("400")


def test_the_page_hides_the_system_rank_and_stratum(workspace: Workspace) -> None:
    audience_id = next(iter(workspace.audiences))
    _, page = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    text = page.decode()
    assert "stratum" not in text and "rank" not in text.lower().replace("ranking", "")


def test_an_earlier_judgement_is_the_starting_answer(workspace: Workspace) -> None:
    audience_id = next(iter(workspace.audiences))
    _, page = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    shown = ids_on(page)
    payload = {
        "token": workspace.token,
        "audience": audience_id,
        "day": DAY,
        "relevant": shown[:1],
        "shown": shown,
    }
    call(workspace, "POST", "/save", payload)
    _, again = call(workspace, "GET", f"/day?audience={audience_id}&day={DAY}")
    assert again.decode().count('class="row yes"') == 1
