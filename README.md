# Verified Media Briefing

One product, configured per team in a few lines, that reads the day's news and social feeds,
groups every report of an event into one story by meaning, ranks what matters to that
audience, and delivers a short briefing with every claim cited and every quote checked against
its source. One system in place of dozens of people doing this by hand, for a few dollars a
month each, with measured precision and recall.

**Status: built and measured; in its measurement month.** The whole pipeline is built,
tested and running: ingestion, deduplication, clustering, ranking, the model re-ranker,
cited summaries, the verifier with one repair, the page, the Markdown and the email draft,
the read-only service and the Cloud Run deployment. It has run daily on Cloud Run since
2026-10-07 for all four audiences, and the digests are at https://digest.peterparker.ca.
Every number below is filled by `clippings report`: relevance against a hand-labelled week
per audience, with a second labeller's agreement on one, the pipeline's own checks, a timed
reader study, and the cost from the gateway's ledger and the vendors' bills. The
measurement month, 2026-11-09 to 2026-12-08, leaves the daily runs alone and reports uptime
and cost over it. The plan is in [PLAN.md](PLAN.md).

**Every source is gated on its terms.** A source is fetched only when its row in
[docs/sources.md](docs/sources.md) says `allowed` with the date the terms were read; until
then the fetcher refuses it and records the refusal. That is a check in the code, not a
note in a document.

**Nothing is sent.** The system publishes a page per audience and writes an email draft
file an owner can send. It has no send path.

## Result

<!-- report:start -->
Measured over 131 digests from 2026-10-07 to 2026-11-08, by `clippings report` on 2026-11-08. 95% intervals throughout. 33 audience-days hand-labelled: every audience has its labelled week.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.5 (7.4 to 9.4) | CA$0.058 (CA$0.049 to CA$0.066) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | 0.71 (0.59 to 0.82) | 4.7 (3.8 to 5.7) | CA$0.046 (CA$0.037 to CA$0.056) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.8 (9.6 to 10.0) | CA$0.066 (CA$0.063 to CA$0.070) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 2.4 (1.5 to 3.4) | CA$0.025 (CA$0.016 to CA$0.034) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| 94% (84% to 98%) / 85% (58% to 100%), 27 audience-days | 1.17 (1.15 to 1.19) items per story | 98% (97% to 100%), 26 audience-days | 100% (99% to 100%) / 100% (99% to 100%) | 100% (100% to 100%) | 99% (98% to 100%), 111 sentences | 15 h (14 to 15) / 33 h (33 to 37) | 0.9 (0.6 to 1.2) vs 1.9 (1.5 to 2.4), 15 sessions | 94% (81% to 99%), 30 of 32 days since 2026-10-08 |

Cluster purity is the share of articles in a story of several that a labeller judged to belong with the rest; over every news article, stories of one included, it is 100% (99% to 100%).

Faithfulness is the share of sampled digest sentences that say only what the sources they cite say, hand-checked against what the summariser read, weighted by the sentences each day's digest showed. 2 of 111 were judged not supported, listed in [docs/report.md](docs/report.md).

Reader minutes are minutes with the page in view, from 3 readers briefed on a morning either from the digest or from the news items it was made from; from the sources they took 2.1 (1.5 to 3.2) times as long. Of the 43 items readers ticked as worth a briefing when working from the sources, 72% (58% to 84%) were in a story the digest showed.

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08, 2026-10-25). The measurement month runs from 2026-11-09 to 2026-12-08.

Deduplication recall is over the pairs whose words overlap most, where a missed duplicate almost always is; of 54 pairs drawn from outside them as a check, 1 was the same story.

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API.

All four digests together cost CA$0.193 (CA$0.171 to CA$0.216) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Google Cloud billed CA$0.00 from 2026-10-07 to 2026-11-08, CA$0.000 a day; X API billed US$8.01 from 2026-10-12 to 2026-11-08, CA$0.386 a day, read from their own billing pages ([docs/bills.yaml](docs/bills.yaml)). Everything together: CA$0.579 (CA$0.557 to CA$0.602) a day, about CA$18 a month. Details, per source and per day: [docs/report.md](docs/report.md).
<!-- report:end -->

## What this does not do

- It does not send anything. No email, no chat messages, no notifications.
- It does not read paywalled content, republish articles, or use any source outside its
  published terms. A source is dropped rather than bent.
- It is not a reader app. No accounts, bookmarks or feeds; a plain page and a draft file.
- It does not score sentiment or "tone". Nothing here can be checked against truth, so it
  is not produced.
- Recall is an estimate from a random sample with importance weights, and is labelled as
  such.

## Tried and rejected

