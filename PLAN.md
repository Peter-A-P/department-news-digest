# Plan: Verified Media Briefing

**Written:** 2026-09-07. **Status:** built and measured, live since 2026-10-07; in its
measurement month, 2026-11-09 to 2026-12-08.

**Build:** three weeks of evenings, not sequenced; the plan is written in relative weeks.
Earliest start: after `boundary` v0.1.0 (Sep 13 2026) and a GCP account with billing
alerts. Followed by one measurement month running daily.
**Package:** `clippings`, after the media-clippings service every department runs by hand.
**Fed by:** 04 (every model call through the gateway; cost per digest from its ledger),
11 (LangGraph pipeline patterns), 03 (the gate runs the precision and recall evaluation
with intervals; its calibrated judge is optional for claim faithfulness once it exists in
February 2027). **Feeds:** 13 reuses the citation and quote verification node.

> **Employer note.** Dozens of departments and divisions each have someone reading the
> media landscape by hand. This is a generic, configurable version built on public sources
> only, with example audiences that are not the employer's. Any internal version is built
> separately on the employer's own tooling, with no shared code in either direction.

> **Nothing is sent.** The system publishes a web page per audience and writes an email
> draft file the owner can send. There is no send path, by design and by the global rule.

---

## 1. What this produces

One product, configured per audience in a few lines (topics, organisations, people,
places, languages, sources to trust and to block, length, delivery time), that reads the
day's news, public forums and social feeds, removes the duplicates, ranks what matters to
that audience, and publishes a short digest with every claim cited and every quote verified
against its source. One system in place of dozens of manual efforts, at a few dollars a
month per audience, with measured relevance instead of a feeling.

The numbers a stranger can check:

