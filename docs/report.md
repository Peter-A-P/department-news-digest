# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 15 digests from 2026-10-07 to 2026-10-10, by `clippings report` on 2026-10-10. 95% intervals throughout. 3 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall, importance-weighted (95% CI) | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|
| Artificial intelligence | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 8.7 (6.0 to 10.0) | US$0.047 (US$0.038 to US$0.055) |
| Municipal affairs, Toronto | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 10.0 on all 4 | US$0.074 (US$0.070 to US$0.078) |
| Regional affairs, Newfoundland and Labrador | 90% (80% to 100%), 3 days | 51% (47% to 53%) | 17.7 (12.0 to 23.2) | _not yet_ | 10.0 on all 4 | US$0.060 (US$0.058 to US$0.063) |
| Public health in Canada | _not yet_ | _not yet_ | _not yet_ | _not yet_ | 7.8 (5.8 to 9.5) | US$0.057 (US$0.046 to US$0.068) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.17 (1.14 to 1.22) items per story | 100% (93% to 100%) / 100% (93% to 100%) | 100% (99% to 100%) | _not yet_ (hand check) | 24 h (20 to 30) / 43 h (42 to 44) | _not yet_ (reader study) | _not yet_ (measurement month) |

All four digests together cost US$0.227 (US$0.219 to US$0.235) a day in model calls, from the gateway's ledger. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: none yet
- Municipal affairs, Toronto: none yet
- Regional affairs, Newfoundland and Labrador: 2026-10-07, 2026-10-08, 2026-10-09
- Public health in Canada: none yet

## Source yield

Items held (thirty days), items a digest showed or cited, and, once labelled, the share of each source's labelled stories judged relevant.

| Audience | Source | Items held | In a digest | Share in a digest (95% CI) | Relevant of labelled |
|---|---|---|---|---|---|
| ai | bluesky | 103 | 7 | 7% (3% to 13%) | _not yet_ |
| ai | techcrunch.com | 44 | 11 | 25% (14% to 39%) | 25 of 40, 62% (47% to 76%) |
| ai | gdelt | 27 | 3 | 11% (3% to 27%) | 2 of 20, 10% (2% to 28%) |
| ai | openai.com | 13 | 5 | 38% (16% to 65%) | 6 of 9, 67% (35% to 89%) |
| ai | cbc.ca | 8 | 0 | 0% (0% to 27%) | 0 of 8, 0% (0% to 27%) |
| ai | huggingface.co | 4 | 1 | 25% (3% to 72%) | 2 of 3, 67% (17% to 96%) |
| ai | anthropic.com | 4 | 2 | 50% (12% to 88%) | 0 of 2, 0% (0% to 67%) |
| ai | spectrum.ieee.org | 3 | 2 | 67% (17% to 96%) | 1 of 3, 33% (4% to 82%) |
| ai | ec.europa.eu | 2 | 1 | 50% (6% to 94%) | 1 of 2, 50% (6% to 94%) |
| ai | nist.gov | 2 | 0 | 0% (0% to 67%) | _not yet_ |
| ai | blog.google | 1 | 1 | 100% (14% to 100%) | 0 of 1, 0% (0% to 86%) |
| ai | deepmind.google | 1 | 1 | 100% (14% to 100%) | 1 of 1, 100% (14% to 100%) |
| municipal-toronto | bluesky | 81 | 2 | 2% (1% to 8%) | _not yet_ |
| municipal-toronto | citynews.ca | 63 | 10 | 16% (8% to 26%) | 10 of 93, 11% (6% to 18%) |
| municipal-toronto | cbc.ca | 53 | 20 | 38% (26% to 51%) | 37 of 81, 46% (35% to 57%) |
| municipal-toronto | toronto.ca | 4 | 3 | 75% (28% to 97%) | 5 of 5, 100% (61% to 100%) |
| newfoundland-labrador | saltwire.com | 55 | 2 | 4% (1% to 11%) | 7 of 89, 8% (4% to 15%) |
| newfoundland-labrador | ntv.ca | 50 | 17 | 34% (22% to 48%) | 22 of 52, 42% (30% to 56%) |
| newfoundland-labrador | cbc.ca | 43 | 20 | 47% (32% to 61%) | 36 of 55, 65% (52% to 77%) |
| newfoundland-labrador | bluesky | 42 | 2 | 5% (1% to 14%) | _not yet_ |
| newfoundland-labrador | vocm.com | 10 | 4 | 40% (15% to 70%) | _not yet_ |
| newfoundland-labrador | gazette.mun.ca | 7 | 0 | 0% (0% to 30%) | 4 of 12, 33% (12% to 61%) |
| newfoundland-labrador | theindependent.ca | 3 | 0 | 0% (0% to 54%) | 1 of 4, 25% (3% to 72%) |
| public-health-canada | canada.ca | 106 | 14 | 13% (8% to 21%) | 10 of 145, 7% (4% to 12%) |
| public-health-canada | bluesky | 17 | 1 | 6% (1% to 25%) | _not yet_ |
| public-health-canada | cbc.ca | 13 | 11 | 85% (59% to 97%) | 17 of 20, 85% (65% to 96%) |
