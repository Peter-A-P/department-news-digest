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

Nothing raw is committed to the repository. `.gitignore` excludes `*.duckdb`, `data/text/`
and `data/raw/`.

## The thirty days

`clippings.constants.RETENTION_DAYS` is thirty, and `Store.retention()` deletes every item
published before the cutoff along with its extracted text and its audience links. It is
run daily. `tests/test_store.py` fails if an item a day past the window survives, or if its
text survives the item.

Thirty days is not a compromise between usefulness and caution. The digest is daily and
the trend view looks back a week; nothing in the product needs text older than that.

## Why the labels outlive the items

A label copies the item's URL and title rather than pointing at the item row. Retention
deletes the item at thirty days, and the labelled week has to stay publishable after that:
a labelled set is published as item ids, URLs and labels, never as article text.

`tests/test_pipeline.py::test_labelling_a_day_records_labels_that_outlive_the_item` runs
retention over a labelled day and asserts the labels are still there and the items are not.

## What a digest shows

A summary, a link, and quotes of at most twenty-five words
(`clippings.constants.QUOTE_MAX_WORDS`). Never the article. The verifier enforces both the
length and the requirement that a quote appears verbatim in its source.

## Deletion at the source

A Reddit post or Bluesky post deleted by its author is honoured by the retention window:
nothing here is kept longer than thirty days, and a published digest quotes at most
twenty-five words of what was public when it was fetched.

## What never leaves this machine

Embeddings and clustering run on CPU inside the job. The only thing sent to a model
provider is the re-ranking and summarisation of the top candidates, through the 04 gateway
with the data class `public`, because every source is public by construction.
