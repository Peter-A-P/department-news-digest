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
which may be closed. The Markdown and the draft file show everything.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC
from email.message import EmailMessage
from email.policy import SMTP
from html import escape

from clippings.assemble.digest import Digest, DigestSentence, DigestStory

# Sentences shown before "Read more"; the rest of the summary is one click away.
LEAD_SENTENCES = 2

# The look follows peterparker.ca's project sites (gate.peterparker.ca): the same paper and
# ink, the teal accent, Newsreader for headlines and Inter for text, both served by this
# site from /fonts/ because the content policy loads nothing from elsewhere. In the .eml
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
  --accent: #0f5c6e; --accent-ink: #0b4653; --accent-soft: #e4eff1; --amber: #9a6700;
  --serif: "Newsreader", Georgia, "Times New Roman", serif;
  --sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --radius: 10px; --column: 46rem; --wide: 60rem;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #0e1013; --paper-soft: #15181d; --ink: #ece9e2; --ink-soft: #c9c6bf;
    --ink-faint: #969ba5; --line: #262a31; --line-2: #363b44;
    --accent: #7cc7d6; --accent-ink: #a9dde7; --accent-soft: #14262b; --amber: #e0b35a;
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
.top-nav a { color: var(--ink-soft); }

main { max-width: var(--wide); margin: 0 auto; padding: 0 1.5rem 4rem; }
.hero { position: relative; padding: 2.75rem 0 2rem; border-bottom: 1px solid var(--line); }
.hero::before { content: ""; position: absolute; z-index: -1; top: 0; bottom: 0; left: 50%;
  width: 100vw; margin-left: -50vw;
  background: linear-gradient(180deg, var(--accent-soft), var(--paper) 85%); }
.hero > * { max-width: var(--column); }
.hero .points { max-width: none; }
.crumbs { font-size: 0.82rem; color: var(--ink-faint); margin: 0 0 1.4rem; }
.crumbs a { color: var(--ink-soft); }
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.72rem;
  font-weight: 600; color: var(--accent-ink); margin: 0 0 0.6rem; }
h1 { font-size: clamp(2rem, 4.4vw, 2.7rem); line-height: 1.12; margin: 0 0 0.9rem; }
h1 .hl { color: var(--accent); }
.lead { font-size: 1.05rem; color: var(--ink-soft); }
.note { font-size: 0.86rem; color: var(--ink-faint); }
.points { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.8rem; margin: 1.5rem 0 1rem; }
.point, .card { background: var(--paper-soft); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 0.9rem 1rem; min-width: 0; }
.point { border-top: 3px solid var(--accent); }
.figure { display: block; font-family: var(--serif); font-size: 1.7rem; font-weight: 500;
  font-variant-numeric: tabular-nums; letter-spacing: -0.02em; line-height: 1.15;
  color: var(--accent-ink); }
.unit { display: block; margin-top: 0.25rem; font-size: 0.8rem; color: var(--ink-soft);
  line-height: 1.4; }
.warn { margin: 1rem 0 0; background: var(--paper-soft); border: 1px solid var(--line);
  border-left: 3px solid var(--amber); border-radius: 6px; padding: 0.7rem 0.9rem;
  font-size: 0.88rem; color: var(--ink-soft); }

.stories { max-width: var(--column); }
.story { padding: 1.7rem 0 1.5rem; border-bottom: 1px solid var(--line); }
.story .pos { font-family: var(--serif); color: var(--accent); font-size: 1rem;
  margin-right: 0.35rem; }
.story h2 { font-size: 1.45rem; line-height: 1.25; margin: 0 0 0.3rem; }
.story h2 a { color: var(--ink); }
.story h2 a:hover { color: var(--accent-ink); }
.meta { font-size: 0.8rem; color: var(--ink-faint); margin: 0 0 0.7rem; }
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
.fold { margin-top: 0.9rem; padding-left: 1rem; border-left: 2px solid var(--line); }
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

