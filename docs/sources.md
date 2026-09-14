# Sources and their terms

Every source this project reads is listed here with the terms that permit it and the date
those terms were read. PLAN.md section 2.2: official APIs and published feeds only, no
scraping around paywalls or robots rules, and a source whose terms change is dropped
rather than bent.

**This table is not documentation of a decision made elsewhere. It is the gate.**
`clippings.sources.terms.TermsGate` reads this file, and an adapter refuses to send a
request for any source whose row does not say `allowed` with a date. A source added to an
audience file without a row here fails the run rather than fetching quietly.

## How to record a source

1. Open the source's terms of use, robots.txt, and any API terms or developer agreement.
2. Read them against what this project does: fetch the feed or API on a schedule, keep the
   extracted text for thirty days, publish a summary with a link and quotes of at most
   twenty-five words, never republish the article.
3. Set **status** to `allowed` if they permit that, `dropped` if they do not.
4. Put the date you read them in **date read**, as YYYY-MM-DD. A row cannot be `allowed`
   without one.
5. Re-read the terms of any source before the measurement month and update the date.

Then `clippings sources check` confirms every source in every audience file has a row.

## Status values

| Status | Meaning |
|---|---|
| `allowed` | Terms read on the date given; they permit this use. The adapter may fetch. |
| `pending` | Not read yet. The adapter refuses. This is the default for a new row. |
| `dropped` | Read, and they do not permit this use, or they changed. Never fetched again; the reason goes in notes. |

## The record

| Key | Source | Terms | Date read | Status | Notes |
|---|---|---|---|---|---|
| ec.europa.eu | European Commission, Shaping Europe's digital future (RSS) | https://commission.europa.eu/legal-notice_en | 2026-09-13 | allowed | Commission reuse policy; check the 2011/833/EU decision on reuse |
| nist.gov | NIST news (RSS) | https://www.nist.gov/privacy-policy#copyright | 2026-09-13 | allowed | US federal work, generally public domain; confirm for images |
| oecd.ai | OECD AI Policy Observatory (RSS) | https://www.oecd.org/en/about/terms-conditions.html | 2026-09-13 | allowed | Check the attribution requirement |
| priv.gc.ca | Office of the Privacy Commissioner of Canada (RSS) | https://www.priv.gc.ca/en/important-notices/ | 2026-09-13 | allowed | Government of Canada terms; non-commercial reproduction |
| hai.stanford.edu | Stanford Institute for Human-Centered AI (RSS) | https://www.stanford.edu/site/terms/ | 2026-09-13 | allowed | University site terms; confirm feed reuse |
| canada.ca | Government of Canada news and Health Canada recalls (Atom, RSS) | https://www.canada.ca/en/transparency/terms.html | 2026-09-13 | allowed | Non-commercial reproduction permitted with attribution; confirm it covers quoting |
| cihi.ca | Canadian Institute for Health Information (RSS) | https://www.cihi.ca/en/privacy-and-terms-of-use | 2026-09-13 | allowed | |
| cmaj.ca | Canadian Medical Association Journal (RSS) | https://www.cmaj.ca/site/misc/terms.xhtml | 2026-09-13 | allowed | Journal content; the feed is abstracts, full text may be restricted |
| cbc.ca | CBC News feeds (RSS) | https://www.cbc.ca/aboutcbc/discover/termsofuse.html | 2026-09-13 | allowed | Personal and non-commercial use; check the position on automated reading |
| toronto.ca | City of Toronto newsroom (RSS) | https://www.toronto.ca/home/copyright-information/ | 2026-09-13 | allowed | |
| ttc.ca | Toronto Transit Commission service alerts (RSS) | https://www.ttc.ca/legal | 2026-09-13 | dropped | Terms read and fine, but the feed returns 403 to an identified non-browser client (probed 2026-09-13). Treated as a refusal of automated access rather than worked around |
| citynews.ca | CityNews Toronto (RSS) | https://toronto.citynews.ca/terms-of-use/ | 2026-09-13 | allowed | Commercial broadcaster; read carefully before allowing |
| news.ontario.ca | Government of Ontario newsroom (RSS) | https://www.ontario.ca/page/terms-use | 2026-09-13 | allowed | |
| gdelt | GDELT 2.0 document API | https://www.gdeltproject.org/about.html#termsofuse | 2026-09-13 | allowed | **Limit observed 2026-09-13**: 429 with "please limit requests to one every 5 seconds". The adapter now waits six seconds between requests and reports a 429 rather than retrying. It was still rate limited at that interval on the day, so the real limit may be lower over a longer window; watch the fetch log across a full day before widening any audience's query list. GDELT is also slow to answer, 10 to 12 seconds for a bare request, and has its own timeout in the adapter. |
| reddit | Reddit Data API, free tier, registered application | https://www.redditinc.com/policies/data-api-terms | 2026-09-13 | allowed | Terms have changed repeatedly. Record the version and re-read before the measurement month |
| bluesky | Bluesky public AT Protocol API | https://bsky.social/about/support/tos | 2026-09-13 | allowed | Public API; respect user deletion through the thirty-day retention |
| vocm.com | VOCM News, St. John's (RSS) | https://vocm.com/terms-of-use/ | - | pending | Commercial broadcaster; read before allowing |
| ntv.ca | NTV News, St. John's (RSS) | https://ntv.ca/privacy-policy/ | - | pending | Commercial broadcaster; find the terms page, it may only have a privacy policy |
| theindependent.ca | The Independent, St. John's (RSS) | https://theindependent.ca/about/ | - | pending | Reader-funded independent outlet; check whether the feed is full text and quote accordingly |
| saltwire.com | SaltWire Network, incl. The Telegram (RSS) | https://www.saltwire.com/terms-of-service | - | pending | Paywalled in part. Extraction must be refused where the article is behind the wall; the feed summary and a link may still be usable |
| gazette.mun.ca | Memorial University Gazette (RSS) | https://www.mun.ca/main/legal/ | - | pending | University publication |

