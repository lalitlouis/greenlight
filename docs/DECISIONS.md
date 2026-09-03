# Decision & research log

Things we pursued, researched, or rejected — with the reasoning, so we stop re-deriving
them. Append-only; newest entries at the top. Bigger architecture decisions live in
`docs/TECH_SPEC.md` (ADR-1); this file is the running notebook.

---

## 2026-09-02 — The F-word count is a rule, not a pattern: the MPA rules become a local tool

Ten gate rolls of one unchanged fixture predicted R nine times and PG-13 once. The cause
was structural: the descriptor vocabulary cannot encode a COUNT, so bare "language" reads
PG-13 and R alike, and the prediction followed whichever intensity word the desk chose.
The corpus measures what CARA did; the MPA's own Classification and Rating Rules say what
it requires — "More than one such expletive requires an R rating," absent a special
two-thirds vote. The product forbade rule-shaped claims because the desks typed rules
from memory; the fix is to make the rule retrievable, on the pattern of the CSATF index.

Shipped: `scripts/harvest_mpa_rules.py` pulls the official PDF (filmratings.com, effective
July 24, 2020, SHA-256 on the asset) into `data/mpa_rating_rules.json` — the five rating
provisions plus the expletive sentences, verbatim. `rating_rules(topic)` serves them as a
free local tool whose output is registered provenance (`rules_table` / `local`). The
normative gate and the eval now ADMIT a rule-shaped rating claim only when a citation
quoting the rules' own text sits on the flag. The prepass census gains a spoken F-word
count (dialogue only), carried in state, and `rating_boundary` floors R into the coverage
set at two or more uses with a note citing the rule — a deterministic floor on a script
fact, alongside the dominant-descriptor floor. What-If's boundary is untouched (it
evaluates the revised profile, not a count). Owner-approved 2026-09-02.

---

## 2026-09-01 — Full-codebase review implemented: 44 defects, one batch, 89 new tests

The six-area review (docs/REVIEW-2026-09-01.md) found every documented learning present in
the code except the verifier regression set, and 44 defects that let a false finding render
or made the report disagree with itself. All were fixed in one deterministic batch (no run,
no spend), pinned by 89 new tests (286 → 375), `make check` green. What changed, by class:

- **False keeps closed.** The overturn guards no longer flip a sourcing rejection to
  SUPPORTED (F1004 in the gate record was a citation_offtopic rejection rendered as
  verified): a no-number rejection cannot anchor, the capitalized-word fallback is gone,
  and any sourcing ground strikes at most the false ground. Re-sourced, refiled, and
  fact-propagated flags now pass the same authority/statute/sync-master/normative gates
  as a first filing; reverify shares the pipeline's post-verification finalizer.
- **Instruments made stable.** One descriptor per category is canonicalised before the
  boundary model sees it and the list is persisted on the record (`descriptors`, schema
  additive) — sixteen same-script runs had produced four different conformal sets. The
  attached marginal is the descriptor the finding names (the longest-key rule had let the
  parser token "unmodified" win). A neighbour at distance 0.0 now weighs as an exact match,
  not as 1.0. Marginal and comparables corpora are labelled as two corpora with one
  rounding rule. Cut lists are dropped, at filing and after reconcile, when the prediction
  is already at target.
- **Deterministic inputs corrected.** Census regexes count compounds and stop counting the
  "chink in the armor" idiom; the parser no longer mints scenes from "EST. 1895" or ".45"
  and now captures shooting-script numbers; the safety prompt's firearms bulletin number
  (#38 was severe weather) is gone in favour of the lookup tool; the public-domain year is a
  substituted placeholder; three prompt self-contradictions (ratings rule vs claim shape,
  safety anchor vs burn-ban, territory NO_ACTION) are resolved; `apply_plan` refuses the
  merges and renames its own instruction forbids.
- **Surfaces reconciled.** Web and binder route cleared rows on kept ids alike; absorbed
  ids are rewritten to their survivor everywhere; open questions that restate a finding
  render under it; fail-open markers, withheld cause, and the two-path cost reach every
  print surface; scene labels are never truncated.
- **Gates widened.** `scripts/eval_invariants.py` is shared by both evals (the scale gate
  had drifted to a subset). New assertions: phantom-id references, prose scenes that do not
  exist, cut-list direction (E2 closed), majority-vote recompute, conformal set reproduced
  from descriptors, counts/cost/days/pages reconciliation, non-vacuous binder coverage,
  year+term arithmetic, rightsholder-name traceability. The cached record grades 44/46;
  both misses are real defects in that record's desk output (Nighthawks "through 2038";
  licensors named in prose that no excerpt carries). `eval_comps` benchmarks the shipped
  `cara_rationales` corpus.

Scene-structure proof: both fixtures and all six case scripts parse to identical scene ids
and headings before and after; the two OCR'd, feed-less case texts (LMS, Wolf) would move
some page numbers on regeneration because mangled cues are now read as speakers.

Left open, stated: budgets/counters still live in ADK state keys under the parallel-delta
merge; `_nudge_tool_use` fixed but unwired (a gated change); rating reconcile after a
marginal-gate demotion is manifest-recorded, not executed; the PDF page-cap truncation count
is computed but not yet written to the record; no cut-beat "pre-removed word" gate (the class
has not reproduced locally); music-fee tiering and the severity-vs-cost assertion remain
backlog; the model-judged verifier pair set remains roadmap. Prompts, parser, and tool
contracts changed, so the next fixture gate run is required before deploy.

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

## 2026-08-27 — Phase 1 delivered: the scale gate, and what its first run caught

`make scale-gate`: a deterministic generator (scripts/gen_scale_fixture.py) produces
fixtures/scale_gate.fountain — an original 100-scene, ~95-entity band-tour feature that
forces all four clearance batches — and scripts/eval_scale.py grades 21 checks: one per
structural failure class of 2026-08-26 (abort, id collision, rejection loop, missing
rating, wall clock, rejection-rate band) plus seeded traps for every doctrine layer.
First run: structural tier 7/7 clean in 10 minutes; final 19/21. The gate immediately
earned its keep by catching three bugs in its own tooling (mtime vs name-sorted "latest"
record — eval_run had it too; flags_about unioning ALL flags on single-param calls —
spurious passes/misses in both directions) and two genuine desk gaps for tomorrow:
(1) ratings desk missed the clustered F-bombs (no rating_language flag at all),
(2) trade_libel_venue doctrine did not fire on its first live casino-destruction test
and no controlled-venue location classification attached. Discipline going forward:
desk/tool/doctrine changes pass BOTH gates before deploy.

---

## 2026-08-27 — Indie pre-screen tuning (Hangover review): noise, venues, locations, music

