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

Completed September 11, 2026 against build
`6438de520c929a576aac0824dd7d730788c1819e`.

**Automated gate: PASS. Manual release review: FAIL. Not deployed.**

Saved record: [run_20260911_demo.json](../../runs/run_20260911_demo.json), an
unchanged copy of local `runs/run_20260911_001339.json`. Local execution log:
`.cache/accuracy/live_gate_20260911_070702.log`. The run used live Gemini, Parallel
and ClickHouse; no model or research-budget override was introduced for the gate.

### Checks and measured results

- `make check` passed; the full offline suite passed **438 tests**.
- All **16/16** contrastive parser/inventory checks passed. These do not measure
  model accuracy; the miniature scripts were not sent through the live desks.
- Parser output and existing counts were unchanged on both real fixture files
  (12 scenes for SLACK TIDE, 100 for the scale fixture, three dialogue F-word uses
  each). Live SLACK TIDE scene metadata also matched the cached baseline exactly.
- `scripts/eval_run.py runs/run_20260911_demo.json` passed **52/52** checks.
- No run error, incomplete desks, unexamined entities, or research failures.
- Elapsed time **396.9 seconds**; estimated model/API cost **$1.7117**. This is the
  run record's estimate, not a reconciled cloud invoice.
- Final report: **22 findings**, with 0 BLOCKER, 9 HIGH, 6 MEDIUM, 6 LOW, 1 FYI.
  The verifier recorded 11 SUPPORTED, 12 PARTIAL and 1 UNSUPPORTED before final
  reconciliation. One recovery was attempted and did not recover the watercraft
  claim; it remains an open question. Counts at different stages are not directly
  interchangeable because reconciliation merges findings.
- The vessel burn and cold-water dive remain HIGH. The fictional missing-permit
  dialogue no longer produces a safety BLOCKER in this run.
- Ratings predicts R, retains PG-13/R uncertainty, records three dialogue uses,
  and preserves the special-vote exception. The proposed cuts do not explicitly
  guarantee PG-13. This is a forecast, not evidence of the eventual official rating.

The older baseline (`run_20260902_221612.json`) took 1,896.5 seconds and estimated
$4.9425, with four recovery attempts/two recoveries. Those observations are useful
for budgeting but **do not establish a speed, cost or accuracy improvement**: builds,
retrieved evidence and desk decisions differ. One run also cannot measure consistency.

### Manual failures the automated gate missed

| Finding | Observed defect | Why it fails this batch's criteria |
| --- | --- | --- |
| F3002, vessel fire, SUPPORTED | Asserts practical execution and unconditional permits from named authorities; its remedy commits to practical rigs. | The production method and shooting jurisdiction are unknown. The separate open question acknowledges this uncertainty without qualifying the finding and remedy. |
| F3006, minor safety, PARTIAL | Finding correctly starts with a child character and conditional casting; the remedy unconditionally requires a studio teacher, guardian and minor work permits. | Conditions must survive into the remedy. The cited excerpts also do not establish every asserted obligation. |
| F3008, firearms, SUPPORTED | Refers to safeguarding the minor performer. | The script establishes Sam's character age, not the performer's age. The verifier accepted the transfer despite the shared evidence instructions. |
| F3001/F3011, water safety, PARTIAL | Verifier identifies specific safeguards that the excerpts do not support; the original requirements remain in the report. | A PARTIAL label alone does not correct unsupported clauses or their cost implications. |

These failures do not negate the underlying depicted hazards. They demonstrate that
shared instructions and overall finding-level verdicts are insufficient to enforce
the evidence boundary. A 52/52 fixture pass must not be described as 100% accuracy
or as satisfying this manual release gate.

### Next bounded implementation

1. Verify the material assertions in both the finding and remedy: script fact,
   production assumption, cited obligation, and suggested precaution. Preserve
   casting/method/jurisdiction conditions across both fields.
2. Give partially supported compound findings a bounded correction and independent
   re-verification pass. Unsupported requirements must be removed or qualified;
   failure to repair must remain visibly unresolved rather than silently clear.
   Retain supported hazards and review severity/cost whenever the remedy changes.
3. Pin the failures above with cached-response tests, including the fully SUPPORTED
   F3008 mistake, condition loss in remedies, and repair/verification failure paths.
   Test renderer and accounting behavior, not just the presence of prompt text.
4. Then budget targeted live safety validation and repeated contrastive runs.
   Independent professional labels remain necessary before claiming desk accuracy.

No second paid full run was performed. This read-off preserves the evaluated build;
it does not add unvalidated prompt changes after the gate.
