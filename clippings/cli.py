"""`clippings` on the command line.

    clippings run       fetch, extract and cluster a day for one audience or all of them
    clippings sources   check the terms record, or probe that the feeds are feeds
    clippings label     label a day's sample for precision and recall
    clippings retention delete items past the thirty-day window
    clippings audiences list the configured audiences

`eval`, `report` and `render` arrive with the measurement and delivery work in weeks two
and three. There is no send command, and there will not be one.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from clippings.cluster.embed import Hashing, default_embedder
from clippings.config.audience import Audience
from clippings.config.load import EXAMPLES, AudienceFileError, load_audience, load_audiences
from clippings.constants import RETENTION_DAYS
from clippings.eval.labels import build_queue, record
from clippings.ingest.pipeline import RunReport, new_run_id, run_audience
from clippings.ingest.remote import LocalRunLock, RunLockHeld
from clippings.ingest.store import Store
from clippings.sources.base import FetchContext, http_client
from clippings.sources.probe import PROBE_TIMEOUT, probe_audience
from clippings.sources.robots import RobotsCache
from clippings.sources.terms import TermsGate, TermsRecordError, load_terms

app = typer.Typer(add_completion=False, help=__doc__)
sources_app = typer.Typer(help="The terms record and what it permits.")
app.add_typer(sources_app, name="sources")

DEFAULT_DB = Path("data/clippings.duckdb")
DEFAULT_LOCK = Path("data/clippings.lock")

AudienceDir = Annotated[
    Path, typer.Option("--audiences", help="Directory of audience files.", show_default=False)
]
DbPath = Annotated[Path, typer.Option("--db", help="Path to the DuckDB file.")]


def _secrets() -> dict[str, str]:
    """Credentials from the environment. Nothing is read from a file in the repository."""
    return {
        key: value
        for key, value in os.environ.items()
        if key.startswith(("REDDIT_", "BLUESKY_", "GDELT_"))
    }


def _pick(directory: Path, audience_id: str | None) -> tuple[Audience, ...]:
    if audience_id:
        path = directory / f"{audience_id}.yaml"
        if not path.is_file():
            raise typer.BadParameter(f"no audience file at {path}")
        return (load_audience(path),)
    return load_audiences(directory)


def _print_report(report: RunReport) -> None:
    typer.echo(f"\n{report.audience_id}  run {report.run_id}  day {report.day}")
    typer.echo(
        f"  sources     {report.sources_ok}/{len(report.sources)} ok, "
        f"{report.fetched} items fetched, {report.new_items} new"
    )
    typer.echo(f"  extraction  {report.extracted} texts stored")
    for reason, count in sorted(report.extraction_skipped.items(), key=lambda pair: -pair[1]):
        typer.echo(f"                {count:4d}  {reason}")
    typer.echo(
        f"  clusters    {report.clusters} stories from {report.clustered_items} items "
        f"(collapse rate {report.collapse_rate:.2f}), embedder {report.embedder}"
    )
    if report.selected:
        displaced = f", {report.displaced} displaced for diversity" if report.displaced else ""
        typer.echo(f"  digest      {len(report.selected)} stories chosen{displaced}")
        for position, story in enumerate(report.selected, start=1):
            sources = f" +{story.cluster.size - 1}" if story.cluster.size > 1 else ""
            typer.echo(f"     {position:2d}. {story.score:.3f}  {story.representative.title[:66]}")
            typer.echo(f"         {story.representative.domain}{sources}   {story.why()}")
    for failure in report.failures():
        typer.echo(f"  ! {failure.source_key} {failure.origin}: {failure.detail}")


@app.command()
def run(
    audience: Annotated[str | None, typer.Argument(help="One audience id, or all of them.")] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    extract: Annotated[bool, typer.Option(help="Fetch and store article text.")] = True,
    real_embedder: Annotated[
        bool,
        typer.Option("--model/--no-model", help="Use bge-small rather than the hashing backend."),
    ] = True,
    lock: Annotated[Path, typer.Option(help="Run lock file.")] = DEFAULT_LOCK,
) -> None:
    """Fetch, extract and cluster today for one audience or all of them."""
    selected = _pick(audiences, audience)
    embedder = default_embedder(prefer_model=real_embedder) if real_embedder else Hashing()
    try:
        gate = TermsGate()
    except TermsRecordError as exc:
        typer.echo(f"terms record: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    try:
        with LocalRunLock(lock), http_client() as client, Store.open(db) as store:
            context = FetchContext(
                client=client,
                gate=gate,
                robots=RobotsCache(client),
                now=datetime.now(UTC),
                secrets=_secrets(),
            )
            run_id = new_run_id(context.now)
            for one in selected:
                report = run_audience(one, store, context, embedder, run_id=run_id, extract=extract)
                _print_report(report)
    except RunLockHeld as exc:
        typer.echo(f"another run holds the lock: {exc}", err=True)
        raise typer.Exit(code=3) from exc


@sources_app.command("check")
def sources_check(audiences: AudienceDir = EXAMPLES) -> None:
    """Check every source in every audience file against the terms record.

    Exits non-zero if a source has no row or is not yet allowed, which is what keeps a
    source from being used before its terms have been read.
    """
    try:
        rows = load_terms()
    except TermsRecordError as exc:
        typer.echo(f"terms record: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    missing: list[str] = []
    not_allowed: list[str] = []
    allowed: list[str] = []
    for audience in load_audiences(audiences):
        keys = {feed.terms for feed in audience.sources.feeds}
        if audience.sources.gdelt.queries:
            keys.add("gdelt")
        if audience.sources.reddit.subreddits:
            keys.add("reddit")
        if audience.sources.bluesky.queries:
            keys.add("bluesky")
        for key in sorted(keys):
            row = rows.get(key)
            if row is None:
                missing.append(f"{audience.id}: {key}")
            elif not row.allowed:
                not_allowed.append(f"{audience.id}: {key} ({row.status})")
            else:
                allowed.append(f"{key} (read {row.date_read})")

    for line in sorted(set(allowed)):
        typer.echo(f"  allowed  {line}")
    for line in not_allowed:
        typer.echo(f"  waiting  {line}", err=True)
    for line in missing:
        typer.echo(f"  MISSING  {line}", err=True)

    if missing or not_allowed:
        typer.echo(
            f"\n{len(set(missing))} source(s) with no row and {len(set(not_allowed))} not yet "
            "allowed. Read the terms, record the date in docs/sources.md, then run this again.",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(f"\nAll {len(set(allowed))} sources have terms recorded and allowed.")


@sources_app.command("probe")
def sources_probe(
    audience: Annotated[str | None, typer.Argument(help="One audience id, or all of them.")] = None,
    audiences: AudienceDir = EXAMPLES,
) -> None:
    """Fetch every feed once and report what came back.

    Run this when adding a source and when a run's yield drops. A feed URL is a guess until
    something fetches it, and the failure this is really for is the 200 that contains a web
    page rather than a feed, which a run would otherwise count as a healthy source.

    Makes one request per feed, so it is never part of a run or of CI.
    """
    selected = _pick(audiences, audience)
    failures = 0
    with http_client(timeout=PROBE_TIMEOUT) as client:
        for one in selected:
            typer.echo(f"\n{one.id}")
            for result in probe_audience(client, one):
                typer.echo(result.line)
                typer.echo(f"        {result.feed.url}")
                failures += not result.ok
    if failures:
        typer.echo(f"\n{failures} feed(s) did not return a usable feed.", err=True)
        raise typer.Exit(code=1)
    typer.echo("\nEvery configured feed returned entries.")


@app.command()
def audiences_list(audiences: AudienceDir = EXAMPLES) -> None:
    """List the configured audiences."""
    try:
        for audience in load_audiences(audiences):
            typer.echo(
                f"{audience.id:24s} {len(audience.sources.feeds)} feeds, "
                f"{audience.digest.max_stories} stories, {audience.delivery.time_local} "
                f"{audience.delivery.timezone}"
            )
    except AudienceFileError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc


@app.command()
def label(
    audience: Annotated[str, typer.Argument(help="Audience id.")],
    labeller: Annotated[str, typer.Option(help="Who is labelling; two are needed for kappa.")],
    day: Annotated[str | None, typer.Option(help="Day to label, YYYY-MM-DD.")] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    limit: Annotated[int, typer.Option(help="Stop after this many labels.")] = 60,
) -> None:
    """Label a day's sample: the top thirty, plus thirty drawn at random from the rest."""
    one = _pick(audiences, audience)[0]
    day = day or datetime.now(UTC).date().isoformat()
    with Store.open(db) as store:
        queue = build_queue(store, one.id, day, labeller, audience=one, embedder=default_embedder())
        if not queue.questions:
            typer.echo(f"nothing left to label for {one.id} on {day}")
            return
        typer.echo(f"\n{one.name} - {day}")
        typer.echo(f"Rubric: {one.rubric.strip()}\n")
        typer.echo(f"{queue.remaining} to label. y = relevant, n = not, s = skip, q = stop.\n")
        done = 0
        for index, question in enumerate(queue.questions[:limit], start=1):
            typer.echo(f"[{index}/{min(queue.remaining, limit)}] {question.prompt}")
            answer = typer.prompt("  relevant?", default="s").strip().lower()[:1]
            if answer == "q":
                break
            if answer in {"y", "n"}:
                record(store, queue, question, relevant=answer == "y")
                done += 1
            typer.echo("")
        typer.echo(f"{done} labels recorded for {one.id} on {day} by {labeller}.")


@app.command()
def retention(
    db: DbPath = DEFAULT_DB,
    days: Annotated[int, typer.Option(help="Retention window in days.")] = RETENTION_DAYS,
) -> None:
    """Delete items past the retention window, and their extracted text."""
    with Store.open(db) as store:
        deleted = store.retention(days=days)
    typer.echo(
        f"deleted {deleted['items']} items and {deleted['texts']} extracted texts "
        f"older than {days} days"
    )


if __name__ == "__main__":
    app()