| Number | What it shows |
|---|---|
| Digest precision at K and recall per audience against a hand-labelled week, 95% bootstrap CIs; recall estimated on a stratified sample with importance weights | Whether the digest contains what matters and misses little |
| Labeller agreement (Cohen's kappa) on one audience with two labellers | How subjective "relevant" is for that audience |
| Deduplication: pairwise precision and recall on a labelled sample of item pairs, cluster purity, and the collapse rate (items ingested against stories shown) | Whether the same story from twenty outlets appears once |
| Quote verification: quotes found verbatim in their source after normalisation, out of all quotes produced, before and after the repair step | No invented quotes; the number says how often the model tried |
| Citation coverage and claim faithfulness: share of digest sentences with a citation, and, on a 100-sentence sample, share supported by the cited item (hand-checked; the 03 judge once calibrated) | The digest says only what its sources say |
| Reader time: minutes to read the digest against minutes to scan the sources for the same day, small study, with CI | The time claim |
| Timeliness: median and p90 lag from source publication to digest inclusion | Whether "the day's news" is the day's |
| Source yield per source: items that reached a digest and items labelled relevant, per item ingested | Which sources earned their place and which added noise |
| Cost per digest per audience from the gateway ledger and the cloud bill | A few dollars a month, shown |
| Uptime of the daily run over the measurement month | It runs without a person |

## 2. Design decisions

### 2.1 Configuration is the product

An audience is a YAML file: topics as short phrases, named entities (organisations,
people, places), geography, languages, trusted and blocked sources, digest length, and
delivery time. Everything downstream reads from it. Four example audiences ship,
deliberately not the employer's: artificial intelligence; public health in Canada;
municipal affairs in one large city; and regional affairs in Newfoundland and Labrador.
Adding a department is adding a file.

The first was "AI policy and regulation" until 2026-10-07. On its first deployed day it kept
one story of 27, because its feeds were government newsrooms where AI is a rare subject and
the rubric rightly excluded the rest. It is now artificial intelligence broadly, read from
technology desks' AI sections and the labs' own blogs, with a rubric that requires AI to be
the item's primary subject rather than a mention. Regulation stays inside it as one topic.

The fourth was added on 2026-09-13, after the first live run, because the three original
audiences are all national or big-city and the product's claim is that a small regional
team gets the same system. A regional audience is where a hand-made digest is most common
and worst served, and it is the harder ranking problem: fewer sources, less duplication to
collapse, and a pool where most items are local but few matter. It is a regional newsroom's
brief, not any department's, and the provincial government's own newsroom feed is
deliberately not one of its sources, for the reason recorded in `docs/sources.md`.

### 2.2 Official APIs and published feeds only; terms recorded before use

RSS and Atom feeds and news APIs; GDELT's document API for global coverage; Bluesky
through the public AT Protocol API. Reddit was planned through a registered application on
its free tier, but since November 2025 that needs Reddit's approval; the request of
2026-10-09 had no answer after four weeks, so Reddit was dropped on 2026-11-07 (Peter). X
only through its official API: out at plan time because no tier fitted the budget, and in
from 2026-10-10 for one post a day on pay-per-use pricing (section 2.3). No
scraping around paywalls or robots rules. Article text is
extracted only from pages that allow it, kept for thirty days for processing, and never
republished: the digest shows a summary, a link, and quotes of at most twenty-five words.
The exceptions are the day's Bluesky pick (section 2.3), shown in full while it exists, and
the day's X pick, shown whole on its day only.
Each source's terms are recorded in `docs/sources.md` with the date read, and a source is
dropped rather than bent.

A publisher that posts news with no feed but publishes a sitemap is read through the
sitemap (added 2026-10-08 for Anthropic, which has no RSS): the sitemap is a machine-readable
index the site publishes for crawlers, its dates choose which pages to look at, and each
page's own metadata gives the title, the description and the publication date. Nothing is
read from a page that the publisher does not put in its metadata for machines.

### 2.3 Cluster before ranking, rank before the model

Near-duplicates collapse by MinHash on shingles; stories cluster by local sentence
embeddings (bge-small on CPU) with a threshold and connected components. Ranking is
hybrid: embedding similarity to the audience profile, entity matches, source trust,
recency. Only the top candidates per day go to a model re-ranker with the audience's
rubric, through the gateway. The model never sees the whole day's pool; that is what
keeps a digest at cents. The LLM-over-everything alternative is a Rule C candidate.

A day is what is new since the last digest (Peter, 2026-10-12). The pool reaches back
forty-eight hours so that today's report joins the story it continues, but a story is a
candidate only if at least one of its news items was first fetched after the previous
digest was built, and a story that gained a new report is headed by that report. Before
this, 69 of the 130 stories shown from 2026-10-08 to 2026-10-12 were stories the previous
day's digest could already have shown. Stories left out this way are not ranked, so they are
not sampled for labelling either: a story the reader saw yesterday is not today's to miss.

Posts are not stories (decided by Peter, 2026-10-08). A Bluesky post reaches a digest
only inside a story that a feed or GDELT also carries, where it counts towards
corroboration and can be cited beside the report; a story made only of posts is not a
candidate, and a story is always headed by a news item. On the first day Bluesky was on,
commentary posts ("Lmfao former Liberal MPP...") took six of Toronto's ten slots, because
they were on topic and the rubric had no reason to exclude them. Measured on that day's
pools, posts join a news story rarely (one to three stories per audience), so their main
effect now is corroboration, and the cost of the re-ranker falls with the smaller pool.

Posts do not chain (2026-10-09). News items alone form a story's connected component; a post
joins the single story whose news item it is closest to, and only if it clears the story
threshold against that news item directly. Chaining through posts had built a twenty-item
story on 2026-10-08 out of OpenAI's mathematics announcement and posts about AI regulation,
one of which was listed as a source; against the announcement itself those posts scored 0.57
to 0.71. The same threshold now also leaves out three on-topic posts that scored 0.78 to 0.81
against it, which is a recall cost the labelled week will measure.

Importance is judged from breadth of coverage as well as subject (2026-10-10). Labelling the
first AI day showed specialist feeds report hundreds of small stories (a startup's round, a
routine model release) that a busy reader does not want. The re-ranker is now shown, for
each candidate, which outlets reported it and how many posts discuss it, and an audience's
rubric may ask it to weigh that: the AI rubric does, and its feeds now include general news
desks (CBC technology and business), which carry AI only when it is big. An audience can also
set `min_rubric_score` so that marginal stories are left out rather than used to fill the
digest, and `measure_from` so that relevance is measured only on days made under the
current rubric.

One Bluesky post a day may appear outside the stories (2026-10-10): the most discussed post
that joined no news story, has at least ten likes, and is scored relevant by the model
against the rubric, with rules for posts on top (no jokes, attacks, private individuals,
link-only posts or promotion). It sits below the stories as "Most discussed on Bluesky",
marked as a post: its own words cut to twenty-five, its counts and a link, and nothing the
model writes except the reason it was picked. It never takes a story's slot, is not counted
in precision or recall, and is labelled on its own ("worth showing?"). Replies and accounts
with no display name are no longer ingested from Bluesky at all.

The pick's whole post is shown (Peter, 2026-10-10; Bluesky caps a post at 300 characters),
since 2026-10-13 as a post card like the X pick's: the author's picture, display name and
handle above the text, Bluesky's mark, the time linking to the post and the counts. The
name and picture come from Bluesky's free public API when the post is picked, are cleared
with the words, and are filled in for older picks by the daily check below.

The Bluesky pick also reads named people since 2026-10-13, as the X pick does: each audience
lists people in public roles (reporters, columnists, researchers, physicians; no politicians
where only some parties could be listed, and no candidates during an election), and their own
recent posts are read from Bluesky's free public author feeds. They enter the pool like any
post: one about a story joins it as commentary, and one that joins no story competes for the
pick with the search results, most engaged first. The model is now shown the sixteen most
engaged rather than eight, because a person's most liked post of the day is often off topic.
For Newfoundland and Labrador and public health, where X is off, this is where the people
those audiences follow are. A post is its author's to delete, so each run checks the picks of the last
thirty days against Bluesky's public API and removes the words of any post that no longer
exists, and after thirty days a pick keeps only its twenty-five-word quote.

One X post a day may appear beside it (Peter, 2026-10-10). It was added while the Reddit access
request was unanswered, and stays now that Reddit is dropped. X's API has been pay-per-use
since February 2026, US$0.005 a post read and US$0.010 a user read, so X is read for the pick
and nothing else: one search a day for the audience's query, ten candidates (X's minimum) by
X's own relevance order from the last day, the same rubric scoring with the rules for posts,
and one author lookup for the post picked, about US$0.06 an audience-day. A monthly cap in the
code (US$10) stops the search before a request, behind the spend limit set in X's console.
X's terms decide the rest ([docs/sources.md](docs/sources.md)). A post shown outside X must be
whole and unaltered, beside its author's name, handle and picture, a timestamp linking to it,
the X logo and the reply, repost and like actions, so the pick is shown that way and X posts
never join a story, where they could only be quoted. Stored posts must be kept current with X,
and checking each one is a paid read, so the next daily run removes the pick's words, name and
picture from every stored copy and its page, whether or not the post still exists; the
candidates not picked are never stored. And X requires an Enterprise plan before its content is
shown to anyone acting for a government body, so X is on for the public example audiences
only, and is not part of what is offered to departments.