Reviewer feedback on the completed Hangover report, adopted: (1) FYI/LOW findings
collapse behind one summary line on the report ("N informational items — protected
expressive use; nothing here blocks production") — the producer's screen belongs to
what can sue them or crash the budget; everything stays one click away (transparency
thesis intact), and anchor jumps auto-open the group. (2) `trade_libel_venue`: a real
named business used as the SETTING for destructive/illegal fictional events is
business-disparagement exposure beyond trademark (litigious casinos/clubs police
depiction, not logos); counterweight — backdrop mentions stay FYI. (3) Location
realism: every location_release remedy classifies PERMIT / LOCATION AGREEMENT /
CONTROLLED VENUE, with controlled venues (casinos, theme parks) marked NOT obtainable
at indie budgets — plan the build, don't price the fantasy. (4) Music at indie
budgets: famous-track sync remedies must carry the budget path (library/indie sync at
hundreds-to-low-thousands, or cut the cue) and warn off sound-alikes (Midler trap).
Not gated by a fresh eval tonight — doctrine additions with explicit counterweights;
next graded run is the check.

---

## 2026-08-27 — Biographical doctrine: defamation/false-light + adaptation context

Reviewer feedback post-TSN, adopted at prompt-layer size (not a fifth desk — the
four-desk architecture mirrors the domain and stays): (1) Clearance now separates
DEFAMATION / FALSE LIGHT (`defamation_false_light`) from right of publicity for real
living persons depicted negatively — calibrated on the DOCUMENTED RECORD the desk must
research: record-supported conduct MEDIUM (truth defense, annotation trail), untraceable
dramatic invention HIGH with the invention named; public figures noted (actual malice
raises the bar, not the annotation duty), private orbit-individuals ranked HIGHER.
Counterweight: neutral/positive depictions never defamation-flag. (2) An adaptation
channel end-to-end: optional "source material / life rights" field on upload + title-page
Source/"based on" auto-detection -> `adaptation_context` state -> clearance instruction;
scenes traceable to declared source inherit its rights posture, untraceable
real-person scenes are presumptively invented. TSN's own findings (Saverin ouster,
Erica Albright composite) are exactly this class.

---

## 2026-08-27 — Clearance batching: the department hires associates

Large-script fix, architecture-true: the clearance desk is now a ParallelAgent of up to
4 batch agents, each holding a bounded, priority-ordered slice (~25 items, PLOT_CRITICAL
first) of the worklist with a FRESH conversation — per-call context is bounded by
construction, killing both the quadratic-prefill slowdown and the long-context
hallucination zone. Shared across batches: session research cache, durable GCS cache,
provenance registry (all pre-existing). Isolated per batch: every mutable state key —
budgets (lazy proportional partition of the desk budget), flag lists, open questions,
research-key indices, done-refusals — because parallel writers to one ADK state key
lose updates (paid for that lesson three times). Flag ids moved to a process-local
counter (gaps on rejection are harmless; collisions are not). Batch agent names
normalize to the base desk in journal events, so the four-desk UI contract is
unchanged. Small scripts: one real batch, three one-turn empty closes.

---

## 2026-08-27 — Self-healing citations: the rejection hands back the real excerpts

TSN re-run exposed the flaw in "archive after first flag": desks legitimately file
SEVERAL flags per entity (sync+master per song; publicity+name per person). Flag #2 for
an archived entity meant quoting from memory -> verbatim gate rejection -> retry loop
(157 attempts, 145 rejections in one run; killed by user). The registry never lost the
text — only the model's view of it. Fix at the point of need: a provenance rejection now
looks up the entity's registered research excerpts (via the per-desk research-key
indices — NEVER by iterating ADK state keys) and returns 400-char verbatim heads in the
rejection message: "copy from these EXACTLY." A head is a substring of registered text,
so a citation copied from it passes the gate. Also: the run page's desk chips now count
FILINGS (tool results saying "Filed F…"), not attempts — the 157-vs-35 counter mismatch
was the tell that found this bug.

---

## 2026-08-27 — Pruning v2: disposition-aware, because age is the wrong signal

The first cut (keep last 8 exchanges) shipped, then a graded fixture run caught it
pruning results the desk had researched but NOT YET FILED from — the desk forgot the
Nighthawks and tattoo work it had paid for (16/21 vs the 19/21 baseline). Age says
nothing about need; the tools already know when a result dies: the desk works case
files, and once an entity has a FILED flag its research is never read again (verifiers
use session state + the provenance registry, not the conversation). Policy now:
(1) trim bulky results for entities this desk has already flagged — closed case files
go to the archive; (2) open case files are untouchable regardless of age; (3) last 12
exchanges always verbatim; (4) hard ceiling at 40 exchanges bounds monster scripts even
for open items. Trims keep a 300-char head + free-re-ask note. Rejected: LLM-summarized
compression — it puts a model in charge of rewriting the evidence trail, against the
product's core thesis, and adds calls to the path we're trying to make cheaper.

---

## 2026-08-27 — History pruning: the slowdown was us, not Vertex

