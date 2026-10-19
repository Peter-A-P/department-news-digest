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

The same server asks the deduplication question at /pairs: a day's sampled pairs of news
items (eval/pairs.py), each to be marked "same story" or left as different, shuffled so the
clustering's decision is not shown, and saved a whole day at a time for the same reason.
At /stories it asks the purity question: each story made of several news items, with its
items in a shuffled order, and the labeller marks any item that does not belong with the
rest. At /faithfulness it asks whether each sampled digest sentence says only what its cited
sources say (eval/faithfulness.py), showing what the summariser read of each source.

It runs on the labeller's own machine, against a copy of the run's store, and writes to a
labels file of its own (one per labeller). The daily job never touches that file, so a day
can be labelled while a run is going, and two labellers cannot overwrite each other.
"""

from __future__ import annotations

import json
import random
import re
import secrets
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from typing import Any, cast
from urllib.parse import parse_qs, urlencode

from clippings.config.audience import Audience
from clippings.eval.faithfulness import (
    SentenceSample,
    cited_sources,
    sample_days,
    sentence_sample,
)
from clippings.eval.labels import LabellingQueue, Question, build_queue, record
from clippings.eval.pairs import (
    JoinedStory,
    PairSample,
    PairUnit,
    joined_stories_for_day,
    pair_sample_for_day,
)
from clippings.ingest.store import Store
from clippings.models import FaithLabel, Item, Label, PairLabel, PurityLabel, Verdict
from clippings.summarise.cite import QUOTE
from clippings.summarise.verify import NUMBER

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

    def pairs(self, audience_id: str, day: str) -> PairSample:
        return pair_sample_for_day(self.store, audience_id, day)

    def pair_answers(self, audience_id: str, day: str) -> dict[tuple[str, str], bool]:
        return {
            (label.left_id, label.right_id): label.same_story
            for label in self.labels.pair_labels_for(audience_id, day, self.labeller)
        }

    def stories(self, audience_id: str, day: str) -> tuple[list[JoinedStory], int]:
        return joined_stories_for_day(self.store, audience_id, day)

    def story_answers(self, audience_id: str, day: str) -> dict[str, bool]:
        return {
            label.item_id: label.belongs
            for label in self.labels.purity_labels_for(audience_id, day, self.labeller)
        }

    def next_open_story_day(self) -> tuple[str, str] | None:
        for audience_id in self.audiences:
            for day in self.days(audience_id):
                if self.stories(audience_id, day)[0] and not self.story_answers(audience_id, day):
                    return audience_id, day
        return None

    def faith_days(self, audience_id: str) -> list[str]:
        return sample_days(self.store, audience_id, self.audiences[audience_id].measure_from)

    def sentences(self, audience_id: str, day: str) -> SentenceSample | None:
        digest = self.store.digest_for(audience_id, day)
        return sentence_sample(digest) if digest is not None else None

    def faith_answers(self, audience_id: str, day: str) -> dict[str, str]:
        return {
            f"{label.story_id}|{label.sentence}": label.verdict
            for label in self.labels.faith_labels_for(audience_id, day, self.labeller)
        }

    def next_open_faith_day(self) -> tuple[str, str] | None:
        for audience_id in self.audiences:
            for day in self.faith_days(audience_id):
                sample = self.sentences(audience_id, day)
                if sample and sample.units and not self.faith_answers(audience_id, day):
                    return audience_id, day
        return None

    def next_open_pair_day(self) -> tuple[str, str] | None:
        for audience_id in self.audiences:
            for day in self.days(audience_id):
                if self.pairs(audience_id, day).units and not self.pair_answers(audience_id, day):
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
.row.pair { grid-template-columns: 2rem 1fr; }
.sides { display: grid; grid-template-columns: 1fr 1fr; gap: 0.8rem; }
@media (max-width: 40rem) { .sides { grid-template-columns: 1fr; } }
.story { border: 1px solid var(--line); border-radius: 10px; padding: 0.5rem 0.7rem;
  margin: 0.9rem 0; }
.row.member.odd { background: var(--must-bg); border-color: var(--must); }
.row.member.odd .mark { border-color: var(--must); color: var(--must); }
.row.member.odd .mark::after { content: "\\2715"; }
.claim { border: 1px solid var(--line); border-radius: 10px; padding: 0.6rem 0.8rem;
  margin: 0.9rem 0; background: var(--card); }
.claim.focus { outline: 2px solid var(--focus); outline-offset: 1px; }
.claim .said { font-size: 1.05rem; margin: 0.3rem 0 0.5rem; }
.claim.supported { border-color: var(--yes); }
.claim.unsupported { border-color: var(--must); background: var(--must-bg); }
.claim.unclear { border-style: dashed; }
.verdicts button { background: transparent; color: var(--soft); border: 1px solid var(--line);
  padding: 0.25rem 0.8rem; margin-right: 0.3rem; font-size: 0.86rem; }
.claim.supported .verdicts .supported { background: var(--yes); color: var(--card); }
.claim.unsupported .verdicts .unsupported { background: var(--must); color: var(--card); }
.claim.unclear .verdicts .unclear { background: var(--faint); color: var(--card); }
details.src { margin: 0.5rem 0 0; font-size: 0.86rem; }
details.src summary { cursor: pointer; color: var(--soft); }
.read { white-space: pre-wrap; color: var(--soft); max-height: 22rem; overflow-y: auto;
  border-left: 3px solid var(--line); padding: 0.2rem 0.6rem; margin-top: 0.3rem; }
mark { background: var(--yes-bg); color: var(--ink); outline: 1px solid var(--yes); }
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
const spots = [...document.querySelectorAll('.spot')];
for (const s of spots) s.addEventListener('click', e => {
  if (!e.target.closest('a')) s.classList.toggle('yes');
});
// The keys mark the first post of each kind; a second is clicked.
const spot = spots.find(s => s.dataset.kind === 'spotlight');
const xspot = spots.find(s => s.dataset.kind === 'x_pick');
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
    posts: Object.fromEntries(spots.map(s => [s.dataset.post, s.classList.contains('yes')])),
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
  else if (k === 'p' && xspot) { xspot.classList.toggle('yes'); }
  else if (k === 'o') { window.open(rows[at].querySelector('a').href, '_blank'); }
  else if (k === 'Enter' && e.shiftKey) { save(); }
  else { return; }
  e.preventDefault();
});
show(0); count();
"""


