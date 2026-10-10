# Which model does which job

Two comparisons, both on 2026-10-10, both against the stored days rather than assumed from a
vendor's description. The re-ranker moved to Haiku 5.5; the summariser stayed on Sonnet 5.5.

## The re-ranker: Haiku 4.5 to Haiku 5.5

Decided 2026-10-10. The re-ranker, and the Bluesky pick that shares its route, moved from
Claude Haiku 4.5 to Claude Haiku 5.5 at its default effort. Haiku 5.5 at low effort was tried
and rejected.

### Why it was a question

Haiku 5.5 was released on 2026-10-07 and the gateway priced it from 1.2.0: US$0.10 in and
US$0.50 out per million tokens, against Haiku 4.5's US$1 and US$5. A tenth of the price is
only worth having if the ranking does not get worse, and the ranking is the stage this
project's precision and recall depend on, so it was measured before the switch rather than
assumed from the vendor's description.

### Method

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

### Result

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

### What it changes

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

## The summariser: Sonnet 5.5 stays

Decided 2026-10-10, after the re-ranker's result raised the obvious next question: if Haiku 5.5
ranks as well as Haiku 4.5, does it also write as well as Sonnet 5.5, at a thirteenth of the
cost per story?

### Method

Every story shown in a stored digest up to 2026-10-10 (131 stories across fourteen
audience-days; 106 that both arms completed are compared, the rest share a story id with
another day) was summarised again by each arm from its stored sources, with the production
prompt, then verified, repaired once where the verifier refused a sentence, and verified
again, exactly as a run does (`summarise/run.py`). Sonnet 5.5 kept its production limit of
700 output tokens; Haiku 5.5 was given 4,000, because its thinking counts against the limit,
and no reply from either arm reached its limit. One draft per story per arm. Intervals are 95%
bootstrap intervals over stories, and the differences are paired. US$0.74 in all.

### Result

| Measure | Sonnet 5.5 | Haiku 5.5 | Haiku minus Sonnet |
|---|---|---|---|
| Cost per story | US$0.0052 | US$0.0004 | -US$0.0048 |
| Story with no summary at all | 0.0% | 7.5% (2.8 to 13.2) | **+7.5 points (+2.8 to +13.2)** |
| First-draft sentences passing the verifier | 99.7% | 98.9% | -0.8 points (-1.9 to 0.0) |
| Sentences shown per story | 2.79 | 2.54 | **-0.25 (-0.42 to -0.11)** |
| Words shown per story | 85.2 | 77.5 | **-7.7 (-13.2 to -2.5)** |
| Quotes per story | 0.25 | 0.12 | **-0.12 (-0.22 to -0.05)** |

Every one of Haiku 5.5's empty stories is a reply the parser could not read (ten with no JSON
object, two with no sentence list), not a sentence the verifier refused: the model did not keep
to the answer format, and a run would show "summary failed" for about one story in thirteen.

The verifier passes nearly everything either model writes, which says the checks are kept, not
that the summaries are equally good. Read side by side, Haiku 5.5 adds sentences of its own
interpretation that cite a source but say what no source said ("For the AI industry, this is a
sign that frontier labs are formally embedding their models into US government science
programs"). The verifier cannot refuse such a sentence: it has no number and no quote, and it
does cite. A crude count of sentences of that shape ("This is a sign that", "For readers
...", "underscores", "highlights") finds 8 of Haiku 5.5's 327 shown sentences and 1 of Sonnet
5.5's 366. That count is a pattern match, not a judgement, and it is the reason the
faithfulness sample in PLAN.md matters.

Rejected. The saving is about US$0.05 an audience-day, roughly CA$6 a month for four
audiences, and it would buy failed summaries, shorter ones, fewer quotes, and more sentences
the verifier is blind to. A prompt or a structured-output mode might fix the format failures;
it would not settle the interpretive sentences without a human read, and at CA$6 a month that
read is not worth anyone's time.
