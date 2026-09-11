# Claim and remedy evidence repair — September 11, 2026

Follow-up to the manually failed safety review of `run_20260911_demo.json`.
Frozen JSON schemas and Gemini/ADK/Parallel/ClickHouse architecture are unchanged.

## Implementation

- Live verifier responses must audit individual material assertions in the finding,
  remedy and severity. Checks distinguish script, production, source and planning
  claims; quote anchors and citation indexes are validated. A positive overall
  verdict cannot override a failed individual check.
- PARTIAL findings and failed production-assumption checks receive one bounded
  correction and one blinded independent verification. Only a supported correction
  is applied. The main panel, salvage and targeted retry share this path.
- Corrections preserve identity, coordinates and verbatim citations. Severity is
  reviewed against the surviving hazard; the old remedy's estimates are cleared.
- Unsuccessful repairs demote to open questions without repeating the unsupported
  obligations. They withhold the report score and do not enter a recovery loop.
- Repair/audit history is retained in verdict metadata. Existing saved reports keep
  their historical results, including their old PARTIAL findings.
- UI/PDF describe incomplete verification; UI cost totals disclose unknown estimates.
  A retry button is shown only when an unverified finding can actually be retried.

## Offline checks

Cached-source and scripted-response tests cover the F3008 false positive, F3006
condition loss, repair failures, input binding, immutable citations/coordinates,
stale estimates, score withholding, open questions, and parity across execution paths.
These tests verify mechanics, not model judgement. The cached original report still
passes its existing assertions plus two new repair invariants (54 total).
`make check` and the full suite passed: **457 tests**. JavaScript syntax and
`git diff --check` also passed.

## Preregistered targeted live check

Run `scripts/eval_evidence_review.py --live` once on F3002, F3006 and F3008 from the
saved original demo, using its matching screenplay and stored citation excerpts.
This deliberately does not rerun the desks or refresh retrieval: it isolates whether
the new verifier handles the already-observed errors. Runtime retrieval stays live.
Maximum three logical model calls per finding, 240-second deadline per finding;
transport retries are handled by the existing SDK policy. Output is a separate audit
artifact with build, source hash, verdict checks, corrected text, usage and cost estimate.
Expected expense is cents, with no full paid screenplay run in this batch.

Manual acceptance criteria:

1. Practical effects and named permit authorities are not treated as confirmed
   production facts. Any applicable precautions retain method/jurisdiction conditions.
2. Child-character age is not asserted as performer age. Minor-performer safeguards
   stay conditional in both finding and remedy.
3. Supported depicted hazards survive with an appropriate severity, or remain explicit
   open questions if the supplied citations cannot support a repair.
4. The revised requirements are entailed by the supplied excerpts. A SUPPORTED label
   is not itself proof. No stale cost/schedule estimate follows a changed remedy.

No deployment or claim of overall accuracy/consistency from three selected failures.
A full combined gate and held-out professional review remain release prerequisites.

## Results

Pending targeted evaluation.