PAIR_SCRIPT = """
const rows = [...document.querySelectorAll('.row')];
let at = 0;
function show(n) {
  at = Math.max(0, Math.min(rows.length - 1, n));
  rows.forEach((r, i) => r.classList.toggle('focus', i === at));
  rows[at] && rows[at].scrollIntoView({block: 'nearest'});
}
function count() {
  document.getElementById('count').textContent =
    rows.filter(r => r.classList.contains('yes')).length;
}
function set(n, same) { rows[n].classList.toggle('yes', same); count(); }
rows.forEach((r, i) => r.addEventListener('click', e => {
  if (e.target.closest('a')) return;
  show(i); set(i, !r.classList.contains('yes'));
}));
async function save() {
  const body = {token: TOKEN, audience: AUDIENCE, day: DAY,
    same: rows.filter(r => r.classList.contains('yes')).map(r => r.dataset.id),
    shown: rows.map(r => r.dataset.id)};
  const button = document.getElementById('save');
  button.disabled = true; button.textContent = 'Saving...';
  const reply = await fetch('/pairs/save', {method: 'POST', body: JSON.stringify(body)});
  if (!reply.ok) { button.textContent = 'Not saved: ' + await reply.text(); return; }
  location.href = (await reply.json()).next;
}
document.getElementById('save').addEventListener('click', save);
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  const links = rows[at] ? rows[at].querySelectorAll('a') : [];
  if (k === 'j' || k === 'ArrowDown') { show(at + 1); }
  else if (k === 'k' || k === 'ArrowUp') { show(at - 1); }
  else if (k === 's') { set(at, true); show(at + 1); }
  else if (k === 'd') { set(at, false); show(at + 1); }
  else if (k === ' ' || k === 'x') { set(at, !rows[at].classList.contains('yes')); }
  else if (k === 'o' && links[0]) { window.open(links[0].href, '_blank'); }
  else if (k === 'p' && links[1]) { window.open(links[1].href, '_blank'); }
  else if (k === 'Enter' && e.shiftKey) { save(); }
  else { return; }
  e.preventDefault();
});
show(0); count();
"""


