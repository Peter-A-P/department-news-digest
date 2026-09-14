# Department News Digest

One product, configured per department in a few lines, that reads the day's news, public
forums and social feeds, removes the duplicates, ranks what matters to that audience, and
delivers a short digest with every claim cited and every quote verified against its
source. One system in place of dozens of people each doing this by hand, at a few dollars
a month per department, with measured precision and recall instead of a feeling.

**Status: building, week 1 of 3.** Ingestion, storage, deduplication and clustering are
built and tested; no digest has been produced and nothing has been measured. The plan is in
[PLAN.md](PLAN.md): a three-week build on Google Cloud Run, then a measurement month
running daily.

**No source has been fetched yet.** Every source is gated on its terms being read and
recorded in [docs/sources.md](docs/sources.md) with the date. Until a row there says
`allowed`, the fetcher refuses that source and records the refusal. That is a check in the
code, not a note in a document.

**Nothing is sent.** The system publishes a page per audience and writes an email draft
file an owner can send. It has no send path.

## Result

Not yet measured. The build fills these tables.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall, importance-weighted (95% CI) | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|
| _not yet_ | | | | | |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / after repair | Citation coverage | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|
| _not yet_ | | | | | | | |

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
uv run clippings run ai-policy            # fetch, extract and cluster today
uv run clippings label ai-policy --labeller you
uv run clippings retention                # delete items past thirty days
```

`clippings run` fetches nothing until the sources it needs are recorded as allowed. That is
the expected state of a fresh clone: read the terms, put the date in
[docs/sources.md](docs/sources.md), and run it again.

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
