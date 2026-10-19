"""The reader study: minutes to be briefed from the digest, against minutes from the sources.

PLAN.md section 1 claims the digest saves a reader time, and section 5 sets the study: three
readers, five days. Each reader is briefed on one audience's day either by reading that day's
digest or by scanning the news items it was made from, as a person doing this by hand scans
their feeds, and is timed. The conditions alternate by day and are swapped between readers,
so every day is read both ways by someone and no reader sees one day twice: reader 1 has
sources, digest, sources, digest, sources; reader 2 the other way round; reader 3 as reader 1.

The task is the same in both: "be briefed for a morning meeting on what this audience needs
to know today". From the sources the reader also ticks the items they would brief on, which
keeps the scan honest (a reader who ticks nothing has not done the task) and gives a second,
smaller number: how many of a person's own picks the digest also showed.

The time reported is time with the page in view, measured in the reader's browser; the time
from start to done is kept beside it. A reader is a pseudonym, `reader-<n>`. Sessions go to a
file of their own in the labels folder, which `clippings report` already reads.

The study days are the first `DAYS` digest days with a story from the audience's
`measure_from`. The news items are deleted thirty days after publication, so the study has to
be run before then.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode

from clippings.assemble.render import html_page
from clippings.config.audience import Audience
from clippings.eval.label_ui import StartResponse, _page, _reply, _snippet
from clippings.ingest.store import Store
from clippings.models import SOCIAL_KINDS, Item, ReaderSession

DAYS = 5
# More than a digest's ten, so the reader is not told how many matter, and few enough that a
# tick list stays a briefing rather than an index.
MAX_PICKS = 15

Condition = Literal["digest", "sources"]


def condition_for(reader_number: int, index: int) -> Condition:
    """Reader 1 starts from the sources, reader 2 from the digest, and they alternate."""
    return "digest" if (reader_number + index) % 2 == 0 else "sources"


def study_days(store: Store, audience: Audience) -> list[str]:
    start = audience.measure_from or ""
    days = []
    for day in sorted(day for day in store.digest_days(audience.id) if day >= start):
        digest = store.digest_for(audience.id, day)
        if digest is not None and digest.stories:
            days.append(day)
        if len(days) == DAYS:
            break
    return days


def pool_items(store: Store, audience_id: str, day: str) -> list[Item]:
    """The day's news items, newest first, as a feed reader lists them. Reprints included:
    removing them is part of what the digest is timed against."""
    items = {item.id: item for item in store.items_for(audience_id)}
    ids = {
        item_id
        for cluster in store.clusters_for(audience_id, day)
        for item_id in cluster.item_ids
        if item_id in items and items[item_id].source_kind not in SOCIAL_KINDS
    }
    return sorted(
        (items[i] for i in ids), key=lambda item: (item.published_at, item.id), reverse=True
    )


def in_digest(store: Store, audience_id: str, day: str) -> set[str]:
    """Every news item in a story the day's digest showed."""
    digest = store.digest_for(audience_id, day)
    shown = {story.story_id for story in digest.stories} if digest else set()
    return {
        item_id
        for cluster in store.clusters_for(audience_id, day)
        if cluster.id in shown
        for item_id in cluster.item_ids
    }


@dataclass
class Study:
    store: Store
    sessions: Store
    audience: Audience
    reader_number: int
    push: Callable[[], None] = lambda: None
    token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    started: dict[str, datetime] = field(default_factory=dict)

    @property
    def reader(self) -> str:
        return f"reader-{self.reader_number}"

    def plan(self) -> list[tuple[str, Condition]]:
        return [
            (day, condition_for(self.reader_number, index))
            for index, day in enumerate(study_days(self.store, self.audience))
        ]

    def done(self) -> set[str]:
        return {
            session.day
            for session in self.sessions.reader_sessions(self.reader)
            if session.audience_id == self.audience.id
        }


INSTRUCTIONS = {
    "digest": (
        "Read this morning's digest until you feel briefed for a meeting on what this audience "
        "needs to know today. Open any link you would open on a normal morning. Press Done "
        "when you are briefed."
    ),
    "sources": (
        "These are this morning's news items for this audience, newest first, as a feed reader "
        "shows them. Scan them as you would your own feeds until you feel briefed for a "
        "meeting on what this audience needs to know today, and tick the items you would "
        f"brief on (at most {MAX_PICKS}). Open any link you would open on a normal morning. "
        "Press Done when you are briefed."
    ),
}