STORY_SCRIPT = """
const rows = [...document.querySelectorAll('.row')];
let at = 0;
function show(n) {
  at = Math.max(0, Math.min(rows.length - 1, n));
  rows.forEach((r, i) => r.classList.toggle('focus', i === at));
  rows[at] && rows[at].scrollIntoView({block: 'nearest'});
}
function count() {
  document.getElementById('count').textContent =
    rows.filter(r => r.classList.contains('odd')).length;
}
function toggle(n) { rows[n].classList.toggle('odd'); count(); }
rows.forEach((r, i) => r.addEventListener('click', e => {
  if (e.target.closest('a')) return;
  show(i); toggle(i);
}));
async function save() {
  const body = {token: TOKEN, audience: AUDIENCE, day: DAY,
    odd: rows.filter(r => r.classList.contains('odd')).map(r => r.dataset.id),
    shown: rows.map(r => r.dataset.id)};
  const button = document.getElementById('save');
  button.disabled = true; button.textContent = 'Saving...';
  const reply = await fetch('/stories/save', {method: 'POST', body: JSON.stringify(body)});
  if (!reply.ok) { button.textContent = 'Not saved: ' + await reply.text(); return; }
  location.href = (await reply.json()).next;
}
document.getElementById('save').addEventListener('click', save);
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === 'j' || k === 'ArrowDown') { show(at + 1); }
  else if (k === 'k' || k === 'ArrowUp') { show(at - 1); }
  else if (k === ' ' || k === 'x') { toggle(at); }
  else if (k === 'o') { window.open(rows[at].querySelector('a').href, '_blank'); }
  else if (k === 'Enter' && e.shiftKey) { save(); }
  else { return; }
  e.preventDefault();
});
show(0); count();
"""


