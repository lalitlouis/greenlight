# Tech Spec — GREENLIGHT

## Why this is an agent system and not a pipeline

An earlier draft of this spec described a pipeline: extract entities, run one search each, run
four prompts, dedupe. That design was wrong — not because it would score badly, but because it
cannot produce a correct clearance report. Four things in this domain require an agent.

**1. Research is iterative and its shape is unknown in advance.** A song is not one lookup.
Search it, discover the composition and the master are separately owned, research each
rightsholder, discover the master sits with a reissue label, research that. The entity graph
*expands as you research it*. No fixed number of calls covers it.

**2. A desk must decide what to look at.** Safety Underwriter reads "the car catches fire" and has
to establish who else is in the scene, whether it reads as practical or VFX, whether a minor is in
frame, and only then what an insurer requires. Each answer changes the next question.

**3. Remedies interact.** Replacing a brand rewrites an action beat, which may move a rating beat
that Ratings Board already scored. Something has to notice and send it back.

**4. A citation is only worth anything if something checked it.** "The model was told to include a
URL" is not a guarantee. A separate agent that re-reads the source and can *reject* the flag is.

## Agent graph

```
GreenlightPipeline                  SequentialAgent
├── ScriptParser                    deterministic — screenplay -> Scene[]
├── Triage                          LlmAgent  -> Entity[] + per-desk worklists
├── GatekeeperPanel                 ParallelAgent — the desks, concurrent
│   ├── ClearanceDepartment         ParallelAgent — up to 4 batch agents
│   │   └── clearance_counsel__bN   LoopAgent(max_iterations=14) each, over a
│   │                               bounded ~25-item slice with a FRESH
│   │                               conversation (context bounded by construction)
│   ├── RatingsBoard                LoopAgent(max_iterations=6)
│   ├── SafetyUnderwriter           LoopAgent(max_iterations=8)
│   └── TerritoryCensor             LoopAgent(max_iterations=12)
├── CompletenessGate                LoopAgent(≤3): deterministic unexamined-set check +
│                                   a scoped sweep desk; verification is not reached while
│                                   any extracted entity lacks a disposition
├── VerificationPanel               ParallelAgent — one verifier per filed flag
├── Adjudicator                     single LlmAgent (gemini-2.5-pro, structured plan)
└── ReportWriter                    deterministic -> Report + marked-up script
```

Each desk is a `LoopAgent` wrapping an `LlmAgent` with tools. It decides what to investigate, how
deep to chase it, and when it is finished. It is not a prompt.

## The toolbelt

Every desk gets the same tools; they differ only in instruction and worklist.

| Tool | Purpose |
|---|---|
| `read_scene(scene_id)` | Full scene text. Desks go back to the script rather than working from a dump. |
| `find_in_script(pattern)` | Where and how often something appears. Prominence is a fact, not a guess. |
| `research(objective, queries)` | Parallel Search. `objective` is the clearance question in prose. |
| `fetch_page(url, objective)` | Parallel Extract — full-page retrieval when a search excerpt is too thin to cite. |
| `deep_research(question)` | Parallel Task API — last-resort multi-source investigation for BLOCKER-deciding chains; ≤2 per desk, 3 budget credits. |
| `query_precedent(text, k)` | ClickHouse kNN over official CARA rating rationales (`cara_rationales`, 4,733 films) in rationale-space — run 17. |
| `file_flag(flag)` | Emit a finding. Schema-validated; a flag without a citation is rejected; cited excerpts must exist VERBATIM in retrieved material (near-misses are auto-repaired from the provenance registry, and every rejection path is retry-capped). |
| `note_open_question(text)` | Record something the desk could not resolve. Surfaced in the report — an honest unknown beats a confident guess. |
| `done(reason)` | Self-terminate. Sets `tool_context.actions.escalate = True`, which is how a `LoopAgent` exits early. |

Tools are plain typed Python functions. ADK reads the signature and docstring as the tool spec, so
docstrings are written for a model, not a human.

## Loop termination

Three independent stops, because a research loop that cannot end is a bill:

1. **Self-termination** — the desk calls `done()` and escalates. The tool REFUSES
   closure while assigned work items remain undispositioned and >=3 research budget is
   left (no refusal cap since 2026-08-28 — the iteration ceiling is the only other stop);
   early quitting is a measured failure mode, so the contract is mechanical, not prose.
