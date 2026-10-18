"""One DuckDB file per environment: items, clusters, watermarks and the run lock.

PLAN.md section 2.5. The file is synchronised to a Cloud Storage bucket in production and
sits on disk in development; `clippings.ingest.remote` holds that half. This module owns
the schema, the writes, the watermarks and the thirty-day retention.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Self

import duckdb

from clippings.constants import RETENTION_DAYS
from clippings.models import Cluster, Item, ItemText, Label, PairLabel, PurityLabel

if TYPE_CHECKING:
    from clippings.assemble.digest import Digest

SCHEMA_VERSION = 6

# The pair-label columns added in version 5, created in place on older files.
PAIR_COLUMNS = (
    ("stratum", "TEXT DEFAULT ''"),
    ("weight", "DOUBLE DEFAULT 0"),
    ("together", "BOOLEAN DEFAULT FALSE"),
    ("left_url", "TEXT DEFAULT ''"),
    ("left_title", "TEXT DEFAULT ''"),
    ("right_url", "TEXT DEFAULT ''"),
    ("right_title", "TEXT DEFAULT ''"),
)

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

-- Cluster purity: per item of a story with several news items, whether it belongs with the
-- rest. Version 6; a new table, so older files gain it on open.
CREATE TABLE IF NOT EXISTS purity_labels (
    audience_id  TEXT NOT NULL,
    day          TEXT NOT NULL,
    cluster_id   TEXT NOT NULL,
    item_id      TEXT NOT NULL,
    labeller     TEXT NOT NULL,
    belongs      BOOLEAN NOT NULL,
    cluster_size INTEGER NOT NULL,
    pool_items   INTEGER NOT NULL,
    url          TEXT NOT NULL,
    title        TEXT NOT NULL,
    labelled_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (audience_id, day, cluster_id, item_id, labeller)
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

-- The order a run put a day's candidates in, after the re-ranker: what the digest was chosen
-- from, and what the week-3 labelling sample calls "top thirty". Scores and the model's
-- one-line reason only; no text.
CREATE TABLE IF NOT EXISTS rankings (
    audience_id TEXT NOT NULL,
    day         TEXT NOT NULL,
    run_id      TEXT NOT NULL,
    position    INTEGER NOT NULL,
    cluster_id  TEXT NOT NULL,
    prefilter   DOUBLE NOT NULL,
    rerank      INTEGER,
    final       DOUBLE NOT NULL,
    reason      TEXT NOT NULL,
    PRIMARY KEY (audience_id, day, run_id, position)
);

-- One row per published digest, as JSON. A digest holds summaries, quotes of at most
-- twenty-five words, titles and links, never article text, so it is kept after retention
-- deletes the items it was built from: it is the archive, and week 3 measures from it.
CREATE TABLE IF NOT EXISTS digests (
    audience_id  TEXT NOT NULL,
    day          TEXT NOT NULL,
    run_id       TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    body         TEXT NOT NULL,
    PRIMARY KEY (audience_id, day, run_id)
);
"""


@dataclass(frozen=True)
class FetchRecord:
    """One attempt at one source: when, how many new items, and what went wrong if anything."""

    at: datetime
    items: int
    ok: bool
    detail: str