Diagnosed the crawling Social Network run with data: Parallel searches 2-5s, ClickHouse
sub-second, ZERO 429s in the window — but Vertex p99 request latency 183s -> 220s ->
537s as the run progressed, tracking conversation growth exactly. The clearance desk's
AFC loop carried every research result ever retrieved on every turn; prefill scales
with input, so turns went quadratic. The same bloat explains the morning's TPM 429s
(giant requests) and the long-context degradation (run_code hallucination, "I will
continue" loops). Fix: before_model_callback `prune_stale_tool_results` on every desk —
last 8 tool exchanges stay verbatim, older tool payloads >600 chars collapse to a stub
telling the model a re-ask is a free cache hit. Small results (file_flag confirmations)
survive at any age; pruning operates on deep copies so session history and the journal
stay intact; flags/budgets/provenance live outside the conversation and are untouched.
User cancelled attempt 4 for this fix; TSN re-run is the validation.

---

## 2026-08-27 — The tool-error shield: a hallucinated tool name must not kill a run

Third Social Network failure, 43 minutes in, 37 findings filed: Gemini slipped into its
code-execution dialect and called a nonexistent `run_code` tool; ADK raises ValueError on
unknown tool names, and the raise sank the whole run. Fix: `on_tool_error_callback` on
every LlmAgent (`tool_error_shield` in agents/common.py) converts any tool error —
unknown name, bad args, tool exception — into a corrective message the model sees
("only the listed tools exist; there is no code execution"), so the desk self-corrects
and the loop continues. The deliberate abort stays deliberate: the research-API circuit
breaker now raises a typed `RunAbortError`, which the shield passes through untouched.
The error-regime hierarchy is now complete: model mistakes are conversation, dependency
outages are aborts, and nothing else can end a paid run.

---

## 2026-08-27 — The retry ladder that never ran: 429 resilience moved to the HTTP layer

Social Network's re-run died on a Vertex 429 after 262s despite our "8 attempts / 120s
backoff" RetryConfig — because that config NEVER APPLIED: `retry_config` is consumed only
by ADK's Workflow system, and LlmAgent silently ignores the unknown kwarg. The genai
client's real knob (`retry_options`) defaults to None = zero retries, and ADK converts a
surfaced 429 into _ResourceExhaustedError instantly. Every 429 since day one has been
run-fatal; the Long Haul "fix" survived on the global endpoint's headroom alone.

Fix: retries now live where requests are made — `Gemini(model=..., retry_options=
HttpRetryOptions(attempts=8, initial_delay=10, max_delay=120))` for all agents, the same
ladder on both verifier clients, and a shorter interactive ladder (4 attempts, ~30s worst
case) via the shared `llmclient.vertex_client()` for First Look / What-If / checks where
a user is watching. Dead `retry_config` kwargs removed everywhere so the code no longer
claims patience it doesn't have. Also reverted the speculative search-payload bump
(10k chars / 8 results back to 8k / 6) — it added ~25-30% token pressure per research
turn on the quota that was already the binding constraint.

Lesson, logged for good: an ignored kwarg is worse than a missing feature — verify that a
resilience setting actually fires (kill a call and watch it retry), don't trust that it
exists.

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

## 2026-08-27 — Flash tier upgraded to gemini-3.7-flash

Gemini 3.x Flash went GA on Vertex (global endpoint only; prod was already on
`GOOGLE_CLOUD_LOCATION=global`, embeddings stay pinned via `EMBED_LOCATION`).
Gated before adoption: two 21-check fixture evals on 3.7-flash scored 21/21 and
20/21 (the one miss, a merged sync/master flag, did not reproduce) at 260–297s —
matching our best fully-calibrated 2.5-flash run cold, with visibly richer remedy
prose. Adjudicator stays on `gemini-2.5-pro`: 3.x Pro is preview-only, and
previews don't ship in a paid product. All model names now live in
`greenlight/models.py` (env-overridable via `GREENLIGHT_FLASH_MODEL` /
`GREENLIGHT_PRO_MODEL`); any future change gates on the same eval. Cost: intro
pricing $0.75/$3.75 per MTok roughly doubles per-run model spend (~$2 → ~$4–5);
accepted deliberately — the case library and demo should showcase the best
engine available. Pricing doubles again 2027-01-01; revisit then.

## 2026-08-27 — Industry-format research adopted as the format roadmap

External research on clearance-industry conventions (input formats, report
conventions, the E&O workflow, WGA revision machinery) accepted as the basis
for ingest/emit priorities. The load-bearing findings:

- **PDF and FDX are both non-negotiable.** Writers send PDF deliberately (to
  prevent alteration); production sends FDX, the delivery standard whose XML
  carries scene boundaries, element types, locked scene numbers, and revision
  marks for free. We ingest PDF and Fountain today; FDX ingest is being added
  now. Third-party FDX is validated, not trusted (Final Draft's own KB warns
  it may not be well-formed).
- **Scene and page numbers are a shared coordinate system, not internal ids.**
  Once a script is locked, scene numbers never change — every department
  references them. Rule adopted: use the script's own numbers whenever they
  exist (FDX Number attributes, Fountain #42# syntax); generate and clearly
  label our own only for unnumbered spec drafts. Internally scene_id stays
  S### (stable machine id); the script's number is carried alongside and is
  what renders. scene.schema.json gains an optional `number` — additive.
- **Draft identity is chain of custody.** A clearance report is only valid for
  the exact draft it ran against. Every new record now carries a draft block:
  title, format, byte size, SHA-256, page count, scene-number provenance
  (script vs generated), and receipt date. Rendered on the report and binder.
- **Binder layout follows the industry**: severity-ranked exposure summary up
  front, body in script order (producers read alongside the script).
- Deferred deliberately: annotated-script PDF, Movie Magic .sex breakdown
  export, rights-holder contact blocks, title-report add-on, DOCX degraded
  path — post-deadline, none demo.

## 2026-08-27 — Revision-aware rescan is the subscription product

The WGA revision system (White -> Blue -> Pink ... colored pages, margin
asterisks at paragraph granularity, locked scene and page numbers, A-pages,
OMITTED pages) is a formal, machine-readable change-tracking protocol — and
incumbents bill against it by hand: $100 per revision pass "if asterisks are
attached." Decision: build revision-aware rescanning natively, in two stages.
Stage 1 (findings diff): ingest a revised draft, run it, and diff finding sets
against the prior run (match on entity + category + scene) -> "N new, M
resolved, K unchanged." Stage 2 (true incremental): read FDX revision
asterisks and re-analyze only changed pages. Stage 1 is the demo-able MVP and
the economic core of the recurring tier; Stage 2 is the software moat no
manual researcher can follow. Not started yet — first in line after the
format work above; privacy-vector detection (phones, addresses, plates) rides
the next gated calibration batch alongside it.

## 2026-08-28 — Cloud execution: GitHub as front door, Google Cloud as engine

Decision on where automation eventually lives. Split by job, not by loyalty:

- **GitHub Actions — triggers and free checks.** The deterministic layer stays
  on every push (lint, contest-compliance scan, the offline unit suite incl.
  the binder-consistency gate). Deploys move behind a workflow that
  authenticates via Workload Identity Federation (no service-account keys
  stored in GitHub) and invokes the same guarded deploy path safe_deploy uses.
- **Google Cloud — everything paid, credentialed, or long-running.** A
  `greenlight-eval` Cloud Run Job runs the fixture pipeline + the 21-check
  grader inside the SAME image that serves production (environment fidelity is
  the point), writes the scorecard to GCS/Firestore, and trips the existing
  run-failure email alert on red. Cloud Scheduler runs it nightly — a standing
  run-to-run variance series, the consistency number the reviews keep asking
  for, accumulated automatically. Case regeneration and the comparables
  benchmark become jobs with args on the same pattern.
- **Why not all-GitHub:** the evals need PARALLEL_API_KEY, CLICKHOUSE_PASSWORD,
  ENCRYPTION_KEY, and Vertex auth — a second credential store to rotate, and a
  runner env that drifts from prod. Also contest optics: evals on Cloud Run is
  a sentence that helps this entry; evals on GitHub runners is not.
- **Why not all-GCP:** Cloud Build's PR feedback is slower and weaker than
  Actions annotations; the public repo's checks/badges belong on GitHub.

Sequencing: post-deadline infrastructure EXCEPT the eval job (~1 hour: the
image and scripts exist; needs an entrypoint + Scheduler cron), which also
demos well. WIF + the deploy workflow wait until after Devpost submission.

## 2026-08-28 — Desks stay on Flash; no Pro migration

Considered moving desk inference to gemini-2.5-pro for reliability (the
instruction-dropping failures: closed-vocabulary override, territory prose
loop, roll-call skipping). Decided against, per the user: Flash is good.
The remedy for instruction-dropping is MECHANICAL enforcement in the tools,
not a bigger model reading longer prose — the Wave-1 batch binds Flash with
code (vocabulary in the tool contract, twelve-disposition territory
checklist, entity-named done() refusals, merge-path caps). Also noted:
2.5-pro is a generation older than 3.7-flash, so "Pro is smarter" is not a
given, 3.x Pro is preview-only (ruled out for a paid product), and wholesale
Pro is ~2-3x model cost per run. The reviewer's narrower idea — routing only
non-neutral-portrayal entities to a Pro sub-pass — stays on the backlog as
the middle path if Flash's judgment on defamation calibration proves weak
with the new guards in place.

## 2026-08-28 — Data-assets roadmap: convert assertions into lookups

The founding doctrine ("never let the model assert what you could retrieve")
extended to reference data. Each asset converts a class of LLM assertion into
a deterministic lookup, on the pattern proven by the CARA rationale harvest
(official source, one-time polite crawl or bulk download, provenance per row,
then a tool the desks call).

**Building now (pre-deadline):**
- **USPTO trademark verification** — official APIs/bulk data. file_flag
  requires a verify_trademark() lookup on record before any registration
  number is cited; live/dead status, owner, and class come from the register,
  not the model. Closes review item #8 (validate identifiers) mechanically.
- **CSATF bulletin index** — one-time harvest of the official safety-bulletin
  list into a checked-in data file + csatf_bulletin() tool. Bulletin numbers
  become un-fumble-able; the never-from-memory rule gets a mechanism.

**Staged (post-deadline, in leverage order):**
- CourtListener/RECAP API — primary-source case law for defamation/ROP
  citations (source-authority floor met at the root).
- Copyright renewal records (Stanford DB +) — actual renewal verification for
  the 1923-1963 PD window.
- MusicBrainz dumps — labels/works/soundtrack graph; unlocks the clearability
  index (severity = cost x P(refusal), both measured) that the roadmap parks
  as Bradley-Terry "if obtainable" — it is obtainable.
- BBFC + Australian classification DBs — official territory ratings text,
  CARA-harvest treatment per territory.
- SEC EDGAR + Wikidata owned-by graph — corporate rights-holder chains.

**Not doing:** IMDb (scraping prohibited, paid data omits what we need);
ASCAP/BMI/Songview stay runtime-query-only per their terms.

## 2026-08-28 — Competitive position (Filmustage) and certification roadmap

**Position:** Filmustage is a pre-production OPERATIONS platform (breakdown ->
schedule -> budget -> call sheets; customer = 1st AD / line producer). Their
page never mentions clearance, E&O, defamation, licensing, rating prediction,
or territory — the desk we serve (production counsel, E&O broker) is absent
from their product. We do not compete on their field; we prove ourselves on
ours: (1) verification as the product (blinded verifier, citation invariant,
rejections shown), (2) published accuracy numbers (Wave 2's alpha / recall /
conformal coverage — nobody in either category publishes any), (3) regulator
data assets (CARA rationales, BBFC cuts records, USPTO live verification,
CSATF index), (4) the forwardable binder as the artifact that reaches counsel.
Long-term they are a natural channel partner: their breakdown identifies the
props/brands/locations; we clear them.

**Certifications:** no audits during deadline week. Sequence: /security page
now (shipped — controls documented control-by-control, badges honestly
absent: "we will not display a badge we have not earned"); TPN Blue Shield
membership + self-assessment after Devpost (MPA-native trust, weeks not
months); SOC 2 Type 1 via a compliance platform when the first enterprise
conversation gets serious, Type 2 following. Operator action items: 2FA on
all provider accounts; one-page incident-response note.

## 2026-08-28 — THE PIVOT: business, not hackathon

The Devpost/Agentic Cinema submission is abandoned; ScriptRisk is a business.
Actions taken same-day: repo made PRIVATE (history was public since day one —
privacy applies going forward, not retroactively; the real moats — harvested
regulator datasets, eval calibration history, measured numbers — never lived
in the repo); CLAUDE.md rewritten from contest rules to operating principles.

What dissolves: the Gemini-only runtime rule, the Parallel-required rule, the
public-repo/MIT requirement, the 3-minute-video constraints, the Sept 9 wall.

What deliberately survives: the current stack (measured and working — changes
go through gates, not through freedom), the forbidden-deps scan as stack
discipline, the demo-fixture-is-original-work rule, safe_deploy as the only
deploy path, and deadline discipline replaced by weekly measured milestones.

What the freedom unlocks, first in line: CROSS-MODEL verification and k-pass
diversity (a non-Gemini desk/verifier pass) to attack correlated blindness —
the measured cause of the useless recall bound. Structurally forbidden under
contest rules; now the most interesting available architecture change.

Business path (from the reviews): Wave 2's three published numbers, then the
revision-aware rescan as the subscription product, then TPN Blue. The
'cannot honestly charge before this point' line is the roadmap's spine.

## 2026-08-28 — Pivot SUSPENDED: contest rules back in force pending next week's decision

Hours after THE PIVOT entry above, the decision was walked back to "keep the
rules for now; final hackathon call next week." CLAUDE.md's contest
constitution is restored (with a status note). The repo REMAINS PRIVATE as
the one standing deviation — the public-repo rule bites only at Stage One
screening, visibility is instantly reversible, and commit history (what
"new projects only" verification reads) is unaffected by visibility windows.
ACTION IF PROCEEDING WITH HACKATHON: flip the repo public before submission.
All rules-contingent work (cross-model verification etc.) is parked in the
contingent roadmap below; nothing rule-breaking lands before the decision.

## 2026-08-28 — Contingent tech roadmap (activates ONLY if contest rules drop)

Ranked by leverage against MEASURED problems, not novelty:

**Tier 1 — attacks measured weaknesses (days of work):**
1. Heterogeneous model families: a verifier from a different family than the
   desks (an auditor from a different school); k=3 passes across three
   families so capture-recapture's independence assumption becomes ~true and
   the recall bound becomes publishable; the adversarial pass on a family
   that does not share the defenders' priors. One root cause — correlated
   blindness — three fixes, mostly routing code on the existing harness.
2. Real zero-shot NER (GLiNER-class, local) as the A4 pre-pass engine —
   deterministic across passes, better proper-noun recall than regex.
3. Classical ML openly at runtime: sklearn/GBM for rating stage-2, the
   clearability index, Monte-Carlo cost distributions (P50/P90/P(hard fail)).

**Tier 2 — cost/speed structure (weeks):**
4. NLI entailment pre-filter before the LLM verifier (cheap mechanical
   rejection of the worst citations).
5. Distillation from our own exhaust: LoRA-tuned small models as first-pass
   verifier/triage from accumulated verdicts; big models only on
   disagreement. COGS falls as volume grows.
6. Batch inference APIs (~50% token cost) for regen, k-runs, nightly evals.

**Tier 3 — product moats (months):**
7. Enterprise privacy tier: open-weight models in the customer's VPC ("your
   script never leaves your tenancy") — converts COGS into deployment fees;
   pairs with TPN.
8. Purpose-trained comparables embedding (contrastive, form features baked in).
9. Debate-style verification (proposer/refuter from different families) for
   BLOCKER/HIGH only.
10. Draft-vs-release delta mining for ground truth + marketing.

**Deliberately unchanged in every scenario:** Gemini desks (measured, gated,
working), Parallel (earning its keep), the gate/deploy discipline. The
freedom's value is diversity where correlation is the enemy and
specialization where one size fits badly — not vendor churn.

## 2026-08-28 — Track B delivers: the CARA boundary measured, the guarantee holds

Full harvest: 4,755 official rationales (75% of the corpus), 74
multi-certificate titles (re-rating cohort), 860 parse-failure films queued
for vocabulary review, 1 fetch error. The decision boundary in plain sight —
and it MEASURES the folklore: 'pervasive language' -> R 99% (n=187) while
'strong language' -> PG-13 89% (n=383): the modifier, not the category, is
the R-line. strong bloody violence -> R 100% (n=122); graphic nudity -> R
99% (n=225); mild anything -> PG 100%; 'intense' is PG-13's signature word.

Model (pure-Python multinomial logistic, coefficients-as-data, deterministic
title-hash splits, post-1990 scope): top-1 82.1%, multiclass Brier 0.280,
**Mondrian conformal coverage 90.1% vs 90% target** on 927 held-out films,
75% singleton prediction sets. The methodology-page sentence now exists with
real numbers behind it. Wobbly middle-confidence bins (0.7-0.9, small n) are
the stated caveat; next accuracy lever is stage-1 descriptor extraction
quality, per the standing 'none of this fixes extraction' caution.

## 2026-08-28 — BBFC harvest complete: 436 regulator-documented band moves

5,275/6,302 matched (84%), 436 cuts records (64 company-elected; 57 state
the uncut-category delta). Dominant move: 15 -> 12A (n=14) — the UK's
commercial sweet spot and the exact Social Network pattern. Combined with
CARA's 4,755 rationales, the corpus now carries two regulators' official
decisions per film. Overnight harvest total: 12,604 films, 5 errors. The
cut simulator's validation set and the cross-jurisdiction feature space
both exist as of tonight.

## 2026-08-28 — Feature-scale k=3 PARKED (owner call)

The feature-length k=3 measurement (three full passes on The Social Network,
~$45 — the publishable consistency alpha plus A3's capture-recapture
validation against the hand-labeled list) is deliberately deferred, to be
brought back later. Consequences, stated for the record: Wave 2's exit
criterion stays open — the consistency number remains fixture-scale
(alpha 0.932, 12 rated rows — too thin to publish) and recall remains
unbounded pending A3's validation. The k=3 harness, the matcher, and the
hand-label sources are ready; resuming is one command
(scripts/consistency_k3.py <script> 3). The methodology page will state
these two numbers as pending rather than claiming them.

## 2026-08-28 — POLICY: quality is never scaled down. Every customer, full treatment.

Owner decision, stated as principle: we never compromise on quality, whatever
it takes. Consequences, binding:
- The proposed "scale contract floors with script size" optimization is DEAD.
  A one-page script gets the same twelve territory dispositions, the same
  per-entity roll-call, the same pre-pass, the same blinded verification and
  re-sourcing as a feature. The rigor floor is the product.
- Latency is accepted as the cost: ~10-15 min for short scripts (the fixed
  floor dominating), ~20-35 min projected for features (floor amortizes;
  iteration ceilings unchanged, so no path to 'hours'). We set expectations
  honestly in the UI rather than trimming the work.
- Performance work is welcome ONLY where it removes waste, never rigor:
  stall-kills, prose-loop nudges, caching, concurrency — yes. Fewer
  dispositions — no.

## 2026-08-28 — Wave 2 close-out (k=3 stays parked)

Owner reconfirmed feature-scale k=3 stays parked; the rest of Wave 2's open items closed:

- **Reliability diagram published** on the methodology page — the unflattering version on
  purpose: mid-confidence bins run overconfident (a 0.74 answer is right ~54% of the time),
  which is the argument for shipping conformal sets instead of raw probabilities. Bins are
  persisted in `rating_model.json` (`test_metrics.reliability`) so the chart regenerates from
  the artifact.
- **CARA parse failures 242 → 75** via two descriptor-vocabulary passes (new categories:
  sexual_violence; new variants: mayhem, battle sequences, racial slurs, bare "images"/
  "dialogue"/"humor" conventions, marijuana/cannabis, etc.). films_parsed 4,535 → 4,544.
  Residual 75 are genuine one-offs ("intense depiction of very bad weather").
- **Model refit on the richer table**: top-1 84.4% → 83.9%, Brier 0.245 → 0.239, conformal
  coverage 92.0% holds, holdout n=937. Comps benchmark 9/9. Runtime asset now built by
  `scripts/build_boundary_asset.py` (previously assembled ad hoc) — 69 marginals at n>=20.
- **Drift claim corrected**: the old "+1.1pt, stable across decades" was measured on the
  narrow vocabulary AND the baseline sampler was biased (truncated a non-random film list;
  fixed to hash-ordered sampling). Honest current number: pre-2010-trained loses **5.0pt**
  on post-2015 — standards/vocabulary moved. Methodology page updated; recency weighting
  noted as the follow-up this number argues for.
- **Re-source recovery rate** stays per-report until production volume makes an aggregate a
  statistic; the page now says exactly that.

## 2026-08-28 — Reviewer round 2: collapse enforcement, set-primary display, honest boundaries

- **Desk-collapse signature enforced end to end.** `_incomplete_desks` existed since Wave 1
  (built for the territory 5→0 failure) but was disclosure-only: nothing graded it and
  nothing rendered it. Now: eval check #22 (a run with any collapsed desk cannot gate),
  a report banner ("silence is unexamined, not clear"), and a binder/PDF INCOMPLETE
  section. The 21-check eval is now the 22-check eval.
- **Conformal set is the primary rating display.** The set was already the filing gate but
  was never persisted; `rating_prediction.conformal_set` added to the report schema
  (additive) and the report card now leads with the set ("The guarantee, 90% coverage"),
  point prediction second ("The desk's call"). Reviewer's argument accepted: Brier 0.239
  with overconfident mid-bins is exactly the profile where the set is the honest claim.
- **Methodology page: population boundary stated** (post-1990 US wide-release features —
  the guarantee does not travel to documentaries/shorts) and **descriptor extraction
  promoted to its own labeled section**: pending, "the load-bearing wall" — calibrated
  model ≠ accurate reports until extraction is validated against hand-labeled scripts (A3).
- A3 validation and a one-off feature-scale k=3 measurement remain owner decisions
  (parked); the reviewer recommends A3 as the cheapest close.

## 2026-08-28 — Feature-scale k=3 + A3: measured, and the results reorder the roadmap

Owner un-parked both. Three full passes on scale_gate.fountain (18.5 / ~11 / 8.1 min;
records runs/k3_pass{1,2,3}_20260828_*.json, binders rendered beside them).

**Judgment: consistent.** Flag-vs-cleared on co-examined items: 42/46 unanimous across
three passes; 36/37 across the two complete passes. Alpha is prevalence-limited at this
uniformity (0.525 / 0.0) — raw agreement is the publishable statistic, stated as such.

**Coverage: NOT consistent — this is the finding.** Union 19 findings (after adding a
containment rule to the matcher: "Nighthawks" ⊆ "Edward Hopper's Nighthawks" — two false
singletons removed, near-miss log now empty). Only 1/19 found by all three passes; between
the two complete passes, 5/16 overlap. Chapman N-hat ≈ 20-28 → per-pass recall bound
≈ 0.4-0.69. Seed-key grades: 13/21, 17/21, 19/21 — pass 1 missed the entire music complex
plus Nighthawks, the tattoo, and Coors; pass 3 missed only the controlled-venue remedy.

**The collapse class recurred:** pass 2 ran with safety_underwriter AND territory_censor
producing zero dispositions — at feature scale, 1 pass in 3. Check #22 (shipped hours
earlier) makes this a failed gate/visible INCOMPLETE rather than silence; eval_scale.py
now carries the same check. The "clearance produced 4 batches" scale check was found to
actually grade a >=25 kept-flags floor (passes kept 8-13); relabeled honestly, left red
pending the coverage work.

**Consequence:** the roadmap's next engineering target is coverage convergence (why a
pass skips seeded entities; why desks still collapse), not further decision-layer work.
Methodology page updated to say all of this plainly — "measured, and the news is mixed."