## Recorded, but not currently in any audience file

Terms were read for these, but the feed itself does not work. They keep their row so the
reading is not lost and so nobody guesses the same URL again. Probed 2026-09-13 with
`clippings sources probe`.

| Key | What happened | What would bring it back |
|---|---|---|
| oecd.ai | Every RSS path tried returns 404. The OECD AI Policy Observatory appears not to publish a feed any more | A feed URL that returns entries, or GDELT covering it instead |
| priv.gc.ca | The news feed returns 404 and the newsroom page is HTML only | A working feed from the Office of the Privacy Commissioner |
| hai.stanford.edu | Returns a 200 with an HTML page, not a feed | A real feed URL |
| cihi.ca | Every path tried returns 404 | A working feed from CIHI |
| news.ontario.ca | Returns a 200 with a 1.5 KB HTML page; the Ontario newsroom feed paths have changed | A feed URL that returns entries |
| ttc.ca | Returns 403 to an identified, non-browser client. Treated as a refusal of automated access and marked `dropped` below rather than worked around | Nothing. A 403 to an honest client is an answer |
| cbc.ca | Every CBC feed, including the national one, times out on read from this machine, with or without a user agent header. Not a 403 and not a wrong URL, so the cause is unclear | Retry from another network. CBC's Newfoundland and Labrador feed would be the strongest single source for that audience, so this is worth chasing |

## The provincial government's own releases

`https://www.gov.nl.ca/releases/feed/` works and would be the highest-value source in the
Newfoundland and Labrador audience. It is deliberately not used.

The reason is not the terms, which are public and permissive. It is that this repository is
public and its author works for that government, and the portfolio keeps a visible
separation between work built here and work built there. The same call was made in project
07, where the real-record test uses published federal releases only and the employer's own
disclosure log is excluded. Including the employer's newsroom in an example audience would
make the separation something a reader has to take on trust rather than something they can
see. The audience is built from independent outlets instead, which is also the more honest
test of the ranking.

## Sources considered and not used

| Source | Why not |
|---|---|
| X (Twitter) | Official API only, and no tier fits the budget at plan time (PLAN.md section 2.2). Scraping it breaks the terms, so it is out rather than bent. The `Source` protocol leaves the door open. |
| Any paywalled outlet | Extraction would mean circumventing the paywall. Out by rule, not by cost. |
| Google News and aggregator scrapes | Redistribution of others' content without the publishers' terms being readable per item. |

## Retention and republication

Article text is kept thirty days for processing and never republished; see
[data-retention.md](data-retention.md). A digest shows a summary, a link, and quotes of at
most twenty-five words, enforced in code by `clippings.constants.QUOTE_MAX_WORDS` and the
verifier.
