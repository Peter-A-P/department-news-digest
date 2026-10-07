"""Delivery: the gateway door, the rendered page, the read-only service, and what survives.

Every model call goes through one module with the public data class declared; spending needs
a switch; a headline is text, never markup; the service cannot write and cannot be walked out
of its directory; and a digest outlives the thirty-day deletion of the items it was built
from.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from boundary import ChatRequest, ChatResponse, Mode, SpendCapExceeded, Usage

from clippings.assemble.digest import (
    Digest,
    DigestSentence,
    DigestStory,
    SourceLink,
    VerificationCounts,
)
from clippings.assemble.publish import LocalSite, publish_digest, publish_indexes, safe_path
from clippings.assemble.render import html_page
from clippings.config.audience import Audience, Feed, Sources
from clippings.gateway import (
    ALLOW_SPEND_ENV,
    GatewayClient,
    ModelCall,
    Purpose,
    SpendCapReached,
    SpendNotAllowed,
    open_client,
)
from clippings.ingest.extract import extract_one
from clippings.ingest.remote import LocalObjectStore, StateSync
from clippings.ingest.store import Store
from clippings.serve.app import application
from clippings.sources.base import FetchContext
from tests.conftest import NOW, gate, item

PACKAGE = Path(__file__).resolve().parents[1] / "clippings"


# -- the gateway ---------------------------------------------------------------------------


def test_only_the_gateway_module_imports_boundary() -> None:
    """One door: a second module importing the gateway is a second way to reach a vendor."""
    importers = []
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.split(".")[0] == "boundary" for name in names):
                importers.append(path.name)
    assert sorted(set(importers)) == ["gateway.py"]


class FakeGateway:
    """Stands where boundary's Gateway stands, and records what it was asked."""

    def __init__(self, raise_cap: bool = False) -> None:
        self.raise_cap = raise_cap
        self.calls: list[dict[str, Any]] = []

    def chat(self, request: ChatRequest, **kwargs: Any) -> ChatResponse:
        self.calls.append({"request": request, **kwargs})
        if self.raise_cap:
            raise SpendCapExceeded(scope="run", cap_usd=2.0, spent_usd=1.99, estimate_usd=0.05)
        return ChatResponse(
            text="ok",
            finish_reason="end_turn",
            usage=Usage(10, 2),
            cost_usd=0.00002,
            costed=True,
            model_requested="anthropic/claude-haiku-4-5-20251001",
            model_returned="claude-haiku-4-5-20251001",
            provider="anthropic",
            latency_ms=1.0,
            status=200,
            headers={},
            raw=None,
            ledger_id=1,
            mode=Mode.STANDARD,
            retries=0,
            cached=False,
            price_list="2026-10-01",
            trace_id=None,
            call_uid="uid-1",
        )

    def close(self) -> None:
        pass


def call() -> ModelCall:
    return ModelCall(purpose=Purpose.RERANK, audience_id="ai", system="s", user="u")


def test_every_call_declares_public_names_the_audience_and_uses_an_alias() -> None:
    fake = FakeGateway()
    reply = GatewayClient(gateway=fake).complete(call(), run_id="run-1")  # type: ignore[arg-type]
    sent = fake.calls[0]
    assert sent["data_class"] == "public"
    assert sent["purpose"] == "rerank/ai"
    assert sent["run_id"] == "run-1"
    assert sent["request"].model == "clippings-rerank", "aliases, never vendor model ids"
    assert (reply.call_uid, reply.cost_usd) == ("uid-1", 0.00002)


def test_a_cap_stops_the_run_rather_than_failing_one_story() -> None:
    with pytest.raises(SpendCapReached, match="run cap"):
        GatewayClient(gateway=FakeGateway(raise_cap=True)).complete(call(), run_id="r")  # type: ignore[arg-type]


def test_no_client_without_the_spend_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ALLOW_SPEND_ENV, raising=False)
    with pytest.raises(SpendNotAllowed, match=ALLOW_SPEND_ENV):
        open_client()


def test_the_caps_file_has_a_cap_for_this_project() -> None:
    import yaml

    caps = yaml.safe_load((PACKAGE / "config" / "gateway" / "caps.yaml").read_text())
    project = caps["projects"]["clippings"]
    assert project["per_run_usd"] <= 5 and project["daily_usd"] <= 10


# -- rendering and the site ----------------------------------------------------------------


