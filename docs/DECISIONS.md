# Decision & research log

Things we pursued, researched, or rejected — with the reasoning, so we stop re-deriving
them. Append-only; newest entries at the top. Bigger architecture decisions live in
`docs/TECH_SPEC.md` (ADR-1); this file is the running notebook.

---

## 2026-08-26 — Vertex throughput: what exists between on-demand and Provisioned Throughput

**Question:** runs hit 429 RESOURCE_EXHAUSTED under load; can we buy modest guaranteed
throughput?

**Findings:**
- On Vertex there is a cliff: Dynamic Shared Quota (free-of-commitment, best-effort, no
  raisable per-project limit for 2.5-gen models) → Provisioned Throughput at **$1,200 per
  GSU per week, minimum 1 GSU / 1 week**, purchased as a console order, meter runs 24/7,
  not toggleable. Google's own sizing example: 17 GSUs = $20,400/wk.
- **Decision: do not buy.** Whole project budget is $100 credits; our burst peak is
  ~10–20 requests/min. PT is rational at real paying-customer traffic (~31 scripts/week
  covers one GSU at $39/script). Revisit with utilization graphs, not vibes.
- **The real middle tier:** the Gemini **Developer API** paid tiers — same models,
  pay-per-token, *defined* rate limits (Tier 1 ≈ 150–300 RPM / ~2M TPM; Tier 2 at $250
  cumulative spend ≈ 1,000+ RPM). ADK switches paths via `GOOGLE_GENAI_USE_VERTEXAI=false`
  + API key. **Caveat:** contest rules say *Google Cloud* AI at runtime; Developer API is
  Google-but-AI-Studio. Plan: buildable as an off-by-default toggle, demo path stays pure
  Vertex; it is the post-hackathon scaling answer.
- Vertex **Batch API** is 50% off but hours-scale — wrong for live runs, right for future
  bulk case-study regeneration.

**What actually fixed the 429s (free):** per-desk triage slicing (~4× less token traffic
— desks were re-sending all four worklists every turn), Gemini via the **global endpoint**
(`GOOGLE_CLOUD_LOCATION=global`; embeddings stay regional via `EMBED_LOCATION` —
text-embedding-005 is not served globally), retries 8×/max 120s, and salvage now runs the
blinded verification fan-out itself so an aborted run still yields a *verified* partial
report. Evidence: 109-scene feature went from aborted → clean 341s.

## 2026-08-26 — Worker-job architecture shipped (ADR-1 Phase 2/3)

Deploys kept killing in-flight runs (twice, once for real on a user run). Shipped:
Firestore event journal (`clearance_runs/{id}/events`, chunked ~1.5s to respect per-doc
write limits) + journal-relay SSE (any instance can serve any run's stream) + Cloud Run
Job `greenlight-worker` (`RUN_MODE=worker` dispatches; job runs to completion regardless
of deploys) + fleet-wide concurrency cap via Firestore (`MAX_CONCURRENT_LIVE`, default 5)
+ guarded deploys (`make deploy` → `scripts/safe_deploy.sh`, refuses when `running_now>0`,
syncs the worker job image). Gotcha learned: Cloud Run Job execution `--args` **replace**
the job's args wholesale — dispatch must pass `["-m","greenlight.worker",run_id]`.
Not per-user fairness capped yet (one user can hold all 5 slots) — noted, deferred.

## 2026-08-26 — Run-speed levers (research)

Where time goes on a feature: desk loops (serial turns/desk, ~5–15s per LLM turn +
research calls), verification burst (one call per flag, semaphore), triage (~2 silent
min on 189 scenes), and above all **429 backoff sleeps** (clean 109-scene run: 341s; the
same architecture under quota contention: 795s+). Ranked plan:
1. ~~Provisioned Throughput~~ — rejected on price (above).
2. **Verification-as-you-file** — dissolve the barrier between desk phase and
   verification; verifiers start the moment a flag is filed. Saves most of the
   verification wall-clock (~60–90s on big runs) and makes Studio Room verdicts stream
   throughout. The one real engineering task on the list.
3. **Concurrent research calls** within a desk turn (async tools) — measurable, small.
4. Verifier semaphore 6 → 10.
5. Perceived speed: triage progress narration (the first 2 minutes feel dead).
Rejected: model downgrades for verifier/adjudicator (quality is the product), budget
cuts (coverage was *just* fixed), scene-batching map-reduce (regression to the killed
pipeline architecture).

## 2026-08-26 — Expressive-work legal doctrine (external review)

External legal review of the public case studies caught the clearance desk calibrated to
commercial-speech law (advertising sources cited for film uses). Adopted **Rogers v.
Grimaldi / nominative fair use** framing: neutral brand/person use in an expressive work
files nothing (or FYI + greeking courtesy); disparagement = MEDIUM framed as defense-cost
risk; HIGH reserved for a named product depicted causing harm or implied endorsement.
Post-mortem rules: no defamation-of-the-dead flags ever; deceased-artist mentions are not
publicity problems (the *recording* still needs sync/master — copyright, not publicity);
photo props stay artwork_license on the photograph's copyright. Departure from the
review: disparagement stays MEDIUM (not LOW) because E&O practice prices defense costs
even for winnable suits. Validated by regenerating the Clerks case: MasterCard/Visa HIGH
flags gone entirely. Declined from the same review: async-architecture rewrite framed as
fixing a "4-minute hanging request" — that request is the SSE stream working as designed
(though ADR-1 Phase 2 shipped later the same day for its own reasons: deploy immunity).

## 2026-08-26 — Feature-length scale test (THE LONG HAUL, 109 scenes)

Original stress screenplay with a 12-trap answer key. Result: 341s, 11/12 traps, all
majors caught (separate sync+master with real ownership chains; PD traps correctly
silent; trademark nuance fired). Two soft misses → two fixes: **counting discipline**
(ratings desk searched the inflected form it noticed — now: stem search, script-wide
claims, excerpts quote tool output) and **page-scaled research budgets**
(`scaled_budgets()`: linear above 12-page baseline, ×2.5 cap — territory had starved to
0 and the name-commonality sweep never ran).

## 2026-08-25 — Score consistency: ensemble averaging rejected

Measured same-script variance after determinism fixes (vocabularies, severity anchors,
temp 0, dedupe, durable research cache): delta dropped 21 → 8 points. 3-run averaging
would cost 3× per run for marginal narrowing — rejected as default; parked as a possible
paid "deep scan" tier. The report carries an honest directional-score caveat instead.

## 2026-08-24 — Ratings corpus pivot

Wikipedia CARA-rationale extraction yielded ~1% and a naive rating regex matched "PG"
inside "PG-13". Pivot: film **content profiles** (Wikidata P1657 CC0 ratings + Wikipedia
article text via official APIs), 2,487 films embedded with text-embedding-005 in
ClickHouse. Prediction became "7 of your 8 nearest released comparables are rated R" —
evidence, not model opinion.

## 2026-08-23 — Architecture: agents, not a pipeline

The original extract→search-once→four-prompts→dedupe design was killed: it cannot chase
ownership chains or decide depth. Replaced with LoopAgent desks + blinded verification +
adjudicator. Governing principle, applied everywhere since: **never let the model assert
what a tool can retrieve.** (Full reasoning: `docs/TECH_SPEC.md`.)