The first pick, on 2026-10-12, found nothing for any audience, and the reason changed the
design (2026-10-13). A topic search's ten "most relevant" posts were reposted headlines with
no likes, and the few popular ones were jokes and political rants the rubric rightly refused.
Searching the outlets instead would only repeat their own reports, which the digest has from
their feeds. So an audience's X query names people in their public roles (for AI, lab leaders,
researchers and policy people; for Toronto, city hall reporters and columnists, and no
candidates before the 2026-10-26 election), and a post that links to an article already in
the day's digest is dropped before the model sees it. X is off for public health in Canada:
much of the health and science community moved to Bluesky, which carries that discussion.
For Newfoundland and Labrador most voices left X too (the City of St. John's closed its
accounts in April 2025), but the Premier and the PC party are on X and not on Bluesky, while
the Liberal and NDP leaders are on Bluesky and not on X. So the two lists are balanced
together (Peter, 2026-10-13): X reads the Premier and the three parties' accounts, Bluesky the
Liberal and NDP leaders, and each party is read once.

Fifteen people and ten posts were too narrow for AI: on 2026-10-15 none of the ten was worth
showing and the section was empty. Peter chose fifty posts a day for AI (2026-10-15): thirty
from a wider list of people (twenty-five, now with the four largest labs' own accounts and two
journalists), and twenty from a second search by subject (`topics`), for the day's popular
posts from people nobody listed. Posts under the likes floor are still never shown to the
model, which is what keeps the subject search's reposted headlines out. Every post the model
scores, Bluesky and X, is written to the run log with its link, likes, score and reason, so a
day with no pick can be checked rather than guessed at.