2. **`max_iterations`** — a hard ceiling per desk.
3. **Research budget** — a per-run cap on `research()` calls, enforced in the tool. When exhausted
   the tool returns "budget spent, file what you have," which the desk handles gracefully.

Chase depth is capped at 3 (entity -> rightsholder -> administrator). Deeper than that is a human's
job and the report says so.

## Verification

Every filed flag fans out to an independent verifier that receives **the claim and the citation,
but not the desk's reasoning**, and answers one question: does this source actually support this
claim?

- `SUPPORTED` — flag stands only after material claims in finding, remedy and severity
  have been checked. A failed clause overrides an inconsistent positive overall label.
- `PARTIAL` — live verification attempts one correction of the finding AND remedy, then
  independently verifies the replacement against the same scene text and citations.
  Only a fully supported replacement renders. A repair failure becomes an open question
  and withholds the score. Legacy saved reports may still carry the earlier
  "partially supported" marker; they are not retroactively repaired.
- `UNSUPPORTED` — flag is dropped and logged. It never reaches the report.

The repair preserves identity, citations and coordinates, reviews severity rather than
automatically capping it, and clears cost/schedule estimates tied to the old remedy.
Claim checks and before/after repair evidence live in verdict metadata; public schemas
are unchanged. The same bounded check/repair/check path serves live fan-out, salvage and
targeted verification retry. Failed repairs do not enter another recovery loop. Production
facts (casting, jurisdiction, effects method) cannot be inferred from fictional events.

All desks and reviewers share the automated pre-qualification scope. A `risk_assessment`
may combine exact script and source receipts into a conditional early warning without
establishing the final licensor, cast or staging method. Normal unknown production facts
do not by themselves constitute verification failure. Evidence strength and potential
impact remain separate; this is not a final clearance or shooting-plan determination.

External rules and production prescriptions, including planning advice, require exact
support spans inside their own cited excerpts. Rule applications and proposed content
edits additionally carry exact screenplay receipts from the first auditor's supplied
scene context. An edit may address a cited trigger without the source literally naming
the screenplay or prescribing that edit, but cannot promise a final rating/clearance
or invent a specialist, permit or ownership assertion. Missing/non-verbatim receipts and
unreviewed material text trigger correction.
Formatting-only display quotes may be anchored back to one unambiguous raw source
substring using preserved character offsets: whitespace, complete inline HTTP(S)
Markdown links, paired bold/underscore emphasis and standalone hash heading markers.
Words, case, numbers, order and punctuation are not approximated. Truncated markup
is not repaired. The original excerpt remains immutable; internal
`support_span_reanchors` records submitted and raw quotes. The independent reviewer
still receives the raw receipt and full excerpt, so anchoring never establishes truth
or applicability.
Coverage permits only internal `and`, `and that`, `or` or `and/or` joins between audited clauses;
omitted conditions, negation and prescriptions still fail. This keeps atomic claim
quoting from rejecting a finding over a connective alone. The second reviewer receives
the complete field as claim context to judge those operators and each alternative's
conditions. Claim context is not source evidence or verified script evidence.

Receipts prove provenance, not entailment. A separate blinded batch checks each claim
against its spans and excerpt context. Applications, edits and risk assessments carry the exact relevant
script receipts; the batch never receives the earlier auditor's reasoning or severity.
Script receipts establish fictional content, not actual production facts or ownership.
Citation title and URL accompany
each excerpt solely for source attribution; metadata cannot supply an operative rule
or establish applicability. This avoids rejecting a correctly attributed quotation
merely because its body does not repeat the publisher's name. It must return every claim
exactly once; an incomplete secondary review withholds the score. Severity judgement
stays in the script-aware audit regardless of the model-chosen basis or optional receipts;
severity never enters the source-only batch. A supported first
pass costs two logical calls; a repair is bounded at five total. No new searches are
introduced. Desk-relevant inquiries may omit external support but receive independent
review for relevance, concealed requirements and unsupported premises. The fixed
production-input inquiry is permitted only for the safety desk. The batch also checks
the initial auditor's positive claims when the overall audit is PARTIAL, before repair
can inherit them. Scope and requirements are separate returned decisions; a negative
component overrides a positive overall boolean, and missing components fail verification.
This is a structured review contract, not deterministic proof of source interpretation.
Remedy actions must
agree with their detail; NO_ACTION is not proof that no follow-up is needed.
Every non-null `est_cost_usd`/`est_added_days` value, including zero, is separately
audited as a canonical JSON value with `basis=estimate`. Missing or rejected numeric
support withholds that field without dropping supported prose or treating normal cost
uncertainty as a verifier outage. Unsupported numbers in prose still need correction.
`audit_input` binds the new audit to the exact flag, including its numeric fields;
`estimate_exclusions` records withheld values. Older saved audits retain their prior
interpretation and are not silently represented as having passed the new audit.
Quote/receipt metadata is session/record-internal (`support_span_version=3`);
frozen public schemas are unchanged.

