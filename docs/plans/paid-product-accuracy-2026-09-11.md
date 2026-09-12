# Accuracy plan for a paid GREENLIGHT product

Decision date: September 11, 2026. Planning document; no runtime changes or paid
evaluations in this turn. Proposed thresholds below are product decisions to validate,
not achieved results or industry standards.

The objective is a useful report a producer can act on: correct observations, correctly
applied current evidence, useful remedies, honest estimates, and visible unresolved work.
Suppressing every difficult finding is not success. A longer report is not success either.

## Current evidence and why the previous approach was insufficient

The latest full release gate remains 45/54, failed. The two fresh desk diagnostics both
failed manual accuracy review. There are 545 passing software tests, but they do not
establish a report accuracy percentage. The current manual labels are developer-authored,
not independent professional validation. See [the diagnostic record](fresh-desks-2026-09-11.md)
and [hash-bound manual outcomes](../../fixtures/cassettes/fresh_desks_manual_review_20260911.json).

| Observed failure | What the implementation currently permits | Why the patch was insufficient |
| --- | --- | --- |
| JAWS was assigned a licensor, talent obligations and a price absent from the cited excerpts. | Desks produce a free-form finding, remedy and numeric estimates. Older instructions demanded ownership leads and rule-of-thumb prices. | Adding evidence warnings did not remove all contradictory instructions. Those contradictions have now been removed, but the change is not live validated. |
| A pyrotechnic rule was extended to open flames and accepted by both reviewers. | A single claim check and boolean can cover multiple duties and alternative conditions. Text coverage and exact quotations do not prove each branch. | Better quote anchoring fixes provenance only. A general instruction to review every condition did not enforce that review. |
| The clearance correction retained the unsupported owner. | The repair receives the initial auditor's accepted/rejected claims. Secondary entailment returns early for an overall PARTIAL verdict. | The initial auditor had incorrectly accepted ownership; repair preserved it, and a later audit rejected the whole correction. We repaired against incomplete evidence validation. |
| $25,000–$75,000 and two days were filed without a basis. | `ClaimCheck.field` covers finding, remedy and severity; numeric estimate fields are not independently covered. | Instructions request evidence, but numeric arguments can still pass schema validation. Resetting estimates on a changed remedy helps only when a correction occurs. |
| Useful concerns disappear or turn into generic questions. | One bad assertion can make the entire corrected finding fail. | Stricter rejection can improve visible precision while worsening recall and usefulness. Unknown ownership must not erase a supported issue. |
| Narrow tests passed while fresh desks failed. | Most tests check mechanics or selected saved excerpts; limited fresh coverage, no expert-held-out benchmark. | Those tests cannot establish generalization, end-to-end accuracy or model-judge reliability. |

The desk, first auditor, repairer and second auditor use the same Flash model. Blinding
reduces information sharing, but does not establish independent errors. Their shared
mistake on the safety example is observed; the extent of correlated failure across
the product has not been measured. More calls to the same reasoning process are not
evidence of higher accuracy.

The parser, stable scene coordinates, honest quote provenance, reconciled accounting,
explicit incomplete states and saved live traces are valuable foundations to retain.
The failure is not evidence that the Gemini/ADK/Parallel/ClickHouse architecture should
be replaced. The investigation remains agentic; we strengthen the filing and delivery
contracts around the desks' reasoning.

## 1. Establish the test before changing the verifier again

Build a versioned reference set with a clearance professional and a production-safety
professional; obtain appropriate ratings/territory expertise for the scopes we intend
to sell. Expert review is a necessary business investment, not a substitute for software
checks.

Start with the observed failures plus 60 contrastive pairs (120 short original cases).
Cover positive findings and legitimate non-findings, missing evidence, exceptions,
use/territory/version mismatches, fictional versus production facts, numeric estimates,
and remedies that remove one trigger without guaranteeing every clearance. Include
the saved scope false approval unchanged. This development set is for iteration.

Separately commission a held-out set across at least 10 varied, authorized scripts,
aiming initially for at least 300 material assertions and 100 independently identified
serious issues. These are starting sample goals, not enough by themselves to substantiate
per-desk reliability. Label expected issues from the screenplay before showing reviewers
the model's report so that omissions are measurable. Have two reviewers resolve disputed
high-impact labels, with ambiguity retained instead of forced consensus. Original or
licensed scripts only; confidential customer scripts stay out of the public repository.

Freeze the rubric, source snapshots, model/config versions, split and thresholds before
comparison. Keep scripts/related cases in one split; paraphrases of the same source or
script are not independent test examples. Developers tune on the development set only.
If a held-out failure guides implementation, retire it into development and obtain a
replacement holdout. Do not repeatedly tune against the nominal test set.

Compare baseline and candidate on identical saved evidence first, then fresh retrieval
and complete scripts. Expert reviewers should not know which build produced a report.
Measure both the desk's raw output and what a customer would receive after verification.
Google's judge-evaluation guidance explicitly compares model ratings against human-rated
reference data; its confusion-matrix approach is suitable for evaluating our verifier.
[Google documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/evaluate-judge-model)

