"""`clippings` on the command line.

    clippings run       a day for one audience or all of them: fetch to published page
    clippings render    re-render stored digests to the site directory
    clippings serve     serve the published pages, read-only
    clippings sources   check the terms record, or probe that the feeds are feeds
    clippings label     label a day's sample for precision and recall
    clippings retention delete items past the thirty-day window
    clippings audiences list the configured audiences

`eval` and `report` arrive with the measurement work in week three. There is no send
command, and there will not be one.
"""

from __future__ import annotations

import os
import webbrowser
from contextlib import ExitStack, suppress
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from wsgiref.simple_server import make_server

import typer

from clippings import graph
from clippings.assemble.deletions import recheck_picks
from clippings.assemble.digest import Digest
from clippings.assemble.publish import GcsSite, LocalSite, Site, publish_digest, publish_indexes
from clippings.assemble.sources_panel import panel_for
from clippings.cluster.embed import Hashing, default_embedder
from clippings.config.audience import Audience
from clippings.config.load import EXAMPLES, AudienceFileError, load_audience, load_audiences
from clippings.constants import RETENTION_DAYS, cad
from clippings.eval.label_ui import Workspace
from clippings.eval.label_ui import application as label_application
from clippings.eval.report import (
    all_labels,
    build_report,
    detail,
    readme_tables,
    replace_between_markers,
)
from clippings.gateway import (
    GatewayClient,
    ModelClient,
    SpendCapReached,
    SpendNotAllowed,
    open_client,
)
from clippings.graph import Pipeline
from clippings.ingest.pipeline import RunReport, new_run_id
from clippings.ingest.remote import (
    GcsObjectStore,
    GcsRunLock,
    LocalRunLock,
    RunLockHeld,
    StateSync,
)
from clippings.ingest.store import Store
from clippings.sources.base import FetchContext, http_client
from clippings.sources.probe import PROBE_TIMEOUT, probe_audience
from clippings.sources.robots import RobotsCache
from clippings.sources.terms import (
    SOURCES_DOC,
    STATUSES,
    TermsGate,
    TermsRecordError,
    load_terms,
    record_reading,
)

app = typer.Typer(add_completion=False, help=__doc__)
sources_app = typer.Typer(help="The terms record and what it permits.")
app.add_typer(sources_app, name="sources")