## 2026-08-28 — k=3 forensics: triage exonerated, the loss is worklist assignment

Reviewer challenged pass 3's ~60-brand cleared list as possible hallucination. Verified
against the fixture: every brand is ON THE PAGE (scale_gate is a deliberate brand-density
stress test — templated grange-hall scenes each swapping two brands). Pass 3 was the
faithful observer; passes 1-2 under-covered.

Forensics: all three passes extracted ~110 entities INCLUDING all sampled brands — triage
extraction is consistent. The variance is in the WORKLISTS triage writes: dispositioned
entities were 39/110, 48/110, 113/111. Fixes shipped (gated):
- **Worklist floor** (pre-pass): any extracted entity on no desk worklist is
  deterministically appended to clearance. Coverage no longer depends on model diligence.
- **Under-coverage joins desks_incomplete**: a desk dispositioning <50% of its assigned
  items (worklist >=8) is INCOMPLETE — the quieter second collapse class from pass 1.
  Same eval check #22 enforces it. Per-desk assigned/dispositioned instrumented on record.
- **Gwet's AC1** (reviewer suggestion): judgment agreement AC1 = 0.93 (k=3) / 0.97
  (complete passes) where alpha degenerated (0.525 / 0.0, cleared-prevalence ~95%).
  Published as raw + AC1 + prevalence.
