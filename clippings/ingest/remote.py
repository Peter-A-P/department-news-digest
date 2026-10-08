"""The run lock, and synchronising the database file with Cloud Storage.

PLAN.md section 2.5: one DuckDB file per environment synchronised to a Cloud Storage
bucket with a run lock. Compute is stateless and the daily job may be retried, so two jobs
can be alive at once; the lock is what stops the second one writing.

The local backends are not a test double. They are how the pipeline runs on a laptop, and
they are what the tests exercise; the Cloud Storage backends are the same interface over
a bucket, behind the `gcs` extra so nothing here needs cloud credentials to run.
"""

from __future__ import annotations

import json
import os
import socket
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

# A run that has held the lock for longer than this is assumed dead: Cloud Run kills a job
# well before it, so a lock older than this was left by a container that did not get to
# release it. Longer than the longest plausible run, shorter than the daily schedule.
DEFAULT_LOCK_TTL = timedelta(hours=2)


def execution_id() -> str:
    """The Cloud Run job execution this process belongs to, or empty outside Cloud Run.

    A retried task runs in a new container with the same execution name, which is what lets
    a retry recognise a lock its own crashed first attempt left behind.
    """
    return os.environ.get("CLOUD_RUN_EXECUTION", "")


def lock_payload(holder: str) -> str:
    return json.dumps(
        {"holder": holder, "taken_at": datetime.now(UTC).isoformat(), "execution": execution_id()}
    )


def breakable(payload: dict[str, str], ttl: timedelta, execution: str | None = None) -> bool:
    """Whether a lock found in place may be broken.

    Two cases. The holder is presumed dead because the lock is older than the TTL. Or the
    lock was taken by an earlier attempt of this same job execution: Cloud Run only retries
    a task after the attempt has ended, so that holder is certainly dead. The second case is
    from 2026-10-08, when the first attempt was killed for running out of memory, its lock
    outlived it, and the retry refused to start, losing the day for three audiences.
    """
    execution = execution_id() if execution is None else execution
    if execution and payload.get("execution") == execution:
        return True
    taken = payload.get("taken_at")
    if not taken:
        return True
    try:
        return datetime.now(UTC) - datetime.fromisoformat(taken) > ttl
    except ValueError:
        return True


class RunLockHeld(RuntimeError):
    """Another run holds the lock. The second job exits rather than writing."""


def holder_id() -> str:
    """Who is asking: enough to find the container or shell that left a lock behind."""
    return f"{socket.gethostname()}:{os.getpid()}"


@runtime_checkable
class RunLock(Protocol):
    """A mutual exclusion the daily job takes before it writes."""

    def acquire(self, holder: str | None = None) -> None: ...

    def release(self) -> None: ...


class LocalRunLock:
    """A lock file taken with O_EXCL, which is atomic on every filesystem this runs on."""

    def __init__(self, path: Path | str, ttl: timedelta = DEFAULT_LOCK_TTL) -> None:
        self.path = Path(path)
        self.ttl = ttl
        self._held = False

    def acquire(self, holder: str | None = None) -> None:
        payload = lock_payload(holder or holder_id())
        try:
            self._write_exclusive(payload)
        except FileExistsError:
            if breakable(self._payload(), self.ttl):
                # The previous holder died without releasing. Break the lock, then take it
                # the same way, so two processes breaking it at once still leaves one winner.
                self.path.unlink(missing_ok=True)
                try:
                    self._write_exclusive(payload)
                except FileExistsError:
                    raise RunLockHeld(f"{self.path}: held by another run") from None
            else:
                raise RunLockHeld(f"{self.path}: held by {self._holder()}") from None
        self._held = True

    def _write_exclusive(self, payload: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)

    def _payload(self) -> dict[str, str]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _holder(self) -> str:
        return self._payload().get("holder", "an unknown run")

    def release(self) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