For a small set of development-reviewed production-rule snapshots, repair can select
source-bound cards from `data/production_rules.json`. A card requires the safety desk,
an existing Parallel receipt, its exact URL and full excerpt hash. Selection cannot
introduce a source or accept changed context. `SourceBoundRepair` selects rule IDs and
writes scene/risk prose; code assembles the remedy from fixed wording that preserves
each rule's trigger and qualifications. The complete correction still goes through
the ordinary blinded audit and secondary check. Selected cards and original receipts
remain in the internal audit trail. Other evidence uses the bounded general repair.

Fresh desk diagnostics (`scripts/eval_desks.py --live`) run hand-assigned worklists
through the existing desk factory and live tools with explicit model/retrieval/time
limits. They preserve the original script and parser coordinates, save model events
and raw retrieval, and label completion as unreviewed. They do not measure triage,
full-panel coverage or release readiness. The September 11 diagnostic exposed an
automatically accepted scope expansion from pyrotechnics to open flames; it remains
a failed manual case despite the automated SUPPORTED verdict. See
`docs/plans/fresh-desks-2026-09-11.md` for evidence and remaining validation.

Withholding the desk's reasoning is deliberate: a verifier shown the argument tends to ratify it.

Implementation note: ADK's `ParallelAgent` takes a static sub-agent list, and flag count is not
known until the desks finish — so the VerificationPanel is built at runtime (or run as a fan-out
inside a custom agent), not declared as a fixed `ParallelAgent`. The same class of care will apply to the
Adjudicator's deferred `AgentTool` re-entry if it ships: a re-entered desk appends to
`flags:<desk>` and must not double-file findings it already made.

This pass is the product thesis made mechanical. Rejected-flag count is a metric we report to
ourselves — if it is zero, the verifier is not doing its job.

## Adjudication

A single `LlmAgent` on gemini-2.5-pro that emits a structured reconciliation plan, applied
deterministically:

