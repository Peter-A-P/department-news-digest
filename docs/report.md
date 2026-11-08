# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 131 digests from 2026-10-07 to 2026-11-08, by `clippings report` on 2026-11-08. 95% intervals throughout. 33 audience-days hand-labelled: every audience has its labelled week.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.5 (7.4 to 9.4) | CA$0.058 (CA$0.049 to CA$0.066) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | 0.71 (0.59 to 0.82) | 4.7 (3.8 to 5.7) | CA$0.046 (CA$0.037 to CA$0.056) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.8 (9.6 to 10.0) | CA$0.066 (CA$0.063 to CA$0.070) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 2.4 (1.5 to 3.4) | CA$0.025 (CA$0.016 to CA$0.034) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| 94% (84% to 98%) / 85% (58% to 100%), 27 audience-days | 1.17 (1.15 to 1.19) items per story | 98% (97% to 100%), 26 audience-days | 100% (99% to 100%) / 100% (99% to 100%) | 100% (100% to 100%) | 99% (98% to 100%), 111 sentences | 15 h (14 to 15) / 33 h (33 to 37) | 0.9 (0.6 to 1.2) vs 1.9 (1.5 to 2.4), 15 sessions | 94% (81% to 99%), 30 of 32 days since 2026-10-08 |

Cluster purity is the share of articles in a story of several that a labeller judged to belong with the rest; over every news article, stories of one included, it is 100% (99% to 100%).

Faithfulness is the share of sampled digest sentences that say only what the sources they cite say, hand-checked against what the summariser read, weighted by the sentences each day's digest showed. 2 of 111 were judged not supported, listed in [docs/report.md](docs/report.md).

Reader minutes are minutes with the page in view, from 3 readers briefed on a morning either from the digest or from the news items it was made from; from the sources they took 2.1 (1.5 to 3.2) times as long. Of the 43 items readers ticked as worth a briefing when working from the sources, 72% (58% to 84%) were in a story the digest showed.

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08, 2026-10-25). The measurement month runs from 2026-11-09 to 2026-12-08.

Deduplication recall is over the pairs whose words overlap most, where a missed duplicate almost always is; of 54 pairs drawn from outside them as a check, 1 was the same story.

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API.

All four digests together cost CA$0.193 (CA$0.171 to CA$0.216) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Google Cloud billed CA$0.00 from 2026-10-07 to 2026-11-08, CA$0.000 a day; X API billed US$8.01 from 2026-10-12 to 2026-11-08, CA$0.386 a day, read from their own billing pages ([docs/bills.yaml](docs/bills.yaml)). Everything together: CA$0.579 (CA$0.557 to CA$0.602) a day, about CA$18 a month. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-19
- Municipal affairs, Toronto: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19, 2026-10-20; kappa against `labeller-2`
- Regional affairs, Newfoundland and Labrador: 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-10, 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15
- Public health in Canada: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18

## Sentences judged not supported

From the faithfulness sample: each sentence as the digest showed it, its story, and the sources it cited.

- public-health-canada, 2026-10-21, "Nigeria confirms case of Ebola in capital city of Abuja": Nigeria's government said a female patient in Abuja has laboratory-confirmed Ebola, and that she travelled from Uganda, a link Ugandan government spokesperson Alan Kasujja disputed by saying "There's no Ebola in Uganda." Cited: <https://www.cbc.ca/news/health/nigeria-ebola-case-confirmed-abuja-9.7389261>
- public-health-canada, 2026-10-21, "Nigeria confirms case of Ebola in capital city of Abuja": The case follows an outbreak of the Bundibugyo strain declared in Democratic Republic of Congo in mid-May, now the world's second-largest ever, with Kenya reporting nine linked cases this month and Africa's top public health agency mobilizing support for Nigeria. Cited: <https://www.cbc.ca/news/health/nigeria-ebola-case-confirmed-abuja-9.7389261>

## Source yield

Items held (thirty days), items a digest showed or cited, and, once labelled, the share of each source's labelled stories judged relevant.

