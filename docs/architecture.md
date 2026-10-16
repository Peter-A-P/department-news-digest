# Architecture

How the briefing is put together, in three pictures: the whole system, one morning's run, and
how each published number is produced, including the ones that wait for more labelled days.
For the reasoning behind the design, read [PLAN.md](../PLAN.md). Every source's terms are in
[sources.md](sources.md), and the measurement is in [report.md](report.md). The same three
pictures are on the live site at
[digest.peterparker.ca/architecture/](https://digest.peterparker.ca/architecture/).

## The system

![A daily Cloud Run job fetches only sources whose terms have been read and dated, stores items with watermarks and thirty-day retention, collapses near-duplicates and clusters stories by meaning, ranks them per audience and re-ranks the top with a model, writes cited summaries that a verifier holds to verbatim quotes, and publishes a page per audience; labelling and the report measure precision and recall against a hand-labelled week.](architecture/system.svg)

Every morning a scheduled job runs on Google Cloud.

It starts with a gate. The list of sources is not just documentation: a source is fetched only
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

![Precision and recall come from hand-labelled audience-days drawn by a stratified sampler and scored through the release gate's harness; quote and citation checks come from the verifier's own record; cost comes from the gateway ledger; deduplication, faithfulness and reader time wait for their labels and studies.](architecture/measurement.svg)

Every number in the README has a stated source, and some are still waiting for theirs.

How many of the stories shown were worth showing, and how many important stories were caught,
come from days labelled by hand. For each audience and day, a sampler picks the top 30 stories
plus 30 at random, a person labels them in a small labelling tool, and they are scored with the
release gate's method, with intervals. Twelve audience-days are labelled so far, and the
numbers fill in as more are done.

How often quotes were exact before and after repair, and how many first-draft sentences
carried a citation, come from the checker's own record. Stories per day, how often duplicates
were collapsed and how long a story takes to appear come from the database. The cost per digest
and per day comes from the gateway's ledger, converted to Canadian dollars.

Three measures are not done yet: how well duplicates are detected, how faithful the summaries
are, and how much time a reader saves. They wait for labelled pairs, a hand check and a reader
study, and the README says "not yet" rather than leaving them blank. One command writes the
README and the report, and neither is edited by hand.

Where it lives: `clippings.eval.sample`, `clippings.eval.label_ui`, the gateway ledger and
`clippings report`.
