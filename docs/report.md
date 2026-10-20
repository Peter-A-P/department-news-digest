# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 55 digests from 2026-10-07 to 2026-10-20, by `clippings report` on 2026-10-20. 95% intervals throughout. 33 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.1 (6.5 to 9.5) | CA$0.057 (CA$0.044 to CA$0.070) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | _not yet_ | 4.8 (3.3 to 6.5) | CA$0.048 (CA$0.032 to CA$0.065) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.9 (9.8 to 10.0) | CA$0.067 (CA$0.062 to CA$0.073) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 3.1 (1.5 to 4.9) | CA$0.032 (CA$0.016 to CA$0.049) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.17 (1.15 to 1.20) items per story | _not yet_ (story checks) | 100% (98% to 100%) / 100% (98% to 100%) | 100% (100% to 100%) | _not yet_ (hand check) | 16 h (15 to 17) / 41 h (40 to 43) | _not yet_ (reader study) | 92% (69% to 99%), 12 of 13 days since 2026-10-08 |

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08).

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.200 (CA$0.163 to CA$0.239) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-19
- Municipal affairs, Toronto: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19, 2026-10-20
- Regional affairs, Newfoundland and Labrador: 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-10, 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15
- Public health in Canada: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18

## Source yield

Items held (thirty days), items a digest showed or cited, and, once labelled, the share of each source's labelled stories judged relevant.

| Audience | Source | Items held | In a digest | Share in a digest (95% CI) | Relevant of labelled |
|---|---|---|---|---|---|
| ai | gdelt | 321 | 39 | 12% (9% to 16%) | 28 of 125, 22% (16% to 30%) |
| ai | bluesky | 311 | 14 | 5% (3% to 7%) | 8 of 8, 100% (73% to 100%) |
| ai | techcrunch.com | 123 | 46 | 37% (29% to 46%) | 56 of 108, 52% (43% to 61%) |
| ai | cbc.ca | 54 | 4 | 7% (3% to 17%) | 4 of 40, 10% (3% to 22%) |
| ai | openai.com | 26 | 7 | 27% (13% to 46%) | 8 of 19, 42% (22% to 64%) |
| ai | huggingface.co | 11 | 3 | 27% (8% to 56%) | 2 of 10, 20% (4% to 50%) |
| ai | spectrum.ieee.org | 8 | 4 | 50% (20% to 80%) | 1 of 8, 12% (1% to 46%) |
| ai | anthropic.com | 8 | 5 | 62% (29% to 88%) | 1 of 6, 17% (2% to 56%) |
| ai | deepmind.google | 6 | 6 | 100% (66% to 100%) | 2 of 3, 67% (17% to 96%) |
| ai | ec.europa.eu | 4 | 2 | 50% (12% to 88%) | 2 of 3, 67% (17% to 96%) |
| ai | nist.gov | 3 | 0 | 0% (0% to 54%) | 0 of 1, 0% (0% to 86%) |
| ai | blog.google | 2 | 2 | 100% (33% to 100%) | 1 of 2, 50% (6% to 94%) |
| municipal-toronto | bluesky | 307 | 6 | 2% (1% to 4%) | 6 of 9, 67% (35% to 89%) |
| municipal-toronto | citynews.ca | 216 | 16 | 7% (4% to 11%) | 18 of 243, 7% (5% to 11%) |
| municipal-toronto | cbc.ca | 162 | 43 | 27% (20% to 34%) | 75 of 206, 36% (30% to 43%) |
| municipal-toronto | gdelt | 73 | 3 | 4% (1% to 11%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | toronto.ca | 7 | 6 | 86% (50% to 98%) | 8 of 8, 100% (73% to 100%) |
| newfoundland-labrador | bluesky | 160 | 6 | 4% (2% to 8%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | ntv.ca | 140 | 49 | 35% (27% to 43%) | 50 of 123, 41% (32% to 49%) |
| newfoundland-labrador | saltwire.com | 127 | 3 | 2% (1% to 6%) | 7 of 145, 5% (2% to 9%) |
| newfoundland-labrador | cbc.ca | 109 | 47 | 43% (34% to 53%) | 60 of 101, 59% (50% to 69%) |
| newfoundland-labrador | vocm.com | 106 | 39 | 37% (28% to 46%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | gazette.mun.ca | 17 | 1 | 6% (1% to 25%) | 4 of 20, 20% (7% to 41%) |
| newfoundland-labrador | gdelt | 7 | 0 | 0% (0% to 30%) | _not yet_ |
| newfoundland-labrador | theindependent.ca | 5 | 2 | 40% (9% to 79%) | 2 of 5, 40% (9% to 79%) |
| public-health-canada | canada.ca | 274 | 20 | 7% (5% to 11%) | 20 of 300, 7% (4% to 10%) |
| public-health-canada | bluesky | 190 | 2 | 1% (0% to 3%) | 4 of 4, 100% (55% to 100%) |
| public-health-canada | gdelt | 74 | 7 | 9% (4% to 18%) | _not yet_ |
| public-health-canada | cbc.ca | 28 | 15 | 54% (35% to 71%) | 28 of 35, 80% (65% to 91%) |
| public-health-canada | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
