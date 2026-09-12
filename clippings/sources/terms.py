"""The terms record, and the gate that makes it more than a document.

PLAN.md section 2.2: every source's terms are read and recorded in `docs/sources.md` with
the date read, and a source is dropped rather than bent. A document alone is a promise
nobody checks, so the document is also the registry: nothing is fetched unless its row in
`docs/sources.md` says `allowed` and carries a date.

The file holds one markdown table. Rows look like:

    | key | source | terms URL | date read | status | notes |

Status is one of:

    allowed   terms read on the date given, and they permit this use
    pending   not read yet; the fetcher refuses the source
    dropped   read, and they do not permit this use, or they changed; never fetched again
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal, NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_DOC = REPO_ROOT / "docs" / "sources.md"

Status = Literal["allowed", "pending", "dropped"]
STATUSES: frozenset[str] = frozenset({"allowed", "pending", "dropped"})

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A markdown link, so the terms column can be either a bare URL or [text](url).
MD_LINK = re.compile(r"\[[^\]]*\]\((?P<url>[^)]+)\)")


class TermsRecordError(ValueError):
    """The terms record does not parse, or a source is used without a row in it."""


class TermsRow(NamedTuple):
    """One recorded source."""

    key: str
    source: str
    terms_url: str
    date_read: date | None
    status: Status
    notes: str

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    # Drop the empty strings the leading and trailing pipes produce.
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _is_separator(cells: Iterable[str]) -> bool:
    return all(set(cell) <= set("-: ") and "-" in cell for cell in cells)


def _url(cell: str) -> str:
    match = MD_LINK.search(cell)
    return match.group("url").strip() if match else cell


def parse_terms(text: str) -> dict[str, TermsRow]:
    """Parse every table row in the terms document, keyed by the `terms` key."""
    rows: dict[str, TermsRow] = {}
    for line in text.splitlines():
        cells = _cells(line)
        if len(cells) < 5 or _is_separator(cells):
            continue
        key = cells[0]
        if key.lower() in {"key", "source"}:
            continue
        status = cells[4].lower()
        if status not in STATUSES:
            raise TermsRecordError(
                f"source {key!r}: status is {cells[4]!r}, expected one of "
                f"{', '.join(sorted(STATUSES))}"
            )
        raw_date = cells[3]
        date_read: date | None = None
        if raw_date and raw_date != "-":
            if not ISO_DATE.fullmatch(raw_date):
                raise TermsRecordError(
                    f"source {key!r}: date read is {raw_date!r}, expected YYYY-MM-DD"
                )
            date_read = date.fromisoformat(raw_date)
        if status == "allowed" and date_read is None:
            raise TermsRecordError(
                f"source {key!r}: status is allowed but no date read is recorded; "
                "the date the terms were read is the point of the record"
            )
        if key in rows:
            raise TermsRecordError(f"source {key!r}: recorded twice")
        rows[key] = TermsRow(
            key=key,
            source=cells[1],
            terms_url=_url(cells[2]),
            date_read=date_read,
            status=status,  # type: ignore[arg-type]  # checked against STATUSES above
            notes=cells[5] if len(cells) > 5 else "",
        )
    return rows


def load_terms(path: Path = SOURCES_DOC) -> dict[str, TermsRow]:
    """Load the terms record from `docs/sources.md`."""
    if not path.is_file():
        raise TermsRecordError(
            f"{path} does not exist; no source can be fetched until its terms are recorded"
        )
    return parse_terms(path.read_text(encoding="utf-8"))


class TermsGate:
    """Refuses any source whose terms are not recorded as read and allowed.

    Constructed once per run and consulted by every adapter before a request leaves.
    """

    def __init__(self, rows: dict[str, TermsRow] | None = None) -> None:
        self._rows = rows if rows is not None else load_terms()

    def row(self, key: str) -> TermsRow:
        try:
            return self._rows[key]
        except KeyError:
            raise TermsRecordError(
                f"source {key!r} has no row in docs/sources.md; read its terms and record "
                "them with the date before using it"
            ) from None

    def check(self, key: str) -> TermsRow:
        """Return the row, or raise if this source may not be fetched."""
        row = self.row(key)
        if row.status == "pending":
            raise TermsRecordError(
                f"source {key!r}: terms not read yet (status pending); it will not be fetched"
            )
        if row.status == "dropped":
            raise TermsRecordError(
                f"source {key!r}: dropped on {row.date_read} ({row.notes or 'no reason recorded'})"
            )
        return row

    def allows(self, key: str) -> bool:
        """Whether this source may be fetched, without raising. Used to skip and report."""
        return key in self._rows and self._rows[key].allowed

    def keys(self) -> frozenset[str]:
        return frozenset(self._rows)
