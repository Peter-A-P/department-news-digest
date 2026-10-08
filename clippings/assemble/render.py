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

STYLE = """
:root { --bg: #fbfaf7; --fg: #1d1d1b; --muted: #66645e; --rule: #e2dfd6; --accent: #1f5f8b;
  --warn-bg: #fff4d6; --warn-fg: #6b4a00; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --fg: #ecebe6; --muted: #a3a199; --rule: #34332f; --accent: #7cb7e0;
    --warn-bg: #3a3017; --warn-fg: #f0d58a; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 17px/1.55 Georgia, "Times New Roman", serif; }
main { max-width: 44rem; margin: 0 auto; padding: 2rem 16px 4rem; }
header p, footer, .meta, .sources, .why { font-family: system-ui, -apple-system, sans-serif; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
header p { color: var(--muted); font-size: .9rem; margin: .2rem 0; }
article { border-top: 1px solid var(--rule); padding: 1.25rem 0; }
h2 { font-size: 1.2rem; margin: 0 0 .35rem; line-height: 1.3; }
h2 a { color: var(--fg); text-decoration: none; }
h2 a:hover { text-decoration: underline; }
.meta { color: var(--muted); font-size: .82rem; margin-bottom: .5rem; }
article p { margin: .4rem 0; }
sup a { color: var(--accent); text-decoration: none; font-family: system-ui, sans-serif;
  font-size: .7rem; }
.sources { font-size: .82rem; margin: .5rem 0 0; padding-left: 1.1rem; color: var(--muted); }
.sources a { color: var(--accent); overflow-wrap: anywhere; }
.why { font-size: .75rem; color: var(--muted); }
details { margin-top: .4rem; }
summary { cursor: pointer; color: var(--accent); font-family: system-ui, sans-serif;
  font-size: .82rem; list-style: none; display: inline-block; }
summary::-webkit-details-marker { display: none; }
summary::after { content: " \25BE"; }
details[open] > summary::after { content: " \25B4"; }
details[open] > summary .more, details:not([open]) > summary .less { display: none; }
.none { color: var(--muted); font-style: italic; }
.warn { background: var(--warn-bg); color: var(--warn-fg); padding: .6rem .8rem;
  border-radius: 4px; font-family: system-ui, sans-serif; font-size: .88rem; }
footer { border-top: 1px solid var(--rule); color: var(--muted); font-size: .8rem;
  padding-top: 1rem; margin-top: 1rem; }
footer a, header a, li a { color: var(--accent); }
ul.plain { list-style: none; padding: 0; }
ul.plain li { padding: .3rem 0; border-bottom: 1px solid var(--rule); }
"""

FOOTER = (
    "Nothing is sent: this is a page and a draft file. Summary sentences are written by a "
    "model and every one cites its sources; any quote is checked word for word against a "
    "source it cites and is at most twenty-five words. Headlines are the publishers' own. "
    "Article text is never republished."
)


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{STYLE}</style>\n</head>\n"
        f"<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
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
        f"{quotes}. Model cost US${digest.cost_usd:.4f}."
    )


def _sentence_html(sentence: DigestSentence, story: DigestStory) -> str:
    urls = {source.sid: source.url for source in story.sources}
    marks = "".join(
        f'<sup><a href="{escape(urls.get(cite, f"#story-{story.position}-{cite}"))}">'
        f"[{escape(cite)}]</a></sup>"
        for cite in sentence.cites
    )
    return f"<p>{escape(sentence.text)} {marks}</p>"


def _story_html(story: DigestStory) -> str:
    anchor = f"story-{story.position}"
    outlets = f" and {story.outlets - 1} more" if story.outlets > 1 else ""
    published = story.published_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        f'<article id="{anchor}">',
        f'<h2><a href="{escape(story.url)}">{escape(story.headline)}</a></h2>',
        f'<div class="meta">{escape(story.domain)}{escape(outlets)}, {published}</div>',
    ]
    rest: list[DigestSentence] = []
    if story.sentences:
        lead, rest = list(story.sentences[:LEAD_SENTENCES]), list(story.sentences[LEAD_SENTENCES:])
        parts.extend(_sentence_html(sentence, story) for sentence in lead)
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
        f'<span class="less">{less}</span></summary>'
    )
    parts.extend(_sentence_html(sentence, story) for sentence in rest)
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
    parts.append("</details>")
    parts.append("</article>")
    return "\n".join(parts)


def html_page(digest: Digest) -> str:
    title = f"{digest.audience_name}, {digest.day}"
    body = [
        "<header>",
        f"<h1>{escape(digest.audience_name)}</h1>",
        f'<p>{escape(digest.day)} · <a href="../">archive</a></p>',
        f"<p>{escape(_summary_line(digest))}</p>",
        "</header>",
    ]
    if not digest.reranked:
        body.append(
            '<p class="warn">The model re-ranker did not run for this digest '
            f"({escape(digest.rerank_error)}), so it is in pre-filter order and the rubric's "
            "exclusions were not applied.</p>"
        )
    if not digest.stories:
        body.append('<p class="none">No story was chosen today.</p>')
    body.extend(_story_html(story) for story in digest.stories)
    body.append(f"<footer>{escape(FOOTER)}<br>Run {escape(digest.run_id)}.</footer>")
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


def audience_index(audience_name: str, days: Sequence[str]) -> str:
    items = "\n".join(f'<li><a href="{escape(day)}/">{escape(day)}</a></li>' for day in days)
    body = (
        f"<header><h1>{escape(audience_name)}</h1>"
        '<p><a href="../">all audiences</a></p></header>\n'
        f'<ul class="plain">\n{items}\n</ul>\n<footer>{escape(FOOTER)}</footer>'
    )
    return _page(audience_name, body)


def site_index(audiences: Sequence[tuple[str, str, str | None]]) -> str:
    """The front page: each audience, its name, and its latest day."""
    rows = []
    for audience_id, name, latest in audiences:
        latest_link = (
            f' · <a href="{escape(audience_id)}/{escape(latest)}/">{escape(latest)}</a>'
            if latest
            else ""
        )
        rows.append(f'<li><a href="{escape(audience_id)}/">{escape(name)}</a>{latest_link}</li>')
    body = (
        "<header><h1>Department News Digest</h1>"
        "<p>One configurable digest per audience, with every claim cited and every quote "
        "verified against its source.</p></header>\n"
        f'<ul class="plain">\n{"".join(rows)}\n</ul>\n<footer>{escape(FOOTER)}</footer>'
    )
    return _page("Department News Digest", body)
