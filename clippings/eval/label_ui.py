"""The labelling page: a day's sample on one screen, judged from the keyboard.

PLAN.md section 2.6 asks a person to judge every story in a day's sample. Put one at a time
in a terminal that is minutes per day per audience of reading prompts and pressing Enter;
here the whole day is one list, every story starts as "not relevant", and the labeller marks
the ones that matter, so the common answer costs nothing. A story judged on an earlier day
starts at that judgement, because a story stays in the pool for two days.

Two things keep the shortcut honest. The page shows the sample in a shuffled order, without
the system's rank or stratum, so the labeller is not told which stories the system liked;
and "Save day" records an answer for every story on the page, so an unmarked story is a
"no" the labeller saw, not a gap.

It runs on the labeller's own machine, against a copy of the run's store, and writes to a
labels file of its own (one per labeller). The daily job never touches that file, so a day
can be labelled while a run is going, and two labellers cannot overwrite each other.
"""

from __future__ import annotations

import json
import random
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode

from clippings.config.audience import Audience
from clippings.eval.labels import LabellingQueue, Question, build_queue, record
from clippings.ingest.store import Store
from clippings.models import Label

StartResponse = Callable[[str, list[tuple[str, str]]], Any]

# Enough of the feed's summary to judge by; the link is there for the rest.
SNIPPET_WORDS = 45


@dataclass
class Workspace:
    """What the page reads from and writes to."""

    store: Store
    labels: Store
    labeller: str
    audiences: dict[str, Audience]
    # Called after each saved day: uploads the labels file. A no-op when working locally.
    push: Callable[[], None] = lambda: None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(16))

    def days(self, audience_id: str) -> list[str]:
        # Only days made under the audience's current rubric: a label against a rubric the
        # digest was not chosen by measures the rubric change, not the system.
        start = self.audiences[audience_id].measure_from or ""
        return [day for day in self.store.cluster_days(audience_id) if day >= start]

    def queue(self, audience_id: str, day: str, *, remaining_only: bool = False) -> LabellingQueue:
        # The whole sample unless asked otherwise, so a finished day can be reopened.
        return build_queue(
            self.store,
            audience_id,
            day,
            self.labeller,
            labels=self.labels,
            include_done=not remaining_only,
            # A day judged before "must read" existed is not finished: it reopens with its
            # answers in place, to star the most important.
            graded_only=True,
        )

    def progress(self, audience_id: str, day: str) -> tuple[int, int]:
        total = len(self.queue(audience_id, day).questions)
        left = len(self.queue(audience_id, day, remaining_only=True).questions)
        return total - left, total

    def next_open_day(self) -> tuple[str, str] | None:
        for audience_id in self.audiences:
            for day in self.days(audience_id):
                if self.queue(audience_id, day, remaining_only=True).questions:
                    return audience_id, day
        return None


def _snippet(text: str) -> str:
    words = text.split()
    return " ".join(words[:SNIPPET_WORDS]) + (" ..." if len(words) > SNIPPET_WORDS else "")


def shuffled(questions: Iterable[Question], audience_id: str, day: str) -> list[Question]:
    """The sample in an order that says nothing about the system's ranking, stable per day."""
    ordered = sorted(questions, key=lambda question: question.unit.item_id)
    random.Random(f"{audience_id}|{day}|order").shuffle(ordered)
    return ordered


