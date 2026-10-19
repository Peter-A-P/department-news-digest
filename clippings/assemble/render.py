"""A digest as a web page, as Markdown, and as an email draft file nobody sends.

Delivery is a page and a draft file (PLAN.md section 2.7). The `.eml` is built with
`email.message`, which constructs a message and has no transport; it carries `X-Unsent: 1`,
which mail clients read as "open this as a draft", and no recipient. An owner who wants to
circulate it opens it, addresses it and presses send themselves. Nothing here can.

Every string from a publisher or a model is escaped before it reaches HTML. A feed is input
from the open web, and a headline containing markup is a headline, not markup.

On the page a story shows its headline and the first two sentences of its summary; the rest
of the summary, the sources and the ranking note open under "Read more". That is a
`<details>` element, because the service's content policy allows no script. For the same
reason a citation mark links straight to the article it cites rather than to the source list,
which may be closed. The Markdown and the draft file show everything, except the day's X
post, which X allows to be shown only with its author's name, handle and picture and the X
logo: the Markdown links to it instead.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC
from email.message import EmailMessage
from email.policy import SMTP
from html import escape

from clippings.assemble.about import about_sections
from clippings.assemble.digest import Digest, DigestSentence, DigestStory, Spotlight, XPick
from clippings.assemble.trends import Trends, describe
from clippings.constants import CAD_PER_USD, cad

# Sentences shown before "Read more"; the rest of the summary is one click away.
LEAD_SENTENCES = 2

# The look follows peterparker.ca's project sites (gate.peterparker.ca): the same paper and
# ink, the teal accent, Newsreader for headlines and Inter for text, both served by this
# site from /fonts/ because the content policy loads nothing from elsewhere but X's profile
# pictures. In the .eml
# draft the fonts do not load and the fallbacks apply.
STYLE = """
@font-face { font-family: "Newsreader"; font-style: normal; font-weight: 200 800;
  font-display: swap; src: url(/fonts/newsreader-latin.woff2) format("woff2"); }
@font-face { font-family: "Inter"; font-style: normal; font-weight: 400 600;
  font-display: swap; src: url(/fonts/inter-latin.woff2) format("woff2"); }
:root {
  color-scheme: light dark;
  --paper: #f5f3ee; --paper-soft: #fdfcf9; --ink: #16181d; --ink-soft: #3c4048;
  --ink-faint: #6b7079; --line: #e3dfd6; --line-2: #cfc9bd;
  --accent: #0f5c6e; --accent-ink: #0b4653; --accent-soft: #e4eff1;
  --teal: #0f5c6e; --teal-soft: #e4eff1; --violet: #6d3f9e; --violet-soft: #efe8f7;
  --green: #1e7a4c; --green-soft: #e3f2ea; --amber: #9a6700; --amber-soft: #f7eed9;
  --rose: #b4434f; --rose-soft: #f8e6e8; --paper-deep: #ebe8e0;
  --aud: var(--teal); --aud-soft: var(--teal-soft);
  --serif: "Newsreader", Georgia, "Times New Roman", serif;
  --sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --radius: 10px; --column: 46rem; --wide: 60rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #0e1013; --paper-soft: #15181d; --ink: #ece9e2; --ink-soft: #c9c6bf;
    --ink-faint: #969ba5; --line: #262a31; --line-2: #363b44;
    --accent: #7cc7d6; --accent-ink: #a9dde7; --accent-soft: #14262b;
    --teal: #7cc7d6; --teal-soft: #14262b; --violet: #b191e0; --violet-soft: #221a2e;
    --green: #58c286; --green-soft: #13261c; --amber: #e0b35a; --amber-soft: #2a2312;
    --rose: #f08a93; --rose-soft: #2c1a1d; --paper-deep: #0a0c0e;
  }
}
* { box-sizing: border-box; }
html { font-size: 18px; -webkit-text-size-adjust: 100%; }
body { margin: 0; overflow-x: clip; background: var(--paper); color: var(--ink);
  font-family: var(--sans); font-size: 1rem; line-height: 1.65;
  border-top: 3px solid var(--accent); }