| Audience | Source | Items held | In a digest | Share in a digest (95% CI) | Relevant of labelled |
|---|---|---|---|---|---|
| ai | gdelt | 1005 | 106 | 11% (9% to 13%) | 28 of 125, 22% (16% to 30%) |
| ai | bluesky | 604 | 12 | 2% (1% to 3%) | 8 of 8, 100% (73% to 100%) |
| ai | techcrunch.com | 260 | 113 | 43% (38% to 49%) | 35 of 75, 47% (36% to 58%) |
| ai | cbc.ca | 164 | 12 | 7% (4% to 12%) | 4 of 36, 11% (4% to 24%) |
| ai | openai.com | 75 | 29 | 39% (28% to 50%) | 2 of 10, 20% (4% to 50%) |
| ai | huggingface.co | 39 | 5 | 13% (5% to 26%) | 0 of 8, 0% (0% to 27%) |
| ai | spectrum.ieee.org | 18 | 6 | 33% (15% to 56%) | 0 of 6, 0% (0% to 33%) |
| ai | deepmind.google | 11 | 9 | 82% (53% to 96%) | 1 of 2, 50% (6% to 94%) |
| ai | ec.europa.eu | 10 | 1 | 10% (1% to 38%) | 1 of 1, 100% (14% to 100%) |
| ai | anthropic.com | 10 | 8 | 80% (50% to 95%) | 1 of 4, 25% (3% to 72%) |
| ai | blog.google | 5 | 5 | 100% (61% to 100%) | 1 of 1, 100% (14% to 100%) |
| ai | nist.gov | 3 | 0 | 0% (0% to 54%) | 0 of 1, 0% (0% to 86%) |
| ai | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
| municipal-toronto | bluesky | 659 | 12 | 2% (1% to 3%) | 6 of 9, 67% (35% to 89%) |
| municipal-toronto | citynews.ca | 453 | 36 | 8% (6% to 11%) | 11 of 161, 7% (4% to 11%) |
| municipal-toronto | gdelt | 375 | 31 | 8% (6% to 11%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | cbc.ca | 359 | 74 | 21% (17% to 25%) | 40 of 135, 30% (22% to 38%) |
| municipal-toronto | toronto.ca | 15 | 9 | 60% (35% to 81%) | 4 of 4, 100% (55% to 100%) |
| newfoundland-labrador | bluesky | 454 | 19 | 4% (3% to 6%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | vocm.com | 296 | 100 | 34% (29% to 39%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | ntv.ca | 295 | 95 | 32% (27% to 38%) | 30 of 77, 39% (29% to 50%) |
| newfoundland-labrador | saltwire.com | 261 | 4 | 2% (1% to 4%) | 0 of 62, 0% (0% to 4%) |
| newfoundland-labrador | cbc.ca | 238 | 99 | 42% (35% to 48%) | 26 of 53, 49% (36% to 62%) |
| newfoundland-labrador | gdelt | 84 | 14 | 17% (10% to 26%) | _not yet_ |
| newfoundland-labrador | gazette.mun.ca | 25 | 4 | 16% (6% to 33%) | 0 of 10, 0% (0% to 22%) |
| newfoundland-labrador | theindependent.ca | 10 | 7 | 70% (39% to 91%) | 2 of 2, 100% (33% to 100%) |
| public-health-canada | bluesky | 536 | 7 | 1% (1% to 3%) | 4 of 4, 100% (55% to 100%) |
| public-health-canada | canada.ca | 527 | 18 | 3% (2% to 5%) | 13 of 174, 7% (4% to 12%) |
| public-health-canada | gdelt | 241 | 28 | 12% (8% to 16%) | _not yet_ |
| public-health-canada | cbc.ca | 64 | 22 | 34% (24% to 46%) | 11 of 15, 73% (49% to 90%) |
| public-health-canada | cmaj.ca | 10 | 0 | 0% (0% to 22%) | _not yet_ |
| public-health-canada | citynews.ca | 2 | 1 | 50% (6% to 94%) | _not yet_ |