FAITH_SCRIPT = """
const claims = [...document.querySelectorAll('.claim')];
const VERDICTS = ['supported', 'unsupported', 'unclear'];
let at = 0;
function show(n) {
  at = Math.max(0, Math.min(claims.length - 1, n));
  claims.forEach((c, i) => c.classList.toggle('focus', i === at));
  claims[at] && claims[at].scrollIntoView({block: 'nearest'});
}
function verdict(c) { return VERDICTS.find(v => c.classList.contains(v)) || ''; }
function count() {
  const left = claims.filter(c => !verdict(c)).length;
  document.getElementById('left').textContent = left;
  document.getElementById('save').disabled = left > 0;
}
function set(n, v) {
  VERDICTS.forEach(w => claims[n].classList.toggle(w, w === v));
  count();
}
claims.forEach((c, i) => c.querySelectorAll('.verdicts button').forEach(b =>
  b.addEventListener('click', () => { show(i); set(i, b.dataset.verdict); })));
async function save() {
  if (claims.some(c => !verdict(c))) return;
  const body = {token: TOKEN, audience: AUDIENCE, day: DAY,
    verdicts: Object.fromEntries(claims.map(c => [c.dataset.id, verdict(c)]))};
  const button = document.getElementById('save');
  button.disabled = true; button.textContent = 'Saving...';
  const reply = await fetch('/faithfulness/save', {method: 'POST', body: JSON.stringify(body)});
  if (!reply.ok) { button.textContent = 'Not saved: ' + await reply.text(); return; }
  location.href = (await reply.json()).next;
}
document.getElementById('save').addEventListener('click', save);
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key;
  if (k === 'j' || k === 'ArrowDown') { show(at + 1); }
  else if (k === 'k' || k === 'ArrowUp') { show(at - 1); }
  else if (k === 's') { set(at, 'supported'); show(at + 1); }
  else if (k === 'n') { set(at, 'unsupported'); show(at + 1); }
  else if (k === 'c') { set(at, 'unclear'); show(at + 1); }
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


def _pair_key(unit: PairUnit) -> str:
    return f"{unit.left_id}|{unit.right_id}"


def _pair_link(path: str, target: tuple[str, str] | None) -> str:
    if target is None:
        return "/pairs"
    return f"{path}?" + urlencode({"audience": target[0], "day": target[1]})


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
        '<p><a href="/pairs">Duplicate pairs</a>: is each pair of articles one story?</p>'
        '<p><a href="/stories">Story checks</a>: does every article in a story belong there?</p>'
        '<p><a href="/faithfulness">Faithfulness</a>: does each digest sentence say only what '
        "its sources say?</p>"
    )
    return _page("Labelling", body)


PAIR_RUBRIC = (
    "Same story means the same event, announcement, decision or report: a reader who had "
    "read one would not want both in a digest. A later update or a reaction to that same "
    "event counts as the same story. Two different events on the same subject are "
    "different stories."
)


def pairs_overview(ws: Workspace) -> bytes:
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
            total = len(ws.pairs(audience_id, day).units)
            done = total if ws.pair_answers(audience_id, day) else 0
            left_total += total - done
            link = "/pairs/day?" + urlencode({"audience": audience_id, "day": day})
            css = ' class="done"' if done == total else ""
            cells.append(f'<td{css}><a href="{escape(link)}">{done}/{total}</a></td>')
        rows.append(f"<tr><th>{escape(audience.name)}</th>{''.join(cells)}</tr>")
    following = ws.next_open_pair_day()
    action = (
        f'<p><a href="/pairs/next"><button>Continue with pairs</button></a> '
        f"{left_total} pairs left</p>"
        if following
        else "<p>Every day's pairs are labelled.</p>"
    )
    body = (
        f'<a href="/">Relevance labelling</a><h1>Duplicate pairs, as {escape(ws.labeller)}</h1>'
        f"{action}<p class='meta'>{escape(PAIR_RUBRIC)}</p>"
        f"<table><tr><th></th>{head}</tr>{''.join(rows)}</table>"
        "<p class='meta'>Each cell is pairs judged, of the day's sample.</p>"
    )
    return _page("Duplicate pairs", body)


def _pair_side(item: Item) -> str:
    published = item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
    return (
        f'<div class="side"><a class="title" href="{escape(item.url)}" target="_blank" '
        f'rel="noopener">{escape(item.title)}</a>'
        f'<div class="meta">{escape(item.domain)} &middot; {published} UTC</div>'
        f'<div class="snip">{escape(_snippet(item.summary))}</div></div>'
    )


def pairs_page(ws: Workspace, audience_id: str, day: str) -> bytes:
    audience = ws.audiences[audience_id]
    sample = ws.pairs(audience_id, day)
    items = {item.id: item for item in ws.store.items_for(audience_id)}
    answers = ws.pair_answers(audience_id, day)
    units = sorted(sample.units, key=_pair_key)
    random.Random(f"{audience_id}|{day}|pairs-order").shuffle(units)
    rows = []
    for unit in units:
        same = answers.get((unit.left_id, unit.right_id), False)
        rows.append(
            f'<div class="row pair{" yes" if same else ""}" data-id="{escape(_pair_key(unit))}">'
            '<div class="mark"></div><div class="sides">'
            f"{_pair_side(items[unit.left_id])}{_pair_side(items[unit.right_id])}</div></div>"
        )
    saved = " &middot; saved before, reopened" if answers else ""
    body = (
        '<div class="bar">'
        f'<a href="/pairs">All days</a><h1>Duplicate pairs: {escape(audience.name)}, '
        f"{escape(day)}</h1>"
        f"<div>{len(units)} pairs &middot; <b id='count'>0</b> marked same story{saved}</div>"
        f'<div class="keys">{escape(PAIR_RUBRIC)} Unmarked means different. '
        "<kbd>s</kbd> same <kbd>d</kbd> different <kbd>space</kbd> toggle "
        "<kbd>j</kbd>/<kbd>k</kbd> move <kbd>o</kbd>/<kbd>p</kbd> open first/second "
        "<kbd>shift</kbd>+<kbd>enter</kbd> save day. Or click a pair.</div>"
        "</div>"
        + "".join(rows)
        + '<div class="save"><button id="save">Save day and continue</button></div>'
    )
    script = (
        f"const TOKEN = {json.dumps(ws.token)}, AUDIENCE = {json.dumps(audience_id)}, "
        f"DAY = {json.dumps(day)};\n{PAIR_SCRIPT}"
    )
    return _page(f"Pairs: {audience.name}, {day}", body, script)


STORY_RUBRIC = (
    "Each box is one story the system made of several articles. Mark any article that is "
    "not about the same event, announcement, decision or report as the rest; a later update "
    "or a reaction to that same event belongs. If the articles split into groups, the "
    "largest group is the story and the others are marked."
)


def stories_overview(ws: Workspace) -> bytes:
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
            total = len(ws.stories(audience_id, day)[0])
            done = total if ws.story_answers(audience_id, day) else 0
            left_total += total - done
            link = "/stories/day?" + urlencode({"audience": audience_id, "day": day})
            css = ' class="done"' if done == total else ""
            cells.append(f'<td{css}><a href="{escape(link)}">{done}/{total}</a></td>')
        rows.append(f"<tr><th>{escape(audience.name)}</th>{''.join(cells)}</tr>")
    action = (
        f'<p><a href="/stories/next"><button>Continue with stories</button></a> '
        f"{left_total} stories left</p>"
        if ws.next_open_story_day()
        else "<p>Every day's stories are checked.</p>"
    )
    body = (
        f'<a href="/">Relevance labelling</a><h1>Story checks, as {escape(ws.labeller)}</h1>'
        f"{action}<p class='meta'>{escape(STORY_RUBRIC)}</p>"
        f"<table><tr><th></th>{head}</tr>{''.join(rows)}</table>"
        "<p class='meta'>Each cell is stories checked, of the day's stories of several "
        "articles.</p>"
    )
    return _page("Story checks", body)


def stories_page(ws: Workspace, audience_id: str, day: str) -> bytes:
    audience = ws.audiences[audience_id]
    stories, _ = ws.stories(audience_id, day)
    items = {item.id: item for item in ws.store.items_for(audience_id)}
    answers = ws.story_answers(audience_id, day)
    rng = random.Random(f"{audience_id}|{day}|stories-order")
    order = list(stories)
    rng.shuffle(order)
    boxes = []
    for number, story in enumerate(order, start=1):
        members = list(story.item_ids)
        rng.shuffle(members)
        rows = []
        for item_id in members:
            item = items[item_id]
            odd = not answers.get(item_id, True)
            published = item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
            rows.append(
                f'<div class="row member{" odd" if odd else ""}" data-id="{escape(item_id)}">'
                '<div class="mark"></div><div>'
                f'<a class="title" href="{escape(item.url)}" target="_blank" rel="noopener">'
                f"{escape(item.title)}</a>"
                f'<div class="meta">{escape(item.domain)} &middot; {published} UTC</div>'
                f'<div class="snip">{escape(_snippet(item.summary))}</div></div></div>'
            )
        boxes.append(
            f'<section class="story"><div class="meta">Story {number}, '
            f"{len(members)} articles</div>{''.join(rows)}</section>"
        )
    saved = " &middot; saved before, reopened" if answers else ""
    body = (
        '<div class="bar">'
        f'<a href="/stories">All days</a><h1>Story checks: {escape(audience.name)}, '
        f"{escape(day)}</h1>"
        f"<div>{len(order)} stories &middot; <b id='count'>0</b> articles marked as not "
        f"belonging{saved}</div>"
        f'<div class="keys">{escape(STORY_RUBRIC)} Unmarked means it belongs. '
        "<kbd>x</kbd>/<kbd>space</kbd> mark or unmark <kbd>j</kbd>/<kbd>k</kbd> move "
        "<kbd>o</kbd> open article <kbd>shift</kbd>+<kbd>enter</kbd> save day. Or click "
        "an article.</div>"
        "</div>"
        + "".join(boxes)
        + '<div class="save"><button id="save">Save day and continue</button></div>'
    )
    script = (
        f"const TOKEN = {json.dumps(ws.token)}, AUDIENCE = {json.dumps(audience_id)}, "
        f"DAY = {json.dumps(day)};\n{STORY_SCRIPT}"
    )
    return _page(f"Stories: {audience.name}, {day}", body, script)


FAITH_RUBRIC = (
    "Supported means everything the sentence says is stated in, or follows directly from, "
    "what the summariser read of the sources it cites, shown under it. Something true that "
    "is not in those words, a wrong attribution, a changed number or a stronger claim than "
    "the source makes is not supported. Can't tell is for when what was read is no longer "
    "on record and the article does not settle it."
)


def _faith_link(target: tuple[str, str] | None) -> str:
    if target is None:
        return "/faithfulness"
    return "/faithfulness/day?" + urlencode({"audience": target[0], "day": target[1]})


def faith_overview(ws: Workspace) -> bytes:
    days = sorted({day for audience_id in ws.audiences for day in ws.faith_days(audience_id)})
    head = "".join(f"<th>{escape(day)}</th>" for day in days)
    rows = []
    left_total = 0
    for audience_id, audience in ws.audiences.items():
        mine = ws.faith_days(audience_id)
        cells = []
        for day in days:
            sample = ws.sentences(audience_id, day) if day in mine else None
            if sample is None:
                cells.append("<td></td>")
                continue
            total = len(sample.units)
            done = total if ws.faith_answers(audience_id, day) else 0
            left_total += total - done
            css = ' class="done"' if done == total else ""
            link = _faith_link((audience_id, day))
            cells.append(f'<td{css}><a href="{escape(link)}">{done}/{total}</a></td>')
        rows.append(f"<tr><th>{escape(audience.name)}</th>{''.join(cells)}</tr>")
    action = (
        f'<p><a href="/faithfulness/next"><button>Continue with sentences</button></a> '
        f"{left_total} sentences left</p>"
        if ws.next_open_faith_day()
        else "<p>Every sampled sentence is checked.</p>"
    )
    body = (
        f'<a href="/">Relevance labelling</a><h1>Faithfulness, as {escape(ws.labeller)}</h1>'
        f"{action}<p class='meta'>{escape(FAITH_RUBRIC)}</p>"
        f"<table><tr><th></th>{head}</tr>{''.join(rows)}</table>"
        "<p class='meta'>Each cell is sentences checked, of those drawn from the day's digest: "
        "the first seven digest days of each audience's labelled week. The article text is "
        "deleted thirty days after publication, so check a day well before then.</p>"
    )
    return _page("Faithfulness", body)


def _highlighted(text: str, sentence: str) -> str:
    """The source text, escaped, with the sentence's quotes and numbers marked where they occur."""
    quotes = [quote for quote in QUOTE.findall(sentence) if quote.strip()]
    figures = {match.group(0).rstrip(".") for match in NUMBER.finditer(sentence)}
    pieces = [re.escape(quote) for quote in sorted(quotes, key=len, reverse=True)]
    pieces += [rf"(?<![\d,.]){re.escape(figure)}(?![\d])" for figure in sorted(figures)]
    if not pieces:
        return escape(text)
    out = []
    last = 0
    for match in re.finditer("|".join(pieces), text, re.IGNORECASE):
        out.append(escape(text[last : match.start()]))
        out.append(f"<mark>{escape(match.group(0))}</mark>")
        last = match.end()
    out.append(escape(text[last:]))
    return "".join(out)


