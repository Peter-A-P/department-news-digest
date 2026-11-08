# Report

Written by `clippings report`; do not edit by hand. 95% intervals throughout.

Measured over 127 digests from 2026-10-07 to 2026-11-07, by `clippings report` on 2026-11-08. 95% intervals throughout. 33 audience-days hand-labelled: every audience has its labelled week.

**Relevance, per audience, against a hand-labelled week**

| Audience | Precision at K (95% CI) | Recall of must-read stories, importance-weighted (95% CI) | Must-read stories per day | Recall of all relevant stories | Relevant stories per day | Labeller kappa | Stories per day | Cost per digest |
|---|---|---|---|---|---|---|---|---|
| Artificial intelligence | 69% (55% to 85%), 8 days | 84% (57% to 100%) | 3.1 (2.1 to 4.4) | 60% (50% to 76%) | 8.5 (5.2 to 12.9) | _not yet_ | 8.4 (7.3 to 9.4) | CA$0.056 (CA$0.047 to CA$0.064) |
| Municipal affairs, Toronto | 77% (66% to 92%), 8 days | 60% (42% to 88%) | 2.9 (1.8 to 4.4) | 53% (42% to 69%) | 5.4 (3.5 to 7.6) | _not yet_ | 4.8 (3.8 to 5.8) | CA$0.047 (CA$0.038 to CA$0.057) |
| Regional affairs, Newfoundland and Labrador | 83% (74% to 91%), 9 days | 67% (50% to 75%) | 7.3 (5.1 to 9.0) | 51% (40% to 62%) | 16.4 (13.0 to 19.9) | _not yet_ | 9.8 (9.5 to 10.0) | CA$0.066 (CA$0.063 to CA$0.070) |
| Public health in Canada | 100% (55% to 100%), 8 days | 60% (10% to 89%) | 1.2 (0.6 to 1.9) | 43% (20% to 60%) | 2.6 (1.5 to 3.8) | _not yet_ | 2.5 (1.6 to 3.5) | CA$0.026 (CA$0.017 to CA$0.035) |

**Pipeline properties**

| Deduplication precision / recall (pairs) | Collapse rate | Cluster purity, stories of several articles | Quotes verbatim, before / after repair | Citation coverage, first draft | Faithfulness (100-sentence sample) | Lag to inclusion p50 / p90 | Reader minutes, digest vs sources (95% CI) | Uptime of the scheduled daily run |
|---|---|---|---|---|---|---|---|---|
| 94% (84% to 98%) / 85% (58% to 100%), 27 audience-days | 1.17 (1.15 to 1.19) items per story | 98% (97% to 100%), 26 audience-days | 100% (99% to 100%) / 100% (99% to 100%) | 100% (100% to 100%) | 99% (98% to 100%), 111 sentences | 15 h (14 to 15) / 33 h (33 to 37) | 0.9 (0.6 to 1.2) vs 1.9 (1.5 to 2.4), 15 sessions | 94% (81% to 99%), 29 of 31 days since 2026-10-08 |

Cluster purity is the share of articles in a story of several that a labeller judged to belong with the rest; over every news article, stories of one included, it is 100% (99% to 100%).

Faithfulness is the share of sampled digest sentences that say only what the sources they cite say, hand-checked against what the summariser read, weighted by the sentences each day's digest showed. 2 of 111 were judged not supported, listed in [docs/report.md](docs/report.md).

Reader minutes are minutes with the page in view, from 3 readers briefed on a morning either from the digest or from the news items it was made from; from the sources they took 2.1 (1.5 to 3.2) times as long. Of the 43 items readers ticked as worth a briefing when working from the sources, 72% (58% to 84%) were in a story the digest showed.

Uptime counts a day as up when the run Cloud Scheduler started at 09:00 UTC, or Cloud Run's automatic retry of it, published every audience's digest; a day rescued by a run started by hand is down (2026-10-08, 2026-10-25).

Deduplication recall is over the pairs whose words overlap most, where a missed duplicate almost always is; of 54 pairs drawn from outside them as a check, 1 was the same story.

Most discussed on Bluesky, judged worth showing: Artificial intelligence 100% (73% to 100%); Municipal affairs, Toronto 75% (38% to 100%); Regional affairs, Newfoundland and Labrador 100% (14% to 100%); Public health in Canada 100% (55% to 100%). A separate section below the stories, not counted in precision or recall.

Most discussed on X, judged worth showing: Artificial intelligence 100% (80% to 100%); Municipal affairs, Toronto 100% (61% to 100%); Regional affairs, Newfoundland and Labrador _not yet_; Public health in Canada _not yet_. The same kind of section, from X's paid API.