- **Cost-span guard**: file_flag rejects ranges spanning >50x (pass 2's F103
  "$500-100,000" merged a license fee with its indie alternative).
- **Background hosts** += grokipedia, whoppah, go-legal.ai, cinemacafe, uscspotlight,
  jakedavidowitz (pass 3 source regression).
- **file_rating_prediction rejection now names the failing leg** (was: always "contradicts
  weighted majority", even when the trigger was near-conflict or the conformal set).
Open (owner decisions): k=3 union as a paid-tier recall feature (reviewer recommends;
~3x cost, best available recall gain today); artwork rights-holder verification tool
(Nighthawks passes disagreed: ARS/2037 vs AIC-Bridgeman/2038 — 2037 is correct);
score shown as range/suppressed until coverage stabilizes.

## 2026-08-28 — OWNER: single-run completeness IS the product; k=3 union optional at most

"i want it to reflect everything in 1 itself, 3 should be optional." The recall fix is
single-pass, not ensembling. Shipped accordingly (one gated batch with the worklist floor):

- **Per-entity accounting end to end**: record["unexamined"] = extracted entities with no
  disposition anywhere (flag kept OR rejected, clearance, or surface-matched open
  question). Rendered loudly: report banner with the named items, binder NOT-EXAMINED
  rows replacing false "No known issue" on affected scenes, PDF section, disclaimer
  updated. Absence can no longer render as cleanliness — a thin report is now visibly
  thin.
- **Eval check #23**: unexamined must be empty (both fixture evals). The gate is now 23
  checks.
- **done() refusal cap 2 → 4**: worklist-floored lists are longer and clearing is cheap;
  the LoopAgent iteration cap remains the hard stop.

Chain of defense now: deterministic extraction floor (pre-pass) → deterministic
assignment floor (every entity on a worklist) → done() refusals by name → under-coverage
= INCOMPLETE desk → anything still missed renders as NOT EXAMINED, never as clean.

## 2026-08-28 — OWNER: completeness is enforced by a loop, not disclosed after the fact

"there should be a loop in the agent that makes sure everyone is accounted and only then
moves to verify stage." Shipped as the **CompletenessGate**, a new pipeline stage between
the desk panel and verification: LoopAgent(≤3 rounds) of [deterministic check, sweep desk].
The check recomputes the unexamined set (toolbelt.unexamined_entities, single source of
truth) and only escalates when it is EMPTY; otherwise it hands exactly those items to a
clearance-family sweep agent (clearance_counsel__sweep, shared toolbelt, small dedicated
budget) and loops. done() changes: refusal cap REMOVED (a desk can no longer outlast the
refusals — the iteration ceiling is the only stop), and the sweeper's done() does not
escalate (ADK escalation would end the gate's loop after one round — the check alone
controls the loop). NOT-EXAMINED rendering and eval #23 remain as defense in depth for
whatever survives all rounds; they are the backstop now, not the mechanism.

## 2026-08-28 — Validation exposed wrong-desk coverage; accounting is now desk-scoped

First single-pass validation on the new architecture (run_20260828_173655): completeness
invariants HELD (0 unexamined, no collapse, 17 min) but the seed grade was 14/23 — the
music complex, Nighthawks, tattoo, and Coors were wrongly "covered". Forensics via the new
desk_coverage instrumentation: safety (assigned 4) blanket-cleared 123 entities as "no
physical hazard", and entity-level accounting accepted ANY desk's disposition — so
clearance's copyright questions were never asked (clearance stopped at 89/115 with 43
research budget UNUSED: its batch iteration ceiling bound, not budget). Fixes (gated):
- unexamined_entities is now DESK-SCOPED: each desk's worklist items must be dispositioned
  by that desk; the completeness gate loops until the right desk answers its own question.