def faith_page(ws: Workspace, audience_id: str, day: str) -> bytes:
    audience = ws.audiences[audience_id]
    digest = ws.store.digest_for(audience_id, day)
    sample = ws.sentences(audience_id, day)
    if digest is None or sample is None:
        raise ValueError(f"no digest for {audience_id} on {day}")
    stories = {story.story_id: story for story in digest.stories}
    answers = ws.faith_answers(audience_id, day)
    cards = []
    for unit in sample.units:
        story = stories[unit.story_id]
        said = story.sentences[unit.sentence].text
        sources = []
        for cited in cited_sources(ws.store, audience_id, story, unit.sentence):
            link = cited.link
            note = f'<div class="meta">{escape(cited.note)}</div>' if cited.note else ""
            read = f'<div class="read">{_highlighted(cited.text, said)}</div>' if cited.text else ""
            sources.append(
                f'<details class="src" open><summary>{escape(link.sid)} '
                f"{escape(link.domain)}: "
                f'<a href="{escape(link.url)}" target="_blank" rel="noopener">'
                f"{escape(link.title)}</a></summary>{note}{read}</details>"
            )
        verdict = answers.get(unit.key, "")
        buttons = "".join(
            f'<button class="{key}" data-verdict="{key}">{label} <kbd>{hotkey}</kbd></button>'
            for key, label, hotkey in (
                ("supported", "Supported", "s"),
                ("unsupported", "Not supported", "n"),
                ("unclear", "Can't tell", "c"),
            )
        )
        cards.append(
            f'<section class="claim {verdict}" data-id="{escape(unit.key)}">'
            f'<div class="meta">From the story: <a href="{escape(story.url)}" target="_blank" '
            f'rel="noopener">{escape(story.headline)}</a></div>'
            f'<p class="said">{escape(said)}</p><div class="verdicts">{buttons}</div>'
            f"{''.join(sources)}</section>"
        )
    saved = " &middot; saved before, reopened" if answers else ""
    body = (
        '<div class="bar">'
        f'<a href="/faithfulness">All days</a><h1>Faithfulness: {escape(audience.name)}, '
        f"{escape(day)}</h1>"
        f"<div>{len(cards)} sentences of the {sample.shown} the digest showed &middot; "
        f"<b id='left'>{len(cards)}</b> left to judge{saved}</div>"
        f'<div class="keys">{escape(FAITH_RUBRIC)} Quotes and numbers from the sentence are '
        "marked where they occur. <kbd>s</kbd> supported <kbd>n</kbd> not supported "
        "<kbd>c</kbd> can't tell <kbd>j</kbd>/<kbd>k</kbd> move "
        "<kbd>shift</kbd>+<kbd>enter</kbd> save day. Every sentence needs an answer.</div>"
        "</div>"
        + "".join(cards)
        + '<div class="save"><button id="save">Save day and continue</button></div>'
    )
    script = (
        f"const TOKEN = {json.dumps(ws.token)}, AUDIENCE = {json.dumps(audience_id)}, "
        f"DAY = {json.dumps(day)};\n{FAITH_SCRIPT}"
    )
    return _page(f"Faithfulness: {audience.name}, {day}", body, script)