footer { max-width: var(--wide); margin: 0 auto; padding: 2rem 1.5rem 3rem;
  font-size: 0.84rem; color: var(--ink-faint); border-top: 1px solid var(--line); }
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
}
"""

PROJECT_PAGE = "https://peterparker.ca/projects/department-news-digest/"

FOOTER = (
    "Nothing is sent: this is a page and a draft file. Summary sentences are written by a "
    "model and every one cites its sources; any quote is checked word for word against a "
    "source it cites and is at most twenty-five words. Headlines are the publishers' own. "
    "Article text is never republished."
)

INTRO = (
    "Every morning this reads the day's news feeds, a global news index and public posts, "
    "merges the articles that report the same thing into one story, and ranks the stories "
    "against what one audience cares about. A model summarises the ones that make the cut. "
    "Every sentence cites the articles it came from, and any quote is checked word for word "
    "against its source before it is shown. Each audience is a few lines of configuration: "
    "its topics, organisations, people, places and trusted sources."
)


def _page(title: str, body: str, *, nav: str = "") -> str:
    nav_html = f'<p class="top-nav">{nav}</p>' if nav else ""
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n<body>\n"
        '<header class="top"><div class="top-inner">\n'
        '<a class="brand" href="https://peterparker.ca">'
        '<span class="mono-mark" aria-hidden="true">P</span>Peter Parker</a>\n'
        f"{nav_html or _project_link()}\n</div></header>\n"
        f"<main>\n{body}\n</main>\n"
        f'<footer>\n<p class="footer-lead">{escape(FOOTER)}</p>\n'
        f'<p><a href="/">All digests</a> &middot; <a href="{PROJECT_PAGE}">The project page</a>'
        ' &middot; <a href="https://peterparker.ca">The rest of the portfolio</a></p>\n'
        "</footer>\n</body>\n</html>\n"
    )


def _project_link() -> str:
    return f'<p class="top-nav"><a href="{PROJECT_PAGE}">Project 14: Department News Digest</a></p>'


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
        f"{quotes}. Model cost US${digest.cost_usd:.4f}."
    )


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


def _story_html(story: DigestStory) -> str:
    anchor = f"story-{story.position}"
    outlets = f" and {story.outlets - 1} more" if story.outlets > 1 else ""
    published = story.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f'<article class="story" id="{anchor}">',
        f'<h2><span class="pos">{story.position}.</span>'
        f'<a href="{escape(story.url)}">{escape(story.headline)}</a></h2>',
        f'<p class="meta">{escape(story.domain)}{escape(outlets)} &middot; {published}</p>',
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
        parts.append(
            f'<li id="{anchor}-{escape(source.sid)}">[{escape(source.sid)}] '
            f"{escape(source.domain)}: "
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


def html_page(digest: Digest, description: str = "") -> str:
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
    points.append(_point(f"US${digest.cost_usd:.2f}", "model cost for this digest"))
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
    if not digest.reranked:
        body.append(
            '<p class="warn">The model re-ranker did not run for this digest '
            f"({escape(digest.rerank_error)}), so it is in pre-filter order and the rubric's "
            "exclusions were not applied.</p>"
        )
    body.append("</header>")
    body.append('<div class="stories">')
    if not digest.stories:
        body.append('<p class="none">No story was chosen today.</p>')
    body.extend(_story_html(story) for story in digest.stories)
    body.append(f'<p class="note">Run {escape(digest.run_id)}.</p>')
    body.append("</div>")
    return _page(title, "\n".join(body))


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


def audience_index(audience_name: str, days: Sequence[str], description: str = "") -> str:
    items = "\n".join(f'<li><a href="{escape(day)}/">{escape(day)}</a></li>' for day in days)
    lead = f'<p class="lead">{escape(description)}</p>' if description else ""
    body = (
        '<header class="hero">'
        '<p class="crumbs"><a href="../">All digests</a></p>'
        '<p class="eyebrow">Archive</p>'
        f"<h1>{escape(audience_name)}</h1>{lead}</header>\n"
        f'<ul class="days">\n{items}\n</ul>'
    )
    return _page(audience_name, body)


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
            f'<div class="card"><h3><a href="{escape(audience_id)}/">{escape(name)}</a></h3>'
            f"<p>{escape(description)}</p>{latest_link}</div>"
        )
    body = (
        '<header class="hero">'
        '<p class="eyebrow">Department News Digest</p>'
        '<h1>The day\'s news for one department, <span class="hl">cited and checked.</span></h1>'
        f'<p class="lead">{escape(INTRO)}</p>'
        '<p class="note">Nothing is sent: each digest is a web page and an email draft file '
        "that its owner may send. The four audiences below are examples, built on public "
        "sources whose terms were read and recorded before anything was fetched.</p>"
        "</header>\n"
        '<h2 class="section-title">Audiences</h2>\n'
        f'<div class="cards">\n{"".join(cards)}\n</div>'
    )
    return _page("Department News Digest", body)
