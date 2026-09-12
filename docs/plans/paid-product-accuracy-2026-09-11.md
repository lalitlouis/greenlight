# Accuracy plan for GREENLIGHT pre-qualification

Decision date: September 11, 2026. Planning document; no runtime changes or paid
evaluations in this turn. Proposed thresholds below are product decisions to validate,
not achieved results or industry standards.

Product scope clarified by the user: this is an automated, paid pre-qualification
assessment that explains what could create clearance, rating, distribution or production
problems. It is not a final clearance determination, binding opinion, licensing service
or approved shooting plan. The product documentation communicates that scope.

The objective is useful early warning: identify relevant script content, explain plausible
consequences and their conditions, prioritize what matters, and suggest practical next
steps. Full ownership, casting and production arrangements are often unknown at this stage.
That uncertainty should qualify the assessment, not erase a useful finding or force every
customer into a human-reviewed service.

This clarification changes the plan's product and acceptance criteria. It does not turn
invented facts, incorrect citations or unsupported mandatory instructions into accurate
pre-qualification. Historical test outputs and recorded failures remain unchanged.

## Product output and verification target

Each issue should answer five questions: what is on the page, what could happen, under
what conditions, how significant is the potential impact, and what can the producer do
next? Keep evidence strength separate from potential impact: a substantial conditional
risk can deserve attention even when its eventual cost or applicability is unknown.

Distinguish script/source facts from reasoned risk assessments, suggested changes, and
facts that need confirmation. An assessment can infer a plausible risk from a cited rule
and depicted content without the source naming the screenplay or prescribing an edit.
Merely adding 'could' to an unrelated or unsupported allegation is not sufficient.

For the saved clip case, the useful output is the depicted third-party footage, the
potential permissions/budget issue if retained, and the choice to investigate rights or
remove/replace that footage. Naming its exact current licensor or fee is not necessary
to deliver that value. A replacement suggestion addresses that clip's trigger; it does
not certify rights in whatever replacement is eventually selected.

For the vessel-fire case, preserve the fire, fireworks and night-water risk and explain
that practical execution could add safety planning, specialist work and cost. Cite relevant
guidance and condition specific requirements on the chosen method and applicable rules.
Do not assert that the production must buy named equipment, obtain named permits or cast
a minor based only on the fictional scene. Ratings and territory forecasts similarly
describe likely pressure points and uncertainty, not guaranteed classification decisions.

An unknown ownership or production fact is normal pre-qualification output when the
conditional assessment is supported. A failed verifier/retrieval or an unsupported claim
is a different state and still needs honest incomplete handling. Do not treat every normal
unknown as a verification failure, or technical failure as a clean result.

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

Build a versioned reference set for pre-qualification: which potential issues should a
producer notice, which are irrelevant noise, and which next steps are helpful? Use
producer feedback and targeted practitioner review to improve these labels. Professional
review of every customer report is not a prerequisite for this automated product.

Start with the observed failures plus 60 contrastive pairs (120 short original cases).
Cover positive findings and legitimate non-findings, missing evidence, exceptions,
use/territory/version mismatches, fictional versus production facts, numeric estimates,
and remedies that remove one trigger without guaranteeing every clearance. Include
the saved scope false approval unchanged. This development set is for iteration.

Separately hold out varied, authorized scripts and expand this set as the product is used.
Label expected issues from the screenplay before showing reviewers the model's report so
that omissions are measurable. Resolve disputed high-impact labels with relevant expertise
where needed, retaining ambiguity instead of forcing a definitive answer. Original or
licensed scripts only; confidential customer scripts stay out of the public repository.
The earlier proposal to commission a fixed 300-assertion professional qualification set
is not a prerequisite for this product. Sample sizes still matter when measuring or
advertising accuracy.

Freeze the rubric, source snapshots, model/config versions, split and thresholds before
comparison. Keep scripts/related cases in one split; paraphrases of the same source or
script are not independent test examples. Developers tune on the development set only.
If a held-out failure guides implementation, retire it into development and obtain a
replacement holdout. Do not repeatedly tune against the nominal test set.

Compare baseline and candidate on identical saved evidence first, then fresh retrieval
and complete scripts. Reviewers should not know which build produced a report.
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
Develop a small source-grounded rule library for frequent questions, using practitioner
review to improve difficult interpretations. Allow conditional risk assessments and
suggested content changes when the cited trigger and script facts justify them. New or
ambiguous evidence can support a clearly scoped question or risk assessment where warranted;
it does not require every report to wait for human review. Definitive factual assertions
and mandatory prescriptions still require appropriate support. No regex system should
pretend to decide arbitrary legal applicability.

For the observed safety failure, a reviewed rule with a pyrotechnic trigger cannot
authorize adding an open-flame alternative. Require a separate supporting rule for that
branch. Evaluate AND/OR structure, negation and exception scope explicitly, not by splitting
strings at every 'and' or accepting one plausible paragraph. Unknown production inputs
can support conditional advice, never an unconditional duty or violation.

Generate customer prose from accepted observations/rules/actions. Preserve conditions
through rendering; reject any additional owner, obligation, amount or guarantee introduced
during wording. Every rendered clause must map back to its accepted evidence record.
Completeness of that mapping is deterministic; correctness of novel source interpretation
still requires semantic review evaluated against independent reference labels. Use the same acceptance path after adjudication,
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

**Costs and days:** support planning estimates with documented rates, comparable production
data or a calibrated estimating method, recording units, currency, date, region, use scope,
quantities and assumptions. User-entered quotes are labelled as such. A preliminary range
does not require a supplier quote, but it does need an explainable basis; where numbers
are weak, describe the potential cost/schedule driver instead. Compute supported arithmetic
deterministically; distinguish a scenario estimate from an actual supplier/licensor quote.
Missing evidence means unknown,
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