All four digests together cost CA$0.193 (CA$0.170 to CA$0.216) a day in model calls, from the gateway's ledger, converted from US dollars at 1.35 CAD per USD. Details, per source and per day: [docs/report.md](docs/report.md).

## Labelled days

Labeller for precision and recall: `peter`. A day counts once its whole sample is labelled.

- Artificial intelligence: 2026-10-11, 2026-10-12, 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-19
- Municipal affairs, Toronto: 2026-10-13, 2026-10-14, 2026-10-15, 2026-10-16, 2026-10-17, 2026-10-18, 2026-10-19, 2026-10-20
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
| ai | gdelt | 883 | 92 | 10% (9% to 13%) | 28 of 125, 22% (16% to 30%) |
| ai | bluesky | 596 | 12 | 2% (1% to 3%) | 8 of 8, 100% (73% to 100%) |
| ai | techcrunch.com | 273 | 118 | 43% (37% to 49%) | 41 of 88, 47% (36% to 57%) |
| ai | cbc.ca | 167 | 12 | 7% (4% to 12%) | 4 of 40, 10% (3% to 22%) |
| ai | openai.com | 80 | 30 | 38% (27% to 48%) | 3 of 13, 23% (7% to 49%) |
| ai | huggingface.co | 39 | 5 | 13% (5% to 26%) | 0 of 8, 0% (0% to 27%) |
| ai | spectrum.ieee.org | 19 | 7 | 37% (18% to 59%) | 1 of 7, 14% (2% to 50%) |
| ai | anthropic.com | 12 | 9 | 75% (47% to 92%) | 1 of 5, 20% (2% to 63%) |
| ai | ec.europa.eu | 11 | 2 | 18% (4% to 46%) | 2 of 2, 100% (33% to 100%) |
| ai | deepmind.google | 11 | 9 | 82% (53% to 96%) | 1 of 2, 50% (6% to 94%) |
| ai | blog.google | 5 | 5 | 100% (61% to 100%) | 1 of 1, 100% (14% to 100%) |
| ai | nist.gov | 5 | 0 | 0% (0% to 38%) | 0 of 1, 0% (0% to 86%) |
| ai | citynews.ca | 1 | 0 | 0% (0% to 86%) | _not yet_ |
| municipal-toronto | bluesky | 651 | 12 | 2% (1% to 3%) | 6 of 9, 67% (35% to 89%) |
| municipal-toronto | citynews.ca | 456 | 37 | 8% (6% to 11%) | 13 of 196, 7% (4% to 11%) |
| municipal-toronto | gdelt | 374 | 27 | 7% (5% to 10%) | 7 of 34, 21% (10% to 36%) |
| municipal-toronto | cbc.ca | 362 | 78 | 22% (18% to 26%) | 50 of 155, 32% (25% to 40%) |
| municipal-toronto | toronto.ca | 13 | 8 | 62% (35% to 84%) | 4 of 4, 100% (55% to 100%) |
| newfoundland-labrador | bluesky | 446 | 18 | 4% (2% to 6%) | 1 of 1, 100% (14% to 100%) |
| newfoundland-labrador | ntv.ca | 296 | 97 | 33% (28% to 38%) | 40 of 94, 43% (33% to 53%) |
| newfoundland-labrador | vocm.com | 286 | 95 | 33% (28% to 39%) | 23 of 72, 32% (22% to 43%) |
| newfoundland-labrador | saltwire.com | 276 | 6 | 2% (1% to 4%) | 5 of 106, 5% (2% to 10%) |
| newfoundland-labrador | cbc.ca | 241 | 98 | 41% (35% to 47%) | 36 of 68, 53% (41% to 64%) |
| newfoundland-labrador | gdelt | 84 | 14 | 17% (10% to 26%) | _not yet_ |
| newfoundland-labrador | gazette.mun.ca | 28 | 4 | 14% (5% to 30%) | 2 of 17, 12% (3% to 32%) |
| newfoundland-labrador | theindependent.ca | 11 | 7 | 64% (35% to 86%) | 2 of 4, 50% (12% to 88%) |
| public-health-canada | canada.ca | 539 | 21 | 4% (2% to 6%) | 15 of 217, 7% (4% to 11%) |
| public-health-canada | bluesky | 525 | 7 | 1% (1% to 3%) | 4 of 4, 100% (55% to 100%) |
| public-health-canada | gdelt | 237 | 28 | 12% (8% to 16%) | _not yet_ |
| public-health-canada | cbc.ca | 67 | 24 | 36% (25% to 48%) | 16 of 20, 80% (59% to 93%) |
| public-health-canada | cmaj.ca | 10 | 0 | 0% (0% to 22%) | _not yet_ |
| public-health-canada | citynews.ca | 2 | 1 | 50% (6% to 94%) | _not yet_ |
