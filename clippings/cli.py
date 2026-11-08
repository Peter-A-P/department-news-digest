"""`clippings` on the command line.

    clippings run       a day for one audience or all of them: fetch to published page
    clippings fetch     fetch one source for every audience and store it, nothing else
    clippings render    re-render stored digests to the site directory
    clippings serve     serve the published pages, read-only
    clippings sources   check the terms record, or probe that the feeds are feeds
    clippings label     label a day's sample, pairs, story checks and sentences
    clippings reader-study  time a reader briefed from the digest and from the sources
    clippings report    the results tables: the README block and docs/report.md
    clippings x-pick    add the X pick to the latest digests, without rebuilding them
    clippings refresh   re-publish every stored digest with the current page design
    clippings retention delete items past the thirty-day window
    clippings audiences list the configured audiences

There is no send command, and there will not be one.
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Sequence
from contextlib import ExitStack, suppress
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated
from wsgiref.simple_server import make_server

import typer

from clippings import graph
from clippings.assemble.deletions import expire_x_picks, recheck_picks
from clippings.assemble.digest import Digest
from clippings.assemble.publish import GcsSite, LocalSite, Site, publish_digest, publish_indexes
from clippings.assemble.render import trends_page
from clippings.assemble.sources_panel import panel_for
from clippings.assemble.trends import latest_trends
from clippings.cluster.embed import Hashing, default_embedder
from clippings.config.audience import Audience
from clippings.config.load import EXAMPLES, AudienceFileError, load_audience, load_audiences
from clippings.constants import RETENTION_DAYS, cad
from clippings.eval.label_ui import Workspace
from clippings.eval.label_ui import application as label_application
from clippings.eval.reader_study import Study
from clippings.eval.reader_study import application as study_application
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
from clippings.ingest.pipeline import RunReport, default_sources, ingest, new_run_id
from clippings.ingest.remote import (
    GcsObjectStore,
    GcsRunLock,
    LocalRunLock,
    RunLockHeld,
    StateSync,
)
from clippings.ingest.store import Store
from clippings.rank.x_pick import added_to, pick_x, still_showing
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
from clippings.sources.x import link_keys

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
        if key.startswith(("BLUESKY_", "GDELT_", "X_"))
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
        f"(collapse rate {report.collapse_rate:.2f}), embedder {report.embedder}; "
        f"{report.stale} already in an earlier digest's pool, left out"
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
        db, ledger, published, sync = _open_state(stack, bucket=bucket, db=db, lock=lock, site=site)

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
            if sync is not None:
                store.checkpoint()
                # Each audience's work is saved as soon as it is done, so a run killed on the
                # third audience keeps the first two (2026-10-08 lost one this way).
                sync.push()
            if "digest" in state:
                _print_digest(state["digest"], state.get("published", []))
                x = state.get("x_pick")
                if x is not None and not x.picks and one.sources.x.searches:
                    typer.echo(f"  x pick      none: {x.detail}")
                bluesky = state.get("spotlight")
                for name, choice in (("bluesky", bluesky), ("x", x)):
                    for line in choice.considered if choice is not None else ():
                        typer.echo(f"    {name} considered  {line[:160]}")
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
                f"bluesky     {len(changed)} picked posts deleted, aged out or given their "
                "author, pages updated"
            )
        # An X pick is shown on its day only, whether or not X is still allowed.
        expired = expire_x_picks(store, published, everyone, datetime.now(UTC), panels)
        typer.echo(f"x           {len(expired)} picked posts past their day, words removed")
        publish_indexes(
            published,
            [(one.id, one.name, one.description) for one in everyone],
            {one.id: store.digest_days(one.id) for one in everyone},
            panels,
            trend_pages(store, everyone),
        )


def trend_pages(store: Store, everyone: Sequence[Audience]) -> dict[str, str]:
    """Each audience's trend view for the week to its latest digest."""
    pages = {}
    for one in everyone:
        found = latest_trends(store, one)
        if found is not None:
            pages[one.id] = trends_page(one.name, one.id, found)
    return pages


