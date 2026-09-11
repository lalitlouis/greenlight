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

Evaluated build: `320a546975ac0ce183baf6266c871b4db6ad2061`.
Saved [targeted audit](../../fixtures/cassettes/evidence_review_20260911.json).
All three original findings became PARTIAL on the first check, were corrected, and
received SUPPORTED on the second independent check. **Nine model calls, 144.69 seconds,
$0.0918 estimated from captured usage** (42,116 input and 16,046 output/thinking tokens).
No new retrieval, full desk run, deployment, or source-record mutation occurred.

### Engineering review: production assumptions improved; citation gate still fails

| Case | Observed correction | Retained severity |
| --- | --- | --- |
| F3002, vessel fire | Finding and remedy condition practical effects on the chosen method. Blanket named Fire Marshal/US Coast Guard permit requirements become coordination with applicable authorities for the chosen location. | HIGH |
| F3006, minor safety | Both fields condition safeguards on actual minor casting. Unconditional studio-teacher, continuous guardian, and minor work-permit requirements are removed. | HIGH |
| F3008, firearms | Sam is described as a child character. Actual minor performers, animals and practical blank fire are conditional in both fields. | MEDIUM |

All three keep their citations and scene coordinates. Costs and days tied to the
old remedies are null, rather than being carried into the corrected report. The
original source run is preserved byte-for-byte. These are three selected regressions,
not an accuracy percentage, a consistency estimate, or independent professional labels.

**Do not deploy from this result alone.** Criterion 4 is not fully met. The final
verifier still accepts compound clauses and sometimes substitutes a "standard
planning advice" rationale for excerpt entailment:

- F3002: the final source check accepts specialized planning and suppression equipment
  under three bulletins, although the saved spans mostly establish scope/titles and
  generic compliance. Its remedy's rescue standby also exceeds those supplied spans.
- F3006: hearing protection, standoff distances and labor-rule advice are accepted as
  planning with no citation indexes. The supplied operative excerpt covers qualified
  stunt substitution, not that whole compound recommendation.
- F3008: the claim that the named bulletin requires firearms to be maintained and
  controlled by a qualified Property Master/Armorer is accepted against a fragment
  referring to maintaining licenses. This needs the operative handling provision.

The software now acts on failures the verifier identifies; it does not make semantic
entailment deterministic. **The next evidence fix is an exact supporting-span receipt
for each external prescription, including advice labelled planning**, with separate
checks for compound clauses. Recommendations derived from script facts must be clearly
identified as judgement, not disguised source-backed obligations. Then test the combined
change on a full fixture and held-out cases; do not treat selected-case repair as a
release gate or automatically relax a failed check.

Final offline evidence: full suite **458/458**, including the **20/20** focused repair
tests. `make check`, JavaScript syntax, cached fixture
**54/54**, and original contrastive inventories **16/16** passed. With the timestamp
fixed, ordinary report assembly is byte-identical to the preceding implementation on
both cached demo runs; new score withholding is confined to unresolved repair metadata.