- Merges duplicates found by one desk on the same scenes (never across desks — different
  desks' findings on one scene are different findings by design).
- Normalizes drifted categories.
- **States conflicts on the record.** Where remedies interact (Ratings wants a line cut;
  Clearance wants it rewritten), the conflict and its proposed resolution are recorded as
  adjudication notes rendered on the report — they are prose for the producer, not
  executable desk re-runs.

**Deferred (roadmap, not shipped):** bounded desk re-entry via `AgentTool` — re-running the
desk a conflicting remedy affects, with the proposed change, in a LoopAgent. STATUS.md has
carried this as deliberately deferred; this section previously described it in the present
tense, which was wrong.

## What deliberately does not use a model

- **Parsing.** A hallucinated scene number breaks every anchor downstream.
- **Scoring.** A score that moves between runs is not a score.
- **Report assembly.** Deterministic rendering from validated objects.
- **Schema validation.** Enforced at the `file_flag` boundary, not requested in a prompt.

## State contract

Desks never read each other's prose. Everything crosses through ADK session state as validated
objects:

| Key | Written by | Read by |
|---|---|---|
| `scenes` | ScriptParser | all |
| `entities` | Triage | all desks |
| `research:<entity_id>:<question>` | `research()` tool | all desks — keyed per entity AND question: a chase asks several questions about one entity; identical questions share across desks |
| `flags:<desk>` | each desk | VerificationPanel |
| `verdicts:<flag_id>` | verifiers | Adjudicator |
| `report` | Adjudicator | ReportWriter |

The research cache is the cost control that matters: four desks asking the same question about
the same song hit the cache, not the API. (Keying on entity alone was tried first and looped —
a desk chasing ownership asks several different questions about one entity and kept getting the
first answer back.)

## Data contracts

`schemas/` — `scene`, `entity`, `flag`, `report`. Frozen. Key invariants:

- `flag.citations` has `minItems: 1`, enforced by schema at the tool boundary.
- `scene.raw_span` is a char-offset pair, which is what makes the marked-up script view possible.
- `entity.depicted_negatively` flips a brand from "courtesy letter" to "will never clear."

## Models

| Component | Model | Why |
|---|---|---|
| Triage | Flash (`gemini-3.7-flash`) | High-volume extraction |
| The desks | Flash (`gemini-3.7-flash`) | Many tool-calling turns; Flash is the default and cost driver |
| Verifiers | Flash | Narrow, single-question judgement |
| Adjudicator | Pro | The only task reasoning across four desks' conflicting output |

All agents use `Gemini` model instances with **HTTP-layer retry**
(`HttpRetryOptions`: 8 attempts, 10→120s backoff, jitter) — the ONLY layer where
retries actually run. ADK's `retry_config` kwarg is silently ignored by
`LlmAgent`, and the genai client defaults to zero retries; we shipped for weeks
believing in a ladder that never fired (see DECISIONS.md, 2026-08-27). Desks
also carry `before_model_callback` history pruning (disposition-aware) and an
`on_tool_error_callback` shield (hallucinated tool names become corrective
feedback, not crashes).

## Cost

$100 total, and iterative research spends faster than a pipeline would. Controls: shared
`research:` cache, per-run research budget, `max_iterations` per desk, chase depth 3, Flash
everywhere except adjudication. Cassettes in `fixtures/cassettes/` make tests free and
deterministic. A full cached run lives in `runs/` so the demo survives a dead network.

## Deployment

- **Agents:** Vertex AI Agent Engine. Deployed from day 9; Cloud Run is the fallback.
- **Web app:** Cloud Run, scales to zero, FastAPI + SSE.
- Region `us-central1`. Staging bucket `gs://greenlight-clearance-2026-staging`.

The UI streams tool calls as they happen. The four columns show what each desk is *doing* —
"two rightsholders found, chasing administrator" — not a progress bar. The agency has to be
visible or it may as well not exist.

## Testing

- Schema validation on every emitted object.
- Parser unit tests against the fixture screenplay.
- Desk tests replay cassettes; no live API calls in the suite.
- **Verifier regression set:** deterministic regression cases drawn from production records
  for the verdict-processing layer (`tests/test_overturn_guards.py`: rejections that must
  stay rejected, true overturns that must fire). A hand-labelled flag/citation pair set that
  exercises the model-judged verdict itself is roadmap, not shipped — cassettes would make it
  free to run.
- `make check` runs lint plus the forbidden-dependency scan.

## Risks

| Risk | Mitigation |
|---|---|
| Research loops burn the budget | Three independent stops; shared cache; depth cap |
| Desks under-investigate and file thin flags | Verifier rejection rate is monitored; instruction tuning |
| Agent Engine deploy fights us | Cloud Run fallback; ADK runs either way |
| Live demo network failure | Pre-computed run committed to `runs/` |
| Latency on a feature script | Concurrent desks; per-entity research cache |

## Scaling architecture (ADR-1) — as built, 2026-08-26

ADR-1's "target shape" shipped ahead of its triggers. Current execution model:

- **Web tier**: Cloud Run service (`greenlight`), stateless for everything durable;
  autoscales, `min-instances=1` to kill cold starts for visitors.
- **Analysis execution**: one **Cloud Run Job** execution per run (`greenlight-worker`,
  `RUN_MODE=worker`). Runs are **deploy-immune** — replacing the web service never
  touches an in-flight analysis. Fleet cap `MAX_CONCURRENT_LIVE=5` enforced against the
  Firestore ledger, not process memory.
- **Event stream**: the worker journals structured events to Firestore
  (`clearance_runs/{id}/events`, ordered chunk docs, ~1.5s cadence). ANY web instance
  serves any run's live view by tailing the journal (`_journal_relay`); a page refresh
  or instance restart replays the full journal — the client cannot tell the difference.
- **Records**: immutable JSON in GCS after completion; the web tier serves them by id.
- `scripts/safe_deploy.sh` is the only sanctioned deploy path: refuses while runs are in
  flight, runs the unit suite and compliance scan first, and keeps the worker job pinned
  to the same image as the service.

## Systems fundamentals (review edition)

The section a systems reviewer should read first. Claims here are load-bearing; the
incident log backing them is `docs/DECISIONS.md` (2026-08-26/27 entries), and the
capacity roadmap is `docs/SCALING.md`.

### Authentication & authorization

- **Users**: Google OAuth 2.0 authorization-code flow. Sessions are **stateless signed
  cookies** (HMAC over `SESSION_SECRET`; no server-side session store to scale or lose).
  Running an analysis requires sign-in; anonymous visitors get replays and case studies.
- **Authorization** is owner-scoped: run records, scripts, deletion, and history are
  keyed by the Google `sub` claim; a non-owner id guesses nothing because record ids are
  128-bit random and every owner-gated route re-checks the session. Admin surface is
  allowlisted by account.
- **Services**: the worker job and web service run as least-privilege service accounts;
  secrets (Parallel key, ClickHouse credentials, session/encryption keys, OAuth client)
  live in **Secret Manager**, injected at deploy, never in the image or repo. The
  browser never sees any third-party key — all external calls are server-side.

### Security posture

- **Transport**: TLS end to end (Cloud Run managed certs on scriptrisk.com).
- **At rest**: GCS/Firestore encrypt by default; uploaded screenplays are additionally
  **app-layer encrypted (Fernet: AES-128-CBC + HMAC) before they reach the bucket**, so
  a bucket-level leak yields ciphertext. Key rotation strategy: key-version prefix on
  blobs, re-encrypt on read (designed, not yet needed).
- **Browser**: strict CSP (`script-src 'self'`, no inline scripts — enforced in anger:
  the dark-mode boot script had to become an external file to comply), `frame-ancestors
  'none'`, nosniff, restricted `form-action`.
- **Abuse controls**: 5MB upload cap, MIME/extension allowlist, per-IP rate limits on
  expensive endpoints, sign-in required for anything that spends money.
- **Log privacy invariant**: log lines never contain screenplay text or titles
  (exception types and counts only) — the privacy page promises it, `pipeline.py`
  enforces it, and the run journal (which does carry excerpts) lives in Firestore
  behind IAM rather than in logs.
- **Supply chain**: `scripts/check_forbidden_deps.sh` blocks non-Google AI SDKs by name
  on every `make check` and inside every deploy.

### Caching (five layers, each with an owner and an invalidation story)

| Layer | Scope | TTL / invalidation |
|---|---|---|
| Session research cache (`research:{entity}:{qhash}` in run state) | one run, all desks & batches | dies with the run |
| Durable research cache (GCS) | cross-run, cross-user | 7 days; key = question hash, so identical questions share sources (score stability + cost moat) |
| Provenance registry | process-local, one run | dies with the worker; deliberately NOT in shared state (parallel delta races, see incidents) |
| Ratings corpus (ClickHouse) | global | rebuilt only by explicit re-ingest |
| Static assets | browser/CDN-ready | version-stamped URLs per deploy (`/static/v-N/...`) — a browser can never mix two revisions |

Records are immutable after completion, so report/binder/one-sheet reads are trivially
cacheable; generated PDFs moving to write-once-at-completion is P0 in SCALING.md.

### Resource usage (measured, per feature-length run)

- 200–400 Gemini Flash calls (+1 Pro adjudication), 30–70 Parallel searches, ~$2–5 API
  cost, 10–30 min wall clock. Concurrency inside a run: 4 desks (clearance further split
  into ≤4 parallel batch agents with bounded context), verification semaphore = 10.
- Fleet: ≤5 concurrent runs (ledger-enforced); worker container is CPU-light (the work
  is remote LLM calls); web instance ~100–200 RPS for pages.
- Hard ceilings that protect the bill: page-scaled research budgets per desk,
  `deep_research` ≤2/desk at 3 credits each, LoopAgent iteration caps, retry caps on
  every rejection path.

### Monitoring & observability

- **Structured logs**: `run_summary` (status/pages/timing, no content) per run;
  warning-level lines for every live-API failure (exception type only).
- **Live metrics**: `/api/metrics-lite` (uptime, runs, errors, `running_now`) +
  durable all-time counters in Firestore.
- **Audit trail**: the journal is a complete, replayable record of every tool call and
  verdict in every run — debugging today's six production incidents used nothing else.
- **External uptime checks** on the public site.
- **Alerting (shipped 2026-08-27)**: a log-based metric (`run_failures`: run_summary
  status=error or RUN ABORTED in worker logs) drives a Cloud Monitoring policy that
  emails on any failure within 5 minutes, auto-closing after 30. Journal-stall and
  429-burst alerts remain candidates if failure modes recur.

### Redundancy & availability

- Web: multi-instance capable, `min-instances=1`; deploys are gated (tests + no-runs) and
  roll atomically with version-stamped assets.
- Runs: isolated per-Job; a web-tier crash or deploy cannot kill one. A page refresh
  reattaches to the journal from event zero.
- Data: GCS + Firestore are regionally replicated managed services; ClickHouse Cloud is
  managed HA; all state that matters survives any single instance dying.
- **Single-region honesty**: everything lives in us-central1 (embeddings are pinned
  there; Gemini uses the global endpoint). A regional outage takes the product down —
  accepted at this stage; multi-region is P2 in SCALING.md. RTO for that event =
  redeploy elsewhere (~30 min, scripted path exists); RPO ≈ 0 for completed records
  (durable in replicated storage), in-flight runs would need re-running.

### Consistency model

- **Firestore ledger/journal**: strongly consistent; journal chunks are append-ordered
  with monotonic sequence — the relay never reorders or drops within a connection, and
  reconnects replay from zero (idempotent client rendering).
- **Records**: write-once at completion; readers see either "running" (live view) or
  the complete record — never a partial.
- **User history stubs**: eventually consistent by design (written at dispatch and at
  completion); the reports page cross-checks any "running" stub against the ledger, so
  a stale stub self-corrects on read.
- **ADK session state**: deltas from concurrent branches merge **last-writer-wins** —
  the sharpest edge in the system. Standing rule, paid for three times: NO mutable
  shared value lives in a state key that two parallel agents write. Budgets, flag
  lists, open questions, and research indices are per-agent keys; flag-id sequence,
  provenance registry, retry ledgers, and live-API health are process-local keyed by
  invocation (a run executes in exactly one process, which makes this sound).

### Partition tolerance & failure modes (graceful-degradation matrix)

| Dependency down | Behavior |
|---|---|
| Vertex Gemini (transient 429/5xx) | HTTP-layer retry ladder (8 attempts, 10→120s, jitter) on every model call incl. verifiers; the run breathes instead of dying |
| Vertex (sustained) | circuit breaker: ≥4 consecutive failures with zero successes aborts the run LOUDLY (`RunAbortError`) — an unresearched report that looks real is worse than an honest failure |
| Parallel API (one call) | error returned to the desk, budget refunded, failure counted and disclosed on the report ("N research calls failed") |
| Parallel (sustained) | same circuit breaker |
| ClickHouse | rating prediction degrades to explicit "comparables unavailable"; clearance work unaffected |
| Firestore (journal write fails) | worker continues the analysis; the live view stales but the record still lands in GCS at completion |
| Model misbehavior (hallucinated tool, malformed args, fabricated quote) | tool-error shield converts to corrective feedback; citation auto-repair substitutes registered verbatim text; per-flag retry caps prevent loops; the blinded verifier is the final gate |
| Worker killed mid-run | salvage path verifies and persists everything filed; run marked failed honestly; resume-from-journal is the designed successor (P1) |

The error-handling hierarchy, in one line: **model mistakes are conversation, transient
faults are patience, dependency outages are loud aborts, and nothing else may end a
paid run.**

### Data lifecycle

Upload → app-encrypted script + run ledger entry → journal (audit) → immutable record →
user-initiated deletion removes record, script, and ownership marker permanently.
Research cache entries expire at 7 days; journals persist for replay until deleted with
the run.
