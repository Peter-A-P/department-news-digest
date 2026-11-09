"""The read-only service: the digest pages, the archive and nothing else.

PLAN.md section 2.5: a Cloud Run service serves what the daily job published, read-only. It
is a small WSGI application over the same `Site` the job writes to, so it has no database
connection, no write path and no way to start a run. GET and HEAD only; everything else is
405.

The standard library's server is enough: the pages are a few kilobytes, the audience is a
handful of readers a day, and Cloud Run puts its own front end in front of the container.
Choosing a framework would add a dependency for routing four kinds of path.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from clippings.assemble.publish import CONTENT_TYPES, Site, safe_path
from clippings.assemble.render import architecture_page

FONTS = {
    f"/fonts/{path.name}": path.read_bytes()
    for path in (Path(__file__).parent / "fonts").glob("*.woff2")
}
# The link-preview card the pages' og:image names (1200 x 630, made in the portfolio plan).
OG_CARD = (Path(__file__).parent / "og.png").read_bytes()
# The portfolio's teal "P" mark, the same icon as every project site.
FAVICON = (Path(__file__).parent / "favicon.svg").read_bytes()

# The architecture page and its diagrams, from docs/ as committed (the image copies them in
# beside the package). Rendered once, at start, from the document itself.
DOCS = Path(__file__).resolve().parents[2] / "docs"


def _architecture() -> dict[str, tuple[bytes, str]]:
    diagrams = sorted((DOCS / "architecture").glob("*.svg"))
    if not (DOCS / "architecture.md").exists() or not diagrams:
        return {}
    sizes: dict[str, tuple[str, str]] = {}
    files: dict[str, tuple[bytes, str]] = {}
    for path in diagrams:
        data = path.read_bytes()
        found = re.search(rb'width="(\d+)" height="(\d+)"', data)
        sizes[path.name] = (found.group(1).decode(), found.group(2).decode()) if found else ("", "")
        files[f"/architecture/{path.name}"] = (data, "image/svg+xml")
    page = architecture_page((DOCS / "architecture.md").read_text(encoding="utf-8"), sizes)
    files["/architecture/"] = (page.encode("utf-8"), "text/html; charset=utf-8")
    return files


ARCHITECTURE = _architecture()

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
Environ = dict[str, Any]

# Nothing on these pages runs script or loads anything from elsewhere, except the author's
# picture beside the day's X and Bluesky posts, from each platform's own image host
# (sources/x.py, sources/bluesky.py); the referrer is not sent with it. Saying so in a header
# means a headline that somehow carried markup still could not. The two fonts are this
# service's own, packaged beside this file (SIL Open Font License, see fonts/LICENSE.txt).
SECURITY_HEADERS = [
    (
        "Content-Security-Policy",
        "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; "
        "img-src 'self' https://pbs.twimg.com https://cdn.bsky.app",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
]


def resolve(path: str) -> str | None:
    """The site file a request path names, or None if it names nothing servable."""
    path = path or "/"
    if path.endswith("/"):
        path += "index.html"
    try:
        return str(safe_path(path))
    except ValueError:
        return None


def application(site: Site) -> Callable[[Environ, StartResponse], Iterable[bytes]]:
    def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        # /health, because Cloud Run's front end answers /healthz itself with a 404 and the
        # request never reaches the container (found on the first deploy, 2026-10-07).
        if path in {"/health", "/healthz"}:
            return _respond(start_response, "200 OK", b"ok\n", "text/plain; charset=utf-8", method)
        if path == "/architecture" and method in {"GET", "HEAD"}:
            return _respond(
                start_response,
                "301 Moved Permanently",
                b"",
                "text/plain",
                method,
                extra=[("Location", "/architecture/")],
            )
        if path in ARCHITECTURE and method in {"GET", "HEAD"}:
            body, content_type = ARCHITECTURE[path]
            return _respond(
                start_response,
                "200 OK",
                body,
                content_type,
                method,
                extra=[("Cache-Control", "public, max-age=3600")],
            )
        if path == "/og.png" and method in {"GET", "HEAD"}:
            return _respond(
                start_response,
                "200 OK",
                OG_CARD,
                "image/png",
                method,
                extra=[("Cache-Control", "public, max-age=86400")],
            )
        if path == "/favicon.svg" and method in {"GET", "HEAD"}:
            return _respond(
                start_response,
                "200 OK",
                FAVICON,
                "image/svg+xml",
                method,
                extra=[("Cache-Control", "public, max-age=86400")],
            )
        if path in FONTS and method in {"GET", "HEAD"}:
            return _respond(
                start_response,
                "200 OK",
                FONTS[path],
                "font/woff2",
                method,
                extra=[("Cache-Control", "public, max-age=604800")],
            )
        if method not in {"GET", "HEAD"}:
            return _respond(
                start_response,
                "405 Method Not Allowed",
                b"read-only\n",
                "text/plain",
                method,
                extra=[("Allow", "GET, HEAD")],
            )
        name = resolve(path)
        data = site.read(name) if name is not None else None
        # A directory asked for without its trailing slash goes to the slash, so the relative
        # links on the page resolve.
        if (
            data is None
            and name is not None
            and not path.endswith("/")
            and site.read(f"{name}/index.html") is not None
        ):
            return _respond(
                start_response,
                "301 Moved Permanently",
                b"",
                "text/plain",
                method,
                extra=[("Location", f"{path}/")],
            )
        if data is None or name is None:
            return _respond(start_response, "404 Not Found", b"not found\n", "text/plain", method)
        suffix = PurePosixPath(name).suffix
        extra = []
        if suffix == ".eml":
            extra.append(("Content-Disposition", 'attachment; filename="digest.eml"'))
        return _respond(
            start_response,
            "200 OK",
            data,
            CONTENT_TYPES.get(suffix, "application/octet-stream"),
            method,
            extra=[*extra, ("Cache-Control", "public, max-age=300")],
        )

    return app


def _respond(
    start_response: StartResponse,
    status: str,
    body: bytes,
    content_type: str,
    method: str,
    *,
    extra: list[tuple[str, str]] | None = None,
) -> list[bytes]:
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        *SECURITY_HEADERS,
        *(extra or []),
    ]
    start_response(status, headers)
    return [] if method == "HEAD" else [body]


class _ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # One line per request to stdout is what Cloud Run's logging collects; keep the
        # standard format but without the client address, which this service has no use for.
        print(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}", flush=True)


def serve(site: Site, host: str = "127.0.0.1", port: int = 8080) -> None:
    with make_server(
        host, port, application(site), server_class=_ThreadingServer, handler_class=_QuietHandler
    ) as server:
        print(f"serving the digest site on http://{host}:{port}/", flush=True)
        server.serve_forever()