a { color: var(--accent); text-decoration: none; text-underline-offset: 0.15em; }
a:hover, a:focus-visible { text-decoration: underline; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
h1, h2, h3 { font-family: var(--serif); font-weight: 500; letter-spacing: -0.012em;
  color: var(--ink); }
p { margin: 0 0 0.8rem; }

.top { border-bottom: 1px solid var(--line); }
.top-inner { max-width: var(--wide); margin: 0 auto; padding: 0 1.5rem; height: 4rem;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.brand { display: inline-flex; align-items: center; gap: 0.7rem; color: var(--ink);
  font-weight: 600; letter-spacing: -0.01em; }
.brand:hover { text-decoration: none; color: var(--accent-ink); }
.mono-mark { width: 1.9rem; height: 1.9rem; border-radius: 6px; background: var(--accent);
  color: var(--paper-soft); font-family: var(--serif); font-weight: 500; font-size: 1.15rem;
  display: inline-flex; align-items: center; justify-content: center; }
.top-nav { font-size: 0.88rem; margin: 0; text-align: right; }
.tabs { border-bottom: 1px solid var(--line); background: var(--paper-soft); }
.tabs-inner { max-width: var(--wide); margin: 0 auto; padding: 0.55rem 1.5rem; display: flex;
  flex-wrap: wrap; gap: 0.2rem; }
.tabs a { font-size: 0.83rem; padding: 0.2rem 0.55rem; border-radius: 999px;
  border: 1px solid transparent; color: var(--ink-soft); }
.tabs a:hover { text-decoration: none; border-color: var(--line-2); color: var(--accent-ink); }
.tabs a[aria-current] { border-color: var(--accent); background: var(--accent-soft);
  color: var(--ink); font-weight: 600; }
.arch-figure { margin: 1.1rem 0 1.4rem; }
.arch-figure a { display: block; }
.arch-figure img { display: block; width: 100%; height: auto; background: #ffffff;
  border: 1px solid var(--line); border-radius: 8px; }
.prose p { max-width: var(--column); }
.prose .where { font-size: 0.86rem; color: var(--ink-faint); }
.arch-back { margin: 0; font-size: 0.95rem; }
.top-nav a { color: var(--ink-soft); }

main { max-width: var(--wide); margin: 0 auto; padding: 0 1.5rem 4rem; }
.hero { position: relative; padding: 2.75rem 0 2rem; border-bottom: 1px solid var(--line); }
.hero::before { content: ""; position: absolute; z-index: -1; top: 0; bottom: 0; left: 50%;
  width: 100vw; margin-left: -50vw;
  background: radial-gradient(55rem 20rem at 88% 0%,
      color-mix(in srgb, var(--violet) 16%, transparent), transparent 70%),
    radial-gradient(40rem 16rem at 8% 100%,
      color-mix(in srgb, var(--amber) 10%, transparent), transparent 70%),
    linear-gradient(180deg, var(--aud-soft), var(--paper) 85%); }
.aud-teal { --aud: var(--teal); --aud-soft: var(--teal-soft); }
.aud-violet { --aud: var(--violet); --aud-soft: var(--violet-soft); }
.aud-green { --aud: var(--green); --aud-soft: var(--green-soft); }
.aud-rose { --aud: var(--rose); --aud-soft: var(--rose-soft); }
.hero > * { max-width: var(--column); }
.hero .points, .hero.wide > * { max-width: none; }
.crumbs { font-size: 0.82rem; color: var(--ink-faint); margin: 0 0 1.4rem; }
.crumbs a { color: var(--ink-soft); }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.72rem;
  font-weight: 600; color: var(--aud); margin: 0 0 0.6rem; }
h1 { font-size: clamp(2rem, 4.4vw, 2.7rem); line-height: 1.12; margin: 0 0 0.9rem; }
h1 .hl { color: var(--accent); }
.lead { font-size: 1.05rem; color: var(--ink-soft); }
.note { font-size: 0.86rem; color: var(--ink-faint); }
.points { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.8rem; margin: 1.5rem 0 1rem; }
.point, .card { background: var(--paper-soft); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 0.9rem 1rem; min-width: 0; }
.card { border-top: 3px solid var(--aud); }
.card .latest a { color: var(--aud); }
.point { --c: var(--teal); border-top: 3px solid var(--c); }
.point:nth-child(2) { --c: var(--green); }
.point:nth-child(3) { --c: var(--violet); }
.point:nth-child(4) { --c: var(--amber); }
.figure { display: block; font-family: var(--serif); font-size: 1.7rem; font-weight: 500;
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em; line-height: 1.15;
  color: var(--c); }
.unit { display: block; margin-top: 0.25rem; font-size: 0.8rem; color: var(--ink-soft);
  line-height: 1.4; }
.warn { margin: 1rem 0 0; background: var(--paper-soft); border: 1px solid var(--line);
  border-left: 3px solid var(--amber); border-radius: 6px; padding: 0.7rem 0.9rem;
  font-size: 0.88rem; color: var(--ink-soft); }

.stories { max-width: var(--column); }
.story { padding: 1.7rem 0 1.5rem; border-bottom: 1px solid var(--line); }
.story .pos { display: inline-flex; align-items: center; justify-content: center;
  width: 1.6rem; height: 1.6rem; margin-right: 0.55rem; border-radius: 50%;
  background: var(--aud-soft); color: var(--aud); font-family: var(--sans);
  font-size: 0.78rem; font-weight: 600; vertical-align: 0.2rem; }
.story h2 { font-size: 1.45rem; line-height: 1.25; margin: 0 0 0.3rem; }
.story h2 a { color: var(--ink); }
.story h2 a:hover { color: var(--accent-ink); }
.meta { font-size: 0.8rem; color: var(--ink-faint); margin: 0 0 0.7rem; }
.tag { display: inline-block; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.02em;
  border-radius: 999px; padding: 0.05rem 0.55rem; margin-right: 0.5rem;
  color: var(--c); background: color-mix(in srgb, var(--c) 13%, transparent); }
.tag.must { --c: var(--rose); }
.tag.relevant { --c: var(--teal); }
.tag.marginal { --c: var(--amber); }
.tag.news { --c: var(--teal); }
.tag.post { --c: var(--violet); }
.story p { color: var(--ink-soft); }
sup a { font-size: 0.68rem; font-weight: 600; margin-left: 0.1rem; }
.none { color: var(--ink-faint); font-style: italic; }
details { margin-top: 0.2rem; }
summary { display: inline-block; cursor: pointer; list-style: none; font-size: 0.8rem;
  font-weight: 600; color: var(--accent-ink); border: 1px solid var(--line-2);
  border-radius: 999px; padding: 0.15rem 0.85rem; user-select: none; }
summary:hover { background: var(--accent-soft); border-color: var(--accent); }
summary::-webkit-details-marker { display: none; }
summary::after { content: " \\25BE"; }
details[open] > summary::after { content: " \\25B4"; }
details[open] > summary .more, details:not([open]) > summary .less { display: none; }
.fold { margin-top: 0.9rem; padding-left: 1rem; border-left: 2px solid var(--aud); }
.sources { font-size: 0.82rem; color: var(--ink-faint); margin: 0.6rem 0 0;
  padding-left: 1.1rem; }
.sources li { margin: 0 0 0.3rem; }
.sources a { overflow-wrap: anywhere; }
.why { font-size: 0.76rem; color: var(--ink-faint); margin-top: 0.5rem; }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
  gap: 0.9rem; margin: 2rem 0; }
.card h3 { font-size: 1.25rem; line-height: 1.25; margin: 0 0 0.4rem; }
.card h3 a { color: var(--ink); }
.card p { font-size: 0.88rem; color: var(--ink-soft); }
.card .latest { font-size: 0.84rem; font-weight: 600; margin: 0; }
.section-title { font-size: 1.5rem; margin: 2.2rem 0 0; }
.days { list-style: none; padding: 0; margin: 1.5rem 0; max-width: var(--column); }
.days li { border-bottom: 1px solid var(--line); }
.days a { display: block; padding: 0.6rem 0; font-family: var(--serif); font-size: 1.15rem; }

