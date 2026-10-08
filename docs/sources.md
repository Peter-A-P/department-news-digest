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

Steps 3 and 4 in one command, which changes that row and nothing else:

    clippings sources record techcrunch.com openai.com --read-on 2026-10-07 --note "Read by Peter"
    clippings sources record some.example --status dropped --note "Bans AI processing"

Prefer it to a find-and-replace of `pending`, which also rewrites the legend below and leaves
the date empty, and a row `allowed` without a date stops every source in the run.

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
| cbc.ca | CBC News feeds (RSS): Newfoundland and Labrador, Toronto, health | https://www.cbc.ca/aboutcbc/discover/termsofuse.html | 2026-09-13 | allowed | Personal and non-commercial use; check the position on automated reading. robots.txt permits the feed paths and names no rule for this project. Its edge refuses any user agent containing a URL, which is why ours no longer carries one; see the section below |
| toronto.ca | City of Toronto newsroom (RSS) | https://www.toronto.ca/home/copyright-information/ | 2026-09-13 | allowed | |
| ttc.ca | Toronto Transit Commission service alerts (RSS) | https://www.ttc.ca/legal | 2026-09-13 | dropped | Terms read and fine, but the feed returns 403 to an identified non-browser client (probed 2026-09-13). Treated as a refusal of automated access rather than worked around |
| citynews.ca | CityNews Toronto (RSS) | https://toronto.citynews.ca/terms-of-use/ | 2026-09-13 | allowed | Commercial broadcaster; read carefully before allowing |
| news.ontario.ca | Government of Ontario newsroom (RSS) | https://www.ontario.ca/page/terms-use | 2026-09-13 | allowed | |
| gdelt | GDELT 2.0 document API | https://www.gdeltproject.org/about.html#termsofuse | 2026-09-13 | allowed | **Limit observed 2026-09-13**: 429 with "please limit requests to one every 5 seconds". The adapter now waits six seconds between requests and reports a 429 rather than retrying. It was still rate limited at that interval on the day, so the real limit may be lower over a longer window; watch the fetch log across a full day before widening any audience's query list. GDELT is also slow to answer, 10 to 12 seconds for a bare request, and has its own timeout in the adapter. |
| reddit | Reddit Data API, free tier, registered application | https://www.redditinc.com/policies/data-api-terms | 2026-09-13 | allowed | Terms have changed repeatedly. Record the version and re-read before the measurement month |
| bluesky | Bluesky public AT Protocol API | https://bsky.social/about/support/tos | 2026-09-13 | allowed | Public API; respect user deletion through the thirty-day retention |
| vocm.com | VOCM News, St. John's (RSS) | https://vocm.com/terms-of-use/ | 2026-10-02 | dropped | Terms read by Peter 2026-10-02 and fine, but every path on the site, the feed and robots.txt's own sitemap included, returns 403 to a non-browser client, identified or not (probed 2026-10-02). Treated as a refusal of automated access, the same call as ttc.ca |
| ntv.ca | NTV News, St. John's (RSS) | https://ntv.ca/privacy-policy/ | 2026-10-02 | allowed | Commercial broadcaster; the site publishes a privacy policy rather than separate terms of use. Read by Peter 2026-10-02 and cleared for this use |
| theindependent.ca | The Independent, St. John's (RSS) | https://theindependent.ca/about/ | 2026-10-02 | allowed | Reader-funded independent outlet. Read by Peter 2026-10-02 and cleared for this use |
| saltwire.com | SaltWire Network, incl. The Telegram (RSS) | https://www.saltwire.com/terms-of-service | 2026-10-02 | allowed | Paywalled in part. Cleared by Peter 2026-10-02 for the feed only: the feed is set `extract: false` in the audience file, so the digest uses the publisher's own feed title and summary and a link, and no article page is ever requested |
| gazette.mun.ca | Memorial University Gazette (RSS) | https://www.mun.ca/main/legal/ | 2026-10-02 | allowed | University publication. Read by Peter 2026-10-02 and cleared for this use |
| techcrunch.com | TechCrunch, AI section (RSS) | https://techcrunch.com/rss-terms-of-use/ | 2026-10-07 | allowed | Summary prepared 2026-10-07: RSS terms allow displaying "the content that is provided in the feed, with attribution" with a link; the site terms are personal non-commercial and ban scrapers; no AI clause found. Read by Peter 2026-10-07 and allowed for the feed only (`extract: false`) |
| theverge.com | The Verge, AI section (RSS) | https://www.pmc.com/terms-of-use/ | 2026-10-07 | dropped | Read 2026-10-07: The Verge is now Penske Media; s.19 allows feeds in aggregators, but the terms bar using content "to train or ground" AI or "automated processing tools". A machine-written summary is that. Not permitted |
| arstechnica.com | Ars Technica, AI section (RSS) | https://www.condenast.com/user-agreement | 2026-10-07 | dropped | Read 2026-10-07: Conde Nast agreement bans crawling, extracting or storing content for any purpose but search indexing, naming grounding and RAG; RSS content is under the same restriction. Not permitted |
| wired.com | Wired, AI tag (RSS) | https://www.condenast.com/user-agreement | 2026-10-07 | dropped | Read 2026-10-07: the same Conde Nast agreement as arstechnica.com. Not permitted |
| technologyreview.com | MIT Technology Review, AI topic (RSS) | https://www.technologyreview.com/terms-of-service/ | 2026-10-07 | dropped | Read 2026-10-07: services "for personal use only"; bans any robot or scraper used to "extract data from, copy, or distribute" content, search engines excepted; separate ban on AI/ML use. Not permitted |
| spectrum.ieee.org | IEEE Spectrum, AI topic (RSS) | https://www.ieee.org/about/help/site-terms-conditions.html | 2026-10-07 | allowed | Summary prepared 2026-10-07: the live terms page did not load (HTTP 202, empty); a 2024 copy says informational or personal use, no retransmission without consent. Read by Peter 2026-10-07 and allowed |
| theguardian.com | The Guardian, AI section (RSS) | https://www.theguardian.com/help/terms-of-service | 2026-10-07 | dropped | Read 2026-10-07: feeds are for personal, non-commercial use under the terms, which ban use with machine learning or AI "to generate any data or content" and text and data mining, and say they prevail over robots.txt. The Open Platform API carries the same clause. Not permitted |
| openai.com | OpenAI news (RSS) | https://openai.com/policies/terms-of-use/ | 2026-10-07 | allowed | Summary prepared 2026-10-07: the terms page answered 403 to an automated reader; the terms found govern OpenAI's products, not its public news site. Robots allows the feed. Read by Peter 2026-10-07 and allowed |
| deepmind.google | Google DeepMind blog (RSS) | https://policies.google.com/terms | 2026-10-07 | allowed | Summary prepared 2026-10-07: Google's terms bar automated access only in violation of robots.txt, which allows this feed; no RSS or summarising restriction found. Read by Peter 2026-10-07 and allowed |
| blog.google | Google blog, AI (RSS) | https://policies.google.com/terms | 2026-10-07 | allowed | Summary prepared 2026-10-07: the same Google terms as deepmind.google; robots allows the feed. Read by Peter 2026-10-07 and allowed |
| huggingface.co | Hugging Face blog (RSS) | https://huggingface.co/terms-of-service | 2026-10-07 | allowed | Summary prepared 2026-10-07: no clause on RSS, scraping or AI use of site content; robots allows the feed. Read by Peter 2026-10-07 and allowed |
| anthropic.com | Anthropic news, through its sitemap (no feed is published) | https://www.anthropic.com/legal | - | pending | Added 2026-10-08. No RSS or Atom feed exists (every usual path 404); the sitemap lists /news/ pages with dates, and robots.txt allows all. The legal page lists product terms (consumer, commercial, usage policy); no separate website terms were found. Not yet read |

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
| vocm.com | Returns 403 on every path, robots.txt excepted, to any non-browser client, with this project's user agent and with curl's. robots.txt itself permits the feed. Marked `dropped` above rather than worked around | Nothing. VOCM publishing a feed it serves to automated readers |