STUDY_SCRIPT = """
let active = 0, since = null, wall0 = null;
function tick() { if (since !== null) { active += performance.now() - since; since = performance.now(); } }
document.addEventListener('visibilitychange', () => {
  if (wall0 === null) return;
  if (document.hidden) { tick(); since = null; } else { since = performance.now(); }
});
document.getElementById('start').addEventListener('click', async () => {
  const reply = await fetch('/start', {method: 'POST',
    body: JSON.stringify({token: TOKEN, day: DAY})});
  if (!reply.ok) { alert(await reply.text()); return; }
  document.getElementById('before').hidden = true;
  document.getElementById('task').hidden = false;
  const frame = document.getElementById('frame');
  if (frame) frame.src = frame.dataset.src;
  wall0 = Date.now(); since = performance.now();
});
const boxes = [...document.querySelectorAll('input.pick')];
boxes.forEach(b => b.addEventListener('change', () => {
  const n = boxes.filter(x => x.checked).length;
  if (n > MAX) { b.checked = false; }
  document.getElementById('picked').textContent = boxes.filter(x => x.checked).length;
}));
document.getElementById('done').addEventListener('click', async () => {
  tick();
  const picks = boxes.filter(x => x.checked).map(x => x.value);
  if (CONDITION === 'sources' && !picks.length &&
      !confirm('You ticked nothing. Is there nothing here you would brief on?')) return;
  const body = {token: TOKEN, day: DAY, seconds_active: active / 1000,
    seconds_wall: (Date.now() - wall0) / 1000, picks};
  const reply = await fetch('/done', {method: 'POST', body: JSON.stringify(body)});
  if (!reply.ok) { alert('Not saved: ' + await reply.text()); return; }
  location.href = '/';
});
"""


def overview(study: Study) -> bytes:
    done = study.done()
    rows = []
    following = None
    for number, (day, condition) in enumerate(study.plan(), start=1):
        if day in done:
            state = "done"
        else:
            state = f'<a href="/session?{urlencode({"day": day})}">start</a>'
            following = following or day
        rows.append(
            f"<tr><td>{number}</td><td>{escape(day)}</td><td>from the {condition}</td>"
            f"<td>{state}</td></tr>"
        )
    action = (
        f'<p><a href="/session?{urlencode({"day": following})}"><button>Next session</button>'
        "</a></p>"
        if following
        else "<p>Every session is done. Thank you.</p>"
    )
    body = (
        f"<h1>Reader study: {escape(study.audience.name)}, as {escape(study.reader)}</h1>"
        "<p>Five short sessions. In each you are briefed on one morning's news for this "
        "audience, either from the digest or from the news items it was made from, and timed. "
        "Do them in order, one sitting each, without a break in the middle of a session.</p>"
        f'<details class="rubric"><summary>Who this audience is</summary>'
        f"<p>{escape(study.audience.description)}</p></details>"
        f"{action}<table><tr><th></th><th>Morning</th><th>Briefed</th><th></th></tr>"
        f"{''.join(rows)}</table>"
    )
    return _page("Reader study", body)


def session_page(study: Study, day: str) -> bytes:
    plan = dict(study.plan())
    if day not in plan:
        raise ValueError(f"{day} is not a study day")
    condition = plan[day]
    if condition == "digest":
        task = (
            f'<iframe id="frame" data-src="/digest?{urlencode({"day": day})}" '
            'style="width:100%;height:78vh;border:1px solid var(--line);border-radius:8px">'
            "</iframe>"
        )
    else:
        rows = []
        for item in pool_items(study.store, study.audience.id, day):
            published = item.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M")
            rows.append(
                '<label class="row" style="cursor:default">'
                f'<input class="pick" type="checkbox" value="{escape(item.url)}"><div>'
                f'<a class="title" href="{escape(item.url)}" target="_blank" rel="noopener">'
                f"{escape(item.title)}</a>"
                f'<div class="meta">{escape(item.domain)} &middot; {published} UTC</div>'
                f'<div class="snip">{escape(_snippet(item.summary))}</div></div></label>'
            )
        task = f"<p><b id='picked'>0</b> ticked, at most {MAX_PICKS}</p>" + "".join(rows)
    body = (
        f'<a href="/">All sessions</a><h1>{escape(study.audience.name)}, the morning of '
        f"{escape(day)}</h1><p>{escape(INSTRUCTIONS[condition])}</p>"
        '<div id="before"><p>The clock starts when you press Start and pauses while this tab '
        'is not in view.</p><button id="start">Start</button></div>'
        f'<div id="task" hidden>{task}'
        '<div class="save"><button id="done">Done, I am briefed</button></div></div>'
    )
    script = (
        f"const TOKEN = {json.dumps(study.token)}, DAY = {json.dumps(day)}, "
        f"CONDITION = {json.dumps(condition)}, MAX = {MAX_PICKS};\n{STUDY_SCRIPT}"
    )
    return _page(f"Reader study, {day}", body, script)