.trend-rose { color: var(--green); font-weight: 600; }
.trend-fell { color: var(--rose); font-weight: 600; }
.trend-terms details { border-bottom: 1px solid var(--line); padding: 0.5rem 0; }
.trend-terms summary { cursor: pointer; font-family: var(--serif); font-size: 1.1rem; }
.trend-terms ul { margin: 0.4rem 0 0.2rem; padding-left: 1.1rem; font-size: 0.88rem; }
.trend-terms .src-note { display: inline; }

.src-panel { margin-top: 1rem; }
.src-body { margin-top: 0.8rem; }
.src-wrap { overflow-x: auto; }
.src-table { border-collapse: collapse; width: 100%; font-size: 0.8rem; background: var(--paper-soft);
  border: 1px solid var(--line); border-radius: var(--radius); }
.src-table th, .src-table td { text-align: left; padding: 0.4rem 0.6rem;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.src-table th { font-weight: 600; color: var(--ink-soft); }
.src-table a { overflow-wrap: anywhere; }
.src-table td:nth-child(3) { white-space: nowrap; }
.src-note { display: block; color: var(--ink-faint); font-size: 0.74rem; }
.failed { color: var(--amber); font-weight: 600; }
.jump { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 1.5rem 0 0; }
.jump a { display: inline-flex; align-items: center; gap: 0.55rem; padding: 0.5rem 1.05rem;
  border-radius: 999px; border: 1px solid var(--line-2); background: var(--paper-soft);
  color: var(--ink); font-weight: 600; font-size: 0.92rem; }
.jump a:hover, .jump a:focus-visible { text-decoration: none; border-color: var(--aud);
  background: var(--aud-soft); }
.jump .n { font-size: 0.8rem; color: var(--aud); }
.jump a.to-posts .n { color: var(--violet); }
#news, #posts { scroll-margin-top: 1rem; }
.posts { max-width: var(--column); margin-top: 2.4rem; }
.posts .section-title { margin: 0; }
.spotlight { max-width: var(--column); margin: 1.6rem 0 0; padding: 1.1rem 1.2rem;
  background: var(--paper-soft); border: 1px solid var(--line);
  border-left: 3px solid var(--violet); border-radius: var(--radius); }
.spotlight .eyebrow { color: var(--violet); }
.post-card { margin: 0.4rem 0 0.7rem; padding: 0.9rem 1rem; border: 1px solid var(--line-2);
  border-radius: var(--radius); background: var(--paper); }
.pc-head { display: flex; align-items: center; gap: 0.6rem; }
.pc-avatar { width: 40px; height: 40px; border-radius: 50%; display: block; }
.pc-who { flex: 1; min-width: 0; line-height: 1.25; }
.pc-who a { display: block; color: var(--ink); text-decoration: none; overflow-wrap: anywhere; }
.pc-name { font-weight: 600; }
.pc-who .pc-user { color: var(--ink-faint); font-size: 0.86rem; }
.pc-logo { color: var(--ink); align-self: flex-start; }
.post-card svg { width: 20px; height: 20px; display: block; }
.pc-text { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0.7rem 0 0.5rem;
  font-size: 1.02rem; line-height: 1.5; color: var(--ink); }
.pc-time { margin: 0; font-size: 0.82rem; }
.pc-time a { color: var(--ink-faint); }
.pc-actions { display: flex; gap: 1.6rem; margin: 0.6rem 0 0; }
.pc-actions a { color: var(--ink-faint); }
/* The front page's long read below the audiences, in the manner of gate.peterparker.ca. */
.section { padding: 2.75rem 0; border-bottom: 1px solid var(--line); }
.section:last-child { border-bottom: 0; }
/* Text runs the full width, the same as the tables, steps and panels beside it. */
.section h2 { font-size: clamp(1.6rem, 3.2vw, 2.1rem); line-height: 1.18; margin: 0 0 0.8rem; }
.section .eyebrow { color: var(--accent-ink); }
#how .eyebrow { color: var(--violet); }
#measure .eyebrow { color: var(--green); }
#rules .eyebrow { color: var(--rose); }
#status .eyebrow { color: var(--amber); }
.section-lead { font-size: 1.02rem; color: var(--ink-soft); }
.section p { color: var(--ink-soft); }
.table-wrap { overflow-x: auto; margin: 1.2rem 0 1.2rem; }
table.idea { width: 100%; border-collapse: collapse; font-size: 0.88rem;
  background: var(--paper-soft); border: 1px solid var(--line); }
table.idea th, table.idea td { text-align: left; padding: 0.6rem 0.8rem; vertical-align: top;
  border-bottom: 1px solid var(--line); }
table.idea th { font-size: 0.8rem; font-weight: 600; color: var(--ink-soft);
  background: var(--paper-deep); }
table.idea td:first-child { width: 30%; }
table.idea td:last-child { color: var(--ink); }
table.idea tr.real { background: color-mix(in srgb, var(--green) 9%, transparent); }
.steps { list-style: none; padding: 0; margin: 1.4rem 0; display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); gap: 0.9rem;
  counter-reset: step; }
.steps li { --c: var(--teal); counter-increment: step; background: var(--paper-soft);
  border: 1px solid var(--line); border-radius: var(--radius); padding: 1rem 1.1rem; margin: 0;
  font-size: 0.88rem; color: var(--ink-soft); line-height: 1.55; }
.steps li:nth-child(5n+2) { --c: var(--violet); }
.steps li:nth-child(5n+3) { --c: var(--green); }
.steps li:nth-child(5n+4) { --c: var(--amber); }
.steps li:nth-child(5n+5) { --c: var(--rose); }
.steps li::before { content: counter(step); display: inline-flex; width: 1.6rem; height: 1.6rem;
  border-radius: 50%; background: var(--c); color: var(--paper-soft); font-weight: 600;
  font-size: 0.78rem; align-items: center; justify-content: center; margin-bottom: 0.5rem; }
.steps strong { display: block; color: var(--ink); font-size: 0.95rem; margin-bottom: 0.25rem; }
.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 1rem 0 0; padding: 0;
  list-style: none; }
.chips li { font-size: 0.78rem; padding: 0.2rem 0.7rem; border: 1px solid var(--line-2);
  border-radius: 999px; background: var(--paper-soft); color: var(--ink-soft); margin: 0; }
.panels { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.3rem 0 1rem; }
.panel { --c: var(--teal); background: var(--paper-soft); border: 1px solid var(--line);
  border-top: 3px solid var(--c); border-radius: var(--radius); padding: 1rem 1.15rem;
  min-width: 0; }
