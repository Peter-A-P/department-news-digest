# Architecture

How the briefing is put together, in three pictures: the whole system, one morning's run, and
how each published number is produced. For the reasoning behind the design, read [PLAN.md](../PLAN.md). Every source's terms are in
[sources.md](sources.md), and the measurement is in [report.md](report.md). The same three
pictures are on the live site at
[digest.peterparker.ca/architecture/](https://digest.peterparker.ca/architecture/).

## The system

![A daily Cloud Run job fetches only sources whose terms have been read and dated, stores items with watermarks and thirty-day retention, collapses near-duplicates and clusters stories by meaning, ranks them per audience and re-ranks the top with a model, writes cited summaries that a verifier holds to verbatim quotes, and publishes a page per audience; labelling and the report measure precision and recall against a hand-labelled week.](architecture/system.svg)

Every morning a scheduled job runs on Google Cloud.

It starts with a gate. The list of sources is enforced in code: a source is fetched only
when its entry says its terms of use were read, and when. The job then fetches from official
feeds and APIs, keeps the article text only where the terms allow, and stores everything in a
small database that remembers what it has already seen and deletes items after thirty days.

Next it sorts the news. Copies of the same article are collapsed, and different reports of the
same event are grouped into one story. Each audience is a short configuration file listing its
topics, organisations, people, places and trusted sources, and stories are ranked against it
by relevance, the sources involved and how recent they are. Only the top candidates go to an AI
model for a second opinion, through the portfolio's gateway, which records and costs every
call.

Then a model writes the summary, and a checker holds it to account. Every sentence must cite
its sources, and every quote must appear word for word in a source it cites. A sentence that
fails gets one chance to be repaired, and is dropped if it still fails.

Finally, a page per audience is published, along with a draft email file. Nothing is ever
sent. The pages are served read-only at digest.peterparker.ca, and a separate labelling tool
and report measure the digests against days labelled by hand.

Where it lives: `deploy/`, `docs/sources.md`, `clippings.sources`, `clippings.ingest`,
`clippings.cluster`, `clippings.rank`, `clippings.config`, `clippings.gateway`,
`clippings.summarise`, `clippings.assemble`, `clippings.serve` and `clippings.eval`.

## One morning's run

![The scheduler fires the job; it fetches under the source gate, stores and normalises, collapses near-duplicates, clusters by meaning, ranks per audience, re-ranks the top candidates and summarises with a model through the gateway, verifies every quote and citation with one repair, and publishes the page and a draft file.](architecture/one-morning.svg)

This is one morning, from the scheduler to the published page.

The job fetches only what is new since the last run, from sources whose terms have been read,
and respects each site's rules for automated readers. It stores and tidies what it fetched,
collapses near-duplicate articles by comparing overlapping runs of words, and groups the rest
into stories by meaning, using a small embedding model that runs on the job itself.

For each audience it ranks the stories, and only the top candidates are re-ranked by a small,
fast Claude model. A larger Claude model then writes cited sentences with marked quotes. Each
sentence is checked: any quote must appear word for word in its source, and every sentence must
cite one. A failure gets one repair, then it is dropped and the drop is recorded.

The day's most-discussed posts on Bluesky and X go in a separate section, which is not counted
when the digest's accuracy is measured. The page for each audience, the draft email and the
about page are then published.

Where it lives: `clippings.sources`, `clippings.ingest.remote`, `clippings.cluster.shingles`,
`clippings.cluster.embed`, `clippings.rank`, `clippings.summarise`,
`clippings.assemble.deletions`, `clippings.rank.spotlight` and `clippings.assemble.publish`.

## How the published numbers are produced

![Precision and recall come from hand-labelled audience-days drawn by a stratified sampler and scored through the release gate's harness; quote and citation checks come from the verifier's own record; cost comes from the gateway ledger; deduplication, cluster purity and faithfulness come from pages labelled by hand; reader time comes from a timed study with three readers; every figure carries a 95% interval.](architecture/measurement.svg)

Every number in the README has a stated source.

How many of the stories shown were worth showing, and how many important stories were caught,
come from days labelled by hand. For each audience and day, a sampler picks the top 30 stories
plus 30 at random, a person labels them in a small labelling tool, and they are scored with the
release gate's method, with intervals. The intervals redraw whole days, because stories from
one morning share a news cycle and are not separate pieces of evidence. Every audience has a
labelled week.

How often quotes were exact before and after repair, and how many first-draft sentences
carried a citation, come from the checker's own record. Stories per day, how often duplicates
were collapsed and how long a story takes to appear come from the database. The cost per digest
and per day comes from the gateway's ledger, converted to Canadian dollars. What the ledger does
not see, the Google Cloud bill and X's pay-per-use charges, is read by hand from each vendor's
billing page into `docs/bills.yaml`, with the period and the day it was read, and added to it.

How well duplicates are detected comes from pairs of articles labelled "same story" or not,
on a second page of the same tool. Each day it asks about pairs the clustering joined, pairs
it kept apart that share many words, and a couple of others as a check. A third page shows
every story made of several articles and asks which articles do not belong, which gives the
share of articles that sit in the right story.

How faithful the summaries are comes from a fourth page. It draws four sentences from each
day's digest over a week per audience, about a hundred and ten in all, and shows each one
beside what the summariser read of the sources it cites, with its quotes and numbers marked.
A person judges whether the sources say everything the sentence says. The checker has
already proved the quotes and numbers; this is the check for a paraphrase that goes further
than its source.

How much time a reader saves comes from a timed study: three readers, each briefed on five
mornings, some from the digest and some from the news items it was made from, the two swapped
between readers. Uptime comes from the store: a day is up when the 09:00 UTC run, or its
automatic retry, published every audience's digest, and down when a person had to step in.

A figure still waiting for its labels, such as the labeller agreement for the three audiences
labelled once, is printed as "not yet" instead of being left blank. One command writes the
README and the report, and neither is edited by hand.

Where it lives: `clippings.eval.sample`, `clippings.eval.pairs`, `clippings.eval.faithfulness`,
`clippings.eval.label_ui`, `clippings.eval.reader_study`, `clippings.eval.uptime`, the gateway
ledger and `clippings report`.
