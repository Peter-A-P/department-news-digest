"""One DuckDB file per environment: items, clusters, watermarks and the run lock.

PLAN.md section 2.5. The file is synchronised to a Cloud Storage bucket in production and
sits on disk in development; `clippings.ingest.remote` holds that half. This module owns
the schema, the writes, the watermarks and the thirty-day retention.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self

import duckdb

from clippings.constants import RETENTION_DAYS
from clippings.models import Cluster, Item, ItemText, Label

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source_key    TEXT NOT NULL,
    source_kind   TEXT NOT NULL,
    url           TEXT NOT NULL,
    original_url  TEXT NOT NULL,
    domain        TEXT NOT NULL,
    title         TEXT NOT NULL,
    summary       TEXT NOT NULL,
    author        TEXT,
    language      TEXT,
    published_at  TIMESTAMPTZ NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL,
    origin        TEXT NOT NULL,
    score         INTEGER,
    comments      INTEGER
);

-- Which audiences have seen an item. One item, many audiences: the same article reaching
-- two departments is one row in items and two here.
CREATE TABLE IF NOT EXISTS item_audiences (
    item_id     TEXT NOT NULL,
    audience_id TEXT NOT NULL,
    first_seen  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (item_id, audience_id)
);

-- Extracted article text. Deleted at thirty days by retention(), separately from the item
-- row, which keeps its title, link and metadata.
CREATE TABLE IF NOT EXISTS item_text (
    item_id      TEXT PRIMARY KEY,
    text         TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL,
    words        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters (
    id                TEXT NOT NULL,
    audience_id       TEXT NOT NULL,
    day               TEXT NOT NULL,
    representative_id TEXT NOT NULL,
    item_ids          TEXT NOT NULL,
    PRIMARY KEY (id, audience_id, day)
);

-- How far each source has been read, so a run picks up where the last one stopped.
CREATE TABLE IF NOT EXISTS watermarks (
    audience_id TEXT NOT NULL,
    source_key  TEXT NOT NULL,
    origin      TEXT NOT NULL,
    watermark   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (audience_id, source_key, origin)
);

-- Relevance labels. The item's title and link are copied in, so a label survives the
-- thirty-day deletion of the item it was made on and the labelled week stays publishable
-- as ids, URLs and labels (PLAN.md section 3).
CREATE TABLE IF NOT EXISTS labels (
    audience_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    item_id     TEXT NOT NULL,
    labeller    TEXT NOT NULL,
    relevant    BOOLEAN NOT NULL,
    stratum     TEXT NOT NULL,
    rank        INTEGER NOT NULL,
    weight      DOUBLE NOT NULL,
    url         TEXT NOT NULL,
    title       TEXT NOT NULL,
    labelled_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (audience_id, day, item_id, labeller)
);

-- Labelled item pairs for the deduplication numbers.
CREATE TABLE IF NOT EXISTS pair_labels (
    audience_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    left_id     TEXT NOT NULL,
    right_id    TEXT NOT NULL,
    labeller    TEXT NOT NULL,
    same_story  BOOLEAN NOT NULL,
    labelled_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (audience_id, day, left_id, right_id, labeller)
);

-- One row per fetch attempt per source, so source yield and failures are countable.
CREATE TABLE IF NOT EXISTS fetch_log (
    run_id      TEXT NOT NULL,
    audience_id TEXT NOT NULL,
    source_key  TEXT NOT NULL,
    origin      TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL,
    items       INTEGER NOT NULL,
    ok          BOOLEAN NOT NULL,
    detail      TEXT NOT NULL
);
"""