.panels .panel:nth-child(4n+2) { --c: var(--violet); }
.panels .panel:nth-child(4n+3) { --c: var(--green); }
.panels .panel:nth-child(4n+4) { --c: var(--amber); }
.panel h3 { font-size: 1.15rem; line-height: 1.25; margin: 0 0 0.45rem; }
.panel p { font-size: 0.88rem; margin: 0; }
.panel ul { margin: 0; padding-left: 1.1rem; font-size: 0.88rem; color: var(--ink-soft); }
.panel li { margin: 0 0 0.45rem; }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.3rem 0 0; }
.panel.built { --c: var(--green); }
.panel.tocome { --c: var(--amber); }
.panel.built h3 { color: var(--green); }
.panel.tocome h3 { color: var(--amber); }
.footer-band { background: var(--paper-deep); border-top: 1px solid var(--line); }
footer { max-width: var(--wide); margin: 0 auto; padding: 2rem 1.5rem 3rem;
  font-size: 0.84rem; color: var(--ink-faint); }
footer .footer-lead { color: var(--ink); font-weight: 600; font-size: 0.92rem; }
footer p { max-width: var(--column); }
@media (max-width: 46rem) {
  html { font-size: 17px; }
  .top-inner { height: auto; padding: 0.8rem 1rem; }
  .top-nav { display: none; }
  main { padding: 0 1rem 3rem; }
  footer { padding: 2rem 1rem 3rem; }
  .hero { padding: 2rem 0 1.5rem; }
  .story h2 { font-size: 1.3rem; }
  .section { padding: 2rem 0; }
  .panels, .split { grid-template-columns: 1fr; }
  table.idea thead { display: none; }
  table.idea tr { display: block; padding: 0.6rem 0.2rem; border-bottom: 1px solid var(--line); }
  table.idea td { display: block; width: auto !important; border: 0; padding: 0.1rem 0.6rem; }
  table.idea td[data-label]::before { content: attr(data-label) ": "; color: var(--ink-faint); }
}
"""

PROJECT_PAGE = "https://peterparker.ca/projects/department-news-digest/"

FOOTER = (
    "Nothing is sent: this is a page and a draft file. Summary sentences are written by a "
    "model and every one cites its sources; any quote is checked word for word against a "
    "source it cites and is at most twenty-five words. Headlines are the publishers' own. "
    "Article text is never republished. A Bluesky post may be shown in full, with its author "
    "and a link, while it exists, and an X post on the day it was picked."
)

INTRO = (
    "Every morning this reads the day's news feeds, a global news index and public posts, "
    "merges the articles that report the same thing into one story, and ranks the stories "
    "against what one audience cares about. A model summarises the ones that make the cut. "
    "Every sentence cites the articles it came from, and any quote is checked word for word "
    "against its source before it is shown. Each audience is a few lines of configuration: "
    "its topics, organisations, people, places and trusted sources."
)


# The site's menu, on every page. Absolute paths, because pages sit at three depths.
MENU = (
    ("/", "All digests"),
    ("/#why", "Why it exists"),
    ("/#how", "How it works"),
    ("/#measure", "How it is measured"),
    ("/architecture/", "How it's built"),
)


def menu(current: str = "") -> str:
    """The menu as HTML, with the page the reader is on marked."""
    links = "".join(
        f'<a href="{href}"{' aria-current="page"' if href == current else ""}>{escape(label)}</a>'
        for href, label in MENU
    )
    return f'<nav class="tabs" aria-label="This site"><div class="tabs-inner">{links}</div></nav>\n'


def _page(title: str, body: str, *, nav: str = "", hue: str = "teal", current: str = "") -> str:
    nav_html = f'<p class="top-nav">{nav}</p>' if nav else ""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n"
        f'<body class="aud-{hue}">\n'
        '<header class="top"><div class="top-inner">\n'
        '<a class="brand" href="https://peterparker.ca">'
        '<span class="mono-mark" aria-hidden="true">P</span>Peter Parker</a>\n'
        f"{nav_html or _project_link()}\n</div></header>\n"
        f"{menu(current)}"
        f"<main>\n{body}\n</main>\n"
        f'<div class="footer-band"><footer>\n<p class="footer-lead">{escape(FOOTER)}</p>\n'
        f'<p><a href="/">All digests</a> &middot; <a href="{PROJECT_PAGE}">The project page</a>'
        ' &middot; <a href="https://peterparker.ca">The rest of the portfolio</a></p>\n'
        "</footer></div>\n</body>\n</html>\n"
    )


def _project_link() -> str:
    return (
        f'<p class="top-nav"><a href="{PROJECT_PAGE}">Project 14: Verified Media Briefing</a></p>'
    )


def _summary_line(digest: Digest) -> str:
    c = digest.counts
    rerank = (
        f"{digest.candidates} candidates re-ranked against the rubric"
        if digest.reranked
        else f"{digest.candidates} candidates, rubric NOT applied"
    )
    quotes = (
        f"; quotes verbatim on first draft {c.quotes_verbatim_first} of {c.quotes_first}"
        if c.quotes_first
        else ""
    )
    return (
        f"Chosen from {digest.pool_items} items in {digest.pool_stories} stories; {rerank}. "
        f"{c.sentences_shown} sentences shown, {c.sentences_dropped} refused by the verifier"
        f"{quotes}. Model cost CA${cad(digest.cost_usd):.4f} (US${digest.cost_usd:.4f} "
        f"at {CAD_PER_USD} CAD per USD)."
    )


# Each audience keeps one colour across its card, its archive and its digests. It is drawn
# from the id, so it needs no configuration and stays put from day to day; the four example
# audiences land on four different colours.
HUES = ("rose", "violet", "teal", "green")

# Posts are commentary attached to a news story (models.SOCIAL_KINDS); the source list marks
# them apart from the reporting. A link carries its domain, not its kind, hence the domains.
POST_DOMAINS = frozenset({"bsky.app", "reddit.com", "www.reddit.com", "old.reddit.com"})

RUBRIC_TAGS = {3: ("must", "Must read"), 2: ("relevant", "Relevant"), 1: ("marginal", "Marginal")}


def hue(audience_id: str) -> str:
    return HUES[zlib.crc32(audience_id.encode("utf-8")) % len(HUES)]


def _rerank_note(digest: Digest) -> str:
    if not digest.reranked:
        return f"{digest.candidates} candidates, in pre-filter order."
    return (
        f"The top {digest.candidates} candidates were re-ranked by a model against this "
        f"audience's rubric, which excluded {digest.rerank_excluded}."
    )


def _point(figure: str, unit: str) -> str:
    return (
        f'<div class="point"><span class="figure">{escape(figure)}</span>'
        f'<span class="unit">{escape(unit)}</span></div>'
    )


def _sentence_html(sentence: DigestSentence, story: DigestStory) -> str:
    urls = {source.sid: source.url for source in story.sources}
    marks = "".join(
        f'<sup><a href="{escape(urls.get(cite, f"#story-{story.position}-{cite}"))}">'
        f"[{escape(cite)}]</a></sup>"
        for cite in sentence.cites
    )
    return f"{escape(sentence.text)}{marks}"


def _paragraph(sentences: Sequence[DigestSentence], story: DigestStory) -> str:
    """Sentences read as prose: one paragraph, each followed by its citation marks."""
    return "<p>" + " ".join(_sentence_html(sentence, story) for sentence in sentences) + "</p>"


def _rubric_tag(story: DigestStory) -> str:
    tag = RUBRIC_TAGS.get(story.rerank_score) if story.rerank_score is not None else None
    return f'<span class="tag {tag[0]}">{tag[1]}</span>' if tag else ""


def _story_html(story: DigestStory) -> str:
    anchor = f"story-{story.position}"
    outlets = f" and {story.outlets - 1} more" if story.outlets > 1 else ""
    published = story.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f'<article class="story" id="{anchor}">',
        f'<h2><span class="pos">{story.position}.</span>'
        f'<a href="{escape(story.url)}">{escape(story.headline)}</a></h2>',
        f'<p class="meta">{_rubric_tag(story)}'
        f"{escape(story.domain)}{escape(outlets)} &middot; {published}</p>",
    ]
    rest: list[DigestSentence] = []
    if story.sentences:
        lead, rest = list(story.sentences[:LEAD_SENTENCES]), list(story.sentences[LEAD_SENTENCES:])
        parts.append(_paragraph(lead, story))
    else:
        why = (
            "The summary could not be produced today"
            if story.status == "summary failed"
            else "No summary passed verification"
        )
        parts.append(f'<p class="none">{why}; the link is the story.</p>')
    more = "Read more" if rest else "Sources"
    less = "Show less" if rest else "Hide sources"
    parts.append(
        f'<details><summary><span class="more">{more}</span>'
        f'<span class="less">{less}</span></summary>\n<div class="fold">'
    )
    if rest:
        parts.append(_paragraph(rest, story))
    parts.append('<ol class="sources">')
    for source in story.sources:
        read = "" if source.extracted else " (feed summary only)"
        kind = ("post", "Post") if source.domain in POST_DOMAINS else ("news", "News")
        parts.append(
            f'<li id="{anchor}-{escape(source.sid)}">[{escape(source.sid)}] '
            f'<span class="tag {kind[0]}">{kind[1]}</span>{escape(source.domain)}: '
            f'<a href="{escape(source.url)}">{escape(source.title)}</a>{escape(read)}</li>'
        )
    parts.append("</ol>")
    if story.rerank_score is not None:
        reason = f": {story.rerank_reason}" if story.rerank_reason else ""
        parts.append(
            f'<div class="why">Rubric score {story.rerank_score} of 3{escape(reason)}. '
            f"Pre-filter {story.prefilter_score:.2f} ({escape(story.why)}).</div>"
        )
    parts.append("</div></details>")
    parts.append("</article>")
    return "\n".join(parts)


def _quoted(text: str) -> str:
    """In quotation marks, unless the post already opens with its own."""
    return text if text[:1] in {'"', "\u201c"} else f'"{text}"'


# X's logo and the reply, repost and like marks its display rules ask for beside a post,
# drawn inline because the page loads nothing from X but the author's picture. The Bluesky
# card uses the same marks.
X_LOGO = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.244 2.25h3.308'
    "l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08"
    'l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>'
)
X_ACTIONS = (
    (
        "Reply",
        "https://x.com/intent/tweet?in_reply_to=",
        "M3 11a8 8 0 0 1 8-8h2a8 8 0 0 1 0 16h-2l-5 4v-4.6A8 8 0 0 1 3 11z",
    ),
    (
        "Repost",
        "https://x.com/intent/retweet?tweet_id=",
        "M4 10V8a3 3 0 0 1 3-3h11m-3-3 3 3-3 3M20 14v2a3 3 0 0 1-3 3H6m3 3-3-3 3-3",
    ),
    (
        "Like",
        "https://x.com/intent/like?tweet_id=",
        "M12 20s-7-4.4-8.8-8.6C2 8.3 4 5 7.3 5c2 0 3.6 1.2 4.7 2.9C13.1 6.2 14.7 5 16.7 5 20 5 22 8.3 20.8 11.4 19 15.6 12 20 12 20z",
    ),
)


# Bluesky's butterfly, from its published brand mark, drawn inline for the same reason.
BLUESKY_LOGO = (
    '<svg viewBox="0 0 600 530" aria-hidden="true"><path fill="currentColor" d="m135.72 44.03'
    "c66.496 49.921 138.02 151.14 164.28 205.46 26.262-54.316 97.782-155.54 164.28-205.46"
    " 47.98-36.021 125.72-63.892 125.72 24.795 0 17.712-10.155 148.79-16.111 170.07"
    "-20.703 73.984-96.144 92.854-163.25 81.433 117.3 19.964 147.14 86.092 82.697 152.22"
    "-122.39 125.59-175.91-31.511-189.63-71.766-2.514-7.3797-3.6904-10.832-3.7077-7.8964"
    "-0.0174-2.9357-1.1937 0.51669-3.7077 7.8964-13.714 40.255-67.233 197.36-189.63 71.766"
    "-64.444-66.128-34.605-132.26 82.697-152.22-67.108 11.421-142.55-7.4491-163.25-81.433"
    "-5.9562-21.282-16.111-152.36-16.111-170.07 0-88.687 77.742-60.816 125.72-24.795z"
    '"/></svg>'
)


def _post_card(
    *,
    platform: str,
    logo: str,
    profile: str,
    name: str,
    handle: str,
    image_url: str,
    text: str,
    url: str,
    posted: str,
    actions: str,
) -> str:
    """A post laid out the way the platforms show one: picture, name and handle above the
    text, the platform's mark at the top right, the time linking to the post, then the
    actions. X's display rules require this layout; Bluesky's pick uses the same one."""
    avatar = (
        f'<a href="{escape(profile)}"><img class="pc-avatar" src="{escape(image_url)}" alt="" '
        'width="40" height="40"></a>'
        if image_url
        else ""
    )
    shown_name = f'<a class="pc-name" href="{escape(profile)}">{escape(name)}</a>' if name else ""
    return (
        '<div class="post-card"><div class="pc-head">'
        f'{avatar}<div class="pc-who">{shown_name}'
        f'<a class="pc-user" href="{escape(profile)}">@{escape(handle)}</a></div>'
        f'<a class="pc-logo" href="{escape(url)}" aria-label="View on {platform}">{logo}</a></div>'
        f'<div class="pc-text">{escape(text)}</div>'
        f'<p class="pc-time"><a href="{escape(url)}">{posted}</a></p>'
        f'<p class="pc-actions">{actions}</p></div>'
    )


def _action_icons(links: Sequence[tuple[str, str, str]]) -> str:
    return "".join(
        f'<a href="{escape(href)}" aria-label="{label}" title="{label}">'
        f'<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="{path}"/></svg></a>'
        for label, href, path in links
    )


def _spotlight_html(post: Spotlight) -> str:
    """The day's most discussed Bluesky post, as a post card: whole while it exists and for
    thirty days, then its twenty-five-word quote; nothing once its author deletes it."""
    posted = post.posted_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if post.deleted:
        return (
            '<section class="spotlight"><p class="eyebrow">Most discussed on Bluesky</p>'
            '<p class="none">This post was deleted by its author, so it is no longer shown.</p>'
            "</section>"
        )
    reason = (
        f'<p class="why">Picked because: {escape(post.reason.rstrip("."))}.</p>'
        if post.reason
        else ""
    )
    # Bluesky has no links that reply, repost or like from outside its app, so each mark
    # opens the post there.
    actions = _action_icons([(label, post.url, path) for label, _, path in X_ACTIONS])
    card = _post_card(
        platform="Bluesky",
        logo=BLUESKY_LOGO,
        profile=f"https://bsky.app/profile/{post.author}",
        name=post.name,
        handle=post.author,
        image_url=post.image_url,
        text=post.full_text or post.quote,
        url=post.url,
        posted=posted,
        actions=actions,
    )
    return (
        '<section class="spotlight">'
        '<p class="eyebrow">Most discussed on Bluesky</p>'
        f'{card}<p class="meta"><span class="tag post">Post</span>{post.likes} likes, '
        f"{post.reposts} reposts, {post.replies} replies</p>{reason}"
        '<p class="note">A post, not reporting: its author\'s own words, shown because people '
        "were discussing it and it fits this audience. Nothing in it has been checked. Shown "
        "while it exists: if the author deletes it, it is removed here too.</p>"
        "</section>"
    )


def _x_pick_html(pick: XPick) -> str:
    """The day's X post, whole, the way X's display rules lay it out; after its day, a link."""
    posted = pick.posted_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    reason = (
        f'<p class="why">Picked because: {escape(pick.reason.rstrip("."))}.</p>'
        if pick.reason
        else ""
    )
    if pick.expired or not pick.text:
        return (
            '<section class="spotlight"><p class="eyebrow">Most discussed on X</p>'
            f'<p class="meta"><span class="tag post">Post</span><a href="{escape(pick.url)}">'
            f"A post by @{escape(pick.username)}</a> &middot; {posted} &middot; "
            f"{pick.likes} likes when picked</p>{reason}"
            '<p class="note">X posts are shown here only on the day they are picked, so its '
            "words are no longer on this page. The link opens it on X if it is still there.</p>"
            "</section>"
        )
    card = _post_card(
        platform="X",
        logo=X_LOGO,
        profile=f"https://x.com/{pick.username}",
        name=pick.name,
        handle=pick.username,
        image_url=pick.image_url,
        text=pick.text,
        url=pick.url,
        posted=posted,
        actions=_action_icons(
            [(label, f"{base}{pick.post_id}", path) for label, base, path in X_ACTIONS]
        ),
    )
    return (
        '<section class="spotlight">'
        '<p class="eyebrow">Most discussed on X</p>'
        f'{card}<p class="meta"><span class="tag post">Post</span>{pick.likes} likes, '
        f"{pick.reposts} reposts, {pick.replies} replies</p>{reason}"
        '<p class="note">A post, not reporting: its author\'s own words, shown whole as X '
        "asks, because people were discussing it and it fits this audience. Nothing in it has "
        "been checked. Shown on the day it was picked only: the next run removes it here.</p>"
        "</section>"
    )


def html_page(digest: Digest, description: str = "", sources: str = "") -> str:
    """One audience's digest for one day. `description` is the audience's own, if known."""
    c = digest.counts
    title = f"{digest.audience_name}, {digest.day}"
    checked = c.sentences_shown + c.sentences_dropped
    points = [
        _point(
            f"{len(digest.stories)} stories",
            f"chosen from {digest.pool_items} articles and posts, "
            f"merged into {digest.pool_stories} stories",
        ),
        _point(
            f"{c.sentences_shown} of {checked}",
            "summary sentences passed the check against their sources",
        ),
    ]
    if c.quotes_first:
        points.append(
            _point(
                f"{c.quotes_verbatim_first} of {c.quotes_first}",
                "quotes word for word on the first draft",
            )
        )
    points.append(_point(f"CA${cad(digest.cost_usd):.2f}", "model cost for this digest"))
    body = [
        '<header class="hero">',
        f'<p class="crumbs"><a href="../../">All digests</a> &rsaquo; '
        f'<a href="../">{escape(digest.audience_name)}</a> &rsaquo; {escape(digest.day)}</p>',
        f'<p class="eyebrow">Daily digest &middot; {escape(digest.day)}</p>',
        f"<h1>{escape(digest.audience_name)}</h1>",
    ]
    if description:
        body.append(f'<p class="lead">{escape(description)}</p>')
    body += [
        f'<div class="points">{"".join(points)}</div>',
        f'<p class="note">{escape(_rerank_note(digest))} '
        '<a href="digest.md">Markdown</a> &middot; '
        '<a href="digest.eml">Email draft (unsent)</a></p>',
    ]
    if sources:
        body.append(sources)
    if not digest.reranked:
        body.append(
            '<p class="warn">The model re-ranker did not run for this digest '
            f"({escape(digest.rerank_error)}), so it is in pre-filter order and the rubric's "
            "exclusions were not applied.</p>"
        )
    body.append("</header>")
    posts = [
        *(_spotlight_html(post) for post in digest.spotlights),
        *(_x_pick_html(pick) for pick in digest.x_picks),
    ]
    if posts:
        # News and posts are different things to read, and a reader usually wants one of
        # them: a button for each, with how many, before either begins (Peter, 2026-10-15).
        stories = len(digest.stories)
        body.append(
            '<nav class="jump" aria-label="On this page">'
            f'<a href="#news">News <span class="n">{stories} '
            f"{'story' if stories == 1 else 'stories'}</span></a>"
            f'<a class="to-posts" href="#posts">Social media posts '
            f'<span class="n">{len(posts)}</span></a></nav>'
        )
    body.append('<div class="stories" id="news">')
    if not digest.stories:
        body.append('<p class="none">No story was chosen today.</p>')
    body.extend(_story_html(story) for story in digest.stories)
    body.append("</div>")
    if posts:
        body.append(
            '<section class="posts" id="posts"><h2 class="section-title">Social media posts</h2>'
            + "".join(posts)
            + "</section>"
        )
    body.append(f'<p class="note">Run {escape(digest.run_id)}.</p>')
    return _page(title, "\n".join(body), hue=hue(digest.audience_id))


def markdown(digest: Digest) -> str:
    lines = [f"# {digest.audience_name}, {digest.day}", "", _summary_line(digest), ""]
    if not digest.reranked:
        lines += [f"> The model re-ranker did not run ({digest.rerank_error}).", ""]
    for story in digest.stories:
        lines += [f"## {story.position}. [{story.headline}]({story.url})", ""]
        lines.append(f"_{story.domain}, {story.published_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC_")
        lines.append("")
        if story.sentences:
            for sentence in story.sentences:
                marks = "".join(f"[{cite}]" for cite in sentence.cites)
                lines.append(f"{sentence.text} {marks}")
            lines.append("")
        else:
            why = (
                "The summary could not be produced today."
                if story.status == "summary failed"
                else "No summary passed verification."
            )
            lines += [f"_{why}_", ""]
        for source in story.sources:
            lines.append(f"- [{source.sid}] {source.domain}: [{source.title}]({source.url})")
        lines.append("")
    for post in digest.spotlights:
        if post.deleted:
            lines += [
                "## Most discussed on Bluesky",
                "",
                "_This post was deleted by its author, so it is no longer shown._",
                "",
            ]
            continue
        body = post.full_text or post.quote
        lines += [
            "## Most discussed on Bluesky",
            "",
            *(f"> {line}" if line else ">" for line in _quoted(body).splitlines()),
            "",
            f"[@{post.author}]({post.url}), {post.likes} likes, {post.replies} replies. "
            "A post, not reporting; nothing in it has been checked.",
            "",
        ]
    for x in digest.x_picks:
        reason = f" Picked because: {x.reason.rstrip('.')}." if x.reason else ""
        lines += [
            "## Most discussed on X",
            "",
            f"[A post by @{x.username}]({x.url}), {x.likes} likes when picked.{reason} "
            "X allows a post to be shown only whole with its author, so it is linked here and "
            "shown on the web page on the day it was picked.",
            "",
        ]
    lines += ["---", "", FOOTER, ""]
    return "\n".join(lines)


def eml_draft(digest: Digest) -> bytes:
    """An unsent email draft: a subject, the digest as text and HTML, and no recipient."""
    message = EmailMessage(policy=SMTP)
    message["Subject"] = f"{digest.audience_name} digest, {digest.day}"
    message["X-Unsent"] = "1"
    message.set_content(markdown(digest))
    message.add_alternative(html_page(digest), subtype="html")
    return message.as_bytes()


def audience_index(
    audience_name: str,
    days: Sequence[str],
    description: str = "",
    audience_id: str = "",
    sources: str = "",
    trends: bool = False,
) -> str:
    items = "\n".join(f'<li><a href="{escape(day)}/">{escape(day)}</a></li>' for day in days)
    lead = f'<p class="lead">{escape(description)}</p>' if description else ""
    trend_link = (
        '<p class="jump"><a href="trends/">Trends: this week against the week before</a></p>'
        if trends
        else ""
    )
    body = (
        '<header class="hero">'
        '<p class="crumbs"><a href="../">All digests</a></p>'
        '<p class="eyebrow">Archive</p>'
        f"<h1>{escape(audience_name)}</h1>{lead}{trend_link}{sources}</header>\n"
        f'<ul class="days">\n{items}\n</ul>'
    )
    return _page(audience_name, body, hue=hue(audience_id) if audience_id else "teal")


KIND_LABEL = {
    "organisation": "Organisation",
    "person": "Person",
    "place": "Place",
    "topic": "Topic",
}


def trends_page(audience_name: str, audience_id: str, trends: Trends) -> str:
    """One audience's trend view: its own terms, counted in two weeks of coverage."""
    rows = []
    details = []
    for term in trends.terms:
        css = {"rose": "trend-rose", "fell": "trend-fell"}.get(term.change, "")
        rows.append(
            f"<tr><td>{escape(term.label)}</td><td>{KIND_LABEL[term.kind]}</td>"
            f"<td>{term.this_week}</td><td>{term.last_week}</td>"
            f'<td class="{css}">{escape(term.change)}</td></tr>'
        )
        if term.items:
            items = "".join(
                f'<li><a href="{escape(item.url)}">{escape(item.title)}</a> '
                f'<span class="src-note">{escape(item.domain)}, '
                f"{item.published_at.astimezone(UTC):%Y-%m-%d}"
                f"{', in a digest' if item.in_digest else ''}</span></li>"
                for item in term.items
            )
            more = (
                f'<p class="src-note">The {len(term.items)} newest of {term.this_week}.</p>'
                if term.this_week > len(term.items)
                else ""
            )
            details.append(
                f"<details><summary>{escape(term.label)}: {term.this_week} this week</summary>"
                f"<ul>{items}</ul>{more}</details>"
            )
    partial = (
        " The week before began before this audience's first digest, so it holds only what "
        "the feeds still carried on the first day."
        if trends.partial_last
        else ""
    )
    unseen = (
        f'<p class="src-note">Not named in either week: {escape(", ".join(trends.unseen))}.</p>'
        if trends.unseen
        else ""
    )
    table = (
        '<div class="src-wrap"><table class="src-table"><tr><th>Term</th><th>Kind</th>'
        f"<th>Articles, week to {trends.end:%Y-%m-%d}</th>"
        f"<th>Week to {trends.last_end:%Y-%m-%d}</th>"
        f"<th>Change</th></tr>{''.join(rows)}</table></div>"
        if rows
        else "<p>None of this audience's terms was named in its news in either week.</p>"
    )
    body = (
        '<header class="hero">'
        f'<p class="crumbs"><a href="../../">All digests</a> &middot; <a href="../">'
        f"{escape(audience_name)}</a></p>"
        '<p class="eyebrow">Trends</p>'
        f"<h1>{escape(audience_name)}</h1>"
        f'<p class="lead">{escape(describe(trends.terms))}</p>'
        f"<p>The organisations, people, places and topics this audience follows, counted in the "
        f"news articles its sources published in the week {trends.start:%Y-%m-%d} to "
        f"{trends.end:%Y-%m-%d} ({trends.this_total} articles) and the week before "
        f"({trends.last_total}). A term rose or fell only when its share of coverage changed "
        f"by more than chance would explain (an exact binomial test at 5%); otherwise it is "
        f"about the same. Reprints count, because this is coverage.{partial}</p>"
        "</header>\n"
        f"{table}{unseen}"
        f'<h2 class="section-title">The articles behind them</h2>'
        f'<div class="trend-terms">{"".join(details)}</div>'
    )
    return _page(f"Trends: {audience_name}", body, hue=hue(audience_id))


