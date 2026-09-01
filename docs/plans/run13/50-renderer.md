# Renderers — marginal block, count derivation, complete clearance log, cost attribution

Files: `web/static/report.js`, `src/greenlight/report.py`,
`src/greenlight/binder.py`, `src/greenlight/pipeline.py` (hard gate),
`scripts/eval_run.py` (new assertions). Items 3c, 6c, 6d, 7.

## Item 3c — marginal renders inside the citation block, hard-gated

### Current behavior
The marginal exists as a citation excerpt (when the desk copies it and the
prune keeps it). Three runs shipped rating findings whose evidence never
rendered as a number. The kNN panel proves the data pipeline works (8-of-8,
51.6% base rate print fine) — this is schema + renderer, not retrieval.

### Planned change
1. `report.js` `citationCard` / the rating finding block prints the structured
   `flag.marginal` (60-schema.md): descriptor, per-rating distribution, n,
   base rate — inside the citation block, labeled as the ScriptRisk CARA
   descriptor corpus (self-citation label rules from run-12 stand).
2. **Hard gate at record assembly (pipeline.py)**: a `rating_*` finding with a
   null/absent `marginal` does not render as a finding. It **demotes to the
   desk's open questions** with honest text ("rating driver filed without a
   measured marginal — rerun with rating_boundary") — never a silent drop
   (absence must not render as clean), never a warning. Manifest-recorded.
3. The eval gains the assertion: every rendered `rating_*` finding carries a
   populated marginal.

### Predicted failure (budgeted in 00-MASTER)
If the fields don't populate on the next run, rating findings drop to zero and
the open-questions section says why. That is the designed, visible failure.

## Item 6c — header counts derive from rendered lists

### Current behavior
The cleared header count is computed independently of the rendered list
(59 vs 60 in run 13). Any pair of "computed here, rendered there" numbers can
drift.

### Planned change
`report.js`: every header count derives from the **length of the list actually
rendered** beneath it (cleared, findings, rejected, open questions). The
accounting object still ships in the record (it feeds other surfaces); the
rendered header just stops trusting it over its own list. Eval assertion:
header == list length is unenforceable from Python for a JS render, so the
rule lands as a code invariant + a comment naming the 59-vs-60 incident;
`entity_accounting` reconciliation (distinct = shown + suppressed) is asserted
in the eval instead.

## Item 6d — clearance log emits every scene

### Current behavior
`binder.py` builds rows from findings and determinations; a scene with neither
can vanish (S050 missing in run 13) — contradicting the log's scene-by-scene
premise.

### Planned change
The binder iterates **scenes**, not findings: every scene emits exactly one of
finding row(s) / "No known issue" / "Not affirmatively cleared" /
"NOT EXAMINED". Assertion (unit test + eval): `rows == len(scenes)` — written
as a derived equality, never a literal 85.

## Item 7 — cost-delta attribution

### Current behavior
`report.py` `_cost_paths` (~line 50) computes target vs as-written totals via
`cost_excluded_on_target_path`; the delta renders unexplained.

### Planned change
1. `report.py`: `est_cost_paths` gains `excluded` — a list of
   `{flag_id, category, est_cost_usd}` for every excluded flag (additive,
   optional; announced in 60-schema.md alongside the flag change).
2. `report.js`: one line under the two-path totals — "Difference is F1012
   (NIN sync, $40k–$80k) — excluded on the target path", composed from the
   structured list, never free text. Multiple exclusions render as a short
   comma list.
3. Unit test: sum(excluded ranges) == as_written − target, to the dollar —
   the math already ties; this pins the attribution to it.

## Regression contract
All renderer changes are deterministic. Before/after on the cached fixture
record: identical rendered content except (a) the marginal block appears,
(b) counts that already agreed stay identical, (c) the one attribution line
appears. `binder` row-count change is the intended fix; the test pins it.
