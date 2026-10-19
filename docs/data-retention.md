# What is kept, for how long, and what is published

Article text is kept thirty days and never republished. This document says exactly what
that means in the code, so a reader does not have to take it on trust.

## What is stored

| Table | Holds | Kept |
|---|---|---|
| `items` | The link, title, feed summary, source, author and publication time of every item ingested | Thirty days from publication |
| `item_text` | Article text extracted from the publisher's page, for summarising and for verifying quotes | Thirty days, deleted with its item |
| `clusters` | Which items are the same story, per audience per day | Thirty days, as its items expire |
| `labels`, `pair_labels` | Relevance and duplicate judgements, with the item's URL and title copied in | Indefinitely: these are the measurement |
| `watermarks`, `fetch_log` | How far each source has been read, and what each fetch attempt returned | Indefinitely: uptime and source yield are published numbers |
| `rankings` | The order each run put a day's stories in: cluster ids, pre-filter and re-ranker scores, and the re-ranker's one-line reason | Indefinitely: the labelling sample is drawn from it |
| `digests` | Each published digest as JSON: the verified summary sentences, the publishers' titles and links, the verifier's counts and the cost of each model call | Indefinitely: it is the archive, and holds no article text |

The gateway's ledger (`boundary.sqlite`, beside the database) holds one row per model call:
tokens, cost, model and hashes of the request and response, never their content.

Nothing raw is committed to the repository. `.gitignore` excludes `*.duckdb`, `data/text/`
and `data/raw/`.

## The thirty days

`clippings.constants.RETENTION_DAYS` is thirty, and `Store.retention()` deletes every item
published before the cutoff along with its extracted text and its audience links. It is
run at the end of every `clippings run`, so the daily job keeps the promise without anyone
remembering to. `tests/test_store.py` fails if an item a day past the window survives, or if its
text survives the item.

Thirty days is not a compromise between usefulness and caution. The digest is daily and
the trend view looks back two weeks and shows titles and links only; nothing in the
product needs text older than that.

## Why the labels outlive the items

A label copies the item's URL and title rather than pointing at the item row. Retention
deletes the item at thirty days, and the labelled week has to stay publishable after that:
a labelled set is published as item ids, URLs and labels, never as article text.
A duplicate-pair label copies both items' URLs and titles for the same reason, and records
what the clustering decided, so the deduplication numbers survive the clusters too. A story
check copies the article's URL and title, the story's size and the day's count of articles,
so purity can be recomputed without the clusters. A faithfulness judgement copies the digest
sentence, its story's headline and the URLs of the sources it cites; the article text it was
judged against is deleted at thirty days like any other, which is why the sample has to be
checked before then.

The reader study keeps, per session, a pseudonym (`reader-1`), the audience, the day, which
way the reader was briefed, two times, how many stories or items were shown and, from the
sources, the URLs of the items the reader ticked. No name, no address, nothing typed.

`tests/test_pipeline.py::test_labelling_a_day_records_labels_that_outlive_the_item` runs
retention over a labelled day and asserts the labels are still there and the items are not.

## What a digest shows

A summary, a link, and quotes of at most twenty-five words
(`clippings.constants.QUOTE_MAX_WORDS`). Never the article. The verifier enforces both the
length and the requirement that a quote appears verbatim in a source the sentence cites.
Headlines are the publishers' own titles, linked.

Because a digest holds only those things, it is kept after the items it was built from are
deleted: `tests/test_delivery.py::test_a_digest_outlives_the_items_it_was_built_from`.

A feed marked `extract: false` in its audience file (SaltWire, which is paywalled in part)
never has its article pages requested; its items are summarised from the publisher's own
feed title and summary, and the page says "feed summary only" beside the link.

## Deletion at the source

A Reddit post or Bluesky post deleted by its author is honoured by the retention window:
nothing here is kept longer than thirty days, and a published digest quotes at most
twenty-five words of what was public when it was fetched.

One post a digest may show in full is the day's Bluesky pick, as a post card with its
author's display name and picture, which come from Bluesky's public API and are removed
with the words.
Each run checks the picks of the last thirty days against Bluesky's public API
(`clippings.assemble.deletions`): a post that no longer exists, or whose author's handle no
longer resolves, has its words removed from the stored digest and its page, which then
says it was deleted. After thirty days a pick keeps only its twenty-five-word quote. A
check that fails for any other reason changes nothing and is tried again the next day.

The day's X pick is shown whole, because X's display rules allow nothing less, and for a
day only. X's Developer Policy asks that stored posts be kept current with X, and checking a
post still exists is a paid read, so the next daily run removes the pick's words, its
author's name and picture from every stored copy of that day's digest and from its page,
Markdown and draft file (`clippings.assemble.deletions.expire_x_picks`), whether or not the
post still exists. What is kept is the link, the handle, the counts when it was picked and
why it was picked. The other candidates the model scored are never stored: they are read,
shown to the model through the gateway, and dropped with the run. The removal runs whatever
the terms record says about X, so dropping X later still clears what it left.

## What never leaves this machine

Embeddings and clustering run on CPU inside the job. The only thing sent to a model
provider is the re-ranking of the top candidates (headline, outlet and the first sixty
words of the feed summary) and the summarisation and repair of the chosen stories (up to
four sources each, at most 450 words of article text per source), and the day's Bluesky
and X candidate posts for the picks (at most 400 characters each), through the 04 gateway
with the data class `public`, because every source is public by construction.
`clippings/gateway.py` is the only module that imports the gateway, and a test asserts it.

langgraph carries LangSmith's tracing client, which would send a run's state to a third
party if an environment variable asked it to. `clippings/graph.py` switches tracing off
whatever the environment says, and a test asserts that too.