STYLE = """
:root { color-scheme: light dark; --bg: #f5f3ee; --card: #fdfcf9; --ink: #16181d;
  --soft: #3c4048; --faint: #6b7079; --line: #e3dfd6; --accent: #0f5c6e;
  --yes: #1e7a4c; --yes-bg: #e3f2ea; --must: #b4434f; --must-bg: #f8e6e8; --focus: #6d3f9e; }
@media (prefers-color-scheme: dark) { :root { --bg: #0e1013; --card: #15181d; --ink: #ece9e2;
  --soft: #c9c6bf; --faint: #969ba5; --line: #262a31; --accent: #7cc7d6; --yes: #58c286;
  --yes-bg: #13261c; --must: #f08a93; --must-bg: #2c1a1d; --focus: #b191e0; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 56rem; margin: 0 auto; padding: 1rem 16px 6rem; }
a { color: var(--accent); }
h1 { font-size: 1.3rem; margin: 0.4rem 0; }
.bar { position: sticky; top: 0; z-index: 2; background: var(--bg);
  border-bottom: 1px solid var(--line); padding: 0.6rem 0; }
.bar .keys { color: var(--faint); font-size: 0.82rem; }
kbd { border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px;
  padding: 0 0.3rem; font-size: 0.78rem; background: var(--card); }
details.rubric { font-size: 0.86rem; color: var(--soft); margin: 0.4rem 0; }
.row { display: grid; grid-template-columns: 2rem 1fr; gap: 0.6rem; padding: 0.45rem 0.6rem;
  border: 1px solid var(--line); border-radius: 8px; margin: 0.4rem 0; background: var(--card);
  cursor: pointer; }
.row.focus { outline: 2px solid var(--focus); outline-offset: 1px; }
.row.yes { background: var(--yes-bg); border-color: var(--yes); }
.mark { width: 1.6rem; height: 1.6rem; border-radius: 50%; border: 2px solid var(--line);
  display: flex; align-items: center; justify-content: center; font-weight: 700;
  color: var(--yes); }
.row.yes .mark { border-color: var(--yes); }
.row.yes .mark::after { content: "\\2713"; }
.row.must { background: var(--must-bg); border-color: var(--must); }
.row.must .mark { border-color: var(--must); color: var(--must); }
.row.must .mark::after { content: "\\2605"; }
.title { font-weight: 600; color: var(--ink); text-decoration: none; }
.title:hover { text-decoration: underline; }
.meta { font-size: 0.78rem; color: var(--faint); }
.prev { font-size: 0.72rem; color: var(--accent); margin-left: 0.4rem; }
.snip { font-size: 0.86rem; color: var(--soft); margin-top: 0.15rem; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.spot { border: 1px dashed var(--line); border-radius: 8px; padding: 0.6rem 0.8rem;
  margin: 0.8rem 0; background: var(--card); cursor: pointer; }
.spot.yes { background: var(--yes-bg); border: 1px solid var(--yes); }
.spot .q { font-style: italic; }
.save { position: fixed; bottom: 0; left: 0; right: 0; background: var(--card);
  border-top: 1px solid var(--line); padding: 0.7rem 16px; text-align: center; }
button { font: inherit; font-weight: 600; padding: 0.5rem 1.4rem; border-radius: 999px;
  border: 0; background: var(--accent); color: var(--card); cursor: pointer; }
table { border-collapse: collapse; margin: 1rem 0; }
td, th { border: 1px solid var(--line); padding: 0.35rem 0.6rem; font-size: 0.86rem; }
td.done { background: var(--yes-bg); }
"""

SCRIPT = """
const rows = [...document.querySelectorAll('.row')];
const spot = document.getElementById('spot');
if (spot) spot.addEventListener('click', e => {
  if (!e.target.closest('a')) spot.classList.toggle('yes');
});
let at = 0;
function show(n) {
  at = Math.max(0, Math.min(rows.length - 1, n));
  rows.forEach((r, i) => r.classList.toggle('focus', i === at));
  rows[at] && rows[at].scrollIntoView({block: 'nearest'});
}
function count() {
  document.getElementById('count').textContent =
    rows.filter(r => r.classList.contains('yes')).length;
  document.getElementById('must').textContent =
    rows.filter(r => r.classList.contains('must')).length;
}
// Three states: not relevant, relevant (yes), must read (yes and must).
function set(n, yes, must) {
  rows[n].classList.toggle('yes', yes || must);
  rows[n].classList.toggle('must', must);
  count();
}
function cycle(n) {
  const r = rows[n];
  if (r.classList.contains('must')) set(n, false, false);
  else if (r.classList.contains('yes')) set(n, true, true);
  else set(n, true, false);
}
rows.forEach((r, i) => r.addEventListener('click', e => {
  if (e.target.closest('a')) return;
  show(i); cycle(i);
}));
async function save() {
  const body = {token: TOKEN, audience: AUDIENCE, day: DAY,
    relevant: rows.filter(r => r.classList.contains('yes')).map(r => r.dataset.id),
    must: rows.filter(r => r.classList.contains('must')).map(r => r.dataset.id),
    spotlight: spot ? spot.classList.contains('yes') : null,
    shown: rows.map(r => r.dataset.id)};
  const button = document.getElementById('save');
  button.disabled = true; button.textContent = 'Saving...';
  const reply = await fetch('/save', {method: 'POST', body: JSON.stringify(body)});
  if (!reply.ok) { button.textContent = 'Not saved: ' + await reply.text(); return; }
  location.href = (await reply.json()).next;
}
document.getElementById('save').addEventListener('click', save);
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === 'j' || k === 'ArrowDown') { show(at + 1); }
  else if (k === 'k' || k === 'ArrowUp') { show(at - 1); }
  else if (k === 'y') { set(at, true, false); show(at + 1); }
  else if (k === 'm') { set(at, true, true); show(at + 1); }
  else if (k === 'n') { set(at, false, false); show(at + 1); }
  else if (k === ' ' || k === 'x') { cycle(at); }
  else if (k === 'b' && spot) { spot.classList.toggle('yes'); }
  else if (k === 'o') { window.open(rows[at].querySelector('a').href, '_blank'); }
  else if (k === 'Enter' && e.shiftKey) { save(); }
  else { return; }
  e.preventDefault();
});
show(0); count();
"""