def save_faith(ws: Workspace, payload: dict[str, Any]) -> str:
    """Record a verdict for every sentence the page showed. Returns where to go next."""
    if payload.get("token") != ws.token:
        raise PermissionError("this page is from an earlier session; reload it")
    audience_id, day = str(payload["audience"]), str(payload["day"])
    if audience_id not in ws.audiences:
        raise ValueError(f"unknown audience {audience_id!r}")
    digest = ws.store.digest_for(audience_id, day)
    sample = ws.sentences(audience_id, day)
    if digest is None or sample is None or not sample.units:
        raise ValueError(f"no sentences to judge for {audience_id} on {day}")
    verdicts = {str(key): str(value) for key, value in (payload.get("verdicts") or {}).items()}
    if set(verdicts) != {unit.key for unit in sample.units}:
        raise ValueError("the page did not show this day's whole sample of sentences; reload it")
    if not set(verdicts.values()) <= {"supported", "unsupported", "unclear"}:
        raise ValueError("every sentence needs a verdict: supported, not supported or can't tell")
    stories = {story.story_id: story for story in digest.stories}
    now = datetime.now(UTC)
    for unit in sample.units:
        story = stories[unit.story_id]
        sentence = story.sentences[unit.sentence]
        by_sid = {link.sid: link for link in story.sources}
        ws.labels.add_faith_label(
            FaithLabel(
                audience_id=audience_id,
                day=day,
                story_id=unit.story_id,
                sentence=unit.sentence,
                labeller=ws.labeller,
                verdict=cast(Verdict, verdicts[unit.key]),
                weight=unit.weight,
                text=sentence.text,
                headline=story.headline,
                cited_urls=tuple(by_sid[sid].url for sid in sentence.cites if sid in by_sid),
                labelled_at=now,
            )
        )
    ws.push()
    return _faith_link(ws.next_open_faith_day())


