# Decision & research log

Things we pursued, researched, or rejected — with the reasoning, so we stop re-deriving
them. Append-only; newest entries at the top. Bigger architecture decisions live in
`docs/TECH_SPEC.md` (ADR-1); this file is the running notebook.

---

## 2026-08-27 — Ratings corpus: 2,487 → 6,302 (the complete MPA era, not 10,000)

Target was "increase to 10,000." Measured the universe first: Wikidata holds 6,760 films
with an MPA rating (P1657), 6,625 of them with an English Wikipedia article — 10,000 does
not exist in any clean-provenance source, and the alternatives (IMDb datasets, TMDB) carry
license terms we don't want under a commercial product. Instead: relaxed the year cutoff
from 1985 to 1968 — the year the MPA rating system began — and ingested the complete era:
6,302 usable content profiles (46 stubs skipped), same CC0/official-API provenance, every
row with a source URL. The claim improved from a bigger number to a complete one: "every
MPA-rated film since 1968 with a citable source." Embedding cost ~$1.30 one-time.

---

## 2026-08-27 — Live-dependency error regime: fail loud, degrade with disclosure, alert always

The Social Network outage (a sorted(None) TypeError in research()'s new cache-key
modifier aborted the whole run — ADK propagates tool exceptions) forced the question of
what a paid product should do when a live call fails. Three tiers, now mechanical:
(1) dependency down — >=4 consecutive live-API failures with zero successes trips a
circuit breaker that aborts the run with an explicit "research API unreachable" error;
an unresearched report that looks real is worse than an honest failure. (2) transient
blip — the failing call returns an error to the desk, refunds its budget, and the
count is disclosed on the report ("N research calls failed during this run"). (3) every
failure logs a structured warning (exception type only, never script text) for log-based
alerting. Health counters live in a process-local registry, not ADK state — same
last-writer-wins race as the provenance saga. Regression tests pin the crash, the
breaker, and the stays-open-after-success behavior.

---

## 2026-08-27 — Parallel, used in depth: Search upgrades + Extract + Task API

Decision: leverage the partner API as far as its surface allows, since the track rewards
genuine integration and cost is no longer the binding constraint. Four changes, all on the
default runtime path, all behind the same provenance gate:

1. **Geo-targeted search** — `research(country="CN")` sets Parallel's `location`; the
   Territory desk now searches *from* the territory it is judging. Prompt requires it for
   territory-specific questions.
2. **Registry-restricted search** — `research(restrict_to_domains=["uspto.gov"])` uses
   Parallel's `source_policy.include_domains`; live-verified that a bbfc.co.uk-restricted
   query returns only BBFC pages. For trademark status, copyright renewals, PRO repertories,
   case law.
