"""The front page's long read, below the audiences: the results, why this exists, how it
works, what did not work, and where it stands.

Written in the manner of the portfolio's other project sites (gate.peterparker.ca): the
result first, then the problem, then the pipeline step by step for the technical reader, the
rules it keeps, what was tried and dropped, and what it deliberately does not do. Every
measured number comes from `results.json`, which `clippings report` writes from the same run
as the README's tables; none is typed here, so the page cannot drift from the README. Keep
the prose in step with the README's "How it works" and PLAN.md: if the pipeline changes,
change this in the same commit.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from clippings.constants import QUOTE_MAX_WORDS, RETENTION_DAYS

RESULTS = Path(__file__).parent / "results.json"
REPO = "https://github.com/Peter-A-P/department-news-digest"


def load_results(path: Path = RESULTS) -> dict[str, Any]:
    """The values `clippings report` wrote. Missing is an error, not an empty page."""
    values: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return values


_WHY = """<section class="section" id="why">
<p class="eyebrow">Why this exists</p>
<h2>Someone reads the news before nine, dozens of times over</h2>
<p class="section-lead">In a government with dozens of departments, or a health authority
with dozens of divisions, someone in each one spends the first hour of the day scanning
twenty sites, deciding what the minister or the chief executive needs to know, and writing
it up. They are reading largely the same articles, and nobody can tell whether the job was
done well, because nothing is measured. If yesterday's digest missed the one item that
mattered, that absence is invisible.</p>
<div class="table-wrap"><table class="idea">
<thead><tr><th>What the job requires</th><th>Why it goes wrong by hand</th><th>What this does instead</th></tr></thead>
<tbody>
<tr><td><strong>Knowing what this audience cares about</strong></td><td data-label="By hand">It lives in one person's head, and changes when they leave</td><td data-label="Here">A rubric written in plain words in the audience's file, which the model ranks against and a person labels against</td></tr>
<tr><td><strong>Recognising one story told by twenty outlets</strong></td><td data-label="By hand">Obvious on the front page, tedious everywhere else</td><td data-label="Here">Articles that report the same thing become one story, with every source attached</td></tr>
<tr><td><strong>Quoting accurately under time pressure</strong></td><td data-label="By hand">Copy, paste, trim to fit, and the trim changes the meaning</td><td data-label="Here">Every quote is checked word for word against its source by code that is not a model</td></tr>
<tr class="real"><td><strong>Not missing the item nobody covered loudly</strong></td><td data-label="By hand">You cannot notice what you did not see</td><td data-label="Here">What was left out is sampled at random and judged, so the misses are estimated</td></tr>
<tr class="real"><td><strong>Knowing whether any of this works</strong></td><td data-label="By hand">There is no feedback and no score</td><td data-label="Here">Precision and recall per audience against hand labels, each with an interval</td></tr>
</tbody></table></div>
<p>So this is one product that does the job, configured per department in a single file:
its topics, the organisations, people and places that matter, the sources to trust and to
block, how long the digest should be, and the rubric. Adding a department is adding a file.
The four audiences above are examples on public sources, chosen to differ: a fast-moving
global subject, a big city, a national public health brief and a small province, where
almost everything in the pool is local and little of it matters.</p>
</section>"""

_HOW = """<section class="section" id="how">
<p class="eyebrow">How it works</p>
<h2>How a story gets onto these pages</h2>
<p class="section-lead">For the technical reader. The job runs once a day, early in the
morning Eastern time, and each step exists because the obvious version of it either costs
too much or cannot be checked.</p>
<ol class="steps">
<li><strong>Read the sources</strong>News feeds, publishers' site indexes, the GDELT global
news index, Bluesky search and, for the AI and Newfoundland and Labrador audiences, X's paid API. A source is requested only if its terms of use were read and
dated in the project's record; the code refuses anything else, and a site's robots rules
are obeyed.</li>
<li><strong>Store and clean</strong>Articles go into DuckDB for {retention} days. Readable text is
extracted only where the publisher allows it; otherwise the headline and the feed's own
summary are all that is kept.</li>
<li><strong>Group into stories</strong>Reprints of wire copy share whole sentences under
new headlines, so they are found from the text itself (MinHash). Independent reports of one
event share the subject and little of the wording, so they are joined by meaning, with a small
embedding model run on the job's own processor. A post joins the one article it is closest to,
as commentary.</li>
<li><strong>Score without a model</strong>Every story is scored against the audience: how close
it is to the description, the organisations, people and places it names, how recent it is,
whether a trusted source carries it and how many outlets do. This costs nothing to run.</li>
<li><strong>Ask a model about the top sixty</strong>Only the strongest candidates go to a
small model, which scores each from 0 to 3 against the rubric and is told which outlets
carried it. The model never sees the whole pool, which is why a digest costs cents.</li>
<li><strong>Choose up to ten</strong>Best first, with a penalty for resembling a story already
chosen, so one event cannot fill the page, and a limit on stories from any one publisher.
A story the rubric calls marginal only fills a place nothing better wants, and for some
audiences is left out altogether.</li>
<li><strong>Summarise with citations</strong>A larger model writes each story in a few
sentences. Every sentence names the articles it came from, and any quotation is marked as
one.</li>
<li><strong>Verify, mechanically</strong>Code checks every sentence: it cites, each citation is a
real source of that story, each quote is at most {quote} words and appears word for word in a
source the sentence cites, and so does every number. A failing sentence is rewritten once,
then dropped, and the page counts both.</li>
<li><strong>Publish, never send</strong>A page per audience per day and an email draft file its
owner may send. Each page shows why every story was chosen, what the verifier refused and
what the model calls cost, taken from the spending ledger.</li>
</ol>
<p>Beside the stories, each digest may show one Bluesky post: the day's most discussed post
that the audience's rubric would want, even when no article covers it, from a search and from
a short list of people in public roles the audience would follow. A model scores the
popular candidates against the rubric with rules for posts on top (no jokes, insults or
posts about private individuals), and the page shows the post's own words, its author and a
link. Where X is switched on, a second post is chosen the same way from the day's posts by a
short list of people in public roles, read through X's paid API, leaving out any that only
share an article the digest already has, and shown whole on that day only, as X's rules
ask. Every model call goes through the portfolio's compliant AI gateway, which records it,
prices it and enforces hard daily and monthly spending caps.</p>
<ul class="chips" aria-label="Built with">
<li>Python 3.13, typed, mypy and ruff clean</li><li>LangGraph pipeline</li><li>DuckDB</li>
<li>MinHash near-duplicates</li><li>bge-small embeddings on CPU</li>
<li>Maximal marginal relevance</li><li>Claude Haiku 5.5 re-ranker</li>
<li>Claude Sonnet 5.5 summaries</li><li>Mechanical quote verifier</li>
<li>Cloud Run job and service</li><li>Cloud Storage</li>
<li>Bootstrap and Jeffreys intervals</li><li>Cohen's kappa</li>
</ul>
</section>"""

_MEASURE = """<section class="section" id="measure">
<p class="eyebrow">How it is measured</p>
<h2>A digest that feels relevant is not evidence</h2>
<p class="section-lead">The point of the project is the numbers, not the pages. Each
audience ends with figures measured against stories a person judged by hand, and every one
of them carries a confidence interval, because a figure from a few dozen judgements a day has
real uncertainty and hiding it would be its own kind of dishonesty.</p>
<div class="panels">
<div class="panel"><h3>Precision</h3><p>Of what the digest showed, how much was worth
showing. A person reads every story it ranked highest and judges each against the same
rubric the model was given, without seeing the model's score.</p></div>
<div class="panel"><h3>Recall, estimated</h3><p>Of what was worth knowing, how much it caught.
Judging the whole pool is hundreds of stories a day, so each day the labeller also sees
stories drawn at random from everything ranked lower. Each stands in for many in a known
proportion, which makes the misses estimable rather than guessed, and the figure is always
labelled as an importance-weighted estimate.</p></div>
<div class="panel"><h3>The ten that matter most</h3><p>A busy reader wants the most important
stories, not every relevant one. The labeller marks the day's must-reads, and the report says
how many of those the digest chose, apart from how many merely relevant ones it found.</p></div>
<div class="panel"><h3>The pipeline's own honesty</h3><p>How often quotes were verbatim on the
first draft, how many sentences the verifier refused, how many articles collapse into one
story, how long a story takes to reach a digest, and what each digest cost. These come from
the run's own records, not from a person.</p></div>
</div>
<p class="note">Because "relevant" is a judgement, one audience's week was labelled twice, by
two people who did not see each other's answers. Their agreement on {{kappa_audience}} is
kappa {{kappa}}: well above chance, short of identical. A reader should know how much two
reasonable people disagree before reading how well a machine matched one of them.</p>
</section>"""

_RULES = """<section class="section" id="rules">
<p class="eyebrow">The rules it keeps</p>
<h2>Built so it can say no</h2>
<div class="panels">
<div class="panel"><h3>Nothing is sent</h3><p>No email, chat or notification path exists, by
design. A test reads every import, installed library and command and fails the build if
anything capable of sending appears. Whether a piece of writing goes to a person stays with a
person.</p></div>
<div class="panel"><h3>Terms before fetching</h3><p>Official interfaces and published feeds
only, no paywalls, robots rules obeyed. Every source's terms are read and dated before it is
used, and a source that changes its terms is dropped rather than bent. Each audience's
"Sources checked" lists every source, its date and how its last check went, failures
included.</p></div>
<div class="panel"><h3>Quotes verbatim or gone</h3><p>The verifier is not optional and has no
switch. A quote that is not word for word in a source the sentence cites is rewritten once
and then removed, and the counts are published, so a reader can see how often the model
tried to invent something.</p></div>
<div class="panel"><h3>Short quotes, short memory</h3><p>Article text is kept {retention} days and
never republished: a digest shows summaries, links and quotes of at most {quote} words. The
day's Bluesky pick may be shown in full while it exists; if its author deletes it, the next
run removes its words. The day's X pick is shown whole, as X requires, and only until the
next run.</p></div>
</div>
</section>"""

_STATUS = """<section class="section" id="status">
<p class="eyebrow">Where it stands</p>
<h2>Built, measured, and left alone for a month</h2>
<p class="section-lead">Every number on this page is published with the code that produces it,
so anyone can run the same command and get the same figures. From {{measurement_from}} to
{{measurement_to}} the daily runs are left alone, to show that the briefing turns up every
morning without a person, and what that costs.</p>
<div class="split">
<div class="panel built"><h3>Built and running</h3><ul>
<li>Four example audiences, each with a daily digest since 7 October 2026.</li>
<li>Reading from news feeds, publishers' site indexes, GDELT, Bluesky and, for two audiences,
X, with the terms record enforced in the code.</li>
<li>Duplicate removal and story grouping, the free pre-filter, the model re-ranker against
each rubric, and selection with a diversity penalty.</li>
<li>Cited summaries and the quote verifier, with one repair attempt per failing sentence.</li>
<li>A trend view per audience: the organisations, people, places and topics it follows,
this week against the week before.</li>
<li>Every check above measured by hand: a labelled week per audience, duplicate pairs,
story checks, a faithfulness sample, a second labeller and a timed reader study.</li>
<li>Hard spending caps, the cost of every digest from the gateway's ledger and the vendors'
bills, and uptime counted from the runs themselves.</li>
</ul></div>
<div class="panel tocome"><h3>Still to come</h3><ul>
<li>Uptime and cost over the measurement month, {{measurement_from}} to {{measurement_to}}.</li>
<li>The pre-filter's weights and the diversity penalty tuned against the labels, in place of
the starting values chosen by reasoning.</li>
</ul></div>
</div>
</section>"""

_REJECTED = """<section class="section" id="rejected">
<p class="eyebrow">What did not work</p>
<h2>Six things that were tried and dropped</h2>
<p class="section-lead">Each of these looked sensible until it met the data. The model
comparisons are written up in full in the repository's
<a href="{{repo}}/blob/main/docs/models.md">docs/models.md</a>.</p>
<div class="panels">
<div class="panel"><h3>A cheaper setting for the re-ranker</h3><p>Asking the small model to
think less scored relevant stories lower and agreed less with the hand labels. The default
setting stayed, and still costs about a sixth of the model it replaced.</p></div>
<div class="panel"><h3>A cheaper model for the summaries</h3><p>The small model left some
stories with no summary because it broke the format, used half the quotes and added
interpretation the verifier cannot hold to a source. The saving was a few dollars a month,
so the larger model stayed.</p></div>
<div class="panel"><h3>Posts as stories</h3><p>On the first day Bluesky was switched on,
commentary posts took six of Toronto's ten places. Since then a post reaches a digest only
inside a story that a news source also carries.</p></div>
<div class="panel"><h3>Searching X by topic</h3><p>The ten "most relevant" posts for a topic
were reposted headlines with no likes, and the popular ones were jokes and rants. X is now
read from short lists of named people in public roles.</p></div>
<div class="panel"><h3>Asking GDELT once a day</h3><p>Cloud Run's outgoing addresses are
shared, and GDELT turned most of the morning's queries away, which once left the AI digest
with two stories. It is now asked every three hours, and a paid fixed address was turned
down on cost.</p></div>
<div class="panel"><h3>Reddit</h3><p>Access now needs Reddit's approval. The request went
unanswered for four weeks, so Reddit was dropped. The pipeline runs on whatever sources are
left, which is what makes dropping one cheap.</p></div>
</div>
</section>"""

_BUILT = """<section class="section" id="built">
<p class="eyebrow">How this was built</p>
<h2>Whose decisions these were</h2>
<p class="section-lead">I designed this project and made the calls in it. I chose the four
audiences to differ, so that one product would have
to serve a fast global subject, a big city, a national brief and a small province. I labelled
every relevance week, duplicate pair, story check and faithfulness sentence myself, and asked
a second person to label Toronto's week without seeing my answers. When Bluesky commentary
crowded out the news, I decided posts are not stories. I kept the quote verifier without an
off switch, turned down a fixed outgoing address for GDELT at about US$32 a month, and
dropped Reddit when its access request went unanswered rather than reach it some other
way.</p>
<p>AI coding assistants (Claude Code) were used for implementation and drafting, the way a
senior engineer uses them in 2026. Every number on this page is reproducible from
<a href="{{repo}}">the public repository</a> with one command, and that
reproducibility is the evidence that matters.</p>
</section>"""

_LIMITS = """<section class="section" id="limits">
<p class="eyebrow">Scope</p>
<h2>What it deliberately does not do</h2>
<div class="panels">
<div class="panel"><h3>It is not a reader app</h3><p>No accounts, bookmarks or feed to scroll.
The product is the pipeline and the numbers; the delivery is a plain page. The reading
experience is where projects like this go to die, because it is more fun than measuring
whether the thing works.</p></div>
<div class="panel"><h3>No sentiment or tone scores</h3><p>They are the standard offering in
commercial media monitoring, and they cannot be checked against anything true, which makes
them the opposite of what this project is for.</p></div>
<div class="panel"><h3>No paywalls, no back doors</h3><p>It does not read paywalled articles,
and it reads social platforms only through their official interfaces, on their terms and at
their price. Anything else is out on the terms, not on the budget.</p></div>
<div class="panel"><h3>It never decides to send</h3><p>It writes a draft. A person reads it and
decides whether it goes anywhere, which is where that decision belongs.</p></div>
</div>
</section>"""


_RESULTS = """<section class="section" id="results">
<p class="eyebrow">Does it work?</p>
<h2>Checked against a person's judgement, with the error bars shown</h2>
<p class="section-lead">A digest that feels relevant is not evidence. Over {{labelled_days}}
audience-days, a person judged every story each digest showed and a random sample of the
ones it left out, against the same rubric the model was given. Every figure carries a 95%
interval, because a few dozen judgements a day leave real uncertainty.</p>
{{chart}}
<div class="verdict"><p><strong>The digests are mostly right about what they show, and
miss more than they show.</strong> Depending on the audience, {{precision_range}} of
the stories shown were worth showing, while {{must_recall_range}} of the stories a person
would put first made it in. A ten-story page cannot hold every must-read on a busy day in
Newfoundland and Labrador.</p></div>
<div class="table-wrap"><table class="idea results">
<thead><tr><th>Check</th><th>Result, 95% interval</th><th>What it means</th></tr></thead>
<tbody>
<tr><td><strong>Quotes word for word</strong></td><td data-label="Result">{{quotes}}</td><td data-label="Means">After the verifier: a quote that is not exact is rewritten once, then removed. On the first draft: {{quotes_first}}.</td></tr>
<tr><td><strong>Sentences faithful to their sources</strong></td><td data-label="Result">{{faith}}</td><td data-label="Means">{{faith_n}} sentences read by hand against what the summariser read; {{faith_unsupported}} said something their sources did not.</td></tr>
<tr><td><strong>Duplicates found, precision / recall</strong></td><td data-label="Result">{{dedup}}</td><td data-label="Means">Pairs of articles judged "same story" or not.</td></tr>
<tr><td><strong>Articles in the right story</strong></td><td data-label="Result">{{purity}}</td><td data-label="Means">Every story of several articles checked for one that does not belong.</td></tr>
<tr><td><strong>Minutes to be briefed</strong></td><td data-label="Result">{{reader_digest}} from the digest, {{reader_sources}} from the sources</td><td data-label="Means">{{reader_count}} readers, {{reader_sessions}} timed sessions: from the sources took {{reader_ratio_text}} times as long.</td></tr>
<tr><td><strong>Two labellers agree</strong></td><td data-label="Result">kappa {{kappa}}</td><td data-label="Means">On {{kappa_audience}}'s week, by two people working apart.</td></tr>
<tr><td><strong>Time to reach a digest</strong></td><td data-label="Result">{{lag_p50}}</td><td data-label="Means">Median from publication to the morning's digest.</td></tr>
<tr><td><strong>Turns up unattended</strong></td><td data-label="Result">{{uptime}}</td><td data-label="Means">A day rescued by a run started by hand counts as down.</td></tr>
<tr><td><strong>Cost, all four audiences</strong></td><td data-label="Result">{{cost_day}} a day, about {{cost_month}} a month</td><td data-label="Means">Model calls from the gateway's ledger, plus X and Google Cloud from their own bills.</td></tr>
</tbody></table></div>
<p class="note">What these do not say: relevance rests on one person's labels over one week per
audience, checked against a second labeller on one audience only. Recall is an
importance-weighted estimate from a random sample, not a count. The reader study is three
people on the AI audience. Measured over {{digests}} digests from {{first_day}} to
{{last_day}}; the full tables are in <a href="{{repo}}#result">the README</a>.</p>
</section>"""


def _chart(audiences: list[dict[str, Any]]) -> str:
    """Precision and must-read recall per audience, each a dot on its 95% interval.

    Built from HTML and CSS rather than SVG, so the text stays the page's own size at any
    width and the plot takes the whole column: on a wide screen each audience's name sits to
    the left of its two rows, on a phone above them. Positions are percentages handed to the
    stylesheet as custom properties; colours come from classes, so dark mode works."""

    def pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    ticks = "".join(
        f'<span class="dc-tick{" minor" if tick in (25, 75) else ""}" style="--x:{tick}%">'
        f"{tick}%</span>"
        for tick in (0, 25, 50, 75, 100)
    )
    groups = []
    for audience in audiences:
        rows = []
        for kind, key, label in (
            ("precision", "precision", "Precision"),
            ("recall", "must_recall", "Must-read recall"),
        ):
            triple = audience[key]
            if triple is None:
                continue
            point, lo, hi = triple
            text = audience[f"{key}_text"]
            figure, _, interval = text.partition(" (")
            rows.append(
                f'<div class="dc-row {kind}"><span class="dc-kind">{label}</span>'
                f'<div class="dc-track" style="--lo:{pct(lo)};--hi:{pct(hi)};--p:{pct(point)}">'
                '<span class="dc-ci"></span><span class="dc-dot"></span></div>'
                f'<div class="dc-val"><b>{escape(figure)}</b> '
                f"<span>{escape(interval.rstrip(')'))}</span></div></div>"
            )
        groups.append(
            f'<div class="dc-group"><div class="dc-name">{escape(audience["name"])}'
            f"<span>{audience['days']} labelled days</span></div>{''.join(rows)}</div>"
        )
    return (
        '<figure class="chart-figure">'
        '<div class="dotchart" role="img" aria-label="Precision and must-read recall per '
        'audience, each with its 95% interval">'
        f'<div class="dc-axis"><div class="dc-ticks">{ticks}</div></div>'
        f"{''.join(groups)}</div>"
        '<ul class="legend"><li><span class="sw precision"></span>Precision: of the stories '
        'shown, the share worth showing</li><li><span class="sw recall"></span>Must-read '
        "recall: of the stories a person would put first, the share the digest chose</li>"
        '<li><span class="sw ci"></span>The bar is the 95% interval</li></ul>'
        f"<figcaption>{_reading(audiences)} Public health's bars are long because its digests "
        "are short: on a quiet day there were only one or two stories to judge.</figcaption>"
        "</figure>"
    )


def _reading(audiences: list[dict[str, Any]]) -> str:
    """What to see in the chart, counted from the values rather than written by hand."""
    both = [a for a in audiences if a["precision"] and a["must_recall"]]
    ahead = sum(a["precision"][0] > a["must_recall"][0] for a in both)
    words = ("none", "one", "two", "three", "four", "five", "six")
    count = words[ahead] if ahead < len(words) else str(ahead)
    total = words[len(both)] if len(both) < len(words) else str(len(both))
    if ahead * 2 > len(both):
        return (
            f"Precision is ahead of recall for {count} of the {total} audiences: what the "
            "digests show is mostly right, and what they leave out is the bigger error."
        )
    return f"Precision is ahead of recall for {count} of the {total} audiences."


def _fill(text: str, values: dict[str, Any]) -> str:
    """Replace every {{token}} from `values`, escaped; a token without a value is an error, so
    a missing number stops the build instead of reaching the page."""

    def one(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"about.py: no value for {{{{{key}}}}} in results.json")
        value = values[key]
        return value if key in RAW else escape(str(value))

    return re.sub(r"\{\{(\w+)\}\}", one, text)


# Values that are HTML already, built here rather than taken from results.json.
RAW = frozenset({"chart", "repo"})


def hero_points(values: dict[str, Any]) -> str:
    """Four figures for the first screen, each with what it counts and its comparison."""
    return _fill(
        '<div class="points">'
        '<div class="point"><div class="figure">{{precision_mean}}</div><div class="unit">of '
        "shown stories worth showing, the average of the four audiences ({{precision_range}}), "
        "against a person's labels</div></div>"
        '<div class="point"><div class="figure">{{faith_point}}</div><div class="unit">of '
        "{{faith_n}} sentences checked by hand say only what their sources say</div></div>"
        '<div class="point"><div class="figure">{{reader_ratio}}x</div><div class="unit">as '
        "long to be briefed from the sources as from the digest, in a timed study</div></div>"
        '<div class="point"><div class="figure">{{cost_month}}</div><div class="unit">a month '
        "for all four audiences: models, X and Google Cloud together</div></div>"
        "</div>",
        {**values, "repo": REPO},
    )


def about_sections(values: dict[str, Any] | None = None) -> str:
    """Every section, in reading order, for the front page below the audience cards."""
    values = load_results() if values is None else values
    filled = {**values, "repo": REPO, "chart": _chart(values["audiences"])}
    return "\n".join(
        _fill(part, filled)
        .replace("{retention}", str(RETENTION_DAYS))
        .replace("{quote}", str(QUOTE_MAX_WORDS))
        for part in (_RESULTS, _WHY, _HOW, _MEASURE, _REJECTED, _RULES, _STATUS, _LIMITS, _BUILT)
    )