class Store:
    """The pipeline's database. Open it with `Store.open`, or as a context manager."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection
        self._connection.execute(SCHEMA)
        self._connection.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [str(SCHEMA_VERSION)],
        )

    @classmethod
    def open(cls, path: Path | str) -> Self:
        """Open (or create) the database file at `path`."""
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return cls(duckdb.connect(str(path)))

    @classmethod
    def memory(cls) -> Self:
        """An in-memory database, for tests."""
        return cls(duckdb.connect(":memory:"))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    # -- items ---------------------------------------------------------------------------

    def add_items(self, items: Iterable[Item], audience_id: str) -> int:
        """Insert items and link them to an audience. Returns the number newly inserted.

        An item already in the store keeps its first row: the earliest fetch is the one the
        timeliness measurement wants.
        """
        rows = list(items)
        if not rows:
            return 0
        before = self.count_items()
        self._connection.executemany(
            """
            INSERT INTO items (
                id, source_key, source_kind, url, original_url, domain, title, summary,
                author, language, published_at, fetched_at, origin, score, comments
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO NOTHING
            """,
            [
                [
                    item.id,
                    item.source_key,
                    item.source_kind,
                    item.url,
                    item.original_url,
                    item.domain,
                    item.title,
                    item.summary,
                    item.author,
                    item.language,
                    item.published_at,
                    item.fetched_at,
                    item.origin,
                    item.score,
                    item.comments,
                ]
                for item in rows
            ],
        )
        now = datetime.now(UTC)
        self._connection.executemany(
            "INSERT INTO item_audiences (item_id, audience_id, first_seen) VALUES (?, ?, ?) "
            "ON CONFLICT (item_id, audience_id) DO NOTHING",
            [[item.id, audience_id, now] for item in rows],
        )
        return self.count_items() - before

    def count_items(self) -> int:
        row = self._connection.execute("SELECT count(*) FROM items").fetchone()
        return int(row[0]) if row else 0

    def items_for(self, audience_id: str, since: datetime | None = None) -> list[Item]:
        """Every item this audience has seen, newest first."""
        query = """
            SELECT i.* FROM items i
            JOIN item_audiences a ON a.item_id = i.id
            WHERE a.audience_id = ?
        """
        params: list[object] = [audience_id]
        if since is not None:
            query += " AND i.published_at >= ?"
            params.append(since)
        query += " ORDER BY i.published_at DESC"
        cursor = self._connection.execute(query, params)
        columns = [description[0] for description in cursor.description or []]
        return [
            Item.model_validate(dict(zip(columns, row, strict=True))) for row in cursor.fetchall()
        ]

    def item_ids(self) -> set[str]:
        return {str(row[0]) for row in self._connection.execute("SELECT id FROM items").fetchall()}

    # -- extracted text ------------------------------------------------------------------

    def add_text(self, text: ItemText) -> None:
        self._connection.execute(
            "INSERT INTO item_text (item_id, text, extracted_at, words) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (item_id) DO UPDATE SET "
            "text = excluded.text, extracted_at = excluded.extracted_at, words = excluded.words",
            [text.item_id, text.text, text.extracted_at, text.words],
        )

    def text_for(self, item_id: str) -> ItemText | None:
        row = self._connection.execute(
            "SELECT item_id, text, extracted_at, words FROM item_text WHERE item_id = ?",
            [item_id],
        ).fetchone()
        if row is None:
            return None
        return ItemText(item_id=row[0], text=row[1], extracted_at=row[2], words=row[3])

    # -- clusters ------------------------------------------------------------------------

    def save_clusters(self, clusters: Sequence[Cluster]) -> None:
        if not clusters:
            return
        audience_id = clusters[0].audience_id
        day = clusters[0].day
        self._connection.execute(
            "DELETE FROM clusters WHERE audience_id = ? AND day = ?", [audience_id, day]
        )
        self._connection.executemany(
            "INSERT INTO clusters (id, audience_id, day, representative_id, item_ids) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                [c.id, c.audience_id, c.day, c.representative_id, json.dumps(list(c.item_ids))]
                for c in clusters
            ],
        )

    def clusters_for(self, audience_id: str, day: str) -> list[Cluster]:
        rows = self._connection.execute(
            "SELECT id, audience_id, day, representative_id, item_ids FROM clusters "
            "WHERE audience_id = ? AND day = ? ORDER BY id",
            [audience_id, day],
        ).fetchall()
        return [
            Cluster(
                id=row[0],
                audience_id=row[1],
                day=row[2],
                representative_id=row[3],
                item_ids=tuple(json.loads(row[4])),
            )
            for row in rows
        ]

    # -- watermarks ----------------------------------------------------------------------

    def watermark(self, audience_id: str, source_key: str, origin: str) -> datetime | None:
        """How far this source has been read for this audience."""
        row = self._connection.execute(
            "SELECT watermark FROM watermarks "
            "WHERE audience_id = ? AND source_key = ? AND origin = ?",
            [audience_id, source_key, origin],
        ).fetchone()
        return row[0] if row else None

    def set_watermark(
        self, audience_id: str, source_key: str, origin: str, watermark: datetime
    ) -> None:
        """Move a watermark forward. It never moves backwards."""
        self._connection.execute(
            """
            INSERT INTO watermarks (audience_id, source_key, origin, watermark)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (audience_id, source_key, origin) DO UPDATE
            SET watermark = greatest(watermarks.watermark, excluded.watermark)
            """,
            [audience_id, source_key, origin, watermark],
        )

    # -- fetch log -----------------------------------------------------------------------

    def log_fetch(
        self,
        run_id: str,
        audience_id: str,
        source_key: str,
        origin: str,
        started_at: datetime,
        items: int,
        ok: bool,
        detail: str = "",
    ) -> None:
        self._connection.execute(
            "INSERT INTO fetch_log (run_id, audience_id, source_key, origin, started_at, "
            "items, ok, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [run_id, audience_id, source_key, origin, started_at, items, ok, detail],
        )

    # -- labels --------------------------------------------------------------------------

    def add_label(self, label: Label) -> None:
        """Record one relevance label. Re-labelling the same item replaces the label."""
        self._connection.execute(
            """
            INSERT INTO labels (
                audience_id, day, item_id, labeller, relevant, stratum, rank, weight,
                url, title, labelled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (audience_id, day, item_id, labeller) DO UPDATE SET
                relevant = excluded.relevant, labelled_at = excluded.labelled_at
            """,
            [
                label.audience_id,
                label.day,
                label.item_id,
                label.labeller,
                label.relevant,
                label.stratum,
                label.rank,
                label.weight,
                label.url,
                label.title,
                label.labelled_at,
            ],
        )

    def labels_for(
        self, audience_id: str, day: str | None = None, labeller: str | None = None
    ) -> list[Label]:
        query = (
            "SELECT audience_id, day, item_id, labeller, relevant, stratum, rank, weight, "
            "url, title, labelled_at FROM labels WHERE audience_id = ?"
        )
        params: list[object] = [audience_id]
        if day is not None:
            query += " AND day = ?"
            params.append(day)
        if labeller is not None:
            query += " AND labeller = ?"
            params.append(labeller)
        query += " ORDER BY day, rank, item_id"
        rows = self._connection.execute(query, params).fetchall()
        return [
            Label(
                audience_id=row[0],
                day=row[1],
                item_id=row[2],
                labeller=row[3],
                relevant=row[4],
                stratum=row[5],
                rank=row[6],
                weight=row[7],
                url=row[8],
                title=row[9],
                labelled_at=row[10],
            )
            for row in rows
        ]

    def labelled_ids(self, audience_id: str, day: str, labeller: str) -> set[str]:
        """Which items this labeller has already done, so the CLI can resume."""
        rows = self._connection.execute(
            "SELECT item_id FROM labels WHERE audience_id = ? AND day = ? AND labeller = ?",
            [audience_id, day, labeller],
        ).fetchall()
        return {str(row[0]) for row in rows}

    def add_pair_label(
        self,
        audience_id: str,
        day: str,
        left_id: str,
        right_id: str,
        labeller: str,
        same_story: bool,
    ) -> None:
        left, right = sorted((left_id, right_id))
        self._connection.execute(
            "INSERT INTO pair_labels (audience_id, day, left_id, right_id, labeller, "
            "same_story, labelled_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (audience_id, day, left_id, right_id, labeller) DO UPDATE SET "
            "same_story = excluded.same_story, labelled_at = excluded.labelled_at",
            [audience_id, day, left, right, labeller, same_story, datetime.now(UTC)],
        )

    def pair_labels_for(
        self, audience_id: str, day: str | None = None
    ) -> dict[tuple[str, str], bool]:
        query = "SELECT left_id, right_id, same_story FROM pair_labels WHERE audience_id = ?"
        params: list[object] = [audience_id]
        if day is not None:
            query += " AND day = ?"
            params.append(day)
        return {
            (str(row[0]), str(row[1])): bool(row[2])
            for row in self._connection.execute(query, params).fetchall()
        }

    # -- retention -----------------------------------------------------------------------

    def retention(self, now: datetime | None = None, days: int = RETENTION_DAYS) -> dict[str, int]:
        """Delete items older than the retention window, and their extracted text.

        Article text is kept thirty days and never republished (PLAN.md section 2.2). The
        item row goes with it: what remains after thirty days is nothing, which is the
        promise. Labels and digests reference item ids and keep their own copies of the
        title and link, so the measurement survives the deletion.
        """
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        expired = [
            str(row[0])
            for row in self._connection.execute(
                "SELECT id FROM items WHERE published_at < ?", [cutoff]
            ).fetchall()
        ]
        if not expired:
            return {"items": 0, "texts": 0}
        placeholders = ", ".join("?" for _ in expired)
        texts_row = self._connection.execute(
            f"SELECT count(*) FROM item_text WHERE item_id IN ({placeholders})", expired
        ).fetchone()
        texts = int(texts_row[0]) if texts_row else 0
        self._connection.execute(
            f"DELETE FROM item_text WHERE item_id IN ({placeholders})", expired
        )
        self._connection.execute(
            f"DELETE FROM item_audiences WHERE item_id IN ({placeholders})", expired
        )
        self._connection.execute(f"DELETE FROM items WHERE id IN ({placeholders})", expired)
        return {"items": len(expired), "texts": texts}
