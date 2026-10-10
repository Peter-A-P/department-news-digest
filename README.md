# Department News Digest

One product, configured per department in a few lines, that reads the day's news, public
forums and social feeds, removes the duplicates, ranks what matters to that audience, and
delivers a short digest with every claim cited and every quote verified against its
source. One system in place of dozens of people each doing this by hand, at a few dollars
a month per department, with measured precision and recall instead of a feeling.

**Status: building.** The whole pipeline is built and tested: ingestion, deduplication,
clustering, ranking, the model re-ranker, cited summaries, the verifier with one repair,
the page, the Markdown and the email draft, the read-only service and the Cloud Run
deployment. It has run daily on Cloud Run since 2026-10-07, for all four audiences, at about
US$0.23 a day in model calls, and the digests are at https://digest.peterparker.ca. The
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
Measured over 15 digests from 2026-10-07 to 2026-10-10, by `clippings report` on 2026-10-10. 95% intervals throughout. 4 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall, importance-weighted (95% CI) | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|
| Artificial intelligence | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 8.7 (6.0 to 10.0) | US$0.047 (US$0.038 to US$0.055) |
| Municipal affairs, Toronto | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 10.0 on all 4 | US$0.074 (US$0.070 to US$0.078) |
| Regional affairs, Newfoundland and Labrador | 82% (70% to 92%), 4 days | 42% (39% to 44%) | 19.8 (14.8 to 24.6) | _not yet_ | 10.0 on all 4 | US$0.060 (US$0.058 to US$0.063) |
| Public health in Canada | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 7.8 (5.8 to 9.5) | US$0.057 (US$0.046 to US$0.068) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.17 (1.14 to 1.22) items per story | 100% (93% to 100%) / 100% (93% to 100%) | 100% (99% to 100%) | _not yet_ (hand check) | 24 h (20 to 30) / 43 h (42 to 44) | _not yet_ (reader study) | _not yet_ (measurement month) |

All four digests together cost US$0.227 (US$0.219 to US$0.235) a day in model calls, from the gateway's ledger. Details, per source and per day: [docs/report.md](docs/report.md).
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

## How it works

See [PLAN.md](PLAN.md). Per audience, a YAML file names topics, entities, geography,
languages, trusted and blocked sources and length. A daily Cloud Run job fetches RSS and
Atom feeds, GDELT, the Reddit API and Bluesky, extracts text where permitted, collapses
near-duplicates and clusters stories with local embeddings, ranks candidates by audience
similarity, entities, source trust and recency, and sends only the top candidates to a
model re-ranker through the portfolio gateway. A summariser writes cited sentences with
marked quotes; a verifier rejects any quote not verbatim in its source and any uncited
sentence, repairing once and dropping otherwise. The digest is rendered as a page and a
draft file. Precision and recall are measured against a hand-labelled week through the AI
Release Gate's harness, with intervals.

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