An audience may show more than one post of each kind (`post_picks`, Peter, 2026-10-15): AI
shows two from Bluesky and two from X, because fifty X posts a day hold more than one worth
showing. The picks are the most engaged posts scored at least 2, one per author, and each X
pick costs its own author lookup. A day with posts opens with two buttons, "News" and
"Social media posts", each with its count, and the posts sit together under their own
heading after the stories.

### 2.4 Every sentence cites, every quote is verbatim, and a verifier enforces it

The summariser writes each digest sentence with the item ids it draws on and marks quotes
explicitly. A verifier checks that every cited id exists in the cluster, that every quote
appears verbatim in its source after whitespace and punctuation normalisation, and that
every sentence has at least one citation. A sentence that fails is repaired once (rewritten
with the failure named) and dropped if it fails again. Counts before and after repair are
published, so the reader can see how often the model invented a quote.

Two refinements made while building it (2026-10-02). A quote must appear in a source the
sentence *cites*, not merely somewhere in the cluster: a real quote attributed to the wrong
outlet is a wrong citation. And every number in a sentence must appear in a source it cites,
the check project 13 found most useful, because a fluent summary still writes 30 where the
source says 60. The headline is never the model's: a story is headed by its representative
item's own title, so the only words no publisher wrote are the checked summary sentences.

### 2.5 A daily job, stateless compute, one small database

A Cloud Run job per day, triggered by Cloud Scheduler, runs the LangGraph pipeline for all
audiences; a Cloud Run service serves the digest pages, the archive and the trend view
read-only. State is one DuckDB file per environment synchronised to a Cloud Storage bucket
with a run lock, holding items, clusters, scores, digests and the ledger export.
Everything fits the free tiers at this volume. This is the portfolio's GCP example and the
cheapest way to run a daily pipeline that a department could copy.

GDELT is also fetched on its own every three hours (decided by Peter, 2026-10-26). It counts
requests per address, and Cloud Run's outbound addresses are shared with everyone else on
Google Cloud: from 2026-10-07 to 2026-10-26 it answered about a quarter of the scheduled
run's queries, and none on 2026-10-26, which left the AI digest two stories on a quiet
Sunday. `clippings fetch gdelt` stores what is new for every audience and nothing else, at
half past the hour on hours that miss 09:00, so each query has eight chances a day and the
morning run finds the items in its pool. AI's two queries became one, a request saved; the
other audiences' pairs cannot be joined under GDELT's one level of parentheses. A fixed
outbound address through Cloud NAT would likely end the refusals, at about US$32 a month,
more than this project's whole running estimate, so it was not taken.

The trend view (built 2026-10-18) is a page per audience beside its archive: the
organisations, people, places and topics in the audience's own file, counted in the news
articles its sources published in the week to the latest digest and the week before, with
the newest articles behind each term, titles and links only. A name counts when the title or
feed summary carries it whole; a topic when two thirds of its content words appear, since no
headline contains "transit service and expansion". A term is said to have risen or fallen
only when an exact binomial test (5%) finds its share of the two weeks' coverage moved by more
than the change in all coverage explains; on the first page that is four AI terms of 15, and
no Toronto, Newfoundland and Labrador or public health term, when the raw counts moved for
nearly all of them. It is rebuilt at the end of every run, needs no model call, and looks back
fourteen days, inside the thirty for which items are kept.

### 2.6 Measured on the harness, labelled the honest way

Labelling every ingested item for a week is thousands of labels per audience and not a
hobby. Instead, per audience per day, the labeller sees every story the system ranked in its
top thirty plus a random sample of thirty from the rest; precision comes from the top,
recall from the random sample with importance weights, both with bootstrap intervals
through the 03 gate's eval spec. One audience is labelled by two people for kappa.

The unit is a news story, shown by the item the digest would link to (2026-10-10). Labelling
items put reprints of one story and posts, which are never candidates, in front of the
labeller: on 2026-10-08 the AI pool was 133 items, 100 of them posts, in 33 news stories.
Labelling is a local page, one screen per audience and day, in a shuffled order that hides
the system's rank and stratum; a story starts as not relevant, or at the labeller's answer
from an earlier day, and saving the day records an answer for every story shown. Labels go to
a file per labeller in the bucket, which the daily job never writes. Measured on the first
four days: 676 story judgements across the four audiences, about 400 of them new.

