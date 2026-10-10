# The re-ranker's model: Haiku 4.5 to Haiku 5.5

Decided 2026-10-10. The re-ranker, and the Bluesky pick that shares its route, moved from
Claude Haiku 4.5 to Claude Haiku 5.5 at its default effort. Haiku 5.5 at low effort was tried
and rejected.

## Why it was a question

Haiku 5.5 was released on 2026-10-07 and the gateway priced it from 1.2.0: US$0.10 in and
US$0.50 out per million tokens, against Haiku 4.5's US$1 and US$5. A tenth of the price is
only worth having if the ranking does not get worse, and the ranking is the stage this
project's precision and recall depend on, so it was measured before the switch rather than
assumed from the vendor's description.

## Method

Every audience-day with labels at the time (fourteen: four audiences, 2026-10-07 to
2026-10-10). For each, the day's stored candidates, the sixty stories the live run showed
the re-ranker, were rebuilt from the store in the order the run gave them, and the identical
request (`rank/rerank.build_call`, today's audience files) was sent through the gateway to
three arms, twice each:

- Haiku 4.5, as in production until now;
- Haiku 5.5 at low effort (`output_config.effort: low`);
- Haiku 5.5 at its default effort.

Each reply was parsed as production parses it, and compared with Peter's labels on the
candidates he had judged: 622 labelled stories, 1,244 judgements per arm over the two
repeats. Intervals are 95% bootstrap intervals over audience-days; the differences are paired,
the same days drawn for both arms. The whole comparison cost US$0.46.

## Result

| Measure | Haiku 4.5 | Haiku 5.5, low effort | Haiku 5.5, default |
|---|---|---|---|
| Cost per re-ranking call | US$0.0126 | US$0.0016 | US$0.0021 |
| Candidates given a parseable score | 1,300 of 1,300 | 1,300 of 1,300 | 1,300 of 1,300 |
| Same verdict (score 2 or more) run to run | 95.8% | 97.5% | 96.3% |
| Top ten by model score: share labelled relevant | 81.3% (74.1 to 88.6) | 80.9% (73.9 to 88.0) | 80.2% (72.9 to 87.4) |
| Must-reads in the top ten (NL only) | 64.5% (38.9 to 88.9) | 68.4% (55.6 to 80.0) | 60.5% (33.3 to 80.0) |
| Kappa, score 2 or more against "relevant" | 0.569 (0.440 to 0.690) | 0.467 (0.333 to 0.595) | 0.554 (0.419 to 0.686) |

Paired against Haiku 4.5:

| Difference | Haiku 5.5, low effort | Haiku 5.5, default |
|---|---|---|
| Top-ten precision | -0.4 points (-3.9 to +3.3) | -1.1 points (-4.3 to +2.2) |
| Must-reads in the top ten | +3.9 points (-11.1 to +14.3) | -3.9 points (-11.1 to 0.0) |
| Kappa | **-0.102 (-0.159 to -0.041)** | -0.015 (-0.067 to +0.047) |

At its default effort Haiku 5.5 is not distinguishable from Haiku 4.5 on any measure here, at
about a sixth of the cost per call (it thinks first, so it writes about one and a half times
the output tokens). It is not shown to be better either: on this task, with these labels, the
honest reading is "the same, cheaper".

At low effort it is worse in one specific way. It scored labelled-relevant stories lower:
161 of 378 relevant judgements got a 2 or 3, against 206 for Haiku 4.5 and 202 for Haiku 5.5
at default. Its top ten is as good, so a ten-story digest would barely notice, but the
audiences that hide marginal stories (`min_rubric_score: 2`) would show fewer stories, and the
kappa difference excludes zero. Rejected, and the saving it would add over default effort is
a twentieth of a cent a call.

## What it changes

- `config/gateway/boundary.yaml`: `clippings-rerank` names `claude-haiku-5-5`.
- `rank/rerank.py` and `rank/spotlight.py`: larger `max_tokens`, because Haiku 5.5's thinking
  counts against the limit. Up to 4,614 output tokens were seen at sixty candidates.
- PLAN.md section 6: the re-ranking line falls from about US$0.013 to about US$0.002 an
  audience-day.

Days labelled before the switch were ranked by Haiku 4.5. They stay in the measurement: the
digest a labeller judged is the digest that was shown, and the comparison above finds no
difference in what either model puts in the top ten.

The three arms ran through a copy of this project's gateway configuration with three extra
routes and a ledger of its own, so the experiment's US$0.46 is not in the production ledger
or in any digest's cost.
