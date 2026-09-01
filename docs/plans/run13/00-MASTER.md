# Run-13 batch — master plan

Seven feedback items from the run-13 review, planned before any code changes.
Each component doc states: current behavior (file:line), the defect, the planned
change, the regression contract, and the test plan. Nothing here is built yet.

## The one rule this batch keeps applying

The rule-vs-observation contract, now applied to its third and fourth fields:
**a text field may state what was measured or what to do — never a rule or a
completed action nothing backs.** Ratings findings learned it in run 12 (filing
gate). This batch extends it to remedies, the cut list, and cleared-path
determinations ("negative check confirmed" with no research receipt).

## Sequencing (reviewer's, adopted)

1. **Item 4 first** (coordinate completion moves upstream) — it changes what the
   audit manifest would record, so building the manifest first would audit
   behavior about to be replaced.
2. **Item 5 second** (guard manifest) — audits the new upstream behavior.
3. **Items 2 + 3 batched** — same validator (`_normative_rule_problem`) and same
   renderer (`report.js` citation block) touched by both.
4. **Items 1, 6, 7 anytime** — independent, deterministic, cheap.

One gate at the end carries the whole batch (owner runs it). `make check` /
`make test` after every step — free.

## Component docs

| Doc | Items | Files touched |
|---|---|---|
| `10-verification.md` | 4, 5, 2b, 6b | `src/greenlight/agents/verification.py` |
| `20-ratings-desk.md` | 2c, 3b | `src/greenlight/agents/ratings_board.py` |
| `30-filing-gates.md` | 2a, 3a | `src/greenlight/tools/toolbelt.py` |
| `40-cleared-path.md` | 1, 6a | `src/greenlight/entity_accounting.py`, `src/greenlight/pipeline.py` |
| `50-renderer.md` | 3c, 6c, 6d, 7 | `web/static/report.js`, `src/greenlight/report.py`, `src/greenlight/binder.py` |
| `60-schema.md` | 3 (fields) | `schemas/flag.schema.json` — **announced schema change** |
| `70-title-and-record.md` | 6e | `src/greenlight/server.py`, `src/greenlight/pipeline.py` |

## Global regression contract

Per CLAUDE.md's determinism contract, split every change into its two layers:

- **Deterministic layer** (validators, suppression, schema, renderers, manifest,
  cost attribution): byte-identical outputs on unchanged inputs, verified
  before/after against the cached fixture run (`runs/run_20260831_221057.json`)
  and pinned with unit tests. No regressions, promised.
- **Desk/verifier output** (prompt additions in 2b/2c, the upstream widening's
  effect on verdicts): non-deterministic; the eval seeds and the new assertions
  are the mechanical checks. No run-to-run stability promised — claims about
  these land as eval checks, not assurances.

## Predicted failures to budget, not read as regressions

- **Item 3's hard gate may drop rating findings to zero** on the next run if the
  structured marginal fields don't populate. That is the designed failure —
  visible instead of three more runs of "plumbing works, nothing came out."
  A dropped rating finding demotes to an open question; it never silently
  vanishes (absence must not render as clean).
- **Item 2's cut-list gate may shorten the cut list.** A stripped justification
  clause is correct behavior; a *vanished cut* is a defect — the gate rewrites
  or strips clauses, it never deletes a beat.
- **Item 4 may change verdicts on findings whose windows were previously
  too narrow** — that is the point. The manifest (item 5) makes each such
  change auditable.

## Invariants added to the eval by this batch

- Clearance log emits exactly one row per scene (85 on the current Hangover
  draft; asserted as `rows == scenes`, not a literal count).
- No cleared determination asserts completed research without a research
  receipt for that entity.
- No rating finding renders without its structured marginal (the hard gate,
  restated as an assertion).
- Rendered header counts equal rendered list lengths (no independently
  computed pair may disagree).