def _page(title: str, body: str, script: str = "") -> bytes:
    tail = f"<script>{script}</script>" if script else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><main>{body}</main>{tail}</body></html>"
    ).encode()


def overview(ws: Workspace) -> bytes:
    days = sorted({day for audience_id in ws.audiences for day in ws.days(audience_id)})
    head = "".join(f"<th>{escape(day)}</th>" for day in days)
    rows = []
    left_total = 0
    for audience_id, audience in ws.audiences.items():
        cells = []
        for day in days:
            if day not in ws.days(audience_id):
                cells.append("<td></td>")
                continue
            done, total = ws.progress(audience_id, day)
            left_total += total - done
            link = "/day?" + urlencode({"audience": audience_id, "day": day})
            css = ' class="done"' if done == total else ""
            cells.append(f'<td{css}><a href="{escape(link)}">{done}/{total}</a></td>')
        rows.append(f"<tr><th>{escape(audience.name)}</th>{''.join(cells)}</tr>")
    following = ws.next_open_day()
    action = (
        f'<p><a href="/next"><button>Continue labelling</button></a> {left_total} stories left</p>'
        if following
        else "<p>Every day is labelled.</p>"
    )
    body = (
        f"<h1>Labelling, as {escape(ws.labeller)}</h1>{action}"
        f"<table><tr><th></th>{head}</tr>{''.join(rows)}</table>"
        "<p class='meta'>Each cell is stories judged, of the day's sample. Click one to open "
        "or correct that day.</p>"
    )
    return _page("Labelling", body)


def day_page(ws: Workspace, audience_id: str, day: str) -> bytes:
    audience = ws.audiences[audience_id]
    questions = shuffled(ws.queue(audience_id, day).questions, audience_id, day)
    today = {
        label.item_id: (label.relevant, label.must_read)
        for label in ws.labels.labels_for(audience_id, day, ws.labeller)
    }
    earlier = ws.labels.previous_labels(audience_id, ws.labeller)
    rows = []
    carried = 0
    for question in questions:
        item = question.item
        note = ""
        if item.id in today:
            yes, must = today[item.id]
            note = '<span class="prev">saved</span>'
        elif item.id in earlier:
            yes, must, on = earlier[item.id]
            carried += 1
            note = f'<span class="prev">as on {escape(on)}</span>'
        else:
            yes = must = False
        state = " yes must" if must else " yes" if yes else ""
        published = item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
        rows.append(
            f'<div class="row{state}" data-id="{escape(item.id)}">'
            '<div class="mark"></div><div>'
            f'<a class="title" href="{escape(item.url)}" target="_blank" rel="noopener">'
            f"{escape(item.title)}</a>{note}"
            f'<div class="meta">{escape(item.domain)} &middot; {published} UTC</div>'
            f'<div class="snip">{escape(_snippet(item.summary))}</div></div></div>'
        )
    done, total = ws.progress(audience_id, day)
    digest = ws.store.digest_for(audience_id, day)
    spot = ""
    if digest is not None and digest.spotlight is not None:
        post = digest.spotlight
        saved = ws.labels.labels_for(audience_id, day, ws.labeller)
        worth = any(lab.item_id == post.item_id and lab.relevant for lab in saved)
        spot = (
            f'<div id="spot" class="spot{" yes" if worth else ""}">'
            "<b>The digest's Bluesky pick.</b> Worth showing this audience? Click or "
            "<kbd>b</kbd> to mark yes; unmarked means no.<br>"
            f'<span class="q">"{escape(post.quote)}"</span> '
            f'<a href="{escape(post.url)}" target="_blank" rel="noopener">@{escape(post.author)}'
            f"</a> &middot; {post.likes} likes</div>"
        )
    body = (
        '<div class="bar">'
        f'<a href="/">All days</a><h1>{escape(audience.name)}, {escape(day)}</h1>'
        f"<div>{total} stories &middot; <b id='count'>0</b> relevant, of them "
        "<b id='must'>0</b> must read"
        f"{f' &middot; {carried} start from an earlier day' if carried else ''}"
        f"{' &middot; saved before, reopened' if done == total and total else ''}</div>"
        '<div class="keys">Mark every story this audience should know about as relevant, '
        "however many. Then star as must read the ones you would put in a ten-story digest "
        "first. Unmarked means not relevant. <kbd>y</kbd> relevant <kbd>m</kbd> must read "
        "<kbd>n</kbd> not <kbd>space</kbd> cycle "
        "<kbd>j</kbd>/<kbd>k</kbd> move <kbd>o</kbd> open article "
        "<kbd>shift</kbd>+<kbd>enter</kbd> save day. Or click a story.</div>"
        f'<details class="rubric"><summary>The audience and its rubric</summary>'
        f"<p>{escape(audience.description)}</p><p>{escape(audience.rubric)}</p></details>"
        "</div>"
        + spot
        + "".join(rows)
        + '<div class="save"><button id="save">Save day and continue</button></div>'
    )
    script = (
        f"const TOKEN = {json.dumps(ws.token)}, AUDIENCE = {json.dumps(audience_id)}, "
        f"DAY = {json.dumps(day)};\n{SCRIPT}"
    )
    return _page(f"{audience.name}, {day}", body, script)