def digest_page(study: Study, day: str) -> bytes:
    if dict(study.plan()).get(day) != "digest" or day not in study.started:
        raise PermissionError("this day is not read from the digest, or has not started")
    digest = study.store.digest_for(study.audience.id, day)
    if digest is None:
        raise ValueError(f"no digest for {day}")
    return html_page(digest, study.audience.description).encode()


def start(study: Study, payload: dict[str, Any]) -> None:
    if payload.get("token") != study.token:
        raise PermissionError("this page is from an earlier session; reload it")
    day = str(payload.get("day", ""))
    if day not in dict(study.plan()):
        raise ValueError(f"{day} is not a study day")
    study.started[day] = datetime.now(UTC)


def finish(study: Study, payload: dict[str, Any]) -> ReaderSession:
    if payload.get("token") != study.token:
        raise PermissionError("this page is from an earlier session; reload it")
    day = str(payload.get("day", ""))
    plan = dict(study.plan())
    if day not in plan or day not in study.started:
        raise ValueError("this session was not started; press Start first")
    condition = plan[day]
    active = float(payload.get("seconds_active", 0))
    wall = float(payload.get("seconds_wall", 0))
    if not 0 < active <= wall + 1:
        raise ValueError("the time sent is not a time this session could have taken")
    audience_id = study.audience.id
    picks: tuple[str, ...] = ()
    found = 0
    if condition == "sources":
        items = {item.url: item for item in pool_items(study.store, audience_id, day)}
        picks = tuple(str(url) for url in payload.get("picks", []))
        if len(picks) > MAX_PICKS or not set(picks) <= set(items):
            raise ValueError(f"picks must be at most {MAX_PICKS} of the items shown")
        shown_ids = in_digest(study.store, audience_id, day)
        found = sum(items[url].id in shown_ids for url in picks)
        shown = len(items)
    else:
        digest = study.store.digest_for(audience_id, day)
        shown = len(digest.stories) if digest else 0
    session = ReaderSession(
        reader=study.reader,
        audience_id=audience_id,
        day=day,
        condition=condition,
        seconds_active=active,
        seconds_wall=wall,
        shown=shown,
        picks=picks,
        picks_in_digest=found,
        started_at=study.started.pop(day),
        finished_at=datetime.now(UTC),
    )
    study.sessions.add_reader_session(session)
    study.push()
    return session


def application(
    study: Study, fonts: dict[str, bytes] | None = None
) -> Callable[[dict[str, Any], StartResponse], list[bytes]]:
    def app(environ: dict[str, Any], start_response: StartResponse) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        query = {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}
        html = "text/html; charset=utf-8"
        try:
            if method == "GET" and path == "/":
                return _reply(start_response, "200 OK", overview(study), html)
            if method == "GET" and path == "/session":
                page = session_page(study, query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "GET" and path == "/digest":
                page = digest_page(study, query.get("day", ""))
                return _reply(start_response, "200 OK", page, html)
            if method == "GET" and fonts and path in fonts:
                return _reply(start_response, "200 OK", fonts[path], "font/woff2")
            if method == "POST" and path in ("/start", "/done"):
                size = int(environ.get("CONTENT_LENGTH") or 0)
                payload = json.loads(environ["wsgi.input"].read(size) or b"{}")
                if path == "/start":
                    start(study, payload)
                else:
                    finish(study, payload)
                return _reply(start_response, "200 OK", b"{}", "application/json")
        except PermissionError as error:
            return _reply(start_response, "403 Forbidden", str(error).encode(), "text/plain")
        except (KeyError, ValueError) as error:
            return _reply(start_response, "400 Bad Request", str(error).encode(), "text/plain")
        return _reply(start_response, "404 Not Found", b"not found", "text/plain")

    return app
