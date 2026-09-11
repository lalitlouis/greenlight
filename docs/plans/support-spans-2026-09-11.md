# Supporting-span verification — September 11, 2026

## Problem and change

The preceding targeted review corrected casting/staging assumptions but still approved
uncited prescriptions as planning advice. Verifier checks now require verbatim support
spans for external claims and every remedy prescription. Citation indexes and spans must
agree, and the spans must occur in their own excerpt. This checks provenance only.

A separate Gemini batch judges entailment from each claim, its spans and full excerpt
context, with no screenplay, severity or previous reasoning. Every check must return
once; a missing, repeated or invented check is unresolved verification. Unsupported
clauses go through the existing single repair and independent re-check. No new retrieval
is introduced, and live Parallel remains the runtime default.

Coverage validation also catches text omitted from the audit. Only a fixed question
requesting casting, jurisdiction and staging method may serve as an uncited remedy;
it cannot include a hidden prescription. Semantic atomicity and entailment still require
judgement. No regex can prove those properties.

Frozen report/flag schemas, parsers, model tiers and report arithmetic are unchanged.
Internal ClaimCheck gains required support_spans; new verdicts carry support_span_version=1.
Historical records keep their recorded verdicts.

## Validation plan

1. Free checks: full unit suite, lint/dependency scan, existing cached fixture gate,
   original contrastive inventories. Regression tests cover planning relabelling,
   forged/paraphrased/wrong-source spans, omitted obligations, inquiry abuse, secondary
   review failure and the five-call correction bound. No live unit tests.
2. One targeted paid check of F3002, F3006 and F3008 from the saved original demo, using
   its exact screenplay and stored citations. At most five logical model calls per
   finding, 240 seconds per finding, expected expense below $0.25. SDK transport retry
   policy remains unchanged. Save raw model responses as well as processed verdicts.
3. If the targeted manual review passes, one full SLACK TIDE run with normal budgets
   and live Gemini, Parallel and ClickHouse, with the existing 40-minute outer limit.
   Historical cost is $2–5, not an invoice guarantee. Evaluate without relaxing checks.

Acceptance: no unsupported specific permit/teacher/equipment duties survive; source
receipts match the actual duty and object, not a title or a related topic. Casting,
method and jurisdiction conditions persist in remedies. Real hazards survive with
supported narrower remedies or explicit open questions. Failed verification withholds
the score. A reference to maintaining licenses must not justify maintaining firearms.

No automatic deployment; neither selected examples nor a fixture run establish overall
accuracy or repeat-run consistency. A source-insufficient case is an unresolved case,
not a successful negative or a report of cleanliness.

## Results

Initial build `1803d58`: 474 offline tests, lint/dependency checks, cached fixture
54/54, and deterministic contrastive inventories 16/16 passed.

The [first targeted attempt](../../fixtures/cassettes/support_spans_20260911.json)
made four logical calls and took 492.53 seconds. F3002 was correctly rejected because
the stored snippets do not establish its operative production requirements. F3006's
first audit returned PARTIAL and identified the unsupported teacher, guardian, acoustic,
permit and other requirements; its correction request timed out. F3008's first request
also timed out. Both hit the 240-second case limit. **Not a completed live gate.**

Only two responses returned token usage: $0.0247 estimated for those responses.
The two interrupted calls may also incur charges; that figure is not total spend.

Inspection found an output-format conflict: the correction prompt inherited the
verifier's instruction to return claim_checks while asking for a CorrectedClaim.
Remove that conflict. It is a real prompt defect, but the trace does not prove it
caused either timeout (one timeout happened on an initial audit).

Resume only F3006/F3008 once after offline checks, reusing the completed same-source
PARTIAL audit for F3006 and restarting only the missing audit for F3008. Source hashes
must match; completed/rejected cases cannot be resumed. This continuation needs at
most eight more logical calls, so the combined targeted work remains below the original
15-call budget. Keep the existing per-case deadline. Log individual stages and save
their responses. No full fixture until the targeted manual review is complete.

Accounting limitation found during review: the full pipeline's current cost_usd is
derived from ADK events, which omit direct verifier/repair/entailment calls. Its estimate
must be described as incomplete; the targeted harness meters returned direct-call usage.

### Bounded continuation and attribution defect

The [continuation](../../fixtures/cassettes/support_spans_resume_20260911.json), build
`a8267d4`, took 265.81 seconds and made five calls. F3006 completed in 25.78 seconds;
F3008's correction hit the same 240-second deadline. Combined: nine logical calls,
six returned responses, three interrupted calls. Captured usage estimates sum to
$0.0581; interrupted calls may incur additional charges. No further paid runs started.

Manual review changes the interpretation of F3006: its correction removed the
unsupported requirements and retained only the conditional stunt-person entitlement
in the SAG-AFTRA excerpt, plus the fixed production inquiry. The independent reviewer
rejected it **solely because the excerpt body did not name SAG-AFTRA**. We had omitted
the stored title and URL from its input. That is a missing-context false rejection,
not successful detection of another overbroad remedy. Withholding the score was the
correct handling of a failed review, but discarding the supported narrower claim is
an accuracy loss.

Fix: send each receipt's citation title/URL as separate source-attribution metadata.
The title/URL can identify the source; operative rules, duties, precautions and
applicability must still be established by the excerpt. Do not infer endorsement
from a title alone. The reviewer remains blinded to screenplay facts and previous
reasoning. Frozen schemas, source excerpts and model-call budgets remain unchanged.
Regression tests replay the saved correction to check the previously missing input
and isolation, and reject metadata used as an excerpt receipt. Scripted model replies
test wiring only; they do not establish semantic accuracy.

F3008's returned first audit correctly rejected the license/firearm substitution and
unsupported buffers. However, its positive checks still strengthen 'walk-through
and/or dry run' into a required dry run. Correction and secondary review did not
complete, so this case remains unresolved. Do not mark the targeted gate passed or
start the full fixture. Next live validation must include the attribution fix and
both positive and negative entailment cases; repeated correction timeouts also need
stage-level latency evidence before expanding runtime budgets or retrying broadly.

Attribution-fix offline validation: 477 tests passed (39 focused evidence-review
tests), `make check` and `git diff --check` passed. No paid validation of the new
attribution input has run; its semantic effect remains unmeasured.