DEFAULT_DB = Path("data/clippings.duckdb")
DEFAULT_LOCK = Path("data/clippings.lock")
DEFAULT_SITE = Path("out/site")
# The gateway's ledger sits beside the database, so one directory (or one bucket prefix)
# holds every record a run writes.
LEDGER_NAME = "boundary.sqlite"

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
    site: Annotated[Path, typer.Option(help="Directory the digest pages are written to.")] = (
        DEFAULT_SITE
    ),
    bucket: Annotated[
        str | None,
        typer.Option(
            envvar="CLIPPINGS_BUCKET",
            help="Cloud Storage bucket: the database, the ledger, the lock and the site live "
            "there, and the run works on local copies. Production only.",
        ),
    ] = None,
) -> None:
    """Fetch, rank, re-rank, summarise, verify and publish today's digest.

    Model calls are made only when CLIPPINGS_ALLOW_SPEND=1 is set. Without it the run stops
    after the free stages and prints what the pre-filter would have chosen.
    """
    selected = _pick(audiences, audience)
    embedder = default_embedder(prefer_model=real_embedder) if real_embedder else Hashing()
    try:
        gate = TermsGate()
    except TermsRecordError as exc:
        typer.echo(f"terms record: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    with ExitStack() as stack:
        try:
            if bucket:
                workdir = Path(stack.enter_context(TemporaryDirectory(prefix="clippings-")))
                stack.enter_context(GcsRunLock(bucket))
                sync = StateSync(GcsObjectStore(bucket), workdir)
                sync.pull()
                stack.callback(sync.push)
                db, ledger = sync.db, sync.ledger
                published: Site = GcsSite(bucket)
            else:
                stack.enter_context(LocalRunLock(lock))
                ledger = db.parent / LEDGER_NAME
                published = LocalSite(site)
        except RunLockHeld as exc:
            typer.echo(f"another run holds the lock: {exc}", err=True)
            raise typer.Exit(code=3) from exc

        client = _model_client(ledger)
        if isinstance(client, GatewayClient):
            stack.callback(client.close)
        http = stack.enter_context(http_client())
        store = stack.enter_context(Store.open(db))
        context = FetchContext(
            client=http,
            gate=gate,
            robots=RobotsCache(http),
            now=datetime.now(UTC),
            secrets=_secrets(),
        )
        run_id = new_run_id(context.now)
        for one in selected:
            pipeline = Pipeline(
                audience=one,
                store=store,
                context=context,
                embedder=embedder,
                run_id=run_id,
                client=client,
                site=published,
                extract=extract,
            )
            try:
                state = graph.run(pipeline)
            except SpendCapReached as exc:
                typer.echo(f"\nstopped: {exc}", err=True)
                typer.echo("No further model call was made. Raise the cap in a commit.", err=True)
                raise typer.Exit(code=4) from exc
            _print_report(state["report"])
            if bucket:
                store.checkpoint()
                # Each audience's work is saved as soon as it is done, so a run killed on the
                # third audience keeps the first two (2026-10-08 lost one this way).
                sync.push()
            if "digest" in state:
                _print_digest(state["digest"], state.get("published", []))
                # A failed call is not a crash, so it would otherwise be invisible here.
                errors = [error for work in state.get("works", []) for error in work.errors]
                for error in sorted(set(errors))[:5]:
                    typer.echo(f"  ! {error[:200]}", err=True)
        # The thirty-day promise is kept by the daily run itself, not by a person remembering
        # to run `clippings retention`.
        deleted = store.retention()
        typer.echo(
            f"\nretention   deleted {deleted['items']} items and {deleted['texts']} texts "
            f"older than {RETENTION_DAYS} days"
        )
        everyone = load_audiences(audiences)
        panels = {one.id: panel_for(one, store) for one in everyone}
        # A Bluesky pick is shown in full only while it exists and for thirty days.
        if context.permitted("bluesky"):
            changed = recheck_picks(store, published, everyone, http, context.now, panels)
            typer.echo(
                f"bluesky     {len(changed)} picked posts deleted or aged out, pages updated"
            )
        publish_indexes(
            published,
            [(one.id, one.name, one.description) for one in everyone],
            {one.id: store.digest_days(one.id) for one in everyone},
            panels,
        )


def _model_client(ledger: Path) -> ModelClient | None:
    """The gateway client if spending is switched on, otherwise None and a note saying so."""
    try:
        return open_client(ledger_path=ledger)
    except SpendNotAllowed as exc:
        typer.echo(f"no model calls: {exc}", err=True)
        return None


def _print_digest(digest: Digest, published: list[str]) -> None:
    c = digest.counts
    rerank = (
        f"re-ranked {digest.candidates}, {digest.rerank_excluded} excluded by the rubric, "
        f"{digest.rerank_unscored} unscored"
        if digest.reranked
        else f"NOT re-ranked: {digest.rerank_error}"
    )
    typer.echo(f"  rerank      {rerank}")
    typer.echo(
        f"  verify      {c.sentences_drafted} drafted, {c.sentences_passed_first} passed first, "
        f"{c.sentences_repaired_ok} repaired, {c.sentences_dropped} dropped; quotes verbatim "
        f"{c.quotes_verbatim_first}/{c.quotes_first} first, "
        f"{c.quotes_verbatim_after_repair}/{c.quotes_after_repair} after repair"
    )
    for reason, count in sorted(c.refusals.items(), key=lambda pair: -pair[1]):
        typer.echo(f"                {count:4d}  {reason}")
    uncosted = f", {digest.uncosted_calls} uncosted" if digest.uncosted_calls else ""
    typer.echo(
        f"  cost        CA${cad(digest.cost_usd):.4f} (US${digest.cost_usd:.4f}) "
        f"over {len(digest.calls)} calls{uncosted}"
    )
    typer.echo(f"  digest      {len(digest.stories)} stories")
    for story in digest.stories:
        mark = "" if story.sentences else f"  ({story.status})"
        score = "-" if story.rerank_score is None else str(story.rerank_score)
        typer.echo(f"     {story.position:2d}. [{score}] {story.headline[:70]}{mark}")
    if published:
        typer.echo(f"  published   {published[0]} and {len(published) - 1} more")


@app.command()
def render(
    audience: Annotated[str | None, typer.Argument(help="One audience id, or all of them.")] = None,
    day: Annotated[str | None, typer.Option(help="Day to render, YYYY-MM-DD.")] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    site: Annotated[Path, typer.Option(help="Directory to write to.")] = DEFAULT_SITE,
) -> None:
    """Re-render stored digests to the site directory. Makes no model call and no fetch."""
    selected = _pick(audiences, audience)
    target = LocalSite(site)
    with Store.open(db) as store:
        for one in selected:
            days = [day] if day else store.digest_days(one.id)
            for each in days:
                digest = store.digest_for(one.id, each)
                if digest is None:
                    typer.echo(f"  no digest for {one.id} on {each}")
                    continue
                publish_digest(target, digest, one.description, panel_for(one, store))
                typer.echo(f"  rendered {one.id} {each}")
        everyone = load_audiences(audiences)
        publish_indexes(
            target,
            [(one.id, one.name, one.description) for one in everyone],
            {one.id: store.digest_days(one.id) for one in everyone},
            {one.id: panel_for(one, store) for one in everyone},
        )


@app.command()
def serve(
    site: Annotated[Path, typer.Option(help="Directory to serve.")] = DEFAULT_SITE,
    bucket: Annotated[
        str | None,
        typer.Option(envvar="CLIPPINGS_BUCKET", help="Serve the bucket's site prefix instead."),
    ] = None,
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(envvar="PORT", help="Port to listen on.")] = 8080,
) -> None:
    """Serve the published digest pages, read-only."""
    from clippings.serve.app import serve as run_server

    run_server(GcsSite(bucket) if bucket else LocalSite(site), host=host, port=port)


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
        keys = audience.terms_keys()
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


