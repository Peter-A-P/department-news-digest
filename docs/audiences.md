# Configuring an audience

An audience is one YAML file. Adding a department is adding one of these; there is no
other configuration and no code to change.

The four files in [`clippings/config/examples/`](../clippings/config/examples/) are worked
examples, deliberately generic: artificial intelligence, public health in Canada,
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
| `sources` | no | `feeds`, `sitemaps`, `gdelt`, `reddit`, `bluesky`, `x`. Any subset. `x` takes `query`, in X's own search syntax, and `candidates` (10 to 100, default 10, X's minimum); it is off while `query` is empty, and each candidate is a paid read. Name people in their public roles with `from:` (reporters, officials, researchers), not outlets: an outlet's posts share reports the digest already has, and a post linking to an article in the day's digest is dropped anyway. A topic search returns mostly unliked reposts. During an election, list every candidate or none. A sitemap takes `url`, `publisher`, `terms`, `include` (the news section's path prefix, such as `/news/`) and `extract`, for a publisher that posts news with no feed; new pages are found by the sitemap's dates and kept only if the page's own publication date is new. Bluesky takes `queries`, `sort` (`top` by default) and `people`: handles, without the @, of people in public roles whose own recent posts are read from their public author feed, with no session, as candidates for the day's Bluesky post. A feed takes `url`, `publisher`, `terms`, and `extract` (default true); `extract: false` means the article pages are never requested and the item is summarised from the feed's own title and summary, for a publisher whose terms clear the feed but not the page. |
| `trusted_sources` | no | Bare domains, subdomains included. Ranked up, and preferred when choosing which item represents a story. |
| `blocked_sources` | no | Bare domains, subdomains included. Never stored, never extracted, never shown. |
| `digest` | no | `max_stories`, `rerank_candidates`, `max_sentences_per_story`, `min_rubric_score`. `rerank_candidates` is how many stories the model re-ranker is shown, and so the cost of that call; the model never sees more. `min_rubric_score` (default 1) is the lowest rubric score a story may be shown with: 2 leaves out "marginal" stories, so a quiet day is a shorter digest. |
| `measure_from` | no | The first day whose digest was made under the current rubric, `YYYY-MM-DD`. Labelling and the relevance numbers start there. Set it whenever the rubric changes. |
| `delivery` | no | `time_local` and `timezone`. When the digest is built. Nothing is sent. |

Unknown fields are rejected rather than ignored, at every level of the file. A typo must
not silently change what a department reads.

## The rubric is not decoration

It is what a labeller reads before judging an item, and it is published next to the
precision and recall numbers, so a reader can see what "relevant" meant. A rubric of fewer
than ten words is rejected at load.

Write it as two halves: what counts, and what does not. The second half is the useful one.
For an audience of busy readers, say how important a story must be, not only what it must
be about. The artificial intelligence example was "about AI" until its first labelled day
showed a digest full of small startups' funding rounds and routine model releases; it now
reads:

> ... It excludes routine funding rounds, valuations and launches of small and mid-sized
> startups; routine model releases, fine-tunes, checkpoints, datasets, library updates and
> benchmark posts, including most Hugging Face releases, unless the model sets a clear new
> state of the art or is being widely adopted; customer case studies and vendor marketing;
> ...

## Every source needs a row in the terms record

Each feed carries a `terms` key. That key must appear in
[`sources.md`](sources.md) with a date read and the status `allowed`, or the fetcher
refuses the source and the run records the refusal. `gdelt`, `reddit`, `bluesky` and `x`
are keys in the same record.

    clippings sources check

reports every source in every audience file against the record and exits non-zero if one
is missing or not yet allowed. This is a gate, not a report: the run itself makes the same
check before any request leaves.

## Sources that need credentials

Reddit and Bluesky both need an account of your own, and neither is committed. Reddit reads
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` from a registered application on the free
tier, and `REDDIT_USERNAME`, the account that owns it, for the user agent Reddit's API
rules ask for (`python:clippings:<client id>:0.1 (by /u/<username>)`). Bluesky reads `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD`: an app password, which is
revocable on its own and cannot change the account. Bluesky's search endpoint began
refusing unauthenticated requests with a 403, and an app password is the official way in,
so that is the way this takes.

Posts from either platform are discussion, not reports: one reaches a digest only inside a
story that a feed or GDELT also carries, and a story made only of posts is never shown
(PLAN.md section 2.3).

X reads `X_BEARER_TOKEN`, the app-only bearer token of a developer account on pay-per-use
pricing, and is used for one post a day and nothing else (PLAN.md section 2.3): one search of
`candidates` posts from the people named in `query`, a second of `topic_candidates` posts by
subject when `topics` is set, and one author lookup. Ten posts and the lookup are about
US$0.06 an audience-day; AI's fifty are about US$0.26. Set a monthly spend limit in X's
developer console before the first request; the code also refuses a search once the month's
reads in the fetch log reach US$12 (`clippings.sources.x.MONTHLY_CAP_USD`).

**X is not for an audience that serves a government body.** X's Developer Agreement
(section XIV.C) requires an Enterprise plan before X content is shown to anyone who is, or
acts for, a government body, and requires those users to be named to X. A department's
audience file leaves `sources.x.query` empty unless the department holds that plan. The four
examples here are public pages for anyone, which is why they may have it on.

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
