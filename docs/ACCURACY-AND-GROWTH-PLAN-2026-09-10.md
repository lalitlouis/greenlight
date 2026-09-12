# GREENLIGHT: accuracy, performance, and growth plan

Review date: September 10, 2026. Planning document; no runtime or schema changes.

The strongest opportunity is a production clearance workspace that helps a producer and their reviewer find, substantiate, and resolve expensive script issues before production. The immediate priority is proving that the findings and resolutions deserve trust. Acquisition should grow alongside that proof.

Working customer assumption: independent producers preparing a project for production, with clearance researchers and entertainment lawyers as evaluation partners and potential distribution partners. This is a hypothesis to test, not evidence of customer demand.

## Evidence and limits

Reviewed the authoritative technical spec, desk prompts, shared tools, prepass, completeness, verification, adjudication, report accounting, ratings model, What-If, revisions, server/product surfaces, evals, and cached runs. This is a targeted architecture and product review, not an exhaustive security or legal audit.

- `make check`: passed.
- Unit suite with cloud credentials disabled: **405 passed**. Plain `make test` stalled on cloud-dependent server lookup paths in this environment; make offline isolation explicit in the test setup.
- Cached demo `runs/run_20260902_221612.json`: **52/52** current fixture/eval checks passed; 23 kept findings, 2 rejected, zero unexamined items.
- That record took **1,896.5 seconds (31.6 minutes)** and records **$4.9425** estimated cost. Flash usage is **12,732,782 prompt tokens**, including **7,896,378 cached tokens**, plus 116,616 output tokens. These are cumulative across calls, not one context window. Cost is the repository's accounting estimate, not an independently reconciled invoice.
- The successful 100-scene scale record `run_20260902_130947.json` took **943.7 seconds**, records **$3.3183**, and passes **32/33** current script-independent invariants. Its failure concerns a rating finding whose severity exceeds its marginal evidence. This is a historical record evaluated with today's checks, not proof that current code still produces the defect.
- Historical records span code changes and use `build: local`; their differences cannot establish same-build desk variance or current production performance.
- No paid live screenplay analysis was started. No production account metrics were accessed. Customer counts, retention, willingness to pay, and present production latency remain unknown.

## What is already good

1. **The architecture fits the work.** Independent desks can investigate iteratively, chase ownership, revisit scenes, and leave questions unresolved. Keep Gemini/ADK, live Parallel retrieval, ClickHouse comparisons, and the independent desk structure.
2. **Evidence is enforced at boundaries.** Citation provenance, source/claim gates, scene checks, rejection recovery, and blinded verification are substantially stronger than asking a model for sourced prose.
3. **The deterministic foundation is substantial.** Parser anchors, language census, entity accounting, merge guards, report reconciliation, cached runs, and hundreds of tests make controlled improvement possible.
4. **There is already a usable delivery product.** Annotated scripts, binder exports, one-sheets, revision comparisons, account ownership, and durable worker execution support real review work. These are assets to build on.
5. **The team documents failure honestly.** The methodology page already acknowledges that descriptor extraction is unmeasured. Carry that precision into report labels and sales claims.

## Accuracy priorities