@sources_app.command("record")
def sources_record(
    keys: Annotated[list[str], typer.Argument(help="Terms keys, as in docs/sources.md.")],
    status: Annotated[str, typer.Option(help="allowed, dropped or pending.")] = "allowed",
    read_on: Annotated[
        str | None, typer.Option("--read-on", help="Date the terms were read, YYYY-MM-DD.")
    ] = None,
    note: Annotated[str, typer.Option(help="Appended to the row's notes.")] = "",
) -> None:
    """Record that a source's terms were read: its row's status and date, nothing else.

    Use this rather than editing the table by hand: a find-and-replace of `pending` also
    changes the legend and the prose, and a row allowed without a date stops every source.
    """
    if status not in STATUSES:
        raise typer.BadParameter(f"status must be one of {', '.join(sorted(STATUSES))}")
    day = date.fromisoformat(read_on) if read_on else datetime.now(UTC).date()
    text = SOURCES_DOC.read_text(encoding="utf-8")
    try:
        for key in keys:
            text = record_reading(text, key, status, day, note)  # type: ignore[arg-type]
    except TermsRecordError as exc:
        typer.echo(f"terms record: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    SOURCES_DOC.write_text(text, encoding="utf-8")
    for key in keys:
        typer.echo(f"  {status:8s} {key} (read {day})")


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
    labeller: Annotated[str, typer.Option(help="Who is labelling; two are needed for kappa.")],
    bucket: Annotated[
        str | None,
        typer.Option(
            envvar="CLIPPINGS_BUCKET",
            help="Take the run's store from this bucket and keep the labels there.",
        ),
    ] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    port: Annotated[int, typer.Option(help="Local port for the labelling page.")] = 8766,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Label the days' samples in the browser: one page per audience and day, keyboard-driven.

    With a bucket, a fresh copy of the run's store is taken first, and this labeller's labels
    file (labels/<labeller>.duckdb) is fetched and sent back after every saved day.
    """
    labels_path = Path("data/labels") / f"{labeller}.duckdb"
    labels_name = f"labels/{labeller}.duckdb"
    objects = GcsObjectStore(bucket) if bucket else None
    store_path = db
    if objects is not None:
        store_path = Path("data/label-snapshot.duckdb")
        typer.echo(f"copying the run's store from gs://{bucket}/{StateSync.DB}")
        objects.download(StateSync.DB, store_path)
        if not labels_path.exists():
            objects.download(labels_name, labels_path)
    with Store.open(store_path) as store, Store.open(labels_path) as labels:

        def push() -> None:
            labels.checkpoint()
            if objects is not None:
                objects.upload(labels_path, labels_name)

        workspace = Workspace(
            store=store,
            labels=labels,
            labeller=labeller,
            audiences={one.id: one for one in load_audiences(audiences)},
            push=push,
        )
        url = f"http://127.0.0.1:{port}/"
        typer.echo(f"labelling page at {url}  (ctrl+c to stop; every saved day is kept)")
        if open_browser:
            webbrowser.open(url)
        with (
            make_server("127.0.0.1", port, label_application(workspace)) as server,
            suppress(KeyboardInterrupt),
        ):
            server.serve_forever()


@app.command()
def report(
    labeller: Annotated[
        str, typer.Option(help="Whose labels give precision and recall; others give kappa.")
    ] = "peter",
    bucket: Annotated[
        str | None,
        typer.Option(envvar="CLIPPINGS_BUCKET", help="Read the run's store and labels from here."),
    ] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    readme: Annotated[
        bool, typer.Option("--readme/--no-readme", help="Rewrite the README's result tables.")
    ] = True,
) -> None:
    """Compute the results tables: the README's block and docs/report.md. No fetch, no model."""
    label_dir = Path("data/labels")
    store_path = db
    if bucket:
        objects = GcsObjectStore(bucket)
        store_path = Path("data/report-snapshot.duckdb")
        objects.download(StateSync.DB, store_path)
        label_dir = Path("data/labels-report")
        for name in objects.names("labels/"):
            objects.download(name, label_dir / Path(name).name)
    with ExitStack() as stack:
        store = stack.enter_context(Store.open(store_path))
        label_stores = [
            stack.enter_context(Store.open(path)) for path in sorted(label_dir.glob("*.duckdb"))
        ]
        result = build_report(
            store, all_labels([store, *label_stores]), load_audiences(audiences), labeller
        )
    Path("docs/report.md").write_text(detail(result), encoding="utf-8")
    typer.echo(readme_tables(result))
    typer.echo("\nwrote docs/report.md")
    if readme:
        path = Path("README.md")
        path.write_text(
            replace_between_markers(path.read_text(encoding="utf-8"), readme_tables(result)),
            encoding="utf-8",
        )
        typer.echo("rewrote the README's result block")


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