def site_index(audiences: Sequence[tuple[str, str, str, str | None]]) -> str:
    """The front page: what this is, then each audience with its description and latest day."""
    cards = []
    for audience_id, name, description, latest in audiences:
        latest_link = (
            f'<p class="latest"><a href="{escape(audience_id)}/{escape(latest)}/">'
            f"Latest digest, {escape(latest)}</a></p>"
            if latest
            else '<p class="latest">No digest yet</p>'
        )
        cards.append(
            f'<div class="card aud-{hue(audience_id)}"><h3><a href="{escape(audience_id)}/">{escape(name)}</a></h3>'
            f"<p>{escape(description)}</p>{latest_link}</div>"
        )
    body = (
        '<header class="hero wide">'
        '<p class="eyebrow">Verified Media Briefing</p>'
        '<h1>The day\'s news for one department, <span class="hl">cited and checked.</span></h1>'
        f'<p class="lead">{escape(INTRO)}</p>'
        '<p class="note">Nothing is sent: each digest is a web page and an email draft file '
        "that its owner may send. The four audiences below are examples, built on public "
        "sources whose terms were read and recorded before anything was fetched.</p>"
        '<p class="note">Below the audiences: <a href="#why">why this exists</a>, '
        '<a href="#how">how it works</a>, <a href="#measure">how it is measured</a>, '
        '<a href="#rules">the rules it keeps</a> and <a href="#status">where it stands</a>. '
        '<a href="/architecture/">See how it\'s built</a>, in three diagrams.</p>'
        "</header>\n"
        '<h2 class="section-title">Audiences</h2>\n'
        f'<div class="cards">\n{"".join(cards)}\n</div>\n'
        f"{about_sections()}"
    )
    return _page("Verified Media Briefing", body, current="/")


