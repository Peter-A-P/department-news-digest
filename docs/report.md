# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 99 digests from 2026-10-07 to 2026-10-31, by `clippings report` on 2026-10-31. 95% intervals throughout. 33 audience-days hand-labelled: every audience has its labelled week.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.6 (7.5 to 9.6) | CA$0.058 (CA$0.049 to CA$0.067) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | _not yet_ | 5.2 (4.0 to 6.2) | CA$0.051 (CA$0.040 to CA$0.062) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 10.0 (9.9 to 10.0) | CA$0.067 (CA$0.063 to CA$0.071) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 2.8 (1.7 to 3.9) | CA$0.028 (CA$0.018 to CA$0.039) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| 94% (84% to 98%) / 85% (58% to 100%), 27 audience-days | 1.18 (1.15 to 1.20) items per story | 98% (97% to 100%), 26 audience-days | 100% (99% to 100%) / 100% (99% to 100%) | 100% (100% to 100%) | _not yet_ (hand check) | 15 h (14 to 16) / 37 h (33 to 40) | _not yet_ (reader study) | 92% (76% to 98%), 22 of 24 days since 2026-10-08 |

Cluster purity is the share of articles in a story of several that a labeller judged to belong with the rest; over every news article, stories of one included, it is 100% (99% to 100%).

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08, 2026-10-25).

Deduplication recall is over the pairs whose words overlap most, where a missed duplicate almost always is; of 54 pairs drawn from outside them as a check, 1 was the same story.

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.202 (CA$0.175 to CA$0.228) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

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
| ai | gdelt | 582 | 66 | 11% (9% to 14%) | 28 of 125, 22% (16% to 30%) |
| ai | bluesky | 552 | 18 | 3% (2% to 5%) | 8 of 8, 100% (73% to 100%) |
| ai | techcrunch.com | 227 | 94 | 41% (35% to 48%) | 56 of 108, 52% (43% to 61%) |
| ai | cbc.ca | 128 | 11 | 9% (5% to 14%) | 4 of 40, 10% (3% to 22%) |
| ai | openai.com | 63 | 24 | 38% (27% to 50%) | 8 of 19, 42% (22% to 64%) |
| ai | huggingface.co | 34 | 6 | 18% (8% to 33%) | 2 of 10, 20% (4% to 50%) |
| ai | spectrum.ieee.org | 17 | 7 | 41% (21% to 64%) | 1 of 8, 12% (1% to 46%) |
| ai | anthropic.com | 14 | 10 | 71% (46% to 90%) | 1 of 6, 17% (2% to 56%) |
| ai | deepmind.google | 9 | 9 | 100% (76% to 100%) | 2 of 3, 67% (17% to 96%) |
| ai | ec.europa.eu | 7 | 2 | 29% (7% to 64%) | 2 of 3, 67% (17% to 96%) |
| ai | nist.gov | 4 | 0 | 0% (0% to 45%) | 0 of 1, 0% (0% to 86%) |
| ai | blog.google | 4 | 4 | 100% (55% to 100%) | 1 of 2, 50% (6% to 94%) |
| ai | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
| municipal-toronto | bluesky | 597 | 13 | 2% (1% to 4%) | 6 of 9, 67% (35% to 89%) |
| municipal-toronto | citynews.ca | 381 | 36 | 9% (7% to 13%) | 18 of 243, 7% (5% to 11%) |
| municipal-toronto | cbc.ca | 311 | 76 | 24% (20% to 29%) | 75 of 206, 36% (30% to 43%) |
| municipal-toronto | gdelt | 303 | 23 | 8% (5% to 11%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | toronto.ca | 11 | 9 | 82% (53% to 96%) | 8 of 8, 100% (73% to 100%) |
| newfoundland-labrador | bluesky | 364 | 12 | 3% (2% to 6%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | ntv.ca | 249 | 85 | 34% (28% to 40%) | 50 of 123, 41% (32% to 49%) |
| newfoundland-labrador | saltwire.com | 234 | 6 | 3% (1% to 5%) | 7 of 145, 5% (2% to 9%) |
| newfoundland-labrador | vocm.com | 216 | 72 | 33% (27% to 40%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | cbc.ca | 204 | 87 | 43% (36% to 49%) | 60 of 101, 59% (50% to 69%) |
| newfoundland-labrador | gdelt | 80 | 13 | 16% (9% to 25%) | _not yet_ |
| newfoundland-labrador | gazette.mun.ca | 23 | 2 | 9% (2% to 25%) | 4 of 20, 20% (7% to 41%) |
| newfoundland-labrador | theindependent.ca | 10 | 5 | 50% (22% to 77%) | 2 of 5, 40% (9% to 79%) |
| public-health-canada | canada.ca | 482 | 27 | 6% (4% to 8%) | 20 of 300, 7% (4% to 10%) |
| public-health-canada | bluesky | 393 | 8 | 2% (1% to 4%) | 4 of 4, 100% (55% to 100%) |
| public-health-canada | gdelt | 213 | 22 | 10% (7% to 15%) | _not yet_ |
| public-health-canada | cbc.ca | 60 | 27 | 45% (33% to 57%) | 28 of 35, 80% (65% to 91%) |
| public-health-canada | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