## 2. Make evidence and applicability explicit before writing the final prose

Add an internal evidence record for each material assertion. At minimum it records:

- The exact screenplay observation and coordinates, separately from user-provided
  production facts and assumptions.
- The source URL, immutable excerpt, retrieval date, content hash and the operative rule.
- The rule's subject, action/object, force (required/recommended/permitted), triggering
  conditions, exceptions, jurisdiction, version and effective date where available.
- Each asserted ownership relationship, remedy prescription, numeric amount and
  applicability branch, with its own evidence or an explicit unresolved status.

These are proposed internal contracts, not an assertion that structured JSON makes a
model correct. A model-generated rule extraction is also a claim needing validation.
Develop a small professionally reviewed rule library for frequent questions; derive
constrained recommendations from those reviewed rules and confirmed inputs. New or
ambiguous rules remain research candidates and enter human review until validated.
No regex system should pretend to decide arbitrary legal applicability.

For the observed safety failure, a reviewed rule with a pyrotechnic trigger cannot
authorize adding an open-flame alternative. Require a separate supporting rule for that
branch. Evaluate AND/OR structure, negation and exception scope explicitly, not by splitting
strings at every 'and' or accepting one plausible paragraph. Unknown production inputs
can support conditional advice, never an unconditional duty or violation.

Generate customer prose from accepted observations/rules/actions. Preserve conditions
through rendering; reject any additional owner, obligation, amount or guarantee introduced
during wording. Every rendered clause must map back to its accepted evidence record.
Completeness of that mapping is deterministic; correctness of novel source interpretation
still requires expert-calibrated review. Use the same acceptance path after adjudication,
reverification, revision, salvage and exports. Unsupported recommendations must not become
actionable merely by acquiring an 'unverified' label; retain the underlying concern as an
unresolved item instead.

First keep these records in session/audit metadata. Any optional public schema extension
needed for customer provenance/status must be announced explicitly, versioned and tested
against old records and every renderer before implementation.

## 3. Fix retrieval and repair together

Have the desk state the missing evidence relationship before another search. For clearance:
exact work/version -> right or permission type -> current relevant owner/administrator ->
intended use/territory/term. A studio directory, distributor credit or generic inquiry link
is a lead, not the missing connection. For safety, retrieve the operative paragraph and
its conditions rather than treating a bulletin title or general prevention rule as a
specific equipment prescription.

Use live Parallel research and fetch_page within existing bounded investigations. Shared
caches retain provenance, scope and freshness; a reviewed source library does not replace
Parallel as the live citation path. Fetch missing scope/exception text when a snippet is
truncated. Prefer current primary authority and explicitly applicable contractual guidance;
conflicting or stale evidence creates an unresolved question, not a convenient choice.

Before repair, independently validate the assertions the first auditor marked supported,
even if a different assertion made the whole flag PARTIAL. Otherwise the repair inherits
an untested positive, as happened with the JAWS owner. Budget this as a reorganization of
the existing bounded audit/check/repair/audit/check path; measure call counts and latency,
and preserve existing failure/timeout behavior. Do not add recursive repair loops.

Repair should construct a narrower recommendation from accepted evidence, rather than
paraphrasing a rejected paragraph. A supported scene observation and general rule may
survive while ownership remains a separate question. If additional evidence is essential,
route a typed missing-evidence request back to the original desk in a bounded research
step; no open-ended verifier research and no pretending a failed retrieval is clearance.
Desk re-entry is not currently implemented, so treat it as a subsequent architectural
task after the core claim contract is proved.

## 4. Treat estimates, ratings and unresolved facts as separate products of evidence

**Costs and days:** add an estimate record with a source/quote or professionally reviewed
rate, units, currency, date, region, use scope, quantities and assumptions. User-entered
quotes are labelled as such. Compute supported arithmetic deterministically; distinguish
a scenario estimate from an actual supplier/licensor quote. Missing evidence means unknown,
including days. Audit structured amounts even when they never appear in the prose, and
reconcile partial totals without presenting them as complete budgets. Do not inherit a
price after changing the remedy or treat a model's broad range as evidence.

**Production inputs:** collect planned filming jurisdiction/date, distribution markets,
target rating, intended use of referenced material, permission status, and relevant casting
or effects choices. Ask only questions triggered by the script; every answer can be unknown.
Version the answers, identify them as producer-supplied rather than externally verified,
and invalidate dependent advice when they change. Do not charge for invented detail
that could have been resolved with one relevant question.

**Ratings:** keep official rule evidence separate from ClickHouse comparisons and the
screenplay forecast. Evaluate the full chain: screenplay -> measured content profile ->
forecast -> applicable released-version outcome. Released-film descriptor classification
alone does not validate screenplay predictions. Split by film/version and time to prevent
leakage; account for edits between screenplay and released cut. Measure exact-class errors,
serious underestimation and calibration by rating class. Return uncertainty supported by
validation; no invented probabilities or promise that a proposed cut guarantees PG-13.
Keep US/UK and other classification systems distinct.

