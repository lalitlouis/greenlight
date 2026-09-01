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

1. **Extend `_NORMATIVE_RULE_RE`** with the phrase class above — **every new
   pattern anchored to a rating token** (PG-13/R/G/NC-17/CARA). "within PG-13
   parameters" is banned; "within swimwear coverage" (a legitimate wardrobe
   remedy, quoted from run 12's F2004) must pass. Negative controls added to
   the tests for every allowed phrasing in 20-ratings-desk.md's table PLUS the
   wardrobe class.
2. **Gate the cut list**: run the validator over each `beats_to_cut` entry at
   `file_rating_prediction` (reject-with-guidance, same UX as file_flag) and
   after `_reconcile_rating` (deterministic strip of the offending clause —
   the reconcile is post-verification, there is no desk left to refile).
   **A stripped clause never deletes the beat** — the action survives, the
   justification dies. And because clause-stripping from free text is fragile
   (the run-12 redact attempt proved it): when the strip cannot cleanly excise
   the clause (dangling punctuation, the clause IS the beat), the beat ships
   **unmodified** and the miss is manifest-recorded — fail visible, never
   mangle silently.
3. **Adjudication notes**: already covered by the eval assertion (run-12);
   apply the same deterministic strip at record assembly so the assertion
   never fires on prose we could have cleaned.

## Item 3a — marginal attachment + hedge gate

1. `rating_boundary` stores its last result per agent
   (`marginal_last:{agent}` state key, same pattern as `boundary_set:`).
2. `file_flag`, for `rating_*` categories: attach `flag["marginal"]` (schema in
   60-schema.md) deterministically from that state. Selection rule when the
   last boundary call matched several descriptors: pick within the flag's
   **category family** (rating_language → the language-family descriptors, via
   the existing vocabulary's category map), most specific match first
   ("pervasive language" over "language"). A flag whose category family has no
   match in the last call gets a null marginal — and the hard gate
   (50-renderer.md) makes that visible. The model cannot supply or alter the
   field (mint-proof, consistent with the typed citation registry).
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