A digest has ten slots, so the recall that matters is whether it picked the most important
stories, not whether it showed every relevant one (Peter, 2026-10-10, after his first labelled
days found 12 to 22 relevant stories a day). The labeller marks every relevant story and
stars as "must read" the ones they would put in a ten-story digest first; the headline recall
is over must-read stories, with the same importance weights, and recall over all relevant
stories is reported beside it with the relevant stories per day that bound it.

Duplicate pairs are labelled the same way, on a second page of the labelling tool, decided
2026-10-17 when the pair sampler was built. A day's pool of a hundred news items holds about
five thousand pairs, nearly all of them plainly two stories, so a uniform sample would almost
never meet a duplicate the clustering missed. Each audience-day is sampled in three strata:
five pairs the clustering put together (precision), six it kept apart from among the day's
top three pairs per item by word overlap (where a missed duplicate almost always is; over 43
audience-days that top held 843 of the 846 pairs the clustering joined), and two from all
the rest. Recall is estimated within the overlapping pairs, with weights, and says so; the
two "check" pairs a day are reported on their own as a test of that boundary rather than
weighted in, where one chance match among thousands would decide the number. About 13 pairs
per audience-day, a few minutes each, and intervals that redraw whole days, as for relevance,
then the pairs within each drawn day; a stratum is redrawn at a Jeffreys rate only when no
labelled day holds the other answer (2026-10-25: redrawing every day at its own Jeffreys
rate, when 22 of 27 days found no missed duplicate, printed recall 85% with an interval of
40% to 84%).

Cluster purity comes from a third page (decided by Peter, 2026-10-17): every story the
clustering made of several news items, its articles shuffled, and the labeller marks any that
do not belong with the rest. An article alone in its story is in the right one by
construction, so only joined stories are asked about: 5 to 8 stories and 11 to 21 articles an
audience-day in the week to 2026-10-17, about an hour over the labelled week. It is reported
over the articles of joined stories, where a merge error can be, with the figure over every
news article beside it. It complements pair precision, which samples five joined pairs a day
and weights a large story by its pairs: purity checks every article of every joined story, so
one badly chained story is neither missed nor allowed to swamp the number.

Both pages ask about each audience's labelled week only, its first seven days from
`measure_from` (decided by Peter, 2026-10-20). Listing every day since had grown to 511 pairs
and 259 stories, and kept growing; the week is 337 pairs and 161 stories.

Claim faithfulness comes from a fourth page (built 2026-10-18). The verifier already proves
every quote verbatim and every number present in a cited source; what it cannot check is a
paraphrase that says more than its source, so that is what a person is asked. Four sentences
are drawn from each audience-day's digest over the first seven digest days with a sentence
from `measure_from`, about 110 in all, the plan's hundred with room for a short day. A day
whose digest was empty (public health had three in its labelled week) has nothing to check,
and the next day stands in for it. Each sentence is shown beside what the summariser read of
the sources it cites, the title, the feed summary and the start of the article, with its
quotes and numbers marked, and is judged supported, not supported, or "can't tell" when what
was read is gone; every sentence needs an answer, because a default would count an unread
sentence as supported. "Can't tell" is reported apart and never counted as supported. The
share is weighted by each day's shown sentences, its interval redraws whole days, and the
sentences judged not supported are listed in the report. The article text is deleted at
thirty days, so the sample has to be checked before then: early November for the first days.

Reader time comes from a timed study (built 2026-10-18), three readers and five days as
section 5 sets. A reader is briefed on one audience's morning, for a meeting on what that
audience needs to know, either from the digest or from the news items it was made from,
listed newest first as a feed reader would, reprints included; from the sources they also
tick the items they would brief on, which keeps the scan honest and says how many of a
person's own picks the digest showed. The conditions alternate by day and are swapped
between readers, so every day is read both ways and no reader sees a day twice. The clock is
time with the page in view, kept in the reader's browser, with time from start to done kept
beside it. The days are the audience's first five digest days with a story from
`measure_from` (AI by default: 2026-10-11 to 10-15), and their items are deleted thirty days
after publication, so the study runs before about 2026-11-10. Readers are pseudonyms,
`reader-1` to `reader-3`; the README reports mean minutes per condition and how many times as
long the sources took, with intervals that resample sessions within each condition.