| Priority | Finding and evidence | Proposed change | Acceptance evidence |
|---|---|---|---|
| P0 | **Fiction is being treated as production evidence.** `agents/safety_underwriter.py` explicitly treats a character's missing permit as a fact about the production plan. Character age also needs separating from performer age. | Track story facts, confirmed production facts, and unresolved staging assumptions separately. Flag the depicted hazard; derive permit violations, performer restrictions, and insurer requirements only from applicable production facts and authority. | Paired scenes with identical hazards but different fictional permit dialogue do not change production compliance status. Changing confirmed production metadata does change the applicable analysis. |
| P0 | **Missing verdicts can appear verified.** A local probe of `apply_verdicts([flag], {})` followed by `build_report` yields no unavailable marker, `verification_degraded=False`, and a numeric score. Explicit verifier-error handling already behaves more safely. | Make every missing/invalid verdict an explicit unverified state across normal, salvage, standalone, and reverify paths. | No finding without an affirmative valid verdict contributes to a verified score; incomplete verification remains visible. This probe establishes a boundary defect, not its incidence in production. |
| P0 | **A disappearing finding becomes “resolved.”** `revision.diff_records` labels absence from the second run resolved. Two cached records with identical draft hashes produced **8 new, 8 resolved, 10 unchanged, 2 severity changes**. | Default to “not reproduced on this analysis.” Use “resolved” only with evidence of a relevant script edit, reviewed clearance document, or recorded human decision. | Same-draft reruns never claim script fixes. A partial/failed follow-up run cannot resolve old findings. |
| P0 | **Cleared decisions have weaker scrutiny than findings.** `record_clearance` accepts an ID and nonempty reasoning. Assembly receipt checks catch some unsupported work claims, but do not prove a no-action conclusion. Completeness covers known work, not everything omitted by extraction. | Require structured disposition reasons and evidence for substantive no-action decisions. Verify high-consequence clearances, sample routine ones, and add independent omission review. | Held-out false-clearance and missed-issue rates are measured. A fabricated public-domain or ownership conclusion cannot close a high-risk item. |
| P0 | **The real desk accuracy benchmark is missing.** Existing seeded-script tests and invariant checks are useful but cannot estimate precision/recall on unseen work. | Build a permissioned, expert-labelled benchmark with positive and negative examples and a locked test split. Use original scenes for public fixtures; keep client scripts private and opt-in. | Publish per-desk precision/recall, serious-issue recall, false blockers, scene accuracy, citation support, and uncertainty intervals on unseen cases. |
| P1 | **Ratings instructions conflict.** `ratings_board.py` says to quote an expletive rule, then broadly forbids normative rule claims. It distinguishes spoken counts, then says action lines count like dialogue. | One evidence contract: spoken dialogue, audible voiceover/lyrics, visible text, action prose, and contextual judgement are distinct inputs. Keep quoted rules separate from observed descriptor frequencies; define precedence once. | Equivalent scene wording produces the same census facts. Nonspoken profanity in action prose does not count as a spoken expletive. Prompt and filing/eval rules agree. |
| P1 | **PARTIAL verifies only part of a claim but leaves the whole claim and severity standing.** This is intentional in `apply_verdicts`, but a marker alone does not remove an unsupported obligation. | Verify atomic claims: script fact, applicability, obligation, remedy, owner, and estimate. Narrow unsupported clauses or mark the unresolved component explicitly, preserving real hazard severity. | A supported core hazard survives while an unsupported mandatory licence, legal conclusion, or remedy is removed. |
| P1 | **Source authority is incompletely visible to verifiers.** `_blinded_prompt` emits citation title OR URL; a titled citation hides its URL. Verification ordinarily receives cited excerpts, not an independently fetched full source. | Always provide URL/domain, source identity, jurisdiction, date and evidence type. Retrieve surrounding source context through Parallel when applicability is ambiguous. | Adversarial citation pairs test misleading titles, off-topic government pages, stale guidance, and omitted exceptions. Measure false acceptance and false rejection separately. |
| P1 | **Jurisdiction and production choices are under-modelled.** Initial state carries target rating and adaptation context, but not a full production brief; territory sweeps are fixed to CN/UAE axes regardless of intended distribution. | Add optional shooting location/date, intended territories and release channel, primary market, staging method, performer ages, rights already secured, and budget/union context. Unknown stays unknown. | A territory not requested does not silently lower the project's primary readiness assessment. Story setting is not substituted for shooting jurisdiction. |
| P1 | **Scoring and estimates are deterministic but not calibrated outcomes.** `report.py` multiplies severity factors, sums remedy costs, and takes the maximum individual delay. | Present an explained issue index, not a probability of clearance. Group shared and alternative remedies; attach estimate basis, location, scope and date. Describe the maximum delay as a rough overlap assumption unless dependencies are known. | Splitting one underlying problem into two flags cannot double-charge its remedy. Do not call `max(days)` a computed critical path without a dependency schedule. |

### Ratings: improve the input model before the headline number

The shipped descriptor model reports **83.9% top-1 accuracy** and **92.2% aggregate prediction-set coverage** over 937 held-out official rationale records. G and NC-17 have only 3 and 8 test examples, with 66.7% and 62.5% observed coverage. The code appropriately pools groups for its conformal construction, but these figures still evaluate **official rationale → rating**, not **screenplay → eventual rating**.

The missing measurement is the model's conversion of a screenplay into those descriptors. Official rationales are summaries written alongside a rating decision; similar language among those summaries is useful evidence, but it is not an independent validation of a screenplay forecast. The methodology page recognizes this, while the report's “Coverage (90% per rating group)” label is easier to overread.

Recommended sequence:

1. Build a scene-linked content inventory with counts, on/off-screen presentation, duration proxies, intensity, and context. Reuse the existing census; let the ratings desk inspect and adjudicate ambiguous content.
2. Have qualified reviewers label a held-out sample of those inventories before seeing model outputs or known film ratings. Measure descriptor extraction agreement independently.
3. Evaluate end-to-end predictions on appropriately permissioned script/finished-version pairs, recording version mismatch and edits. A released film's rating is not automatically ground truth for an earlier draft.
4. Split by film identity and time, deduplicating alternative titles and rereleases. Fit feature selection on training data only; `rating_model.py` currently chooses vocabulary before splitting.
5. Track underprediction, top-1 accuracy, set coverage, set width, and probability calibration by rating, genre, format, era and content type. Preserve an uncertainty/abstention path for thinly represented content.
6. Treat What-If as an estimate until a proposed scene edit has been re-extracted. Today it rewrites the rationale and evaluates that revised description; it does not establish that the rewritten script earns the projected rating. BBFC cut records inform UK classification, not a direct US MPA guarantee.

Do not replace the existing model with a larger one until this benchmark can distinguish an improvement from changed wording.

### Clearance: make conclusions auditable

Separate “this material is present,” “this use may require authorization,” “this is a current ownership lead,” and “the production has obtained sufficient rights.” A source mentioning a company does not prove that company's current authority to grant the required rights.

Represent rights by work/recording/version, use, territory, medium and term. Keep composition and recording rights separate. Capture registry identifiers and dated evidence where available. Provide multiple viable remedies, including counsel review of an exception where relevant; avoid turning broad prompt heuristics into categorical legal conclusions.

For fictional names, a web search with no result should become a scoped negative-search record, not an assertion that no conflicting person or business exists. For all clearances, an unresolved owner can coexist with a supported licensing concern.