**Severity and confidence:** define a desk-specific prioritization rubric for potential
production impact and improve it with producer/practitioner feedback. Keep confidence in
the evidence separate from how serious the issue could be. A deterministic risk-score formula is not an empirical
probability of clearance. Model-supplied 0.95 confidence is not calibrated reliability.
Avoid presenting either as such; preserve score withholding for incomplete analysis.

## 5. Define release gates that cannot be passed by hiding findings

Evaluate as pre-qualification, not as a final professional determination. The earlier
99%/95%/90% qualification thresholds are withdrawn as launch prerequisites; they were
proposals for a different delivery standard, not measured performance. Set numeric goals
after establishing a baseline with a rubric that matches this product.

| Measure | Proposed gate and reporting rule |
| --- | --- |
| Factual integrity | Scene facts and citations are correct. Known fabricated owners, invented price claims and unsupported mandatory duties remain regression failures. |
| Risk relevance | Potential issues follow from the script and relevant evidence, with conditions stated. Measure unnecessary flags as well as incorrect factual claims. |
| Serious-issue recall | Detect the major plausible clearance, rating, territory and production complications in the reference set. Count issues from the screenplay, not only entities triage extracted. Missing final ownership or shooting details must not erase a supported risk signal. |
| Useful output | Findings explain why the issue matters and give a practical next step or a specific relevant question. A conditional assessment can be useful without resolving the issue. Track generic questions and empty reports as failures of usefulness. |
| Consistency | All deterministic invariants pass. On three runs of fixed scripts/production inputs, no unexplained loss of a critical issue or change from supported to cleared; report severity and tail disagreement rather than claiming byte-identical desk prose. |
| Estimates and scores | Every delivered number has a validated basis or is explicitly unknown. All totals, coordinates, unresolved counts and score-withholding rules reconcile in every customer format. |
| Verifier quality | Report both acceptance of unsupported assertions and rejection of valid conditional assessments. Include the saved open-flame failure and supported controls. A model's SUPPORTED label is never the reference answer. |

Small samples cannot prove these population rates. For illustration, zero errors in 300
independent representative trials still gives approximately a 1% one-sided 95% upper bound
on the error rate (`1 - 0.05 ** (1/300)`). Assertions from the same script are correlated;
report uncertainty clustered by script and do not apply that illustration to them blindly.
Before claiming a rate, require enough independent evidence that its confidence bounds
support the claim. Do not advertise accuracy percentages based on software-test counts.

Start by fixing the saved failure without breaking its supported controls. Then require a
paired improvement on untouched cases, useful fresh desk outputs, and sampled full-report
evaluation. A higher rejection rate, lower recall or more generic questions is not accepted as
an improvement. Source-grounding quality and real-world correctness must both be assessed.

Independent, domain-informed review, documented uncertainty and testing in deployment-like
conditions follow the measurement principles in [NIST's AI RMF](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/).
These references inform evaluation design; they do not require professional sign-off on
each report or certify this product.

## 6. Deliver a paid service whose promise matches its evidence

Deliver an automated pre-qualification report with a clear scope and useful evidence-backed
early warnings. Begin with a controlled paid beta and gather producer feedback on missed
issues, distracting flags, unclear conditions and helpful next steps. Sample complete
reports for quality review, including omissions rather than only model-selected HIGH flags.
Practitioner review is a calibration activity or optional service, not the default delivery
model or a blanket prerequisite to charging for automated pre-qualification.

Each issue should clearly state the scene fact, source/rule, applicable condition, practical
next step, and unresolved input. Identify the analysis version and date; disclose human
review only where it actually occurred. Keep
confirmed producer actions and permissions separate from AI analysis. Provide a correction
and version-history workflow; a changed script/source invalidates affected advice and its
score rather than silently declaring an issue resolved. Do not reuse customer material for
training or benchmark publication without appropriate authorization.

Track correction/reversal rates, serious misses, evaluation/review effort, customer usefulness and
repeat use. Optimize cost per accepted useful report, including every model/retrieval call,
human review, support and rework. Current pipeline cost accounting omits direct verifier
calls; close that gap before setting margin or turnaround promises. Defer acquisition
scaling until the delivery promise and these economics are demonstrated.

## Execution order and stop conditions

| Order | Concrete deliverable | Evidence required before moving on |
| --- | --- | --- |
| A | Pre-qualification rubric, frozen current baseline and error taxonomy separating factual errors, valid conditional risks, irrelevant flags and missing issues. | Saved examples labelled for the intended product; software tests and semantic/usefulness tests reported separately. |
| B | Internal assertion/applicability and estimate contracts; shared acceptance boundary; source-grounded common-rule prototypes. | Unsupported mandatory claims rejected, supported conditional risks retained, normal unknowns distinguished from failed verification, estimates covered outside prose, compatibility/invariants green. |
| C | Validate accepted claims before repair; construct constrained corrections; source scope and missing-link retrieval feedback. | Blind comparison shows fewer errors without lower serious recall or fewer useful remedies. Spend and latency remain bounded. |
| D | Fresh desks, diverse held-out scripts, repeated runs and rating-specific validation. | More relevant issues and useful next steps, fewer factual errors/unnecessary flags, stable major risks, and reconciled full reports. |
| E | Automated paid pre-qualification beta with feedback and sampled quality review. | Measured usefulness, correction rate, quality and contribution margin support a wider rollout. |

Work A/B is the next engineering batch: preserve the useful warning while constraining
unsupported details, rather than pursuing final legal certainty. Practitioner availability
does not block this work. Known factual false approvals, major recall loss or unexplained
critical inconsistency remain reasons not to promote a candidate change. Preserve every
failed experiment and measure progress against the clarified product scope.