Uptime is counted from the store, not from Cloud Run's console, so a stranger with the
database gets the same number (decided 2026-10-18). A day is up when the run Cloud Scheduler
started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest;
a day rescued by a run started by hand is down, because the claim is that it runs without a
person. A run's id carries its start time, and a retry now marks itself `-retry<n>`, so the
two are told apart without the console. Counted from 2026-10-08, the first morning the
schedule fired; checked against Cloud Run's execution list on 2026-10-18, it finds the one
day that was down (2026-10-08, out of memory, rerun by hand). It is reported from that day
until the measurement month has a start date, and then over the month: 2026-11-09 to
2026-12-08 (Peter, 2026-11-08), set in `clippings/constants.py`.

### 2.7 Out of scope, on purpose

- A reader app: bookmarks, accounts, notifications, mobile layout. The product is the
  pipeline and its numbers; delivery is a plain page and a draft file.
- Sending anything. No email, no chat messages, no notifications.
- Sentiment analysis and "media tone" scores. Unmeasurable against truth here.
- Paywalled content, full-text republication, X without the official API.
- Real-time alerts. Daily, with the lag measured.

## 3. Data

| Source | Volume | What it gives | Access and terms |
|---|---|---|---|
| RSS and Atom feeds from news outlets, government newsrooms, journals | Hundreds of items per day across four audiences | The core news stream | Publisher terms and robots rules respected; text kept thirty days; recorded per feed |
| GDELT document API | Queried per audience daily | Global coverage of the audience's entities | Free, open; rate limits respected |
| Bluesky public API (AT Protocol) | Search and feeds per audience | Public discussion | Public API; user preferences respected |
| X API v2, pay-per-use | One search of ten posts and one author lookup per audience per day; for AI, thirty posts from named people and twenty by subject | The day's X pick only | Official API, terms read and recorded; shown whole on its day only; not for government users without an Enterprise plan |
| Hand-labelled week | About 420 labels per audience, 60 per day; one audience double-labelled | Precision, recall, kappa | Own |
| Labelled duplicate pairs | About 13 pairs per audience-day in three strata, about 360 over the labelled week (section 2.6) | Deduplication precision and recall | Own |
| Story checks | Every article of every story of several news articles, about 15 an audience-day (section 2.6) | Cluster purity | Own |

Nothing raw is committed. The labelled sets are published as item ids, URLs and labels,
never as article text.

## 4. Architecture

```
clippings/
  config/      audience.py (pydantic schema), examples/ (ai.yaml, public-health-canada.yaml,
               municipal-<city>.yaml), load.py
  sources/     base.py (Source protocol: fetch since watermark, record terms), rss.py, gdelt.py,
               bluesky.py, x.py (the X pick's search and author lookup), robots.py
  ingest/      normalise.py (canonical URL, language), extract.py (trafilatura where permitted),
               store.py (DuckDB on Cloud Storage, watermarks, thirty-day retention, run lock)
  cluster/     shingles.py (MinHash near-duplicates), embed.py (bge-small, CPU), cluster.py, metrics.py
  rank/        features.py (audience similarity, entities, trust, recency), score.py,
               rerank.py (top candidates to the gateway with the audience rubric), select.py (K with diversity),
               spotlight.py and x_pick.py (the day's Bluesky and X posts)
  summarise/   prompt.py (cited sentences, marked quotes), cite.py, verify.py (ids exist, quotes verbatim,
               every sentence cited), repair.py (one rewrite, then drop)
  assemble/    digest.py (sections, length budget), render.py (HTML page, Markdown, .eml draft file),
               trends.py (weekly entity and topic deltas with the items behind them)
  gateway.py   the only module that imports the gateway: aliases per purpose, data class `public`,
               the spend switch, and a scripted client for the tests
  graph.py     LangGraph: ingest -> rank -> rerank -> select -> summarise -> verify (-> repair -> verify)
               -> assemble -> publish, with a stop after rank when no model may be called;
               no send node exists
  eval/        sample.py (top-30 plus random-30 per day), labels.py (labelling CLI), precision_recall.py
               (importance-weighted recall, bootstrap CIs), dedup_eval.py, quotes_eval.py, faithfulness.py
               (hand-check tool; 03 judge adapter), reader_study.py, source_yield.py, timeliness.py,
               gate/ (03 eval spec and item loader)
  serve/       Cloud Run service: digest per audience, archive, trend page, read-only (stdlib WSGI
               over the bucket's site prefix; GET and HEAD only)
  cli.py       clippings run | label | eval | report | render | serve
deploy/        Dockerfile; Cloud Run job and service; Cloud Scheduler; Cloud Storage bucket; budget alerts;
               custom domain digest.peterparker.ca
docs/          sources.md (terms per source, date read), audiences.md, data-retention.md
```

