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

### Attribution and latency follow-up plan

On the next authorized continuation, run five isolated entailment probes using the
unchanged source excerpts: conditional minor entitlement with attribution (positive),
license/firearm substitution (negative), required dry run (negative), walk-through
and/or dry run preserved (positive), and a scope heading used to demand a permit and
specialist (negative). Expectations are frozen in
`fixtures/accuracy/entailment_cases_20260911.json` before the live calls, never sent to
the model, and are developer-authored excerpt checks rather than expert accuracy labels.
One call per case; malformed/unavailable responses cannot count as correct rejection.

Also allow one instrumented F3008 continuation reusing its returned first PARTIAL
audit, at most three calls (correction, independent audit, independent entailment).
This adds latency evidence instead of repeating its successful audit. Keep the
240-second per-case deadline and runtime settings. The two follow-up checks together
are at most eight additional logical calls, expected captured usage below $0.15;
transport retries and interrupted charges remain outside that estimate. This new
five-case diagnostic set is additional to the earlier three-finding gate budget.

The evaluation harness now saves a sidecar after each call starts and finishes,
including response schema/stage, elapsed time, input length/hash and returned/error/
cancelled status. Timings measure client-observed calls including SDK retries, not
server inference time; do not infer a server root cause from them. Runtime code,
timeouts and schemas are unchanged. No broader paid run until the results are reviewed.

### Follow-up results and coverage correction

Build `b52fb63` passed 481 offline tests and `make check`. The
[five entailment cases](../../fixtures/cassettes/entailment_cases_20260911.json) matched
all pre-registered expectations in 54.42 seconds, five calls, $0.0086 captured-usage
estimate. The original attribution false rejection was absent; the three unsupported
prescriptions were rejected. This is a selected diagnostic result, not overall accuracy.

The [instrumented firearms correction](../../fixtures/cassettes/firearms_timing_20260911.json)
returned in 53.69 seconds; the subsequent audit returned in 9.01 seconds. The candidate
removed the unsupported requirements. The audit marked its clauses SUPPORTED, but our
deterministic coverage check rejected the connective **and that** between two quoted
clauses as omitted material. Secondary entailment never ran. This is another false
rejection; it is not evidence that the narrowed candidate is unsupported.

Coverage now allows only `and`/`and that` (with punctuation/whitespace) in an otherwise
empty gap bounded on both sides by audited text. It still rejects leading/trailing
fragments, missing prescriptions, `or`, exceptions, conditions and negation. Exact
source receipts and independent semantic review still apply to each audited claim.
Regression tests include the saved real failure and negative omission variants.
Frozen schemas and source text are unchanged.

Complete only the previously skipped secondary review of the unchanged saved candidate,
using the eighth reserved call. The evaluation verifies the source hash and current
claim audit before spending; it refuses a correction whose secondary review already
completed. Do not regenerate the correction or repeat its successful audit. Nothing
here establishes the cause of previous transport latency or justifies larger timeouts.

Upstream follow-up identified during the wait: safety desk instructions demand specific
staged-gag methods and rule-of-thumb estimates while separately requiring retrieved
support. Resolve that instruction conflict and use the existing `fetch_page` capability
when excerpts are only scope headings; measure whether fewer unsupported filings and
repairs result. This is still proposed work, not part of these verifier changes.

The coverage fix passed the full 490-test suite; after extracting its helper for lint,
all 52 focused evaluation/evidence tests and `make check` passed. Build `51d7e82`
then completed the [skipped firearms review](../../fixtures/cassettes/firearms_entailment_20260911.json)
in 7.62 seconds and one call, $0.0049 captured-usage estimate. Both source clauses
passed; manual comparison found no remaining unsupported specific duty. The changed
remedy keeps costs/days null. All eight reserved follow-up calls returned usage;
their summed estimates total $0.0362 (not invoice reconciliation).

With the selected evidence checks complete, start the previously planned single full
SLACK TIDE gate at build `51d7e82` on September 11, 08:47:37 UTC, normal runtime
settings and live integrations, maximum 40 minutes. This is the first full run of the
support-span changes. Keep the original September 11 demo as the comparison record.
Do not equate fewer findings or a withheld score with better accuracy; manually inspect
supported hazards, lost findings, open questions and citation entailment after the
unchanged mechanical evaluation. The full-run cost field still omits direct verification
calls and cannot be reported as total spend.

### Full gate: failed, do not release