## What CBC taught us about identifying ourselves

CBC first looked like a dead end: every CBC feed timed out on read, with and without a user
agent, so it was written up as cause unknown. That was wrong, and the finding matters more
than the source.

`curl` fetched the same feed in 0.3 seconds. Holding the client constant and varying only
the user agent, on 2026-09-13:

| User agent sent | CBC's answer |
|---|---|
| `curl/8.5.0` | 200 |
| `clippings/0.1` | 200 |
| `clippings/0.1 news digest research` | 200 |
| `clippings/0.1 (+https://github.com/Peter-A-P/department-news-digest)` | connection reset |
| `python-httpx/0.28.1` | connection reset |

CBC's edge refuses a user agent that contains a URL. The `Product/Version (+https://...)`
form is the convention a well-behaved crawler uses to say who it is and how to reach its
owner, and it is the one thing that gets the request dropped. A user agent that says nothing
about who is asking is served.

The user agent is now `clippings/0.1 news digest research`, with the measurement recorded in
`clippings/constants.py`. That is not a way around a refusal. CBC's robots.txt permits the
feed paths and names no rule against this project, so there is no decision here to go
around, only a filter. The product token, the version and the purpose are all still sent and
all still true, and the way a publisher stops this project was never the URL: they write
`User-agent: clippings` in robots.txt, and the robots check honours that token on every
request.

The cost is real and worth naming: a publisher reading their logs can no longer click
through to find out what this is. That is CBC's filter making the web slightly less legible,
and this project declining to be the only one paying for it.

## The AI desks: what their terms say about this use

Read on 2026-10-07 when the `ai` audience was widened from policy to AI broadly. The large
technology publishers have each added terms that cover exactly what this project does: an
automated reader whose output is a machine-written summary. Robots.txt allows this project's
user agent everywhere below, and the terms still say no; the Guardian's say in terms that
they prevail over robots.txt. Robots permission was never the test here, the terms are.

Dropped, and recorded so nobody adds them again: MIT Technology Review, The Verge (now Penske
Media), Ars Technica and Wired (Conde Nast), and The Guardian. Read by Peter and allowed on
2026-10-07: TechCrunch (feed only; its RSS terms allow display with attribution and a link),
IEEE Spectrum and OpenAI (neither terms page could be read by an automated client, so these
were read in a browser), Google DeepMind, the Google blog and Hugging Face.

This is also a reason to re-read the news sources allowed on 2026-09-13 and 2026-10-02 with
these clauses in mind before the measurement month, as step 5 above already asks: several
of those terms say "personal and non-commercial", and some publishers have added AI clauses
since.

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
| The Register (AI section) | Its robots.txt disallows this project's user agent for the feed path (probed 2026-10-07). Not read further. |
| VentureBeat (AI section) | Answered 429 on the first request (2026-10-07). Not read further. |

## Retention and republication

Article text is kept thirty days for processing and never republished; see
[data-retention.md](data-retention.md). A digest shows a summary, a link, and quotes of at
most twenty-five words, enforced in code by `clippings.constants.QUOTE_MAX_WORDS` and the
verifier.
