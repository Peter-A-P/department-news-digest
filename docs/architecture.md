# Architecture

Three figures: the system as a whole, one morning's run, and how each published number is
produced, including the ones that wait for more labelled days. Each names the module that
implements what it shows; [PLAN.md](../PLAN.md) says why, [sources.md](sources.md) records
every source's terms and [report.md](report.md) is the measurement.

## The system

![A daily Cloud Run job fetches only sources whose terms have been read and dated, stores items with watermarks and thirty-day retention, collapses near-duplicates and clusters stories by meaning, ranks them per audience and re-ranks the top with a model, writes cited summaries that a verifier holds to verbatim quotes, and publishes a page per audience; labelling and the report measure precision and recall against a hand-labelled week.](architecture/system.svg)

Cloud Scheduler fires one Cloud Run job each morning (`deploy/`, built by Cloud Build). Inside
it, the source registry (`docs/sources.md`, read by `clippings.sources.probe`) is a gate rather
than a document: a source is fetched only when its row says the terms were read, with a date.
Ingestion (`clippings.ingest`) fetches the official APIs and feeds, extracts text where the
terms permit and normalises it into DuckDB on Cloud Storage with watermarks, a fetch log and
thirty-day retention (`clippings.ingest.store`). Clustering (`clippings.cluster`) collapses
near-duplicates with MinHash and groups reports of one event into one story with local
embeddings; ranking (`clippings.rank`) scores stories per audience from the YAML audience
files (`clippings.config`) by similarity, entities, source trust and recency, and sends only
the top candidates to a model re-ranker through the portfolio gateway (`clippings.gateway`);
summarising (`clippings.summarise`) writes cited sentences with marked quotes and its verifier
rejects any quote not verbatim in its source and any uncited sentence, repairing once and
dropping otherwise. Assembly (`clippings.assemble`) renders a page per audience and a draft
file, and nothing is sent. The read-only pages are served at digest.peterparker.ca
(`clippings.serve`); labelling and the report (`clippings.eval`) measure the digests against a
hand-labelled week.

## One morning's run

![The scheduler fires the job; it fetches under the source gate, stores and normalises, collapses near-duplicates, clusters by meaning, ranks per audience, re-ranks the top candidates and summarises with a model through the gateway, verifies every quote and citation with one repair, and publishes the page and a draft file.](architecture/one-morning.svg)

The job fetches new items since each source's watermark from the sources whose terms are
dated, honouring `robots.txt` (`clippings.sources`, `clippings.ingest.remote`), normalises and
stores them, collapses near-duplicates by MinHash shingles (`clippings.cluster.shingles`) and
clusters the rest by meaning with local embeddings (`clippings.cluster.embed`). For each
audience file it ranks the stories (`clippings.rank.score`, `select`), re-ranks only the top
candidates with Haiku through the gateway (`clippings.rank.rerank`), has Sonnet write cited
sentences with marked quotes (`clippings.summarise`), and verifies each sentence: a quote must
be verbatim in its source and every sentence must be cited, with one repair and then a drop
that is logged as a deletion (`clippings.assemble.deletions`). The most-discussed items on
Bluesky and X go in a separate section that is not counted in precision or recall
(`clippings.rank.spotlight`, `x_pick`). The page per audience, the draft file and the about
page are published (`clippings.assemble.publish`) and served at digest.peterparker.ca.

## How the published numbers are produced

![Precision and recall come from hand-labelled audience-days drawn by a stratified sampler and scored through the release gate's harness; quote and citation checks come from the verifier's own record; cost comes from the gateway ledger; deduplication, faithfulness and reader time wait for their labels and studies.](architecture/measurement.svg)

Precision at K and importance-weighted recall come from a stratified sample per audience-day,
the top 30 plus a random 30 (`clippings.eval.sample`), labelled by hand in the label UI
(`clippings.eval.label_ui`) and scored through the release gate's harness with intervals;
twelve audience-days are labelled so far and the columns fill as the week does. Quotes
verbatim before and after repair and the citation coverage of the first draft come from the
verifier's own record. Stories per day, the collapse rate and the lag to inclusion come from
the store; cost per digest and per day comes from the gateway ledger, converted to Canadian
dollars. Deduplication precision and recall, faithfulness and reader minutes wait for pair
labels, a hand check and a reader study, and the README shows them as not yet rather than
blank. `clippings report` writes the README and [report.md](report.md), never edited by hand.