@app.command()
def fetch(
    source: Annotated[str, typer.Argument(help="The source kind to fetch, such as gdelt.")],
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    lock: Annotated[Path, typer.Option(help="Run lock file.")] = DEFAULT_LOCK,
    site: Annotated[Path, typer.Option(help="Unused; the fetch publishes nothing.")] = (
        DEFAULT_SITE
    ),
    bucket: Annotated[
        str | None,
        typer.Option(envvar="CLIPPINGS_BUCKET", help="Cloud Storage bucket. Production only."),
    ] = None,
) -> None:
    """Fetch one source for every audience and store what is new: no clustering, no model
    call, nothing published. The morning run then finds the items in its pool.

    For GDELT, which counts requests per address and refuses most of them from Cloud Run's
    shared addresses: from 2026-10-07 to 2026-10-26 about a quarter of the scheduled run's
    GDELT queries were answered, and on 2026-10-26 none, which left the AI digest two
    stories on a quiet Sunday. A small fetch every three hours gives each query eight
    chances a day instead of one, and each takes only what is new since its watermark.

    If the daily run holds the lock, the fetch steps aside and exits cleanly: the run is
    fetching anyway.
    """
    chosen = [one for one in default_sources() if one.kind == source]
    if not chosen:
        kinds = ", ".join(one.kind for one in default_sources())
        raise typer.BadParameter(f"unknown source {source!r}; one of {kinds}")
    try:
        gate = TermsGate()
    except TermsRecordError as exc:
        typer.echo(f"terms record: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    with ExitStack() as stack:
        try:
            db, _, _, sync = _open_state(stack, bucket=bucket, db=db, lock=lock, site=site)
        except typer.Exit as exc:
            if exc.exit_code == 3:
                typer.echo("the daily run holds the lock; this fetch steps aside")
                return
            raise
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
        # One adapter for every audience, so GDELT's interval holds across them.
        for one in load_audiences(audiences):
            report = ingest(one, store, context, run_id=run_id, sources=chosen)
            for line in report.sources:
                state = "ok" if line.ok else f"failed: {line.detail[:80]}"
                typer.echo(f"{one.id:24s} {line.origin[:48]:48s} {line.stored:4d} new  {state}")
        if sync is not None:
            store.checkpoint()


@app.command()
def refresh(
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    lock: Annotated[Path, typer.Option(help="Run lock file.")] = DEFAULT_LOCK,
    site: Annotated[Path, typer.Option(help="Directory the digest pages are written to.")] = (
        DEFAULT_SITE
    ),
    bucket: Annotated[
        str | None,
        typer.Option(envvar="CLIPPINGS_BUCKET", help="Cloud Storage bucket. Production only."),
    ] = None,
) -> None:
    """Re-publish every stored digest with the current page design, after the daily check
    of its Bluesky pick. No model call; Bluesky's free public API is the only request."""
    everyone = load_audiences(audiences)
    with ExitStack() as stack:
        db, _, published, sync = _open_state(stack, bucket=bucket, db=db, lock=lock, site=site)
        http = stack.enter_context(http_client())
        store = stack.enter_context(Store.open(db))
        panels = {one.id: panel_for(one, store) for one in everyone}
        changed = recheck_picks(store, published, everyone, http, datetime.now(UTC), panels)
        typer.echo(f"bluesky     {len(changed)} picks deleted, aged out or given their author")
        pages = 0
        for one in everyone:
            for day in store.digest_days(one.id):
                digest = store.digest_for(one.id, day)
                if digest is not None:
                    publish_digest(published, digest, one.description, panels[one.id])
                    pages += 1
        publish_indexes(
            published,
            [(one.id, one.name, one.description) for one in everyone],
            {one.id: store.digest_days(one.id) for one in everyone},
            panels,
            trend_pages(store, everyone),
        )
        typer.echo(f"published   {pages} digest pages and the indexes")
        if sync is not None:
            store.checkpoint()


@app.command("x-pick")
def x_pick(
    audience: Annotated[str | None, typer.Argument(help="One audience id, or all of them.")] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    lock: Annotated[Path, typer.Option(help="Run lock file.")] = DEFAULT_LOCK,
    site: Annotated[Path, typer.Option(help="Directory the digest pages are written to.")] = (
        DEFAULT_SITE
    ),
    bucket: Annotated[
        str | None,
        typer.Option(envvar="CLIPPINGS_BUCKET", help="Cloud Storage bucket. Production only."),
    ] = None,
) -> None:
    """Add the X pick to each audience's latest digest, without rebuilding the digest.

    For a day whose digest was made before X was switched on. One search, one model call and
    one author lookup per audience, as in a run; an audience whose latest digest already has
    a pick, or is too old for one to be shown, is left as it is.
    """
    selected = [one for one in _pick(audiences, audience) if one.sources.x.searches]
    with ExitStack() as stack:
        db, ledger, published, _ = _open_state(stack, bucket=bucket, db=db, lock=lock, site=site)
        client = _model_client(ledger)
        if client is None:
            raise typer.Exit(code=2)
        if isinstance(client, GatewayClient):
            stack.callback(client.close)
        http = stack.enter_context(http_client())
        store = stack.enter_context(Store.open(db))
        context = FetchContext(
            client=http,
            gate=TermsGate(),
            robots=RobotsCache(http),
            now=datetime.now(UTC),
            secrets=_secrets(),
        )
        run_id = new_run_id(context.now)
        for one in selected:
            days = store.digest_days(one.id)
            digest = store.digest_for(one.id, days[0]) if days else None
            # A digest with fewer picks than the audience now asks for is picked again, and
            # the new picks replace the old.
            if digest is None or len(digest.x_picks) >= one.digest.post_picks:
                typer.echo(
                    f"{one.id:24s} skipped: {'no digest' if digest is None else 'has its picks'}"
                )
                continue
            if not still_showing(digest, context.now):
                typer.echo(f"{one.id:24s} skipped: {digest.day} is past its day")
                continue
            covered = link_keys(source.url for story in digest.stories for source in story.sources)
            chosen = pick_x(one, context, store, client, run_id=run_id, covered=covered)
            if not chosen.picks:
                typer.echo(f"{one.id:24s} {digest.day} no pick: {chosen.detail}")
                continue
            updated = added_to(digest, chosen)
            store.save_digest(updated)
            publish_digest(published, updated, one.description, panel_for(one, store))
            for x in updated.x_picks:
                typer.echo(
                    f"{one.id:24s} {digest.day} @{x.username}, {x.likes} likes "
                    f"[{x.rubric_score}]: {x.reason}"
                )
            typer.echo(f"{one.id:24s} X reads US${chosen.reads_usd:.3f}")
        if bucket:
            store.checkpoint()


def _open_state(
    stack: ExitStack, *, bucket: str | None, db: Path, lock: Path, site: Path
) -> tuple[Path, Path, Site, StateSync | None]:
    """Take the run lock and return the database, the ledger and the site. With a bucket
    they are local copies pulled from it, pushed back when the stack closes."""
    try:
        if bucket:
            workdir = Path(stack.enter_context(TemporaryDirectory(prefix="clippings-")))
            stack.enter_context(GcsRunLock(bucket))
            sync = StateSync(GcsObjectStore(bucket), workdir)
            sync.pull()
            stack.callback(sync.push)
            return sync.db, sync.ledger, GcsSite(bucket), sync
        stack.enter_context(LocalRunLock(lock))
        return db, db.parent / LEDGER_NAME, LocalSite(site), None
    except RunLockHeld as exc:
        typer.echo(f"another run holds the lock: {exc}", err=True)
        raise typer.Exit(code=3) from exc


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
    for x in digest.x_picks:
        typer.echo(f"  x pick      @{x.username}, {x.likes} likes [{x.rubric_score}]")
    if digest.x_picks:
        reads = digest.x_picks[0].reads_usd
        typer.echo(f"  x reads     CA${cad(reads):.3f} (US${reads:.3f}) at list price")
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
            trend_pages(store, everyone),
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


def _require_bucket(bucket: str | None, local: bool, command: str) -> None:
    """Labels and study sessions only mean something against the production store.

    On 2026-10-23 the labelling tool was started without a bucket and opened the local
    development store, whose only measured days were two Newfoundland and Labrador days from
    a development run: a day of pairs, story checks and sentences was judged against
    clusters and digests production never made, and never uploaded. So the bucket is
    required, and the local store has to be asked for by name.
    """
    if bucket or local:
        return
    typer.echo(
        "No bucket: this would open the local development store, not the run's. Use\n"
        f"  uv run --extra gcs clippings {command} --bucket clippings-digest-clippings\n"
        "or set CLIPPINGS_BUCKET. Pass --local only to work against data/clippings.duckdb.",
        err=True,
    )
    raise typer.Exit(code=2)


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
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Work against the local store instead of the bucket's, for development only.",
        ),
    ] = False,
    port: Annotated[int, typer.Option(help="Local port for the labelling page.")] = 8766,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Label the days' samples in the browser: one page per audience and day, keyboard-driven.

    Relevance at /, duplicate pairs at /pairs and story checks for cluster purity at /stories
    (eval/pairs.py), and digest sentences checked against their sources at /faithfulness
    (eval/faithfulness.py), all kept in the same file.

    With a bucket, a fresh copy of the run's store is taken first, and this labeller's labels
    file (labels/<labeller>.duckdb) is fetched and sent back after every saved day.
    """
    _require_bucket(bucket, local, f"label --labeller {labeller}")
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
        typer.echo(f"duplicate pairs at {url}pairs")
        typer.echo(f"story checks at {url}stories")
        typer.echo(f"faithfulness at {url}faithfulness")
        if open_browser:
            webbrowser.open(url)
        with (
            make_server("127.0.0.1", port, label_application(workspace)) as server,
            suppress(KeyboardInterrupt),
        ):
            server.serve_forever()


@app.command("reader-study")
def reader_study(
    reader: Annotated[
        int,
        typer.Option(
            help="The reader's number, 1 to 3: it sets which days are read from the digest. "
            "Readers are pseudonyms, never names."
        ),
    ],
    audience: Annotated[str, typer.Option(help="The audience the reader is briefed for.")] = "ai",
    bucket: Annotated[
        str | None,
        typer.Option(
            envvar="CLIPPINGS_BUCKET",
            help="Take the run's store from this bucket and keep the sessions there.",
        ),
    ] = None,
    audiences: AudienceDir = EXAMPLES,
    db: DbPath = DEFAULT_DB,
    local: Annotated[
        bool,
        typer.Option(
            "--local",
            help="Work against the local store instead of the bucket's, for development only.",
        ),
    ] = False,
    port: Annotated[int, typer.Option(help="Local port for the study page.")] = 8767,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Time a reader briefed from the digest against from the sources (eval/reader_study.py).

    Five sessions, one per study day, the condition alternating by day and swapped between
    readers. Sessions are kept in labels/study-reader-<n>.duckdb, which `clippings report`
    reads with the labels.
    """
    from clippings.serve.app import FONTS

    if reader < 1:
        raise typer.BadParameter("readers are numbered from 1")
    chosen = {one.id: one for one in load_audiences(audiences)}
    if audience not in chosen:
        raise typer.BadParameter(f"unknown audience {audience!r}")
    _require_bucket(bucket, local, f"reader-study --reader {reader}")
    sessions_path = Path("data/labels") / f"study-reader-{reader}.duckdb"
    sessions_name = f"labels/study-reader-{reader}.duckdb"
    objects = GcsObjectStore(bucket) if bucket else None
    store_path = db
    if objects is not None:
        store_path = Path("data/label-snapshot.duckdb")
        typer.echo(f"copying the run's store from gs://{bucket}/{StateSync.DB}")
        objects.download(StateSync.DB, store_path)
        if not sessions_path.exists():
            objects.download(sessions_name, sessions_path)
    with Store.open(store_path) as store, Store.open(sessions_path) as sessions:

        def push() -> None:
            sessions.checkpoint()
            if objects is not None:
                objects.upload(sessions_path, sessions_name)

        study = Study(
            store=store,
            sessions=sessions,
            audience=chosen[audience],
            reader_number=reader,
            push=push,
        )
        url = f"http://127.0.0.1:{port}/"
        typer.echo(f"reader study at {url}  (ctrl+c to stop; every finished session is kept)")
        if open_browser:
            webbrowser.open(url)
        with (
            make_server("127.0.0.1", port, study_application(study, FONTS)) as server,
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
            store,
            all_labels([store, *label_stores]),
            load_audiences(audiences),
            labeller,
            pair_labels=[pair for one in [store, *label_stores] for pair in one.pair_labels_for()],
            purity_labels=[
                label for one in [store, *label_stores] for label in one.purity_labels_for()
            ],
            faith_labels=[
                label for one in [store, *label_stores] for label in one.faith_labels_for()
            ],
            reader_sessions=[
                session for one in [store, *label_stores] for session in one.reader_sessions()
            ],
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
