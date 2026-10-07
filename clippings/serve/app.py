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

from collections.abc import Callable, Iterable
from pathlib import PurePosixPath
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from clippings.assemble.publish import CONTENT_TYPES, Site, safe_path

StartResponse = Callable[[str, list[tuple[str, str]]], Any]
Environ = dict[str, Any]

# Nothing on these pages runs script or loads anything from elsewhere. Saying so in a header
# means a headline that somehow carried markup still could not.
SECURITY_HEADERS = [
    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'"),
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
        if path == "/healthz":
            return _respond(start_response, "200 OK", b"ok\n", "text/plain; charset=utf-8", method)
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