def save_day(ws: Workspace, payload: dict[str, Any]) -> str:
    """Record an answer for every story the page showed. Returns where to go next."""
    if payload.get("token") != ws.token:
        raise PermissionError("this page is from an earlier session; reload it")
    audience_id, day = str(payload["audience"]), str(payload["day"])
    if audience_id not in ws.audiences:
        raise ValueError(f"unknown audience {audience_id!r}")
    queue = ws.queue(audience_id, day)
    by_id = {question.unit.item_id: question for question in queue.questions}
    shown = [str(item_id) for item_id in payload.get("shown", [])]
    relevant = {str(item_id) for item_id in payload.get("relevant", [])}
    must = {str(item_id) for item_id in payload.get("must", [])}
    if set(shown) != set(by_id):
        raise ValueError("the page did not show this day's whole sample; reload it")
    real = LabellingQueue(
        audience_id=audience_id,
        day=day,
        labeller=ws.labeller,
        sample=queue.sample,
        questions=queue.questions,
    )
    for item_id in shown:
        record(
            ws.labels,
            real,
            by_id[item_id],
            relevant=item_id in relevant or item_id in must,
            must_read=item_id in must,
            graded=True,
        )
    digest = ws.store.digest_for(audience_id, day)
    if digest is not None and digest.spotlight is not None and payload.get("spotlight") is not None:
        post = digest.spotlight
        ws.labels.add_label(
            Label(
                audience_id=audience_id,
                day=day,
                item_id=post.item_id,
                labeller=ws.labeller,
                relevant=bool(payload["spotlight"]),
                stratum="spotlight",
                rank=0,
                weight=0.0,
                url=post.url,
                title=post.quote,
                labelled_at=datetime.now(UTC),
                graded=True,
            )
        )
    ws.push()
    following = ws.next_open_day()
    if following is None:
        return "/"
    return "/day?" + urlencode({"audience": following[0], "day": following[1]})


def application(ws: Workspace) -> Callable[[dict[str, Any], StartResponse], list[bytes]]:
    def app(environ: dict[str, Any], start_response: StartResponse) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        query = {
            key: values[0] for key, values in parse_qs(environ.get("QUERY_STRING", "")).items()
        }
        html = "text/html; charset=utf-8"
        try:
            if method == "GET" and path == "/":
                return _reply(start_response, "200 OK", overview(ws), html)
            if method == "GET" and path == "/next":
                following = ws.next_open_day()
                target = (
                    "/day?" + urlencode({"audience": following[0], "day": following[1]})
                    if following
                    else "/"
                )
                return _reply(start_response, "303 See Other", b"", html, location=target)
            if method == "GET" and path == "/day" and query.get("audience") in ws.audiences:
                page = day_page(ws, query["audience"], query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "POST" and path == "/save":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                payload = json.loads(environ["wsgi.input"].read(size) or b"{}")
                target = save_day(ws, payload)
                body = json.dumps({"next": target}).encode("utf-8")
                return _reply(start_response, "200 OK", body, "application/json")
        except PermissionError as error:
            return _reply(start_response, "403 Forbidden", str(error).encode(), "text/plain")
        except (KeyError, ValueError) as error:
            return _reply(start_response, "400 Bad Request", str(error).encode(), "text/plain")
        return _reply(start_response, "404 Not Found", b"not found", "text/plain")

    return app


def _reply(
    start_response: StartResponse,
    status: str,
    body: bytes,
    content_type: str,
    *,
    location: str | None = None,
) -> list[bytes]:
    headers = [("Content-Type", content_type), ("Content-Length", str(len(body)))]
    if location:
        headers.append(("Location", location))
    start_response(status, headers)
    return [body]
