"""The front page's long read, below the audiences: why this exists, how it works, where it is.

Written in the manner of the portfolio's other project sites (gate.peterparker.ca): the
problem first, then the pipeline step by step for the technical reader, then the rules it
keeps, what is built and what is to come, and what it deliberately does not do. It states
no measured result. The numbers belong in the README, filled by the report command with
their intervals, and a figure copied here by hand would go stale the day the next label
lands. Keep it in step with the README's "How it works" and PLAN.md: if the pipeline
changes, change this in the same commit.
"""

from __future__ import annotations

from clippings.constants import QUOTE_MAX_WORDS, RETENTION_DAYS

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
news index, Bluesky search and, for the AI and Toronto audiences, X's paid API. A source is requested only if its terms of use were read and
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
<p class="note">One audience will be labelled twice, by two people, and their agreement
published as kappa, because "relevant" is a judgement and a reader should know how much two
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
<h2>Running every day, still being measured</h2>
<p class="section-lead">This is a working build, not a finished product. The digests above
are real and produced every morning; the measurement that says how good they are is under way,
and its results will be published with the code that produces them, so anyone can run the
same command and get the same numbers.</p>
<div class="split">
<div class="panel built"><h3>Built and running</h3><ul>
<li>Four example audiences, each with a daily digest since 7 October 2026.</li>
<li>Reading from news feeds, publishers' site indexes, GDELT, Bluesky and, for two audiences,
X, with the terms record enforced in the code.</li>
<li>Duplicate removal and story grouping, the free pre-filter, the model re-ranker against
each rubric, and selection with a diversity penalty.</li>
<li>Cited summaries and the quote verifier, with one repair attempt per failing sentence.</li>
<li>The day's Bluesky pick, shown in full while it exists, and the day's X pick, shown whole
on its day only.</li>
<li>A trend view per audience: the organisations, people, places and topics it follows,
this week against the week before.</li>
<li>A labelled week for all four audiences, and precision and recall published with
intervals in the README.</li>
<li>Duplicate grouping judged pair by pair over the labelled week, every story of several
articles checked for articles that do not belong, and a sample of summary sentences read
against their sources for faithfulness, each with its numbers in the README.</li>
<li>A timed study with three readers: minutes to be briefed from the digest against from
the sources.</li>
<li>Labelling pages built for speed, a day on one screen and a key per judgement, and the
report that turns labels into the results tables with intervals.</li>
<li>Hard spending caps, the cost of every digest from the gateway's ledger, and the uptime
of the scheduled run counted from the runs themselves.</li>
</ul></div>
<div class="panel tocome"><h3>Still to come</h3><ul>
<li>A second labeller's agreement on one audience, which says how subjective "relevant" is.</li>
<li>The pre-filter's weights and the diversity penalty tuned against the labels, in place of
the starting values chosen by reasoning.</li>
<li>The repository made public, with the results table at the top of its README.</li>
</ul></div>
</div>
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


def about_sections() -> str:
    """Every section, in reading order, for the front page below the audience cards."""
    return "\n".join(
        part.replace("{retention}", str(RETENTION_DAYS)).replace("{quote}", str(QUOTE_MAX_WORDS))
        for part in (_WHY, _HOW, _MEASURE, _RULES, _STATUS, _LIMITS)
    )
