# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 23 digests from 2026-10-07 to 2026-10-12, by `clippings report` on 2026-10-13. 95% intervals throughout. 12 audience-days hand-labelled so far; the relevance columns fill as the labelled week does.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 79% (57% to 100%), 2 days | 100% (70% to 100%) | 3.5 (2.0 to 5.0) | 79% (65% to 79%) | 7.0 (4.0 to 10.0) | _not yet_ | 8.0 (5.6 to 10.0) | CA$0.055 (CA$0.038 to CA$0.069) |
| Municipal affairs, Toronto | 33% (0% to 100%), 2 days | 25% (12% to 25%) | 2.0 on all 2 | 8% (6% to 8%) | 6.5 (4.0 to 9.0) | _not yet_ | 6.2 (3.2 to 9.0) | CA$0.064 (CA$0.033 to CA$0.095) |
| Regional affairs, Newfoundland and Labrador | 85% (75% to 93%), 6 days | 66% (56% to 67%) | 8.8 (7.8 to 9.9) | 45% (42% to 47%) | 18.9 (15.4 to 22.5) | _not yet_ | 10.0 on all 6 | CA$0.077 (CA$0.069 to CA$0.083) |
| Public health in Canada | 100% (33% to 100%), 2 days | 100% (100% to 100%) | 0.5 (0.0 to 1.0) | 67% (67% to 67%) | 1.5 (0.0 to 3.0) | _not yet_ | 5.5 (2.7 to 8.2) | CA$0.054 (CA$0.026 to CA$0.080) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime, measurement month |
|---|---|---|---|---|---|---|---|
| _not yet_ (pair labels) | 1.15 (1.12 to 1.19) items per story | 100% (95% to 100%) / 100% (95% to 100%) | 100% (99% to 100%) | _not yet_ (hand check) | 26 h (22 to 33) / 43 h (43 to 44) | _not yet_ (reader study) | _not yet_ (measurement month) |

Most discussed on Bluesky, judged worth showing: Artificial intelligence _not yet_; Municipal affairs, Toronto 0% (0% to 86%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (14% to 100%); Municipal affairs, Toronto _not yet_; Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API, while Reddit access is pending.

All four digests together cost CA$0.241 (CA$0.173 to CA$0.299) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: 2026-10-11, 2026-10-12
- Municipal affairs, Toronto: 2026-10-11, 2026-10-12
- Regional affairs, Newfoundland and Labrador: 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-10, 2026-10-11, 2026-10-12
- Public health in Canada: 2026-10-11, 2026-10-12

## Source yield

Items held (thirty days), items a digest showed or cited, and, once labelled, the share of each source's labelled stories judged relevant.

| Audience | Source | Items held | In a digest | Share in a digest (95% CI) | Relevant of labelled |
|---|---|---|---|---|---|
| ai | bluesky | 106 | 7 | 7% (3% to 12%) | _not yet_ |
| ai | techcrunch.com | 52 | 17 | 33% (21% to 46%) | 33 of 58, 57% (44% to 69%) |
| ai | gdelt | 27 | 7 | 26% (12% to 44%) | 7 of 41, 17% (8% to 30%) |
| ai | openai.com | 13 | 5 | 38% (16% to 65%) | 6 of 9, 67% (35% to 89%) |
| ai | cbc.ca | 12 | 1 | 8% (1% to 33%) | 1 of 16, 6% (1% to 26%) |
| ai | huggingface.co | 4 | 1 | 25% (3% to 72%) | 2 of 4, 50% (12% to 88%) |
| ai | anthropic.com | 4 | 2 | 50% (12% to 88%) | 0 of 2, 0% (0% to 67%) |
| ai | spectrum.ieee.org | 3 | 2 | 67% (17% to 96%) | 1 of 4, 25% (3% to 72%) |
| ai | ec.europa.eu | 2 | 1 | 50% (6% to 94%) | 1 of 2, 50% (6% to 94%) |
| ai | nist.gov | 2 | 0 | 0% (0% to 67%) | _not yet_ |
| ai | blog.google | 1 | 1 | 100% (14% to 100%) | 0 of 1, 0% (0% to 86%) |
| ai | deepmind.google | 1 | 1 | 100% (14% to 100%) | 1 of 1, 100% (14% to 100%) |
| municipal-toronto | citynews.ca | 96 | 8 | 8% (4% to 15%) | 13 of 150, 9% (5% to 14%) |
| municipal-toronto | bluesky | 82 | 2 | 2% (1% to 8%) | 0 of 1, 0% (0% to 86%) |
| municipal-toronto | cbc.ca | 68 | 20 | 29% (20% to 41%) | 46 of 114, 40% (32% to 49%) |
| municipal-toronto | toronto.ca | 4 | 3 | 75% (28% to 97%) | 6 of 6, 100% (66% to 100%) |
| newfoundland-labrador | ntv.ca | 61 | 20 | 33% (22% to 45%) | 40 of 96, 42% (32% to 52%) |
| newfoundland-labrador | saltwire.com | 60 | 2 | 3% (1% to 10%) | 7 of 115, 6% (3% to 12%) |
| newfoundland-labrador | cbc.ca | 50 | 21 | 42% (29% to 56%) | 46 of 81, 57% (46% to 67%) |
| newfoundland-labrador | bluesky | 43 | 2 | 5% (1% to 14%) | _not yet_ |
| newfoundland-labrador | vocm.com | 26 | 8 | 31% (16% to 50%) | 13 of 45, 29% (17% to 43%) |
| newfoundland-labrador | gazette.mun.ca | 7 | 0 | 0% (0% to 30%) | 4 of 14, 29% (10% to 54%) |
| newfoundland-labrador | theindependent.ca | 3 | 1 | 33% (4% to 82%) | 2 of 5, 40% (9% to 79%) |
| public-health-canada | canada.ca | 106 | 14 | 13% (8% to 21%) | 13 of 170, 8% (4% to 12%) |
| public-health-canada | bluesky | 17 | 1 | 6% (1% to 25%) | _not yet_ |
| public-health-canada | cbc.ca | 14 | 11 | 79% (53% to 94%) | 17 of 21, 81% (61% to 93%) |
