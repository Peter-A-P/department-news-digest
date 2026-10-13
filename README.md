# Department News Digest

One product, configured per department in a few lines, that reads the day's news, forums
and social feeds, removes the duplicates, ranks what matters to that audience, and delivers a
short digest with every claim cited and every quote checked against its source. One system in
place of dozens of people doing this by hand, for a few dollars a month each, with measured
precision and recall.

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
Measured over 23 digests from 2026-10-07 to 2026-10-12, by `clippings report` on 2026-10-13. 95% intervals throughout. 12 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 79% (57% to 100%), 2 days | 100% (70% to 100%) | 3.5 (2.0 to 5.0) | 79% (65% to 79%) | 7.0 (4.0 to 10.0) | _not yet_ | 8.0 (5.6 to 10.0) | CA$0.055 (CA$0.038 to CA$0.069) |
| Municipal affairs, Toronto | 33% (0% to 100%), 2 days | 25% (12% to 25%) | 2.0 on all 2 | 8% (6% to 8%) | 6.5 (4.0 to 9.0) | _not yet_ | 6.2 (3.2 to 9.0) | CA$0.064 (CA$0.033 to CA$0.095) |
| Regional affairs, Newfoundland and Labrador | 85% (75% to 93%), 6 days | 66% (56% to 67%) | 8.8 (7.8 to 9.9) | 45% (42% to 47%) | 18.9 (15.4 to 22.5) | _not yet_ | 10.0 on all 6 | CA$0.077 (CA$0.069 to CA$0.083) |
| Public health in Canada | 100% (33% to 100%), 2 days | 100% (100% to 100%) | 0.5 (0.0 to 1.0) | 67% (67% to 67%) | 1.5 (0.0 to 3.0) | _not yet_ | 5.5 (2.7 to 8.2) | CA$0.054 (CA$0.026 to CA$0.080) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.15 (1.12 to 1.19) items per story | 100% (95% to 100%) / 100% (95% to 100%) | 100% (99% to 100%) | _not yet_ (hand check) | 26 h (22 to 33) / 43 h (43 to 44) | _not yet_ (reader study) | _not yet_ (measurement month) |

Most discussed on Bluesky, judged worth showing: Artificial intelligence _not yet_; Municipal affairs, Toronto 0% (0% to 86%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (14% to 100%); Municipal affairs, Toronto _not yet_; Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.241 (CA$0.173 to CA$0.299) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).
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
uv run clippings label --labeller you     # labelling page in the browser, one page per day
uv run clippings report                   # the results tables: README block and docs/report.md
uv run clippings x-pick                   # add the X pick to the latest digests, not rebuilding them
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