**Severity and confidence:** agree a desk-specific prioritization rubric with practitioners
and measure reviewer agreement. A deterministic risk-score formula is not an empirical
probability of clearance. Model-supplied 0.95 confidence is not calibrated reliability.
Avoid presenting either as such; preserve score withholding for incomplete analysis.

## 5. Define release gates that cannot be passed by hiding findings

Proposed initial acceptance criteria for consideration with the domain reviewers:

| Measure | Proposed gate and reporting rule |
| --- | --- |
| High-impact errors | Zero observed fabricated owners, serious unsafe prescriptions, unsupported mandatory legal duties or material fabricated cost claims in the qualification set. Any such error stops promotion, even when averages improve. |
| Precision | At least 99% of delivered material assertions correct and applicable on the held-out set; report per desk, source/claim/remedy/estimate type, sample size and uncertainty. This is a proposed target, not current performance. |
| Serious-issue recall | At least 95% of expert-labelled serious issues identified, with zero misses on designated critical sentinel cases. Count issues from the screenplay, not just entities triage happened to extract. |
| Useful output | At least 90% of expert-labelled resolvable issues retain a correct actionable remedy. Legitimate unknowns are reported separately; they do not count as resolved or disappear from recall. |
| Consistency | All deterministic invariants pass. On three runs of fixed scripts/production inputs, no unexplained loss of a critical issue or change from supported to cleared; report severity and tail disagreement rather than claiming byte-identical desk prose. |
| Estimates and scores | Every delivered number has a validated basis or is explicitly unknown. All totals, coordinates, unresolved counts and score-withholding rules reconcile in every customer format. |
| Verifier quality | Report false approvals and false rejections against expert labels, including the saved open-flame failure and supported controls. A model's SUPPORTED label is never the reference answer. |

Small samples cannot prove these population rates. For illustration, zero errors in 300
independent representative trials still gives approximately a 1% one-sided 95% upper bound
on the error rate (`1 - 0.05 ** (1/300)`). Assertions from the same script are correlated;
report uncertainty clustered by script and do not apply that illustration to them blindly.
Before claiming a rate, require enough independent evidence that its confidence bounds
support the claim. Qualification thresholds alone are not a customer accuracy guarantee.

Start by fixing the saved failure without breaking its supported controls. Then require a
paired improvement on untouched cases, useful fresh desk outputs, and full-report manual
review. A higher rejection rate, lower recall or more generic questions is not accepted as
an improvement. Source-grounding quality and real-world correctness must both be assessed.

Independent, domain-informed review, documented uncertainty and testing in deployment-like
conditions follow the measurement principles in [NIST's AI RMF](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/).
The numeric gates above are our proposals; NIST and Google do not certify or prescribe them.

## 6. Deliver a paid service whose promise matches its evidence

Until automated qualification is demonstrated, recommend an explicitly human-reviewed
paid pilot with a narrow, declared scope. Review the complete report and independently
check for omissions, not just HIGH flags selected by the model. The scope can expand desk
by desk as qualified expertise and evidence permit. If qualified reviewers are unavailable,
do not market the current automated output as a professional clearance replacement.

Each issue should clearly state the scene fact, source/rule, applicable condition, practical
next step, and unresolved input. Show who reviewed the delivered version and when. Keep
confirmed producer actions and permissions separate from AI analysis. Provide a correction
and version-history workflow; a changed script/source invalidates affected advice and its
score rather than silently declaring an issue resolved. Do not reuse customer material for
training or benchmark publication without appropriate authorization.

Track correction/reversal rates, serious misses, reviewer minutes, customer usefulness and
repeat use. Optimize cost per accepted useful report, including every model/retrieval call,
human review, support and rework. Current pipeline cost accounting omits direct verifier
calls; close that gap before setting margin or turnaround promises. Defer acquisition
scaling until the delivery promise and these economics are demonstrated.

## Execution order and stop conditions

| Order | Concrete deliverable | Evidence required before moving on |
| --- | --- | --- |
| A | Expert rubric, reference-set design, frozen current baseline and error taxonomy. In parallel, implement the known scope and numeric-field regression tests. | Every saved failure has a reviewed label; software tests and semantic tests are reported separately. |
| B | Internal assertion/applicability and estimate contracts; shared acceptance boundary; reviewed common-rule prototypes. | Saved false approval rejected, supported controls retained, unknowns preserved, estimates covered outside prose, compatibility/invariants green. |
| C | Validate accepted claims before repair; construct constrained corrections; source scope and missing-link retrieval feedback. | Blind comparison shows fewer errors without lower serious recall or fewer useful remedies. Spend and latency remain bounded. |
| D | Fresh desks, diverse held-out scripts, repeated runs and rating-specific validation. | Proposed gates supported by adequate evidence; full gate and expert report review pass. |
| E | Human-reviewed paid pilot and ongoing correction/quality monitoring. | Measured usefulness, reviewer workload, quality and contribution margin support a wider rollout. |

Do not promise a calendar date for qualification before expert availability and benchmark
size are known. Work A/B is the next engineering batch, not another sequence of prompt-only
patches or a full production run. A known false approval, major recall loss or unexplained
critical inconsistency blocks promotion. Preserve every failed experiment.