class GcsRunLock:
    """The same lock as one object in the bucket.

    `if_generation_match=0` makes the upload succeed only when the object does not exist,
    which is Cloud Storage's compare-and-set and is atomic across containers.
    """

    def __init__(
        self, bucket: str, name: str = "locks/run.lock", ttl: timedelta = DEFAULT_LOCK_TTL
    ) -> None:
        self.bucket_name = bucket
        self.name = name
        self.ttl = ttl
        self._held = False

    def _blob(self) -> object:
        from google.cloud import storage  # imported here: the `gcs` extra is optional

        client = storage.Client()
        return client.bucket(self.bucket_name).blob(self.name)

    def acquire(self, holder: str | None = None) -> None:
        from google.api_core.exceptions import PreconditionFailed

        payload = lock_payload(holder or holder_id())
        blob = self._blob()
        try:
            blob.upload_from_string(payload, if_generation_match=0)  # type: ignore[attr-defined]
        except PreconditionFailed:
            if self._is_breakable(blob):
                blob.delete()  # type: ignore[attr-defined]
                try:
                    blob.upload_from_string(payload, if_generation_match=0)  # type: ignore[attr-defined]
                except PreconditionFailed:
                    raise RunLockHeld(f"gs://{self.bucket_name}/{self.name}: held") from None
            else:
                raise RunLockHeld(f"gs://{self.bucket_name}/{self.name}: held") from None
        self._held = True

    def _is_breakable(self, blob: object) -> bool:
        try:
            payload = json.loads(blob.download_as_text())  # type: ignore[attr-defined]
        except Exception:
            return True
        return breakable(payload if isinstance(payload, dict) else {}, self.ttl)

    def release(self) -> None:
        if self._held:
            from google.api_core.exceptions import NotFound

            with suppress(NotFound):
                self._blob().delete()  # type: ignore[attr-defined]
            self._held = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()


@runtime_checkable
class ObjectStore(Protocol):
    """Where the database file lives between runs."""

    def download(self, name: str, destination: Path) -> bool:
        """Fetch `name` to `destination`. False if it is not there yet."""
        ...

    def upload(self, source: Path, name: str) -> None: ...


class LocalObjectStore:
    """A directory standing in for the bucket, which is how development runs."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def download(self, name: str, destination: Path) -> bool:
        source = self.root / name
        if not source.is_file():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return True

    def upload(self, source: Path, name: str) -> None:
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


class GcsObjectStore:
    """The bucket itself."""

    def __init__(self, bucket: str) -> None:
        self.bucket_name = bucket

    def _bucket(self) -> object:
        from google.cloud import storage  # imported here: the `gcs` extra is optional

        return storage.Client().bucket(self.bucket_name)

    def download(self, name: str, destination: Path) -> bool:
        from google.api_core.exceptions import NotFound

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._bucket().blob(name).download_to_filename(str(destination))  # type: ignore[attr-defined]
        except NotFound:
            return False
        return True

    def upload(self, source: Path, name: str) -> None:
        self._bucket().blob(name).upload_from_filename(str(source))  # type: ignore[attr-defined]


class StateSync:
    """The run's state files, copied down from the bucket before a run and back up after.

    Two files: the DuckDB store and the gateway's ledger. Both are single-writer files, and
    the run lock is what makes a copy-modify-upload cycle safe: nothing else writes to the
    bucket's copies while the lock is held. Taken only inside the lock, by the CLI.

    A file that is not in the bucket yet is not an error on the first run: the run creates
    it and the push uploads it.
    """

    DB = "state/clippings.duckdb"
    LEDGER = "state/boundary.sqlite"

    def __init__(self, objects: ObjectStore, workdir: Path) -> None:
        self.objects = objects
        self.db = workdir / "clippings.duckdb"
        self.ledger = workdir / "boundary.sqlite"

    def pull(self) -> None:
        self.objects.download(self.DB, self.db)
        self.objects.download(self.LEDGER, self.ledger)

    def push(self) -> None:
        if self.db.is_file():
            self.objects.upload(self.db, self.DB)
        if self.ledger.is_file():
            self.objects.upload(self.ledger, self.LEDGER)