3. **`fetch_page()` = Extract API** — full-page retrieval when a search excerpt is too thin
   to cite (repertory entries, court opinions, regulators' guideline pages). Costs 1 research
   credit; refunds on fetch failure; excerpts enter the provenance registry so they are
   citable verbatim.
4. **`deep_research()` = Task API** (`core` processor) — the last-resort escalation for
   ownership chains that decide a BLOCKER/HIGH and that two searches couldn't resolve.
   Costs 3 credits, hard cap 2 per desk per run (mechanical, in the tool, not the prompt).
   Task citations carry verbatim excerpts → same provenance gate as Search.

Also: search `max_results` 10→12, `max_chars_total` 8k→10k, results-to-model 6→8 — modest,
because the 429 saga taught us token appetite is the real budget. Rules check: all three are
official `parallel-web` SDK products (the sanctioned partner SDK); Search remains the default
path, so the track requirement is untouched; no non-Google AI SDK enters the repo.

**Not done, deliberately**: giving blinded verifiers their own live searches. It would be a
strong "survives cross-examination" story, but a verifier that retrieves *different* evidence
than the desk saw can reject true findings for reasons of retrieval variance, and the demo
record is already promoted. Parked for after the deadline.

---

## 2026-08-27 — The overnight demo-refresh saga: six bugs, one mechanical contract

Ten graded eval runs converged the refreshed demo record (promoted: run 8, 19/21 —
every visual USE item including the new Krane-tattoo trap, sync, all safety/territory).
The night's bug ledger, each earned from a failing run: (1) State.keys() crash;
(2) shared provenance index clobbered across desk branches; (3) same clobbering within
one turn's parallel tool calls — ANY mutable index in ADK session state loses writes
(deltas merge last-writer-wins) → registry moved to process memory keyed by invocation;
(4) chunk-boundary excerpt stitching → joined-text registration + word-overlap fallback
(residual rejections proved to be the check WORKING: desks quoting regulations from
model memory before sourcing them); (5) clearance priority inversion → two-pass order
(cheap USE-level certainties before deep ownership chains) + budget 18→24→28,
iterations 8→10, enum-safe remedy verbs (my own doctrine text had induced LEGAL_REVIEW);
(6) the early-quit failure mode (three sightings: desks closing with worklists
unaddressed and budget unspent) → done() now MECHANICALLY refuses closure below 50%
worklist coverage with ≥3 budget left (max 2 refusals) — never let the model promise
what a tool can verify. Case regens under the final doctrine: Reservoir Dogs 0→24
(needle-drop master filed, brands at FYI; the closing contract doubled its findings),
Little Miss Sunshine 13→2 after adjudicator consolidation was extended: rating_* AND
territory_* categories are script-wide claims that merge across disjoint scenes (a run
had filed 17 rating_language flags, one per F-bomb). Old fixture-based records purged —
the tattoo edit shifted raw_span offsets.

## 2026-08-26 — Multilingual screenplays: roadmap, plus a shipped language guard

Question: support non-English scripts? Three problems of different sizes. (1) Reading:
Gemini handles 40+ languages; INT./EXT. sluglines are fairly international; Romance/
Germanic need per-language parser tweaks (time-words, cues); CJK/Arabic are real projects
(no uppercase, RTL). (2) In-language research: Parallel + provenance machinery are
language-agnostic — mostly free. (3) THE BLOCKER — legal/ratings calibration: our
doctrine is US law (Rogers, CARA math, MPA comparables corpus on an English-optimized
embedding model). A French script for a French production lives under droit moral/CNC
where our calibrations are confidently wrong. Roadmap: phase 1 "non-English script, US
production" (parser only, doctrine unchanged); phase 2 per-jurisdiction calibration,
market by market, like the territory-expansion model. SHIPPED NOW: a deterministic
language guard (langguard.py — common-word smoke test + non-Latin detection) that stamps
english_ok on the run and shows an honest amber caveat on the run page instead of
silently serving Anglo-calibrated analysis for a non-English script. Related decision
same day: territory selection deliberately NOT built (user choice: keep evaluating all
four calibrated markets for every run); territory expansion criteria logged with the
selector design in this file's future entries if revisited.

## 2026-08-26 — Switchback re-run: burn-ban doctrine validated; recounted-stunt fix

Sixth external review, on the corrected Switchback log: the script-cites-a-rule doctrine
fired exactly as designed (burn-ban campfire = MEDIUM with fire-marshal permit remedy),
CCR sync+master captured with Concord Music as the master holder, motorcycle/water
logistics filed sanely. One remaining quirk, same shape as earlier ratings fixes: the
safety desk flagged a cliff jump characters only TALK about (past-tense anecdote) as an
active $50-250k stunt. Fix: DEPICTED vs RECOUNTED on the safety desk — underwrite only
what the production must stage; recounted events file nothing unless a flashback, a
re-attempt, or later-depicted setup stages them. Counterweight shipped in the same
commit per the pendulum lesson.

## 2026-08-26 — Switchback validation + the "script cites a rule" principle

Fifth external review (Switchback, a quiet two-hander): 100/100 with correct restraint —
mention-vs-use held (CCR recording and a Jack Daniel's bottle processed as standard cues
without false-positive tantrums), zero ghost flags, anxiety scaled to the script. Two
soft misses shared one missing principle, now in the safety desk's doctrine: WHEN THE
SCRIPT ITSELF CITES A RULE, THE PRODUCTION FACES THAT RULE — dialogue naming a burn ban
over a depicted campfire = MEDIUM fire_safety (fire permit, certified FSO, staged water,
even simulated); script-raised legality that is plot rather than physical production
(scattering remains) = LOW/FYI permitting note. Distinct from ghost flags: element and
constraint are both on the page. Also reverted the SCRIPT MONO typewriter theme same day
(user verdict: no) — clean two-commit revert back to midnight-navy/gold; the mono
experiment's assets live in git history if ever revisited.

## 2026-08-26 — Hangover stress test: the pendulum correction

Fourth external review (The Hangover run) caught two regressions the doctrine overhaul
introduced. (1) Clearance flatlined — ZERO flags, zero open questions, 19/45 budget
unspent on the script containing film history's most famous tattoo-copyright suit, a
Tyson cameo, a stolen police cruiser, and a performed Phil Collins track: the desk read
"expressive works are protected" as blanket IP suppression. Fix: the MENTION vs USE
rule — Rogers protects references; the production must still clear what it PHOTOGRAPHS,
PERFORMS, or FEATURES (cameos → publicity agreement; played/performed songs →
sync/master; recognizable custom tattoos → artwork_license, the litigated case; real
branded property as story vehicle → trademark_use/location at MEDIUM) — plus a zero-flag
self-check: never close entity-dense scripts with no flags, no questions, unspent
budget. (2) Ghost flags: 10 NO_ACTION findings across three desks describing ABSENT
elements ("no chicken present; if added...") — the "cleared item is silence" rule had
only ever been written into clearance's prompt. Now on all four desks, with an explicit
ban on speculative if/then filings, and a verifier backstop: absence-premised or
conditional-on-unwritten-changes claims are REJECTED regardless of citations.
Lesson worth keeping: every doctrine correction needs a counterweight rule in the same
commit, or the pendulum swings; and desk-shared discipline belongs in COMMON text, not
one desk's prompt.

## 2026-08-26 — First Look: filling the triage dead-air (waves 1+2 built; wave 3 planned)

The first ~2-6 minutes of a big run are one giant triage call with no visible output.
Built: **wave 1** — deterministic script profile (profile.py: pages/runtime, INT-EXT,
day/night, night exteriors, locations, cast by dialogue share, element keyword hits)
rendered instantly from /api/script; **wave 2** — one Flash call (firstlook.py) for
logline/genre/tone/3 observations + corpus comparables, journaled to the run doc and
emitted over the same SSE stream, rendered under an explicit "first impressions ·
unverified" label so 40-second opinions never dress like cited findings. Cost ~$0.02/run;
failure is silent (garnish, never a blocker).

**Wave 3 — planned, not built: parallel Writer's Room worker.** An upload toggle ("also
run Writer's Room") dispatching a SECOND worker job on the same script — full
coverage/pitch/format alongside clearance, results panel on the run page, link to the
full writer report. One upload → breakdown + coverage + cited clearance: the direct
strike at Prescene's feature set (compare page updates with it). Needs a writer-worker
entrypoint mirroring greenlight.worker; gate behind the toggle so casual runs don't
double-spend (~$0.10-0.30/run extra). Build after waves 1+2 prove out.

## 2026-08-26 — Accuracy playbook (second external review): adopted with corrections

A consolidated prompt/architecture playbook was reviewed line by line rather than pasted
in wholesale (wholesale replacement would have dropped the citation invariant, coverage
roll-call, counting discipline, and PRO targeting). Adopted as ADDITIONS: clearance
contact-info sweep (non-555-0100..0199 phone numbers, real domains/handles), art/tattoo/
mural copyright sweep, PD-by-age check before music flags; safety minors-no-speculation,
environmental-compounding rule, CSATF bulletin grounding (#1/#4/#8/#20/#33/#38),
post-2021 firearms/armorer protocol; ratings dialogue-vs-depiction distinction;
territory hard-blocker-vs-localized-alt-cut calibration, cultural-realism filter,
cartographic/geopolitical sweep; verifier multi-step-inference rejection standard.
Corrected while adopting: "pre-1929 = PD" is stale (2026 line: pre-1931; stated as
95-years rolling); "2+ F-words = mandatory R" softened to our cited language-math rule.
Already shipped elsewhere: Rogers doctrine, post-mortem rules, negative clearance
phrasing, cost-band separation, multi-scene dedupe, async/worker architecture,
zero-impact suppression (a cleared item is silence). Backlogged: immutable finding IDs
for draft-over-draft change tracking (pairs with the parked run-comparison view).

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