def digest(headline: str = "Council passes budget", day: str = "2026-09-12") -> Digest:
    source = SourceLink(
        sid="s1",
        item_id="a",
        domain="gov.example",
        title=headline,
        url="https://gov.example/a",
        published_at=NOW,
        extracted=True,
    )
    story = DigestStory(
        story_id="k1",
        position=1,
        headline=headline,
        url="https://gov.example/a",
        domain="gov.example",
        published_at=NOW,
        outlets=1,
        sentences=(DigestSentence(text='The council said "it passed".', cites=("s1",)),),
        sources=(source,),
        status="verified",
        prefilter_score=0.5,
        rerank_score=3,
        rerank_reason="budget decision",
        final_score=0.9,
        why="entity hits 0.20",
    )
    return Digest(
        audience_id="test-audience",
        audience_name="Test audience",
        day=day,
        run_id="r1",
        generated_at=NOW,
        stories=(story,),
        counts=VerificationCounts(),
        calls=(),
        pool_items=10,
        pool_stories=8,
        candidates=8,
        reranked=True,
        rerank_error="",
        rerank_unscored=0,
        rerank_excluded=2,
        embedder="hashing",
        model_client="scripted",
    )


def test_a_headline_is_text_never_markup() -> None:
    page = html_page(digest('<script>alert("x")</script> & co'))
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_the_page_says_when_the_rubric_was_not_applied() -> None:
    unranked = digest().model_copy(update={"reranked": False, "rerank_error": "upstream 529"})
    assert "rubric's exclusions were not applied" in html_page(unranked)


@pytest.mark.parametrize("path", ["../secrets", "/../x", "a/../../b", ".env", "a/.git/config"])
def test_the_site_cannot_be_walked_out_of(path: str) -> None:
    with pytest.raises(ValueError):
        safe_path(path)


def get(app: Any, path: str, method: str = "GET") -> tuple[str, dict[str, str], bytes]:
    captured: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"], captured["headers"] = status, dict(headers)

    body: Iterable[bytes] = app({"REQUEST_METHOD": method, "PATH_INFO": path}, start_response)
    return captured["status"], captured["headers"], b"".join(body)


def test_the_service_serves_pages_and_nothing_else(tmp_path: Path) -> None:
    site = LocalSite(tmp_path / "site")
    publish_digest(site, digest())
    publish_indexes(site, [("test-audience", "Test audience")], {"test-audience": ["2026-09-12"]})
    (tmp_path / "secret.txt").write_text("not for the web")
    app = application(site)

    status, headers, body = get(app, "/test-audience/2026-09-12/")
    assert status.startswith("200") and b"Council passes budget" in body
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert get(app, "/")[0].startswith("200")
    assert get(app, "/test-audience")[1]["Location"] == "/test-audience/"
    assert get(app, "/../secret.txt")[0].startswith("404")
    assert get(app, "/test-audience/2026-09-12/", "POST")[0].startswith("405")
    eml = get(app, "/test-audience/2026-09-12/digest.eml")
    assert eml[1]["Content-Disposition"].startswith("attachment")
    assert get(app, "/health")[2] == b"ok\n"


# -- what survives, and what is never fetched ------------------------------------------------


def test_a_digest_outlives_the_items_it_was_built_from(store: Store) -> None:
    store.add_items([item("a", published_at=NOW - timedelta(days=40))], "test-audience")
    store.save_digest(digest())
    store.retention(now=NOW)
    assert store.count_items() == 0
    kept = store.digest_for("test-audience", "2026-09-12")
    assert kept is not None and kept.stories[0].sources[0].url == "https://gov.example/a"


def test_a_feed_cleared_for_its_summary_only_is_never_requested(
    audience: Audience, context: FetchContext
) -> None:
    """The conftest client fails the test on any request, so reaching it would show."""
    feed = Feed(url="https://gov.example/feed", publisher="Gov", terms="gov.example", extract=False)
    configured = audience.model_copy(update={"sources": Sources(feeds=(feed,))})
    context.gate = gate(**{"gov.example": "allowed"})
    outcome = extract_one(item("a"), configured, context)
    assert outcome.text is None and outcome.reason == "feed cleared for its summary only"


def test_an_item_from_a_feed_no_longer_configured_is_not_extracted(
    audience: Audience, context: FetchContext
) -> None:
    context.gate = gate(**{"gov.example": "allowed"})
    assert extract_one(item("a"), audience, context).reason == "feed cleared for its summary only"


def test_state_sync_round_trips_through_the_bucket(tmp_path: Path) -> None:
    bucket = LocalObjectStore(tmp_path / "bucket")
    first = StateSync(bucket, tmp_path / "run1")
    first.pull()
    first.db.parent.mkdir(parents=True)
    first.db.write_bytes(b"db")
    first.ledger.write_bytes(b"ledger")
    first.push()

    second = StateSync(bucket, tmp_path / "run2")
    second.pull()
    assert (second.db.read_bytes(), second.ledger.read_bytes()) == (b"db", b"ledger")


def test_temperature_is_not_sent_unless_a_call_asks_for_it() -> None:
    """Sonnet 5.5 answers 400 to any request carrying `temperature` (2026-10-07)."""
    fake = FakeGateway()
    GatewayClient(gateway=fake).complete(call(), run_id="r")  # type: ignore[arg-type]
    assert fake.calls[0]["request"].temperature is None
