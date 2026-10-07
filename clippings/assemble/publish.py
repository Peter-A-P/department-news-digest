"""Writing the rendered digest where the read-only service serves it from.

Publishing is writing files, not sending them. Locally the site is a directory; in production
it is a prefix in the Cloud Storage bucket the Cloud Run service reads. The two share one
small protocol so the job and the tests run the same code.

Layout, the same in both:

    index.html                         every audience and its latest day
    <audience>/index.html              that audience's archive
    <audience>/<day>/index.html        the digest page
    <audience>/<day>/digest.md         the same digest as Markdown
    <audience>/<day>/digest.eml        an unsent email draft an owner may open and send
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol

from clippings.assemble import render
from clippings.assemble.digest import Digest

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".eml": "message/rfc822",
}


class Site(Protocol):
    """Somewhere rendered pages are written and read back."""

    def write(self, path: str, data: bytes) -> None: ...

    def read(self, path: str) -> bytes | None: ...


def safe_path(path: str) -> PurePosixPath:
    """A relative path inside the site, or ValueError. No '..', no absolute paths."""
    candidate = PurePosixPath(path.lstrip("/"))
    if any(part in {"..", ""} or part.startswith(".") for part in candidate.parts):
        raise ValueError(f"not a path inside the site: {path!r}")
    return candidate


class LocalSite:
    """A directory. How development runs, and what the tests exercise."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def write(self, path: str, data: bytes) -> None:
        target = self.root / safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def read(self, path: str) -> bytes | None:
        try:
            target = self.root / safe_path(path)
        except ValueError:
            return None
        return target.read_bytes() if target.is_file() else None


class GcsSite:
    """A prefix in the bucket. Behind the `gcs` extra, like the rest of the cloud code."""

    def __init__(self, bucket: str, prefix: str = "site") -> None:
        self.bucket_name = bucket
        self.prefix = prefix.strip("/")

    def _blob(self, path: str) -> object:
        from google.cloud import storage  # imported here: the `gcs` extra is optional

        name = f"{self.prefix}/{safe_path(path)}"
        return storage.Client().bucket(self.bucket_name).blob(name)

    def write(self, path: str, data: bytes) -> None:
        content_type = CONTENT_TYPES.get(PurePosixPath(path).suffix, "application/octet-stream")
        self._blob(path).upload_from_string(data, content_type=content_type)  # type: ignore[attr-defined]

    def read(self, path: str) -> bytes | None:
        from google.api_core.exceptions import NotFound

        try:
            blob = self._blob(path)
        except ValueError:
            return None
        try:
            data: bytes = blob.download_as_bytes()  # type: ignore[attr-defined]
        except NotFound:
            return None
        return data


def publish_digest(site: Site, digest: Digest) -> list[str]:
    """Write one digest's three files. Returns the paths written."""
    base = f"{digest.audience_id}/{digest.day}"
    files = {
        f"{base}/index.html": render.html_page(digest).encode("utf-8"),
        f"{base}/digest.md": render.markdown(digest).encode("utf-8"),
        f"{base}/digest.eml": render.eml_draft(digest),
    }
    for path, data in files.items():
        site.write(path, data)
    return list(files)


def publish_indexes(
    site: Site,
    audiences: Sequence[tuple[str, str]],
    days_by_audience: dict[str, list[str]],
) -> None:
    """The front page and each audience's archive, newest day first."""
    rows: list[tuple[str, str, str | None]] = []
    for audience_id, name in audiences:
        days = sorted(days_by_audience.get(audience_id, []), reverse=True)
        site.write(f"{audience_id}/index.html", render.audience_index(name, days).encode("utf-8"))
        rows.append((audience_id, name, days[0] if days else None))
    site.write("index.html", render.site_index(rows).encode("utf-8"))