### Tests that matter

The verifier rejects a quote altered by one word, a citation to an id outside the
cluster, and an uncited sentence; the repair step runs at most once; retention deletes
items older than thirty days and their extracted text; a blocked source never reaches the
store; the .eml render produces a draft file and no code path opens a network connection
to a mail server (asserted by a test that scans the dependency graph for SMTP clients);
the audience schema rejects an unknown field; the run lock prevents a second job from
writing.

## 5. Week by week

| Week | Built | Done when |
|---|---|---|
| 1 | Source adapters with terms recorded; normalise, extract, store on DuckDB with Cloud Storage sync; near-duplicate and story clustering; the four audience configs; gateway aliases; labelling CLI; first local end-to-end run on one audience | A day's pool for one audience clustered locally; `docs/sources.md` complete |
| 2 | Hybrid ranking and gateway re-ranker; cited summariser, verifier, repair; assembly and rendering (page, Markdown, .eml draft); LangGraph graph; Cloud Run job, service and scheduler deployed; daily runs begin for all four audiences; labelling week starts as days arrive | Four digests published daily at digest.peterparker.ca; labels accumulating |
| 3 | Evaluation: precision, recall and kappa through the gate; deduplication pairs; quote and faithfulness checks; source yield; timeliness; cost per digest; reader study (three readers, five days); trend view; Rule C write-up; README; `v0.1.0` | Every table in section 1 filled except uptime; repository public |
| Measurement month, 2026-11-09 to 2026-12-08 | Daily runs unattended; uptime, cost and timeliness collected; a second labelled week on one audience if drift in relevance is suspected | Uptime and monthly cost added to the README |

First to drop if behind: the trend view; Bluesky (RSS and GDELT stay); the reader
study to two readers. The four audiences, the labelled week with intervals,
deduplication, quote verification, cost per digest and the terms record are not droppable.

## 6. Cost