def save_stories(ws: Workspace, payload: dict[str, Any]) -> str:
    """Record a judgement for every article of every story the page showed."""
    if payload.get("token") != ws.token:
        raise PermissionError("this page is from an earlier session; reload it")
    audience_id, day = str(payload["audience"]), str(payload["day"])
    if audience_id not in ws.audiences:
        raise ValueError(f"unknown audience {audience_id!r}")
    stories, pool = ws.stories(audience_id, day)
    expected = {item_id for story in stories for item_id in story.item_ids}
    shown = {str(item_id) for item_id in payload.get("shown", [])}
    odd = {str(item_id) for item_id in payload.get("odd", [])}
    if not expected or shown != expected:
        raise ValueError("the page did not show this day's whole set of stories; reload it")
    items = {item.id: item for item in ws.store.items_for(audience_id)}
    now = datetime.now(UTC)
    for story in stories:
        for item_id in story.item_ids:
            ws.labels.add_purity_label(
                PurityLabel(
                    audience_id=audience_id,
                    day=day,
                    cluster_id=story.cluster_id,
                    item_id=item_id,
                    labeller=ws.labeller,
                    belongs=item_id not in odd,
                    cluster_size=len(story.item_ids),
                    pool_items=pool,
                    url=items[item_id].url,
                    title=items[item_id].title,
                    labelled_at=now,
                )
            )
    ws.push()
    following = ws.next_open_story_day()
    if following is None:
        return "/stories"
    return "/stories/day?" + urlencode({"audience": following[0], "day": following[1]})


