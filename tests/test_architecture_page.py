"""The architecture page: docs/architecture.md rendered, its diagrams served as committed,
and a menu on every page that reaches it."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from clippings.assemble import render
from clippings.serve import app as serve_app

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _get(path: str) -> tuple[str, dict[str, str], bytes]:
    seen: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        seen["status"], seen["headers"] = status, dict(headers)

    wsgi = serve_app.application(site=None)  # type: ignore[arg-type]
    body: Iterable[bytes] = wsgi({"REQUEST_METHOD": "GET", "PATH_INFO": path}, start_response)
    return seen["status"], seen["headers"], b"".join(body)


def test_the_page_shows_every_diagram_and_each_is_served_as_committed() -> None:
    status, headers, body = _get("/architecture/")
    assert status.startswith("200") and headers["Content-Type"].startswith("text/html")
    page = body.decode("utf-8")
    shown = set(re.findall(r'<img src="([^"]+)"', page))
    committed = {p.name for p in (DOCS / "architecture").glob("*.svg")}
    assert shown == committed and len(shown) >= 3
    for name in shown:
        status, headers, data = _get(f"/architecture/{name}")
        assert status.startswith("200") and headers["Content-Type"] == "image/svg+xml"
        assert data == (DOCS / "architecture" / name).read_bytes()
    assert 'href="/architecture/" aria-current="page"' in page
    assert "<script" not in page


def test_the_address_without_a_slash_goes_to_the_page() -> None:
    status, headers, _ = _get("/architecture")
    assert status.startswith("301") and headers["Location"] == "/architecture/"


def test_every_page_carries_the_menu_and_the_front_page_links_it_early() -> None:
    front = render.site_index([])
    assert render.menu("/") in front
    hero = front.partition('<header class="hero')[2].partition("</header>")[0]
    assert 'href="/architecture/"' in hero
    archive = render.audience_index("Example", ["2026-10-16"])
    assert 'href="/architecture/">How it' in archive