class Store:
    """The pipeline's database. Open it with `Store.open`, or as a context manager."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection
        # DuckDB hands TIMESTAMPTZ values back in the session's time zone, which defaults to
        # the machine's. Every time this project stores is UTC, and a page that printed a
        # Warsaw wall-clock time labelled UTC (found 2026-10-02) is the bug this prevents.
        self._connection.execute("SET TimeZone = 'UTC'")
        self._connection.execute(SCHEMA)
        # Version 4: must-read labels. Added in place, so label files from before keep
        # every label they hold, with must_read false and graded false.
        self._connection.execute(
            "ALTER TABLE labels ADD COLUMN IF NOT EXISTS must_read BOOLEAN DEFAULT FALSE"
        )
        self._connection.execute(
            "ALTER TABLE labels ADD COLUMN IF NOT EXISTS graded BOOLEAN DEFAULT FALSE"
        )
        # Version 5: pair labels carry their stratum, weight, the clustering's decision and
        # both items' URLs and titles. No pair had been labelled before, so the defaults are
        # never read as a judgement.
        for column, kind in PAIR_COLUMNS:
            self._connection.execute(
                f"ALTER TABLE pair_labels ADD COLUMN IF NOT EXISTS {column} {kind}"
            )
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

    def checkpoint(self) -> None:
        """Write everything to the database file, so a copy of the file taken now is whole."""
        self._connection.execute("CHECKPOINT")

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

    def last_fetches(self, audience_id: str) -> dict[tuple[str, str], FetchRecord]:
        """Each source's most recent attempt for this audience, by (source key, origin)."""
        rows = self._connection.execute(
            "SELECT source_key, origin, max(started_at), arg_max(items, started_at), "
            "arg_max(ok, started_at), arg_max(detail, started_at) FROM fetch_log "
            "WHERE audience_id = ? GROUP BY source_key, origin",
            [audience_id],
        ).fetchall()
        return {
            (str(row[0]), str(row[1])): FetchRecord(row[2], int(row[3]), bool(row[4]), str(row[5]))
            for row in rows
        }

    def reads_since(self, source_key: str, since: datetime) -> dict[str, int]:
        """Items fetched from one source since a time, summed by origin, failures included.

        For a source billed per item read (X), this is what the run checks against its cap
        before asking for more.
        """
        rows = self._connection.execute(
            "SELECT origin, sum(items) FROM fetch_log "
            "WHERE source_key = ? AND started_at >= ? GROUP BY origin",
            [source_key, since],
        ).fetchall()
        return {str(row[0]): int(row[1] or 0) for row in rows}

    # -- labels --------------------------------------------------------------------------

    def add_label(self, label: Label) -> None:
        """Record one relevance label. Re-labelling the same item replaces the label."""
        self._connection.execute(
            """
            INSERT INTO labels (
                audience_id, day, item_id, labeller, relevant, stratum, rank, weight,
                url, title, labelled_at, must_read, graded
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (audience_id, day, item_id, labeller) DO UPDATE SET
                relevant = excluded.relevant, labelled_at = excluded.labelled_at,
                must_read = excluded.must_read, graded = excluded.graded
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
                label.must_read,
                label.graded,
            ],
        )

    def labels_for(
        self, audience_id: str, day: str | None = None, labeller: str | None = None
    ) -> list[Label]:
        query = (
            "SELECT audience_id, day, item_id, labeller, relevant, stratum, rank, weight, "
            "url, title, labelled_at, must_read, graded FROM labels WHERE audience_id = ?"
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
                must_read=bool(row[11]),
                graded=bool(row[12]),
            )
            for row in rows
        ]

    def all_labels(self) -> list[Label]:
        """Every label in this file, whoever gave it."""
        audiences = self._connection.execute("SELECT DISTINCT audience_id FROM labels").fetchall()
        return [label for (audience_id,) in audiences for label in self.labels_for(audience_id)]

    def labelled_ids(
        self, audience_id: str, day: str, labeller: str, *, graded_only: bool = False
    ) -> set[str]:
        """Which items this labeller has already done, so the CLI can resume. With
        `graded_only`, only those judged on a page that offered "must read"."""
        query = "SELECT item_id FROM labels WHERE audience_id = ? AND day = ? AND labeller = ?"
        if graded_only:
            query += " AND graded"
        rows = self._connection.execute(query, [audience_id, day, labeller]).fetchall()
        return {str(row[0]) for row in rows}

    def previous_labels(self, audience_id: str, labeller: str) -> dict[str, tuple[bool, bool, str]]:
        """This labeller's latest judgement of each item: relevant, must read, and the day.

        A story stays in the pool for two days, so most of a day's sample was judged the day
        before. The labelling page shows that judgement as the starting answer; it is still
        the labeller who confirms it for the new day.
        """
        rows = self._connection.execute(
            "SELECT item_id, relevant, must_read, day FROM labels "
            "WHERE audience_id = ? AND labeller = ? ORDER BY labelled_at",
            [audience_id, labeller],
        ).fetchall()
        return {str(row[0]): (bool(row[1]), bool(row[2]), str(row[3])) for row in rows}

    def add_pair_label(self, label: PairLabel) -> None:
        """Record one pair judgement. Judging the same pair again replaces it."""
        left, right = sorted((label.left_id, label.right_id))
        if (left, right) != (label.left_id, label.right_id):
            raise ValueError("a pair label's left_id must sort before its right_id")
        self._connection.execute(
            """
            INSERT INTO pair_labels (
                audience_id, day, left_id, right_id, labeller, same_story, labelled_at,
                stratum, weight, together, left_url, left_title, right_url, right_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (audience_id, day, left_id, right_id, labeller) DO UPDATE SET
                same_story = excluded.same_story, labelled_at = excluded.labelled_at
            """,
            [
                label.audience_id,
                label.day,
                label.left_id,
                label.right_id,
                label.labeller,
                label.same_story,
                label.labelled_at,
                label.stratum,
                label.weight,
                label.together,
                label.left_url,
                label.left_title,
                label.right_url,
                label.right_title,
            ],
        )

    def pair_labels_for(
        self, audience_id: str | None = None, day: str | None = None, labeller: str | None = None
    ) -> list[PairLabel]:
        query = (
            "SELECT audience_id, day, left_id, right_id, labeller, same_story, stratum, weight, "
            "together, left_url, left_title, right_url, right_title, labelled_at "
            "FROM pair_labels WHERE TRUE"
        )
        params: list[object] = []
        for column, value in (("audience_id", audience_id), ("day", day), ("labeller", labeller)):
            if value is not None:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY audience_id, day, left_id, right_id"
        return [
            PairLabel(
                audience_id=row[0],
                day=row[1],
                left_id=row[2],
                right_id=row[3],
                labeller=row[4],
                same_story=bool(row[5]),
                stratum=row[6],
                weight=row[7],
                together=bool(row[8]),
                left_url=row[9],
                left_title=row[10],
                right_url=row[11],
                right_title=row[12],
                labelled_at=row[13],
            )
            for row in self._connection.execute(query, params).fetchall()
        ]

    def add_purity_label(self, label: PurityLabel) -> None:
        """Record one item's judgement. Judging it again replaces it."""
        self._connection.execute(
            """
            INSERT INTO purity_labels (
                audience_id, day, cluster_id, item_id, labeller, belongs, cluster_size,
                pool_items, url, title, labelled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (audience_id, day, cluster_id, item_id, labeller) DO UPDATE SET
                belongs = excluded.belongs, labelled_at = excluded.labelled_at
            """,
            [
                label.audience_id,
                label.day,
                label.cluster_id,
                label.item_id,
                label.labeller,
                label.belongs,
                label.cluster_size,
                label.pool_items,
                label.url,
                label.title,
                label.labelled_at,
            ],
        )

    def purity_labels_for(
        self, audience_id: str | None = None, day: str | None = None, labeller: str | None = None
    ) -> list[PurityLabel]:
        query = (
            "SELECT audience_id, day, cluster_id, item_id, labeller, belongs, cluster_size, "
            "pool_items, url, title, labelled_at FROM purity_labels WHERE TRUE"
        )
        params: list[object] = []
        for column, value in (("audience_id", audience_id), ("day", day), ("labeller", labeller)):
            if value is not None:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY audience_id, day, cluster_id, item_id"
        return [
            PurityLabel(
                audience_id=row[0],
                day=row[1],
                cluster_id=row[2],
                item_id=row[3],
                labeller=row[4],
                belongs=bool(row[5]),
                cluster_size=row[6],
                pool_items=row[7],
                url=row[8],
                title=row[9],
                labelled_at=row[10],
            )
            for row in self._connection.execute(query, params).fetchall()
        ]

    # -- rankings and digests ------------------------------------------------------------

    def cluster_days(self, audience_id: str) -> list[str]:
        """The days this audience's pool was clustered, oldest first: the days there are to label."""
        rows = self._connection.execute(
            "SELECT DISTINCT day FROM clusters WHERE audience_id = ? ORDER BY day", [audience_id]
        ).fetchall()
        return [str(row[0]) for row in rows]

    def save_ranking(
        self,
        audience_id: str,
        day: str,
        run_id: str,
        rows: Sequence[tuple[str, float, int | None, float, str]],
    ) -> None:
        """Rows of (cluster id, pre-filter, rerank score or None, final, reason), best first."""
        self._connection.executemany(
            "INSERT INTO rankings (audience_id, day, run_id, position, cluster_id, prefilter, "
            "rerank, final, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [
                [audience_id, day, run_id, position, *row]
                for position, row in enumerate(rows, start=1)
            ],
        )

    def ranking_for(self, audience_id: str, day: str) -> list[str]:
        """Cluster ids in the order the day's latest run ranked them; empty if none ran."""
        latest = self._connection.execute(
            "SELECT max(run_id) FROM rankings WHERE audience_id = ? AND day = ?",
            [audience_id, day],
        ).fetchone()
        if not latest or latest[0] is None:
            return []
        rows = self._connection.execute(
            "SELECT cluster_id FROM rankings WHERE audience_id = ? AND day = ? AND run_id = ? "
            "ORDER BY position",
            [audience_id, day, latest[0]],
        ).fetchall()
        return [str(row[0]) for row in rows]

    def save_digest(self, digest: Digest) -> None:
        self._connection.execute(
            "INSERT INTO digests (audience_id, day, run_id, generated_at, body) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (audience_id, day, run_id) DO UPDATE SET "
            "generated_at = excluded.generated_at, body = excluded.body",
            [
                digest.audience_id,
                digest.day,
                digest.run_id,
                digest.generated_at,
                digest.model_dump_json(),
            ],
        )

    def digest_for(self, audience_id: str, day: str) -> Digest | None:
        """The latest digest built for this audience on this day."""
        from clippings.assemble.digest import Digest

        row = self._connection.execute(
            "SELECT body FROM digests WHERE audience_id = ? AND day = ? "
            "ORDER BY generated_at DESC, run_id DESC LIMIT 1",
            [audience_id, day],
        ).fetchone()
        return Digest.model_validate_json(row[0]) if row else None

    def digest_runs(self, audience_id: str, day: str) -> list[Digest]:
        """Every digest built for this audience on this day, one per run, latest first.

        `digest_for` gives the one that is shown; this gives all of them, for a change that
        must reach every stored copy, such as removing an X post's words.
        """
        from clippings.assemble.digest import Digest

        rows = self._connection.execute(
            "SELECT body FROM digests WHERE audience_id = ? AND day = ? "
            "ORDER BY generated_at DESC, run_id DESC",
            [audience_id, day],
        ).fetchall()
        return [Digest.model_validate_json(row[0]) for row in rows]

    def previous_digest_at(self, audience_id: str, day: str) -> datetime | None:
        """When the latest digest before `day` was built: what it could show, it has shown."""
        row = self._connection.execute(
            "SELECT max(generated_at) FROM digests WHERE audience_id = ? AND day < ?",
            [audience_id, day],
        ).fetchone()
        return row[0] if row and row[0] is not None else None

    def digest_days(self, audience_id: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT day FROM digests WHERE audience_id = ? ORDER BY day DESC",
            [audience_id],
        ).fetchall()
        return [str(row[0]) for row in rows]

    def texts_for(self, item_ids: Iterable[str]) -> dict[str, ItemText]:
        ids = list(item_ids)
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            "SELECT item_id, text, extracted_at, words FROM item_text "
            f"WHERE item_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {
            row[0]: ItemText(item_id=row[0], text=row[1], extracted_at=row[2], words=row[3])
            for row in rows
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
