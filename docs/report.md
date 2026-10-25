# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 74 digests from 2026-10-07 to 2026-10-25, by `clippings report` on 2026-10-25. 95% intervals throughout. 33 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.6 (7.4 to 9.7) | CA$0.060 (CA$0.050 to CA$0.070) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | _not yet_ | 5.4 (4.1 to 6.6) | CA$0.054 (CA$0.040 to CA$0.067) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.9 (9.8 to 10.0) | CA$0.069 (CA$0.064 to CA$0.073) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 3.4 (1.9 to 4.9) | CA$0.034 (CA$0.020 to CA$0.048) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| 94% (84% to 98%) / 85% (58% to 100%), 27 audience-days | 1.20 (1.17 to 1.23) items per story | 100% (interval undefined, n=8), 1 audience-days | 100% (98% to 100%) / 100% (98% to 100%) | 100% (100% to 100%) | _not yet_ (hand check) | 15 h (15 to 16) / 40 h (37 to 41) | _not yet_ (reader study) | 89% (69% to 98%), 16 of 18 days since 2026-10-08 |

Cluster purity is the share of articles in a story of several that a labeller judged to belong with the rest; over every news article, stories of one included, it is 100% (interval undefined, n=40).

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08, 2026-10-25).

Deduplication recall is over the pairs whose words overlap most, where a missed duplicate almost always is; of 54 pairs drawn from outside them as a check, 1 was the same story.

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.212 (CA$0.182 to CA$0.241) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

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
| ai | gdelt | 501 | 60 | 12% (9% to 15%) | 28 of 125, 22% (16% to 30%) |
| ai | bluesky | 414 | 17 | 4% (2% to 6%) | 8 of 8, 100% (73% to 100%) |
| ai | techcrunch.com | 167 | 67 | 40% (33% to 48%) | 56 of 108, 52% (43% to 61%) |
| ai | cbc.ca | 92 | 5 | 5% (2% to 11%) | 4 of 40, 10% (3% to 22%) |
| ai | openai.com | 44 | 15 | 34% (21% to 49%) | 8 of 19, 42% (22% to 64%) |
| ai | huggingface.co | 26 | 3 | 12% (3% to 27%) | 2 of 10, 20% (4% to 50%) |
| ai | spectrum.ieee.org | 11 | 6 | 55% (27% to 80%) | 1 of 8, 12% (1% to 46%) |
| ai | anthropic.com | 11 | 7 | 64% (35% to 86%) | 1 of 6, 17% (2% to 56%) |
| ai | deepmind.google | 7 | 7 | 100% (70% to 100%) | 2 of 3, 67% (17% to 96%) |
| ai | ec.europa.eu | 4 | 2 | 50% (12% to 88%) | 2 of 3, 67% (17% to 96%) |
| ai | blog.google | 3 | 3 | 100% (46% to 100%) | 1 of 2, 50% (6% to 94%) |
| ai | nist.gov | 3 | 0 | 0% (0% to 54%) | 0 of 1, 0% (0% to 86%) |
| municipal-toronto | bluesky | 445 | 9 | 2% (1% to 4%) | 6 of 9, 67% (35% to 89%) |
| municipal-toronto | citynews.ca | 291 | 23 | 8% (5% to 11%) | 18 of 243, 7% (5% to 11%) |
| municipal-toronto | gdelt | 249 | 23 | 9% (6% to 13%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | cbc.ca | 231 | 61 | 26% (21% to 32%) | 75 of 206, 36% (30% to 43%) |
| municipal-toronto | toronto.ca | 9 | 7 | 78% (46% to 95%) | 8 of 8, 100% (73% to 100%) |
| newfoundland-labrador | bluesky | 243 | 8 | 3% (2% to 6%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | ntv.ca | 189 | 66 | 35% (28% to 42%) | 50 of 123, 41% (32% to 49%) |
| newfoundland-labrador | saltwire.com | 175 | 3 | 2% (0% to 4%) | 7 of 145, 5% (2% to 9%) |
| newfoundland-labrador | vocm.com | 156 | 50 | 32% (25% to 40%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | cbc.ca | 151 | 64 | 42% (35% to 50%) | 60 of 101, 59% (50% to 69%) |
| newfoundland-labrador | gdelt | 80 | 13 | 16% (9% to 25%) | _not yet_ |
| newfoundland-labrador | gazette.mun.ca | 18 | 2 | 11% (2% to 31%) | 4 of 20, 20% (7% to 41%) |
| newfoundland-labrador | theindependent.ca | 6 | 3 | 50% (17% to 83%) | 2 of 5, 40% (9% to 79%) |
| public-health-canada | canada.ca | 374 | 24 | 6% (4% to 9%) | 20 of 300, 7% (4% to 10%) |
| public-health-canada | bluesky | 266 | 6 | 2% (1% to 5%) | 4 of 4, 100% (55% to 100%) |
| public-health-canada | gdelt | 191 | 21 | 11% (7% to 16%) | _not yet_ |
| public-health-canada | cbc.ca | 47 | 22 | 47% (33% to 61%) | 28 of 35, 80% (65% to 91%) |
| public-health-canada | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
