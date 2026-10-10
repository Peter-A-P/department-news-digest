# Working notes for Claude Code

This repository is the Department News Digest, package `clippings`: a configurable,
multi-source news digest pipeline on Google Cloud Run with clustering, per-audience
ranking, cited summaries with verified quotes, and measured precision and recall. The plan
is in [PLAN.md](PLAN.md).

## Read first

- [README.md](README.md): what this is and the current result tables.
- [PLAN.md](PLAN.md): the design. Do not deviate from it silently; if something in it turns
  out wrong, change the plan in the same commit as the code and say why in the commit
  message.
- `docs/sources.md` once it exists: every source's terms and the date they were read.

## Engineering standard

- Python 3.13. Typed throughout; `mypy --strict` and `ruff` clean in CI.
- Tests that fail meaningfully: the verifier against altered quotes and wrong citations,
  retention, blocked sources, the run lock, and the no-send test.
- `pyproject.toml` with pinned major versions and a comment saying why for each pin.
- Docs ship in the same commit as the change.
- Never commit credentials, API tokens, or anything from `.env`.

## Rules specific to this repository

- **Nothing is ever sent.** No email, chat or notification path exists. No mail client is
  a dependency; a test asserts it. Delivery is a page and a draft file. This mirrors a
  global rule and is not negotiable.
- **Official APIs and published feeds only.** Terms are read and recorded before a source
  is added. No paywall circumvention, no ignoring robots rules. A source that changes its
  terms is dropped, not bent.
- **Article text is kept thirty days and never republished.** Digests show summaries,
  links and quotes of at most twenty-five words. One exception, decided by Peter on
  2026-10-10: the day's Bluesky pick may be shown in full, with its author and a link,
  while it exists and for thirty days; each run removes a deleted pick's words. Reddit
  posts never go beyond the quote, as the access request to Reddit promised.
- **Every quote is verbatim or it is gone.** The verifier is not optional in production.
- **The model never sees the whole pool.** Pre-filter first; the re-ranker gets top
  candidates only.
- **Every model call goes through the 04 gateway** with the `public` data class; cost per
  digest comes from its ledger.
- **Example audiences are not the employer's.** Generic product, public sources only.
- **Every reported number carries a confidence interval**, and recall is labelled as an
  importance-weighted estimate.
- **Plain punctuation** in everything written here: no em-dashes or other typographic
  dashes, straight quotes only.

## What goes in the README

The README opens with the one-liner, the "nothing is sent" line, the results tables and
the honest limitation, before any installation instructions. The report command fills the
tables; do not hand-edit them. Record one approach that was tried and rejected, with the
evidence, once the work has produced it.
