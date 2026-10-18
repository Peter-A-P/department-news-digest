# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 43 digests from 2026-10-07 to 2026-10-17, by `clippings report` on 2026-10-18. 95% intervals throughout. 28 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 68% (53% to 84%), 7 days | 83% (57% to 100%) | 3.4 (2.4 to 4.6) | 58% (48% to 72%) | 9.3 (5.7 to 13.6) | _not yet_ | 8.2 (6.6 to 9.6) | CA$0.060 (CA$0.046 to CA$0.073) |
| Municipal affairs, Toronto | 70% (60% to 92%), 5 days | 65% (45% to 100%) | 3.1 (1.4 to 5.2) | 51% (38% to 75%) | 5.5 (2.6 to 9.2) | _not yet_ | 5.2 (3.3 to 7.1) | CA$0.052 (CA$0.033 to CA$0.073) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 10.0 on all 11 | CA$0.069 (CA$0.063 to CA$0.076) |
| Public health in Canada | 100% (55% to 100%), 7 days | 60% (11% to 88%) | 1.4 (0.9 to 2.1) | 45% (22% to 62%) | 2.9 (1.6 to 4.1) | _not yet_ | 3.6 (1.7 to 5.8) | CA$0.037 (CA$0.018 to CA$0.058) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.16 (1.14 to 1.19) items per story | _not yet_ (story checks) | 100% (97% to 100%) / 100% (97% to 100%) | 100% (100% to 100%) | _not yet_ (hand check) | 17 h (16 to 19) / 42 h (40 to 43) | _not yet_ (reader study) | _not yet_ (measurement month) |

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (66% to 100%); Municipal affairs, Toronto 60% (20% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (46% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (76% to 100%); Municipal affairs, Toronto 100% (46% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.213 (CA$0.167 to CA$0.257) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17
- Municipal affairs, Toronto: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17
- Regional affairs, Newfoundland and Labrador: 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-10, 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15
- Public health in Canada: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17

## Source yield

Items held (thirty days), items a digest showed or cited, and, once labelled, the share of each source's labelled stories judged relevant.

| Audience | Source | Items held | In a digest | Share in a digest (95% CI) | Relevant of labelled |
|---|---|---|---|---|---|
| ai | bluesky | 243 | 14 | 6% (3% to 9%) | 6 of 6, 100% (66% to 100%) |
| ai | gdelt | 177 | 27 | 15% (11% to 21%) | 28 of 125, 22% (16% to 30%) |
| ai | techcrunch.com | 106 | 34 | 32% (24% to 41%) | 55 of 107, 51% (42% to 61%) |
| ai | cbc.ca | 42 | 3 | 7% (2% to 18%) | 4 of 40, 10% (3% to 22%) |
| ai | openai.com | 25 | 6 | 24% (11% to 43%) | 8 of 19, 42% (22% to 64%) |
| ai | huggingface.co | 10 | 3 | 30% (9% to 60%) | 2 of 10, 20% (4% to 50%) |
| ai | spectrum.ieee.org | 7 | 4 | 57% (23% to 86%) | 1 of 8, 12% (1% to 46%) |
| ai | anthropic.com | 7 | 4 | 57% (23% to 86%) | 0 of 5, 0% (0% to 38%) |
| ai | deepmind.google | 6 | 6 | 100% (66% to 100%) | 2 of 3, 67% (17% to 96%) |
| ai | nist.gov | 3 | 0 | 0% (0% to 54%) | 0 of 1, 0% (0% to 86%) |
| ai | blog.google | 2 | 2 | 100% (33% to 100%) | 1 of 2, 50% (6% to 94%) |
| ai | ec.europa.eu | 2 | 1 | 50% (6% to 94%) | 1 of 2, 50% (6% to 94%) |
| municipal-toronto | bluesky | 243 | 6 | 2% (1% to 5%) | 3 of 6, 50% (17% to 83%) |
| municipal-toronto | citynews.ca | 171 | 12 | 7% (4% to 12%) | 15 of 208, 7% (4% to 11%) |
| municipal-toronto | cbc.ca | 129 | 35 | 27% (20% to 35%) | 62 of 174, 36% (29% to 43%) |
| municipal-toronto | gdelt | 73 | 3 | 4% (1% to 11%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | toronto.ca | 7 | 6 | 86% (50% to 98%) | 8 of 8, 100% (73% to 100%) |
| newfoundland-labrador | bluesky | 126 | 4 | 3% (1% to 7%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | ntv.ca | 111 | 38 | 34% (26% to 43%) | 50 of 123, 41% (32% to 49%) |
| newfoundland-labrador | saltwire.com | 110 | 3 | 3% (1% to 7%) | 7 of 145, 5% (2% to 9%) |
| newfoundland-labrador | cbc.ca | 93 | 41 | 44% (34% to 54%) | 60 of 101, 59% (50% to 69%) |
| newfoundland-labrador | vocm.com | 76 | 25 | 33% (23% to 44%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | gazette.mun.ca | 15 | 1 | 7% (1% to 27%) | 4 of 20, 20% (7% to 41%) |
| newfoundland-labrador | gdelt | 7 | 0 | 0% (0% to 30%) | _not yet_ |
| newfoundland-labrador | theindependent.ca | 4 | 1 | 25% (3% to 72%) | 2 of 5, 40% (9% to 79%) |
| public-health-canada | canada.ca | 251 | 19 | 8% (5% to 11%) | 20 of 299, 7% (4% to 10%) |
| public-health-canada | bluesky | 147 | 2 | 1% (0% to 4%) | 3 of 3, 100% (46% to 100%) |
| public-health-canada | cbc.ca | 26 | 15 | 58% (39% to 75%) | 27 of 33, 82% (67% to 92%) |