def save_pairs(ws: Workspace, payload: dict[str, Any]) -> str:
    """Record an answer for every pair the page showed. Returns where to go next."""
    if payload.get("token") != ws.token:
        raise PermissionError("this page is from an earlier session; reload it")
    audience_id, day = str(payload["audience"]), str(payload["day"])
    if audience_id not in ws.audiences:
        raise ValueError(f"unknown audience {audience_id!r}")
    by_key = {_pair_key(unit): unit for unit in ws.pairs(audience_id, day).units}
    shown = {str(key) for key in payload.get("shown", [])}
    same = {str(key) for key in payload.get("same", [])}
    if not by_key or shown != set(by_key):
        raise ValueError("the page did not show this day's whole sample of pairs; reload it")
    items = {item.id: item for item in ws.store.items_for(audience_id)}
    now = datetime.now(UTC)
    for key, unit in by_key.items():
        left, right = items[unit.left_id], items[unit.right_id]
        ws.labels.add_pair_label(
            PairLabel(
                audience_id=audience_id,
                day=day,
                left_id=unit.left_id,
                right_id=unit.right_id,
                labeller=ws.labeller,
                same_story=key in same,
                stratum=unit.stratum,
                weight=unit.weight,
                together=unit.together,
                left_url=left.url,
                left_title=left.title,
                right_url=right.url,
                right_title=right.title,
                labelled_at=now,
            )
        )
    ws.push()
    return _pair_link("/pairs/day", ws.next_open_pair_day())


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
    saved = ws.labels.labels_for(audience_id, day, ws.labeller)
    worth = {lab.item_id for lab in saved if lab.relevant}
    for number, post in enumerate(digest.spotlights if digest is not None else (), start=1):
        key = " Click or <kbd>b</kbd>" if number == 1 else " Click"
        spot += (
            f'<div class="spot{" yes" if post.item_id in worth else ""}" '
            f'data-kind="spotlight" data-post="{escape(post.item_id)}">'
            f"<b>The digest's Bluesky pick {number}.</b> Worth showing this audience?{key} "
            "to mark yes; unmarked means no.<br>"
            f'<span class="q">"{escape(post.quote)}"</span> '
            f'<a href="{escape(post.url)}" target="_blank" rel="noopener">@{escape(post.author)}'
            f"</a> &middot; {post.likes} likes</div>"
        )
    for number, x in enumerate(digest.x_picks if digest is not None else (), start=1):
        key = " Click or <kbd>p</kbd>" if number == 1 else " Click"
        # The words are kept for a day only, so most days the labeller opens the post on X.
        words = f'<span class="q">"{escape(x.text)}"</span> ' if x.text else ""
        spot += (
            f'<div class="spot{" yes" if x_label_id(x.post_id) in worth else ""}" '
            f'data-kind="x_pick" data-post="{escape(x_label_id(x.post_id))}">'
            f"<b>The digest's X pick {number}.</b> Worth showing this audience?{key} "
            "to mark yes; unmarked means no.<br>"
            f'{words}<a href="{escape(x.url)}" target="_blank" rel="noopener">'
            f"@{escape(x.username)}</a> &middot; {x.likes} likes"
            f"{f' &middot; picked because: {escape(x.reason)}' if x.reason else ''}</div>"
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


def x_label_id(post_id: str) -> str:
    """An X post is not an item in the store, so its label is keyed by the post's own id."""
    return f"x:{post_id}"


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
    marked = payload.get("posts") or {}
    for post in digest.spotlights if digest is not None else ():
        if post.item_id not in marked:
            continue
        ws.labels.add_label(
            Label(
                audience_id=audience_id,
                day=day,
                item_id=post.item_id,
                labeller=ws.labeller,
                relevant=bool(marked[post.item_id]),
                stratum="spotlight",
                rank=0,
                weight=0.0,
                url=post.url,
                title=post.quote,
                labelled_at=datetime.now(UTC),
                graded=True,
            )
        )
    for x in digest.x_picks if digest is not None else ():
        if x_label_id(x.post_id) not in marked:
            continue
        ws.labels.add_label(
            Label(
                audience_id=audience_id,
                day=day,
                item_id=x_label_id(x.post_id),
                labeller=ws.labeller,
                relevant=bool(marked[x_label_id(x.post_id)]),
                stratum="x_pick",
                rank=0,
                weight=0.0,
                url=x.url,
                title=f"@{x.username}: {x.reason}",
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
            if method == "GET" and path == "/stories":
                return _reply(start_response, "200 OK", stories_overview(ws), html)
            if method == "GET" and path == "/stories/next":
                following = ws.next_open_story_day()
                target = (
                    "/stories/day?" + urlencode({"audience": following[0], "day": following[1]})
                    if following
                    else "/stories"
                )
                return _reply(start_response, "303 See Other", b"", html, location=target)
            if method == "GET" and path == "/stories/day" and query.get("audience") in ws.audiences:
                page = stories_page(ws, query["audience"], query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "POST" and path == "/stories/save":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                payload = json.loads(environ["wsgi.input"].read(size) or b"{}")
                body = json.dumps({"next": save_stories(ws, payload)}).encode("utf-8")
                return _reply(start_response, "200 OK", body, "application/json")
            if method == "GET" and path == "/faithfulness":
                return _reply(start_response, "200 OK", faith_overview(ws), html)
            if method == "GET" and path == "/faithfulness/next":
                target = _faith_link(ws.next_open_faith_day())
                return _reply(start_response, "303 See Other", b"", html, location=target)
            if (
                method == "GET"
                and path == "/faithfulness/day"
                and query.get("audience") in ws.audiences
            ):
                page = faith_page(ws, query["audience"], query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "POST" and path == "/faithfulness/save":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                payload = json.loads(environ["wsgi.input"].read(size) or b"{}")
                body = json.dumps({"next": save_faith(ws, payload)}).encode("utf-8")
                return _reply(start_response, "200 OK", body, "application/json")
            if method == "GET" and path == "/pairs":
                return _reply(start_response, "200 OK", pairs_overview(ws), html)
            if method == "GET" and path == "/pairs/next":
                target = _pair_link("/pairs/day", ws.next_open_pair_day())
                return _reply(start_response, "303 See Other", b"", html, location=target)
            if method == "GET" and path == "/pairs/day" and query.get("audience") in ws.audiences:
                page = pairs_page(ws, query["audience"], query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "POST" and path == "/pairs/save":
                size = int(environ.get("CONTENT_LENGTH") or 0)
                payload = json.loads(environ["wsgi.input"].read(size) or b"{}")
                body = json.dumps({"next": save_pairs(ws, payload)}).encode("utf-8")
                return _reply(start_response, "200 OK", body, "application/json")
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