- COVERAGE_RULE: your worklist is the assignment; the entity table is context — clearing
  another desk's items covers nothing.
- Sweep items carry which desk left them + rights-item treatment ("never clear a FEATURED
  item on vibes").
- Clearance batch max_iterations 10 → 14 (the binding constraint at 29-item slices).

## 2026-08-28 — Third stall in one day: run-level inactivity watchdog; aborted runs exit red

The desk-scoped gate run hung for 2h20m mid-panel and aborted with a bare TimeoutError —
third multi-hour stall today, all below the per-client timeout bounds (parked streaming
reads the 480s HttpOptions never fire on). Two mechanical fixes:
- **pipeline.run inactivity watchdog**: if no agent event arrives for 900s (beyond every
  client's worst retry envelope), the run aborts deliberately with a StallTimeout error
  and salvages. Bounded, disclosed failure instead of a silent multi-hour hang — applies
  to prod worker runs too.
- **cli exits 2 on any aborted/salvaged run** (was: 0 whenever flags existed — RUN_EXIT
  lied to the gate; the "grade without a green exit" law now holds inside the run).
The 18/23 salvage grade is struck as evidence: aborted run, not a measurement. The
desk-scoped batch still awaits its first clean gate.

## 2026-08-29 — External review (28 Aug) implemented in full: evidence plumbing + comparison math

Three verification agents confirmed every review finding (several worse than claimed);
all three phases implemented overnight, code-only per owner ("fix everything, don't run
anything"). Commits 8b79ae1, d98ab36, bc98a76.

**Phase A (P0):** local tools (rating_boundary/csatf_bulletin/bbfc_cut_precedent) register
their output as citable provenance — their instructed citations no longer reject or get
silently substituted. Work-item identity end to end: deterministic CC/RB/SU/TC-Wnnn ids in
prepass, 12 synthetic TC-AX-* territory axis items (the "MECHANICAL" checklist is now
mechanical), wi_done side channel on all three disposition tools, done()/unexamined/
completeness-sweep consume ids, desk_coverage instrumented, eval check #24 (territory
work_items_done >= 12). Scene-level work was previously PERMANENTLY unsatisfiable in
done() — with the uncapped refusals this burned whole desks' iterations. Ratings lineage:
Wikipedia content profiles are no longer called "official CARA rationales" anywhere
agent-facing (query_precedent docstring, ratings prompt, report schema description —
announced); marketing copy split. Conformal: pooled Mondrian groups {G,PG}/{PG-13}/
{R,NC-17} with a hybrid per-class floor (naive pooling degenerated: the group hit 90% by
letting G fail always) — groups all >=91.4% held-out, per-class table + calibration counts
published on methodology; every "90% guarantee" claim restated per pooled group.
Descriptors: parsed with the embedded harvest vocabulary, matched/unmatched returned, and
a set built from partial input is ADVISORY — it no longer hard-rejects a desk's correct
prediction (the review's sharpest find: the evidence contract inverting).

**Phase B (P1):** ONE voting rule — What-If now uses the shared inverse-distance weighted
majority and excludes the film's own title (it could previously vote in its own What-If);
report.js's third client-side tally removed. Score labeled an ordinal risk index (the old
caveat claimed few-point re-run stability that k=3 disproved); confidence labeled "desk
self-assessment (uncalibrated)"; cost totals labeled independent-remedy sums; methodology
gains a "labeled for what they are" card. Adjudicator docs now match runtime everywhere
(single Pro pass; AgentTool re-entry explicitly deferred roadmap); RatingsBoard cap 4->6
doc drift fixed.

**Phase C (P2):** re-sourced citations pass the same background-host tier gate a filed
flag faces, join the run's Parallel session, and are counted (resource_searches);
fail-open (verifier-unavailable) flags are EXCLUDED from score/cost/schedule aggregation
(rendered with their chip, no longer scored as verified); salvage-path verdicts carry
failure_mode (were permanently mislabeled "none"); research cache key now includes the
queries; budget decrement is atomic (the race UNDERCOUNTED spend); concurrent identical
cache misses dedupe in flight.

**MORNING QUEUE (nothing run tonight, per owner):** 1) make comps-gate (ClickHouse) —
9/9 required after the asset rebuild; 2) the caffeinated 24-check fixture gate -> deploy
on pass; 3) one feature-length validation on scale_gate graded by eval_scale (expect: no
refusal-burn, territory work_items_done >= 12, grade >= 19/21, zero unexamined).