Prices as of 2026-09-07 (Anthropic list per million tokens: Haiku 4.5 at $1 in and $5 out,
Sonnet 5 at $2 in and $10 out). Embeddings and clustering run on CPU inside the job.
Summaries route to Sonnet 5.5 since 2026-10-02: newer, and the same $2 and $10 in the
gateway's 2026-10-01 price list, so no line below moves. The re-ranker is shown about 150
tokens per candidate (headline, outlet, sixty words of feed summary) rather than the 500
assumed here, so its line is an upper bound. Re-ranking moved to Haiku 5.5 on 2026-10-10
(US$0.10 in and US$0.50 out in the gateway's 2026-10-08 price list) after it was measured
against Haiku 4.5 on every labelled day and found no different within the intervals, at about
a sixth of the cost per call; at low effort it agreed less with the labels and was rejected
([docs/models.md](docs/models.md)).

| Item | Basis | US$ | CA$ |
|---|---|---:|---:|
| Re-ranking | 60 candidates per audience per day; Haiku 5.5 since 2026-10-10 (Haiku 4.5, about US$0.013 measured, before) | 0.002 per audience-day | |
| Summaries | About 10 stories per digest at about 3,000 tokens in and 400 out; Sonnet 5 | 0.10 per audience-day | |
| Running cost, four audiences | About US$0.10 per audience-day, 30 days | 12 per month | 16 per month |
| X API, since 2026-10-12 | Post reads per day: fifty for AI since 2026-10-15, ten for Newfoundland and Labrador, and ten for Toronto until 2026-11-09; one user read per audience per day; at list price; capped at US$12 a month in code | 11.40 per month | 15.40 per month |
| Cloud Run job and service, Scheduler, Storage | Within free tiers at this volume; egress a few GB | 0 to 3 per month | 0 to 4 per month |
| Build month | Development reruns, the labelled week rerun under five configurations, faithfulness sample | 40 | 54 |
| **Build** | | **40** | **54** |
| **Running** | | **23 to 26 per month** | **31 to 35 per month** |

Still under the CA$40 per month first estimated, with less room than before:
the fourth audience added on 2026-09-13 costs about a third more to run, and X adds about
CA$15. The difference is
a small model for
re-ranking and the pre-filter that keeps the model away from the full pool. Measured on
2026-11-08: about CA$18 a month for all four audiences, models and X together, with Google
Cloud inside its free tier (README).

## 7. Handover

`clippings` v0.1.0 at the end of week 3. 13 (Grounded Email Response Drafting) reuses the
verification node: cited sentences, verbatim quotes, repair-once-then-drop. The audience
schema is the pattern for any per-team configuration in the portfolio. A department that
wants its own instance copies three files and a Cloud Run deployment.

## 8. Risks

| Risk | Handling |
|---|---|
| Source terms change (Reddit and X have, repeatedly) | Terms recorded with dates; a source is dropped, not bent; the pipeline runs with any subset of sources. Reddit was dropped on 2026-11-07, when its access request went unanswered |
| It becomes a reader app | Out of scope by decision; delivery is a plain page and a draft file |
| Relevance labels are subjective | Two labellers on one audience, kappa published; the rubric per audience is in the config, so a reader can see what "relevant" meant |
| The model invents quotes | The verifier rejects any quote not verbatim in the source; the before-and-after counts are published |
| Recall is hard to measure | Importance-weighted estimate from the random sample, with intervals; the method is stated, and the estimate is labelled as such |
| Cloud Run cold starts or job failures | Daily job with retries; uptime is a published number; alerts on failure to the owner's console only |
| Cost drift as sources grow | Gateway caps per project; the pre-filter bounds model calls per day by construction |
| Anything gets sent | No send node, no mail client dependency, a test that asserts it; the global rule stands |
| Perception at work | Generic product, example audiences not the employer's, two toolchains with nothing crossing |

## 9. Rule C candidates

1. **Model-only ranking over the whole pool.** Send every ingested item to the re-ranker for
   one week on one audience. Expected: cost per digest an order of magnitude higher for
   precision within the interval of the hybrid pre-filter.
2. **Deduplication by URL and title only.** Expected: the same story from many outlets
   appears several times per digest; the labelled pairs give the missed-duplicate rate.
3. **Summaries without the verifier.** Run the summariser with verification off for a week.
   Expected: a measurable share of quotes not verbatim in any source and citations to the
   wrong item. That share is the reason the verifier exists.

Whichever produces the clearest evidence becomes `docs/rejected.md`.

## 10. Definition of done

- [x] Four example audiences configured and running daily on Cloud Run with Cloud Scheduler
- [x] Hand-labelled week per audience; precision at K and importance-weighted recall with CIs through the 03 gate; kappa on one audience
- [x] Deduplication precision and recall on labelled pairs; collapse rate reported
- [x] Every quote in a published digest verified verbatim against its source; before-and-after repair counts published
- [x] Citation coverage and faithfulness on a 100-sentence sample
- [x] Reader time with and without the digest, with CI
- [x] Timeliness and source yield reported
- [x] Cost per digest per audience from the gateway ledger and the cloud bill
- [x] Source terms recorded for every source used, with dates
- [x] No send path; the test that asserts it passes
- [ ] Uptime over the measurement month (2026-11-09 to 2026-12-08)
- [x] Digest pages live at digest.peterparker.ca
- [x] README opens with the one-liner and the results table
- [x] One rejected approach documented with evidence (Rule C)
- [ ] Repository public, `v0.1.0` tagged

## 11. Deferred

| Deferred | Kept so the door stays open |
|---|---|
| French-language audiences and bilingual digests | Language is already an audience field; the embeddings are multilingual; the rubric prompt is parameterised |
| Claim faithfulness with the 03 calibrated judge on every digest | The hand-checked sample from `eval/faithfulness.py` keeps each sentence, its sources' links and the verdict: the calibration set such a judge needs. The adapter is written when the judge is calibrated and the cost is accepted |
| Per-reader personalisation | Audiences are the unit; a reader is a smaller audience, one more file |
| Alerts on breaking stories | The pipeline is a graph; an hourly trigger on a subset of sources is a scheduler change |
| Learning from reader feedback on relevance | Digest pages could collect a thumbs signal into the labels table; the evaluation would then have a second, ongoing label source |