[Saved full run](../../runs/run_20260911_015915.json), build `51d7e82`, completed
without a runtime error in 697.9 seconds (11m38s), versus 396.9 seconds for the saved
earlier baseline. That is one run of each build, not a controlled latency benchmark.
The normal model/desk budgets were unchanged. Live search and corpus queries ran.
The recorded $1.4026 cost excludes direct verification calls and is **not total spend**.

The unchanged eval passed **45/54** checks. It missed seven clearance seeds, the China
supernatural seed and the rejection-rate ceiling: **6 kept, 16 rejected from 22 filed**.
All nine filed clearance findings were rejected. This is a release-blocking completeness
failure. Do not weaken the seed checks or call a smaller report more accurate.

The deterministic safety behavior worked: 16 sourcing failures became explicit open
questions; failed corrections do not render; the score and all dimension scores were
withheld (`greenlight_score=null`, `dimension_scores={}`, `verification_degraded=true`).
Costs and days are unknown, not stale estimates. Counts, scenes, comparables and
entity dispositions passed the unchanged invariants. Three ratings findings, vessel
fire, firearms and UAE drug-content concern survived. These six findings still require
the following product-quality qualifications; model approval alone is insufficient.

Manual findings:

- **Severity review bug (fixed after this run):** F1001's first auditor voluntarily
  supplied a citation for HIGH. The source-only reviewer then rejected HIGH because
  the word was absent from the excerpt. Severity must stay with the script-aware
  judgement layer even when a model attaches a receipt. The secondary batch now
  excludes severity by field, not merely by missing receipts. This fixes that spurious
  reason, not the independent problems in F1001's remedy.
- **Irrelevant remedies:** five of six kept findings use the exact production-input
  inquiry, including all three ratings findings and the UAE finding. Casting and
  shooting method do not address a target-rating edit or distribution restrictions.
  The inquiry escape hatch preserved text at the expense of usefulness. All six
  actions are NO_ACTION, even the firearms remedy prescribing safety work. This is
  not a satisfactory producer-facing result.
- **Mixed evidence and derived edits:** F3002 combines depicted hazards with source
  rules; the source-only reviewer complains the excerpts do not establish the depicted
  fire/watercraft. F1001 is criticized for naming JAWS/TV playback, which are script
  facts, alongside an independently questionable replacement prescription. F4001's
  proposed edit is rejected because the source describes an exception without literally
  instructing an editor to use it. These need separate evaluation of script facts,
  external rules and proposed edits, not a blanket exemption for planning advice.
- **Genuine retrieval gaps:** F1010's source says Columbia is part of Sony but does
  not connect that label to the selected recording; F1005's short excerpt says
  Whitmill sued over a design without identifying it as a tattoo; F3005 ends at
  'all aspects of'. The ownership link and operative clauses must be retrieved.
- **Receipt formatting failures:** F3006's requested support span omits a literal
  `###` embedded in the supplied excerpt; F1008 omits Markdown links/emphasis.
  Exact receipt validation rejects both before semantic review. Any future fix must
  map a display-text match back to an exact raw-source span, preserving words and
  negations; do not accept free paraphrases or rewrite the saved excerpt.
- **Conditional remedy loss:** F3007's corrected approval requirement drops the
  condition that an animal is in/around water, extending it to any water scene.
  That rejection is substantively warranted by the supplied excerpt.

Next batch, before any further full run:

1. Define separate evidence handling for a source rule, verified script application,
   proposed content edit and unknown input. Keep specific production duties and
   ownership assertions strictly sourced. Replace the universal production inquiry
   with desk-relevant, useful uncertainty handling; align action labels with the prose.
2. Add positive/negative cached cases from these clearance and ratings failures,
   including edits that remove a cited trigger without claiming guaranteed clearance
   or a guaranteed rating. Include mixed script/source assertions and severity receipts.
3. Resolve conflicting safety instructions and retrieve full operative passages using
   the existing Parallel tools. Diagnose formatting-only receipts independently of
   semantic support. Meter direct verifier work before claiming a total run cost.
4. Batch those changes, run free checks, then a small pre-registered live comparison.
   A new full gate is justified only after it preserves supported findings **and**
   rejects unsupported prescriptions with useful remedies. No deployment from this run.

Final free checks after the severity fix: **491 tests passed**, `make check` and
`git diff --check` passed. The new full record has the same screenplay SHA-256 and
identical parsed scenes as the baseline. All 16 rejected ids occur in its open
questions. No further paid check or full run followed the failed gate; the severity
exclusion has offline regression coverage but has not been live-tested separately.