def _md_inline(text: str) -> str:
    """`code` and [text](link) as HTML. Links become their words, because the document's
    links point inside the repository."""
    text = escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def architecture_page(document: str, sizes: Mapping[str, tuple[str, str]]) -> str:
    """docs/architecture.md after its introduction, one section per diagram, as a page.

    Rendered from the document itself so the site and the repository cannot tell different
    stories. `sizes` gives each diagram's width and height, read from the SVG."""
    parts = [
        '<header class="hero">'
        '<p class="eyebrow">Architecture</p><h1>How it\'s built</h1>'
        '<p class="lead">How the briefing is put together, in three pictures: the whole '
        "system, one morning's run, and how each published number is produced. Select a "
        "diagram to open it full size.</p></header>"
    ]
    for section in re.split(r"^## ", document, flags=re.M)[1:]:
        title, _, body = section.partition("\n")
        blocks = [b.strip() for b in body.strip().split("\n\n") if b.strip()]
        image = re.fullmatch(r"!\[(.*)\]\(architecture/([^)]+\.svg)\)", blocks[0], re.S)
        if image is None:
            raise ValueError(f"docs/architecture.md: {title!r} does not open with a diagram")
        alt, name = image.groups()
        width, height = sizes[name]
        paragraphs = []
        for block in blocks[1:]:
            text = " ".join(line.strip() for line in block.splitlines())
            where = ' class="where"' if text.startswith("Where it lives:") else ""
            paragraphs.append(f"<p{where}>{_md_inline(text)}</p>")
        parts.append(
            f'<section class="section"><h2>{_md_inline(title.strip())}</h2>'
            f'<figure class="arch-figure"><a href="{name}"><img src="{name}" width="{width}" '
            f'height="{height}" alt="{escape(alt)}"></a></figure>'
            f'<div class="prose">{"".join(paragraphs)}</div></section>'
        )
    parts.append('<p class="arch-back"><a href="/">Back to all digests</a></p>')
    return _page(
        "How it's built | Verified Media Briefing", "\n".join(parts), current="/architecture/"
    )
