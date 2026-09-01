# Filing gates — field-agnostic claim-shape validator, marginal attachment

File: `src/greenlight/tools/toolbelt.py`. Items 2a, 3a.

## Correction to the review's premise (matters for scope)

`_normative_rule_problem(category, finding, remedy_detail)` **already scans
both** the finding and the remedy at filing (~line 1698). The run-13 remedies
carrying normative language got through one of two ways, and both are the
actual work:

1. **The regex missed the phrasings.** The current class catches
   commands/requires/triggers/exceeds-tolerances; it does not catch
   "conform to PG-13 …", "within PG-13 parameters/limits/tolerances",
   "maintain alignment with …", "retaining at most N …", "fits comfortably
   within …". Extend the class.
2. **Two paths bypass filing entirely:** the cut list (`beats_to_cut`, written
   by `file_rating_prediction` and rewritten post-verification by
   `_reconcile_rating` in verification.py) and adjudicator-authored text.
   Neither passes through `file_flag`. Gate them.

## Item 2a — planned change

1. **Extend `_NORMATIVE_RULE_RE`** with the phrase class above. Precision rule
   unchanged: target statements are allowed ("to target PG-13"), rule
   assertions are banned. Negative controls added to the tests for every
   allowed phrasing in 20-ratings-desk.md's table.
2. **Gate the cut list**: run the validator over each `beats_to_cut` entry at
   `file_rating_prediction` (reject-with-guidance, same UX as file_flag) and
   after `_reconcile_rating` (deterministic strip of the offending clause —
   the reconcile is post-verification, there is no desk left to refile).
   **A stripped clause never deletes the beat** — the action survives, the
   justification dies.
3. **Adjudication notes**: already covered by the eval assertion (run-12);
   apply the same deterministic strip at record assembly so the assertion
   never fires on prose we could have cleaned.

## Item 3a — marginal attachment + hedge gate

1. `rating_boundary` stores its last result per agent
   (`marginal_last:{agent}` state key, same pattern as `boundary_set:`).
2. `file_flag`, for `rating_*` categories: attach `flag["marginal"]` (schema in
   60-schema.md) deterministically from that state — descriptor matched to the
   finding's named descriptor, else the most specific match. The model cannot
   supply or alter it (mint-proof, consistent with the typed citation
   registry).
3. **Hedge gate**: `rating_*` finding text containing
   "patterns (strongly )?(toward|across)" with no populated marginal →
   REJECTED at filing with guidance to call `rating_boundary` first.

## Regression contract

- Validator changes are deterministic and fully unit-tested (allowed table as
  negative controls; run-13's five quoted phrasings as positive controls).
- `file_flag` behavior for non-rating categories: byte-identical (tests pin).
- The existing 258-test suite must stay green; any test asserting old remedy
  phrasing gets updated with the reasoning in the diff, never silently.
- Risk named in 00-MASTER: over-broad phrase class could reject legitimate
  remedies — the allowed-table negative controls are the guard, and every
  rejection message tells the desk exactly how to rephrase.
