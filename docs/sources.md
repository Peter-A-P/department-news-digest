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
| ec.europa.eu | European Commission, Shaping Europe's digital future (RSS) | https://commission.europa.eu/legal-notice_en | - | pending | Commission reuse policy; check the 2011/833/EU decision on reuse |
| nist.gov | NIST news (RSS) | https://www.nist.gov/privacy-policy#copyright | - | pending | US federal work, generally public domain; confirm for images |
| oecd.ai | OECD AI Policy Observatory (RSS) | https://www.oecd.org/en/about/terms-conditions.html | - | pending | Check the attribution requirement |
| priv.gc.ca | Office of the Privacy Commissioner of Canada (RSS) | https://www.priv.gc.ca/en/important-notices/ | - | pending | Government of Canada terms; non-commercial reproduction |
| hai.stanford.edu | Stanford Institute for Human-Centered AI (RSS) | https://www.stanford.edu/site/terms/ | - | pending | University site terms; confirm feed reuse |
| canada.ca | Government of Canada news and Health Canada recalls (Atom, RSS) | https://www.canada.ca/en/transparency/terms.html | - | pending | Non-commercial reproduction permitted with attribution; confirm it covers quoting |
| cihi.ca | Canadian Institute for Health Information (RSS) | https://www.cihi.ca/en/privacy-and-terms-of-use | - | pending | |
| cmaj.ca | Canadian Medical Association Journal (RSS) | https://www.cmaj.ca/site/misc/terms.xhtml | - | pending | Journal content; the feed is abstracts, full text may be restricted |
| cbc.ca | CBC News feeds (RSS) | https://www.cbc.ca/aboutcbc/discover/termsofuse.html | - | pending | Personal and non-commercial use; check the position on automated reading |
| toronto.ca | City of Toronto newsroom (RSS) | https://www.toronto.ca/home/copyright-information/ | - | pending | |
| ttc.ca | Toronto Transit Commission service alerts (RSS) | https://www.ttc.ca/legal | - | pending | |
| citynews.ca | CityNews Toronto (RSS) | https://toronto.citynews.ca/terms-of-use/ | - | pending | Commercial broadcaster; read carefully before allowing |
| news.ontario.ca | Government of Ontario newsroom (RSS) | https://www.ontario.ca/page/terms-use | - | pending | |
| gdelt | GDELT 2.0 document API | https://www.gdeltproject.org/about.html#termsofuse | - | pending | Free and open; rate limits are the constraint. Record the limit observed |
| reddit | Reddit Data API, free tier, registered application | https://www.redditinc.com/policies/data-api-terms | - | pending | Terms have changed repeatedly. Record the version and re-read before the measurement month |
| bluesky | Bluesky public AT Protocol API | https://bsky.social/about/support/tos | - | pending | Public API; respect user deletion through the thirty-day retention |

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
