# Verified Media Briefing

One product, configured per team in a few lines, that reads the day's news and social feeds,
groups every report of an event into one story by meaning, ranks what matters to that
audience, and delivers a short briefing with every claim cited and every quote checked against
its source. One system in place of dozens of people doing this by hand, for a few dollars a
month each, with measured precision and recall.

**Status: building.** The whole pipeline is built and tested: ingestion, deduplication,
clustering, ranking, the model re-ranker, cited summaries, the verifier with one repair,
the page, the Markdown and the email draft, the read-only service and the Cloud Run
deployment. It has run daily on Cloud Run since 2026-10-07, for all four audiences, at about
CA$0.31 (US$0.23) a day in model calls, and the digests are at https://digest.peterparker.ca. The
pipeline's own properties are measured below by `clippings report`; relevance waits on the
hand-labelled week.
The plan is in [PLAN.md](PLAN.md): a build on Google Cloud Run, then a measurement month
running daily.

**Every source is gated on its terms.** A source is fetched only when its row in
[docs/sources.md](docs/sources.md) says `allowed` with the date the terms were read; until
then the fetcher refuses it and records the refusal. That is a check in the code, not a
note in a document.

**Nothing is sent.** The system publishes a page per audience and writes an email draft
file an owner can send. It has no send path.

## Result

<!-- report:start -->
Measured over 47 digests from 2026-10-07 to 2026-10-18, by `clippings report` on 2026-10-19. 95% intervals throughout. 29 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 68% (53% to 84%), 7 days | 83% (57% to 100%) | 3.4 (2.4 to 4.6) | 58% (48% to 72%) | 9.3 (5.7 to 13.6) | _not yet_ | 8.4 (6.9 to 9.6) | CA$0.062 (CA$0.048 to CA$0.074) |
| Municipal affairs, Toronto | 71% (62% to 88%), 6 days | 57% (38% to 86%) | 3.2 (1.7 to 5.0) | 50% (38% to 70%) | 5.7 (3.2 to 8.7) | _not yet_ | 5.1 (3.3 to 7.0) | CA$0.051 (CA$0.033 to CA$0.071) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.9 (9.8 to 10.0) | CA$0.069 (CA$0.063 to CA$0.075) |
| Public health in Canada | 100% (55% to 100%), 7 days | 60% (11% to 88%) | 1.4 (0.9 to 2.1) | 45% (22% to 62%) | 2.9 (1.6 to 4.1) | _not yet_ | 3.3 (1.5 to 5.5) | CA$0.034 (CA$0.016 to CA$0.054) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.16 (1.14 to 1.19) items per story | _not yet_ (story checks) | 100% (97% to 100%) / 100% (97% to 100%) | 100% (100% to 100%) | _not yet_ (hand check) | 17 h (15 to 18) / 42 h (40 to 43) | _not yet_ (reader study) | 91% (64% to 99%), 10 of 11 days since 2026-10-08 |

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08).

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (66% to 100%); Municipal affairs, Toronto 67% (33% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (46% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (76% to 100%); Municipal affairs, Toronto 100% (55% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.210 (CA$0.169 to CA$0.250) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).
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
Atom feeds, GDELT, the Reddit API and Bluesky (and, for one post a day, X's paid API),
extracts text where permitted, collapses
near-duplicates and clusters stories with local embeddings, ranks candidates by audience
similarity, entities, source trust and recency, and sends only the top candidates to a
model re-ranker through the portfolio gateway. A summariser writes cited sentences with
marked quotes; a verifier rejects any quote not verbatim in its source and any uncited
sentence, repairing once and dropping otherwise. The digest is rendered as a page and a
draft file. Precision and recall are measured against a hand-labelled week through the AI
Release Gate's harness, with intervals.

The site's front page explains the same for a visitor, below the audience cards: why this
exists, the pipeline step by step, how it is measured, the rules it keeps, what is built and
what is to come. It is in `clippings/assemble/about.py`, states no measured result (those
are here, with their intervals), and changes with this section.

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
uv run clippings label --labeller you     # labelling page in the browser, one page per day; duplicate pairs at /pairs, story checks at /stories, faithfulness at /faithfulness
uv run clippings reader-study --reader 1  # one reader's five timed sessions, in the browser
uv run clippings report                   # the results tables: README block and docs/report.md
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