These distinctions reflect the practical process described in [WIPO's filmmaker clearance guide](https://www.wipo.int/web-publications/rights-clearance-a-guide-for-independent-filmmakers/en/2-rights-clearance-from-idea-to-distribution.html): evaluate circumstances and required rights, then document licensing, substitution, removal, or a decision to proceed without permission.

## Performance plan

Optimize measured cost per useful reviewed report, with accuracy held fixed.

1. **Instrument each stage and tool call.** Persist desk, batch, model version, token usage, cache hits, latency, retries, filing rejections, correction attempts and stop reason. Add git/prompt/parser/schema/source-corpus versions to the draft hash already stored. Run-level totals and `build: local` are insufficient for attribution.
2. **Actually bound clearance conversations.** `clearance_batch_slices` caps the number of batches at four, then spreads every item across them. A 200-item probe produced four 50-item batches; the advertised ~25-item bound does not hold at scale. Queue fixed-size batches with at most four executing concurrently, preserving independent conversations and shared provenance.
3. **Reduce accumulated context.** Existing disposition-aware pruning is a good start. Give desks compact evidence references and active case summaries, keeping original retrieved material available to tools and verification. Measure retry/refile loops before shrinking budgets.
4. **Improve cache identity.** Existing research caching includes generated objectives, queries and positional entity IDs. Stable entity/work identifiers plus question type, jurisdiction, source scope and freshness can improve reuse. Keep script-specific context private; share generic authority retrieval only where safe. Preserve live Parallel as the normal cache-miss path.
5. **Tune concurrency against quotas.** Use observed 429s and queue times to choose per-run and fleet limits. Add an overall time/cost budget and checkpoints, since retries can turn a short script into a long-running job. Do not increase all parallelism blindly.
6. **Add dependency-aware revision analysis later.** Changed scenes may affect cross-scene identity, counts, ownership assumptions and interacting remedies. Reuse unaffected evidence; invalidate affected decisions and global aggregates. Existing revision comparison is the starting point, not yet incremental analysis.

Initial engineering target: reduce median token cost and wall time by **30% on a fixed benchmark**, with no serious-recall regression and all deterministic gates green. This is a proposed target, not a forecast. Establish p50/p95 baselines before publishing a customer turnaround promise.

## Product and distribution

The business should sell a concrete job: **“Find expensive script issues early, review the evidence, and track what has been fixed.”** Lead with a producer's decisions and deliverables. The four desks explain the method after the benefit is clear.

There is a paid incumbent service category. The Clearance Lab currently lists **$15/page for a three-day report** and **$10/page for seven days**—roughly $1,500/$1,000 for 100 pages. That is a useful purchasing anchor, not proof GREENLIGHT replaces professional review. [Provider pricing](https://theclearancelab.com/product/script-clearance-report-three-day-turnaround/).

Remove “nobody has automated it” from market assumptions. Current providers market digital workflows, and adjacent AI screenplay products already compete for budget. [No Conflict Clearance](https://www.noconflictclearance.com/) emphasizes digital submission and confidentiality; [Prescene](https://prescene.com/coverage) sells AI coverage from $49/month. These are vendor claims, not independently verified product quality. Human clearance review, a producer's existing spreadsheet, and general AI tools are also alternatives.

The defensible advantage would be reviewed outcome data, useful repeat workflow, and trusted distribution. Agent count and access to public citations are readily copied.

### Build the missing workflow

- A finding can be assigned, commented on, accepted, disputed, mitigated or referred to counsel. Keep model evidence immutable; append human decisions with author, time and reason.
- Attach releases, permissions and licence scope. Do not silently convert a document upload into verified clearance.
- Show unresolved/high-impact items first and explain why a decision changed between drafts.
- Let a producer share a restricted review workspace and export the existing binder in the format their reviewer accepts.
- Collect optional correction reasons: wrong scene, nonexistent issue, wrong authority, unsupported requirement, bad estimate, missed item. With permission, adjudicated corrections become eval cases rather than automatic training data.
- Align privacy promises with actual retrieval. The research tool asks models to include script context in objectives, while the privacy page says only short queries are sent to Parallel. Audit actual payloads, minimize what is transmitted, and make the explanation accurate. This is a trust review item, not a confirmed disclosure incident.

### Win a small group before broad acquisition

1. Recruit **10 design partners**: roughly 5 producing teams, 3 clearance professionals and 2 entertainment-law/E&O contacts. Ask for an actual recent workflow and permissioned script, not just an opinion about AI.
2. Run paired reviews: professional review and GREENLIGHT on the same draft, with blinded scoring of mistakes, misses and useful findings. Measure review time and the effort needed to correct the report.
3. Sell a bounded paid pilot after showing the deliverable. Test per-project pricing, with a fixed revision allowance, before assuming subscriptions fit episodic producer use. A **$49 versus $99 software-only project pilot** is an experiment, not recommended settled pricing; human-reviewed service must price reviewer labour separately.
4. Use partner referrals, targeted producer/line-producer outreach, and approved educational workshops. Film schools can supply learning and feedback; do not confuse student usage with professional willingness to pay.
5. Publish permissioned case studies with issue, source, accepted remedy and reviewer outcome. Avoid unsupported “lawsuits prevented” or “money saved” claims.
6. Add privacy-conscious first-party funnel events: example viewed → upload → report completed → finding reviewed → action/export/share → new draft/project → payment. Track no screenplay text in analytics and update disclosures as needed.

The main product metric should be **projects returning for another draft or project after taking a useful reviewed action**. Track paid conversion, repeat use, referral, review minutes saved, material missed issues, and gross margin including support. Raw signups alone will not establish this business.

## Proposed 90-day sequence

| Window | Engineering | Customer work | Decision gate |
|---|---|---|---|
| Days 1–14 | Fix missing-verdict and false-resolution boundaries; separate fiction/production facts; reconcile ratings instructions; add version/timing telemetry. | Interview first 10 partners; inspect their existing clearance logs and handoffs. | Concrete defect reproductions pass; users identify a repeated job and agree to evaluate real deliverables. |
| Days 15–30 | Build ~100 original/permissioned contrastive scenes and an initial ~10-script held-out set; add no-action verification and source metadata. | Conduct expert-labelled paired reviews; show measured report errors openly. | Report per-desk metrics with denominators; identify whether remaining misses prevent a useful pilot. |
| Days 31–60 | Bound batch size; reduce token accumulation; ship reviewer decisions, attachments and trustworthy revision status. | Run 5 paid project pilots; test two prices and partner referrals. | Proposed pilot goals: high-impact recall ≥95%, actionable precision ≥90%, and zero observed false blockers on the agreed labelled set. Small samples are preliminary; report confidence intervals and every material miss. |
| Days 61–90 | Improve end-to-end rating validation; trial safe incremental review; standardize exports and onboarding around actual use. | Expand the channel that produces repeat paid projects; publish approved case studies. | Continue acquisition spending only if review effort falls, users return, and price covers model cost, retries, support and any human review. |

Keep new agents, additional territories, a broad writing assistant, and enterprise certification projects behind demonstrated customer demand. The near-term work is to make the existing product's conclusions more accurate, its changes more consistent, and its reports easier to act on.