## 2026-08-29 — Morning queue complete: review batch gated 24/24, deployed, validated 20/23

comps 9/9 → fixture gate **24/24** (first-try pass incl. new check #24: all 12 territory
axis sweeps by work-item id) → deployed (df5a99bc) → feature validation on scale_gate:
**20/23, the best feature-length grade recorded** (prior spread 13–19), in 12.4 min
(vs 17–18 broken): zero unexamined, zero collapse, zero done() refusal-burn; territory
17/17 work items, ratings 4/4, safety 5/5, clearance 103/114 by id with the completeness
gate catching 29 leftovers (Nighthawks first among them) and the sweep producing the
actual artwork FLAG, not a cheap clearance. Every k=3 pass-1 miss (music sync/master/
indie path, Nighthawks, tattoo, Coors) is green.

Residual misses: (1) location-realism controlled-venue remedy — the one persistent
judgment gap (has failed every run ever); (2) verification-rate>0% — small-n flakiness:
0 rejections among 11 well-gated flags can be legitimate; left as-is for now;
(3) kept-findings floor recalibrated 25→10 (dated from the FYI-noise era; 11 kept with
all 14 content seeds passing is the direct thinness measure — logged, not hidden).
Also: OTel context-detach noise (~1,000 swallowed tracebacks/run, appeared with the
threading additions) silenced via logger level; zero functional effect either way.

## 2026-08-29 — Minor residuals fixed

- **Location realism**: forensics showed the doctrine existed but the desk cleared the
  fictional venue NAME and never filed the location flag — "A FICTIONAL NAME CLEARS THE
  NAME, NOT THE SHOOT" added to clearance doctrine (controlled-venue remedy required even
  for invented venues when the scene needs the venue class; the Grand Meridian failure
  named in the prompt).
- **Verification-rate checks** (both evals): "rejections > 0" replaced with "verdicts
  recorded for every kept flag AND no fail-open markers AND rate <= cap" — zero rejections
  is legitimate now that filing gates block weak flags at the desk; a sleeping verifier
  still fails via missing verdicts/fail-open.
- Dead `_DONE_COVERAGE` constant removed (unused since the refusal-cap removal).
- Validation record re-grades 22/23 under recalibrated checks; the location seed is the
  one remaining red and requires a fresh run to test the doctrine.

## 2026-08-29 — Post-registration citation laziness: local-tool strings need substantive pairing

Gate roll 2 (21/24) exposed a regression the provenance registration unlocked: local-tool
strings became citable, so desks leaned on them as easy excerpts — bulletin TITLE lines as
sole safety support (3 rejections in one run), a filmratings glossary line that softened
the desk's own R-line premise (rating_language rejected as self-contradicting), doctrine-
adjacent excerpts under master-use flags. The verifier was RIGHT each time. Fixes (prompt/
tool-text): ratings frames the multi-F-word line as measured boundary risk (marginals +
comps + set, never a bright-line the glossary contradicts); safety pairs the bulletin
index (number verification) with researched substantive text; csatf_bulletin says so at
the point of use; master-use flags cite licensing practice. Roll 1's fix (disparagement
cites trade-libel authority, never Rogers) PASSED its seed on roll 2.

