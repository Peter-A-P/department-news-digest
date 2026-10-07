# Configuring an audience

An audience is one YAML file. Adding a department is adding one of these; there is no
other configuration and no code to change.

The four files in [`clippings/config/examples/`](../clippings/config/examples/) are worked
examples, deliberately generic: AI policy and regulation, public health in Canada,
municipal affairs in Toronto, and regional affairs in Newfoundland and Labrador.

The fourth is there because the other three are national or big-city, and the product's
claim is that a small regional team gets the same system from the same code. It is also the
harder ranking problem: fewer sources, less duplication to collapse, and a pool where
almost everything is local but little of it matters.

## The fields

| Field | Required | What it does |
|---|---|---|
| `id` | yes | Lower-case slug. Must match the file name. |
| `name` | yes | What the digest page is headed. |
| `description` | yes | One sentence. Embedded as part of the audience profile the ranker scores against. |
| `rubric` | yes | What "relevant" means for this audience, in at least ten words. See below. |
| `topics` | yes | Short phrases. Ranking features and part of the profile. |
| `entities` | no | `organisations`, `people`, `places`. Matched in item text; also used to build GDELT queries. |
| `geography` | no | Places this audience is about, as part of the profile. |
| `languages` | no | ISO 639-1 codes, default `["en"]`. Restricts GDELT server-side. |
| `sources` | no | `feeds`, `gdelt`, `reddit`, `bluesky`. Any subset. A feed takes `url`, `publisher`, `terms`, and `extract` (default true); `extract: false` means the article pages are never requested and the item is summarised from the feed's own title and summary, for a publisher whose terms clear the feed but not the page. |
| `trusted_sources` | no | Bare domains, subdomains included. Ranked up, and preferred when choosing which item represents a story. |
| `blocked_sources` | no | Bare domains, subdomains included. Never stored, never extracted, never shown. |
| `digest` | no | `max_stories`, `rerank_candidates`, `max_sentences_per_story`. `rerank_candidates` is how many stories the model re-ranker is shown, and so the cost of that call; the model never sees more. |
| `delivery` | no | `time_local` and `timezone`. When the digest is built. Nothing is sent. |

Unknown fields are rejected rather than ignored, at every level of the file. A typo must
not silently change what a department reads.

## The rubric is not decoration

It is what a labeller reads before judging an item, and it is published next to the
precision and recall numbers, so a reader can see what "relevant" meant. A rubric of fewer
than ten words is rejected at load.

Write it as two halves: what counts, and what does not. The second half is the useful one.
From the AI policy example:

> ... It excludes product launches, funding rounds, model benchmarks, opinion columns
> without new facts, and company announcements that carry no regulatory consequence.

## Every source needs a row in the terms record

Each feed carries a `terms` key. That key must appear in
[`sources.md`](sources.md) with a date read and the status `allowed`, or the fetcher
refuses the source and the run records the refusal. `gdelt`, `reddit` and `bluesky` are
keys in the same record.

    clippings sources check

reports every source in every audience file against the record and exits non-zero if one
is missing or not yet allowed. This is a gate, not a report: the run itself makes the same
check before any request leaves.

## Sources that need credentials

Reddit and Bluesky both need an account of your own, and neither is committed. Reddit reads
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` from a registered application on the free
tier. Bluesky reads `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`: an app password, which is
revocable on its own and cannot change the account. Bluesky's search endpoint began
refusing unauthenticated requests with a 403, and an app password is the official way in,
so that is the way this takes.

Without those variables each source reports itself unavailable and the run carries on with
the rest. That is deliberate: the pipeline runs with any subset of its sources, which is
what makes dropping one cheap.

## Adding an audience

1. Copy an example to `<your-id>.yaml` and edit it.
2. Add a row to `docs/sources.md` for any source not already there, and read its terms.
3. `clippings sources check` confirms every source is recorded and allowed.
4. `clippings sources probe <your-id>` fetches each feed once and confirms it is a feed.
5. `clippings run <your-id>`

Step 4 is not optional politeness. On the first live run, six of the thirteen feeds
originally configured here were wrong: four returned 404 and two returned a 200 with an
HTML page, which the parser reads as a feed with no entries and the run counts as a healthy
source. A feed URL is a guess until something has fetched it.

## What `rerank_candidates` costs

It is the number of items the model sees per day. The pre-filter bounds the day's model
spend by construction: at 60 candidates and about 500 tokens each, re-ranking is roughly
US$0.03 per audience per day. Raising it raises the bill linearly and, on the evidence the
project will publish in week 3, does not raise precision.
