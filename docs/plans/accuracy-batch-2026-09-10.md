# Safety and ratings accuracy batch — September 10, 2026

Pre-registered before the live fixture run. Runtime remains Gemini/ADK with live
Parallel retrieval and ClickHouse comparisons. Frozen schemas are unchanged.
Session-only language inventory gains dialogue/action token-and-scene pairs.

## Changes under evaluation

- Safety and verification share the distinction between story facts and production
  facts. Preserve depicted hazards; do not derive permit violations, performer age,
  practical ammunition/effects, or insurer decisions from the screenplay.
- Safety blockers require confirmed production facts. Fictional missing-permit
  dialogue alone is not a blocker. Child-character hazards retain casting/staging
  questions with conditional minor-performer safeguards.
- Ratings and verification share a channel/presentation/evidence contract. The
  worklist distinguishes dialogue from action inventory; action may describe visible
  text or audio, so neither automatic inclusion nor blanket exclusion is valid.
- Rule claims remain admissible beside operative MPA rule text with exceptions;
  marginal-only rule claims remain inadmissible. Cut lists remain actions, not rules.
- Sixteen original contrastive cases and an offline evaluator are added. Their labels
  are engineering expectations pending professional review. Offline passing checks
  do not establish desk accuracy.

## Offline gate

1. `make check` and the entire unit suite with cloud credentials disabled.
2. All 16 original case inventories pass; voiceover counts as dialogue, visible text
   and nonspoken description do not enter the dialogue-only count.
3. Before/after parser output, whole-text census and spoken count are identical on
   `slack_tide.fountain` and `scale_gate.fountain`. No scene structure changes.
4. Existing cached demo still passes the 52 fixture checks.

## One live fixture gate

Run the unchanged original `fixtures/slack_tide.fountain` once using configured models
and normal research budgets. Record commit identity, full logs and output. Expected
cost is roughly $2–5 from prior records, not a guaranteed invoice; use a 40-minute
outer time limit. Do not silently change models, mock retrieval, or repeat a full run.

Predictions and review criteria:

- No error/salvage, no unexamined work, no collapsed desk, complete verification.
- Existing 52-check fixture eval passes. Any failure is recorded; do not relax it to
  get a green result.
- Scenes and whole-text/dialogue profanity counts remain unchanged (three dialogue
  F-word uses at S003/S006/S011).
- The vessel burn and other meaningful safety hazards remain findings. No safety
  BLOCKER or assertion of actual production noncompliance rests on fictional permit
  dialogue. Sam's character age is not asserted as confirmed performer age.
- Ratings predicts R or explicitly records uncertainty including R; no guarantee
  that cutting two words alone earns PG-13. Rule assertions quote the operative rule
  and retain the exception. Drug references and depicted use remain distinguished.
- Compare citation support, retained serious hazards, open questions, recovery work,
  cost and elapsed time with the cached baseline. The baseline spans a different
  build and evidence date; this is a smoke gate, not a controlled accuracy uplift.

No automatic deployment. Any live access failure is a blocked validation, not a pass.
The 16 miniature cases are not 16 extra paid runs; independent professional labelling
and a separately budgeted model evaluation remain follow-up work.

## Read-off

Pending.