## 2026-08-29 — Fix cycle closed: 24/24 on roll 4, all four doctrine fixes deployed

Rolls: 23/24 (Coors: wrong doctrine cited) → 21/24 (title-line citations, the
registration side effect) → 23/24 (drug-use: generic-threshold citation) → **24/24**
(deployed, revision 00166). Every roll's fix held on subsequent rolls; roll 4's verdicts
show all three ratings flags surviving verification under quote-the-marginal. The cycle's
lesson, now doctrine in four places: local-tool output VERIFIES (numbers, marginals,
records) — substantive support comes from researched authority matched to the claim class
(trade-libel for disparagement, licensing practice for master-use, bulletin text for
safety, measured marginals for rating drivers). Owner directive standing: no new
features (taxonomy sweeps, registry tools, cost priors, real-script A3 all logged as the
E&O-accuracy roadmap, not started).

## 2026-08-29 — PLANNED (owner-approved, not yet built): run identity + access control

Queued for implementation after the current stabilization pause:
- **Backend-run identity**: dedicated least-privilege `greenlight-ci` service account for
  all gate/test/validation runs (impersonation via ADC), so backend spend is attributed,
  separable from prod in billing/audit logs, and revocable — today those runs use ambient
  .env credentials under no product identity.
- **Gate-run tagging**: fixture/gate/validation runs write `source: "gate"` into the run
  record so the product's own accounting (make costs, metrics) reports backend spend as a
  line item instead of not at all.
- **Access control trio for launch**: login required to start a run (auth exists — flip to
  mandatory), invite codes/allowlist for the pilot phase, and an admin kill switch that
  pauses new run starts instantly. Together these close the abuse scenario (IP-rotation
  past the 8/hr limit + camping the 5-slot concurrency cap ≈ tens of $/day + denial of
  slots) without touching legitimate users.

## 2026-08-29 — Hangover review (real-script QA) fixes

Reviewer verified the run line-by-line against the script; big prior fixes held
(per-location findings, count reconciliation, cleared/OQ split, scene caps, 15/15 claim
spot-checks accurate; rating ground-truth R). Fixed this batch:
- **Pages were fabricated** (~0.81 scale, 17pp drift by act three): pdf_to_text now
  preserves page breaks as form feeds and the parser anchors scenes to REAL pages
  (55-line model only for feed-less Fountain).
- **Verifier false denial** (F116 Sbarro: asserted absence about an unshown scene,
  killed a true finding): context now includes every scene the FINDING references,
  chunks are labeled === S### ===, and asserting absence about unshown scenes is
  forbidden (at most premise_unsupported).
- **script_misstatement is recoverable**: one correct-and-refile round rewrites the
  finding to what the script supports (UNSALVAGEABLE stands as rejected) — a wrong
  character name no longer deletes a whole territory analysis.
- **Cleared referential integrity**: reasonings citing later-rejected flag ids are
  annotated "(later rejected in verification — see Rejected)".
- **Mid-word truncation at source**: record_clearance clips at word boundaries.
- **[partially supported] defined** in the binder disclaimer.
- **Pre-pass junk**: leading discourse words stripped (Then Vick→Vick), weekday/marker
  junk dropped, and signage-colon rescue (the caps filter had eaten CHAPS entirely).
- **file_flag doctrine**: scene_ids = only scenes where the element appears.
DEFERRED (logged): mini-slug sub-anchoring (S012 mis-head — parser-stability risk,
scene ids would shift under revision diffing); deeper merge-range membership pruning;
re-source citation-recovery rework (1/13 lifetime).

## 2026-08-29 — Hangover run-3 review: the score must never reward desk failure

Reviewer compared run 3 vs run 2 vs the script. Root finding: score rose 33→45 BECAUSE
coverage fell (territory desk produced zero own dispositions; its 18 items were absorbed
by the clearance-family completeness sweeper, whose shallow generalist conclusions
rendered as "[Clearance counsel]" and reversed the real desk's run-2 analysis). Fixes
(gated):
- **Score withheld** (null, schema announced) whenever any desk has zero own
  dispositions — rendered "Score withheld — analysis incomplete" in report + PDF.
- **Sweep attribution**: sweeper clearances get their own "completeness_sweep" bucket
  (never blended into clearance counsel); the incomplete-desk banner says swept items are
  provisional/reduced-depth.
- **Pages exact**: front-matter form feeds subtracted — scene pages now match the
  script's PRINTED numbers (the +1 fencepost).
- **PARTIAL no longer caps severity** (blank-fire stunt had sorted below a location fee);
  it is a citation-confidence marker only; test updated to the new contract.
- **Deterministic language census** (prepass regex; profanity+slur inventory with scene
  ids) injected as enforceable RB-CENSUS-LANGUAGE / TC-CENSUS-SLURS work items — the
  dropped-F-words/slur class can no longer vary by model attention.
- **Scene refs never silently truncate** ("+2 more" had hidden S037 entirely).
- **Re-source queries are category-matched** to the authority class the claim needs
  (six of seven rejections shared right-claim-wrong-authority; the generic query re-found
  the wrong class).
- paramount internal hostname → background tier.
Honest answer to "are we not running comprehensive checks?": coverage is enforced at the
work-item level, but which FACTS a desk surfaces still varies with model attention; the
fix direction is exactly the census pattern — deterministic inventories for everything
countable. DEFERRED still: desk-retry for a collapsed desk (vs sweep), location
availability/currency caveats (Bel Air Bay Club post-fire), mini-slug sub-anchoring.

## 2026-08-29 — Territory collapse root-caused and triple-fixed

Journal forensics on run 3 (643965843e3a): territory ran its axis sweeps correctly
(find_in_script, free — budget untouched at 20/20), then spent every remaining iteration
on read_scene batches and hit the LoopAgent cap having filed NOTHING — no done(), no
error, a silent cap exit. Root cause: read-forever-file-never work ordering under a hard
8-turn cap; run-to-run variance is just whether the model happens to interleave filing.
Three fixes (gated):
1. **Filing pressure**: territory prompt + COVERAGE_RULE — disposition in the same turn
   evidence arrives; a turn with zero new dispositions after the first is stalling.
2. **Territory max_iterations 8 → 12** (feature scripts surface 20+ scenes per sweep).
3. **Desk-retry in the completeness gate**: collapsed_desks() (worklist + zero OWN
   dispositions; sweeper excluded, __retry counts) → the gate re-runs THAT desk on its
   own worklist with a filing-first preamble (name {desk}__retry, budget 12, done()
   reads retry_worklist, escalate suppressed inside the gate loop) BEFORE the generalist
   sweep may touch its items; sweep only takes what retry leaves. Healthy runs cost
   nothing (check escalates before the retry agents run).