**Haiku 5.5 at low effort as the re-ranker** (2026-10-10). Haiku 5.5 at its default effort
replaced Haiku 4.5 at about a sixth of the cost per call, with no difference measurable on the
labelled days. At low effort it scored relevant stories lower, and its agreement with the
labels fell by kappa 0.102 (95% interval 0.041 to 0.159), so it was not used:
[docs/models.md](docs/models.md).

**Haiku 5.5 as the summariser** (2026-10-10). At a thirteenth of Sonnet 5.5's cost per story,
it left 7.5% of stories with no summary (2.8 to 13.2) because its answers did not keep the
format, wrote shorter summaries with half the quotes, and added interpretive sentences that
cite a source the verifier cannot hold them to. The saving was about CA$6 a month. Same file.

## How it works

See [PLAN.md](PLAN.md). Per audience, a YAML file names topics, entities, geography,
languages, trusted and blocked sources and length. A daily Cloud Run job fetches RSS and
Atom feeds, GDELT and Bluesky (and, for one post a day, X's paid API),
extracts text where permitted, collapses
near-duplicates and clusters stories with local embeddings, ranks candidates by audience
similarity, entities, source trust and recency, and sends only the top candidates to a
model re-ranker through the portfolio gateway. A summariser writes cited sentences with
marked quotes; a verifier rejects any quote not verbatim in its source and any uncited
sentence, repairing once and dropping otherwise. The digest is rendered as a page and a
draft file, and each audience's archive links a trend view: its own organisations, people,
places and topics counted in two weeks of coverage, a change called only when it is beyond
chance. Precision and recall are measured against a hand-labelled week through the AI
Release Gate's harness, with intervals.

The site's front page explains the same for a visitor, below the audience cards: the
results with a chart, why this exists, the pipeline step by step, how it is measured, what
did not work, the rules it keeps and where it stands. It is in `clippings/assemble/about.py`
and changes with this section. Its numbers are never typed: `clippings report` writes them
to `clippings/assemble/results.json` from the same run as the tables above, and the page
refuses to render without one.

Three architecture diagrams, the system, one morning's run and how the numbers are produced, are in
[docs/architecture.md](docs/architecture.md).

## Running it

Python 3.13 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run clippings audiences-list           # the four example audiences
uv run clippings sources check            # every source against the terms record
uv run clippings sources probe            # fetch each feed once and check it is a feed
uv run clippings run ai                   # today's digest, written to out/site/
uv run clippings serve                    # the pages at http://127.0.0.1:8080/
uv run clippings render                   # re-render stored digests, no fetch, no model
uv run --extra gcs clippings label --labeller you --bucket BUCKET      # labelling page against the run's store; duplicate pairs at /pairs, story checks at /stories, faithfulness at /faithfulness
uv run --extra gcs clippings reader-study --reader 1 --bucket BUCKET  # one reader's five timed sessions, in the browser
uv run clippings report                   # the results tables: README block and docs/report.md
uv run clippings fetch gdelt              # fetch one source for every audience and store it, nothing else
uv run clippings x-pick                   # add the X pick to the latest digests, not rebuilding them
uv run clippings refresh                  # re-publish every stored digest with the current design
uv run clippings retention                # delete items past thirty days (run also does this)
```

`clippings run` makes no model call unless `CLIPPINGS_ALLOW_SPEND=1` is set; without it the
run stops after the free stages and prints what the pre-filter would have chosen. With it,
every call goes through the gateway with this project's caps in
[clippings/config/gateway/caps.yaml](clippings/config/gateway/caps.yaml), and the key is
read from `ANTHROPIC_API_KEY` or a gitignored `.env`.

Deploying to Cloud Run is [deploy/README.md](deploy/README.md).

Optional extras: `uv sync --extra embed` installs bge-small through ONNX for story
clustering, and `--extra gcs` installs the Cloud Storage backend. Without the first, the
pipeline falls back to a hashing backend and every run says which one produced its numbers.

Configuring an audience is [docs/audiences.md](docs/audiences.md). What is stored and for
how long is [docs/data-retention.md](docs/data-retention.md).

## Part of a portfolio

Built alongside ten sequenced projects. Every model call goes through the Compliant AI
Gateway; the evaluation runs on the AI Release Gate's harness; the pipeline patterns come
from Overload. It is the portfolio's Google Cloud example.

## How this was built

Design, methodology, evaluation choices and judgement are Peter Parker's. AI coding
assistants (Claude Code) were used for implementation and drafting, the way a senior
engineer uses them in 2026. Every number in the results tables is reproducible from this
repository with one command, and that reproducibility is the evidence that matters.
