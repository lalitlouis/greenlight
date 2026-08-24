# Status

Last updated: **2026-08-24** (evening). Deadline **2026-09-09, 2:00 PM PT** — treat Sept 8 as real.

## Architecture changed on 2026-08-23 — read this first

The original design was a **pipeline**: extract entities, run one search each, run four prompts,
dedupe. Lalit challenged it — *"where is the agent aspect, how is this different from just calling
Parallel?"* — and he was right. It has been rewritten as a genuine agent system. **Do not regress
to the pipeline.**

Each desk is now a `LoopAgent` over an `LlmAgent` with seven tools, deciding what to investigate
and when to stop. Plus a blinded verification fan-out that can reject flags, and an adjudicator
loop that can re-enter a desk via `AgentTool` when remedies interact. Full reasoning in
`docs/TECH_SPEC.md`.

Governing principle, applied twice: **never let the model assert what you could retrieve.**
Parallel for the outside world, ClickHouse for the comparison set. Gemini does judgement only.

## Phase 0 — COMPLETE

All four preflight checks pass. Verified by live calls, not credential checks:

```
PASS  Google Cloud / Vertex AI (Gemini)   [contest gate]   gemini-2.5-flash replied
PASS  Parallel Search API                 [contest gate]   10 sourced results
PASS  ClickHouse Cloud                                     server 26.2.1.558
PASS  Contest compliance                  [contest gate]   LICENSE + no non-Google AI SDKs
```

Reproduce with `python -m greenlight.checks all`.

### Provisioned

| Resource | Value |
|---|---|
| GitHub | github.com/lalitlouis/greenlight — public, MIT detected |
| GCP project | `greenlight-clearance-2026` (`219740804594`) |
| Billing | `012600-29EBC8-C419FB`; budget alerts at 40/75/90% of $100 |
| Region | `us-central1` (ClickHouse is in the same region) |
| Staging bucket | `gs://greenlight-clearance-2026-staging` |
| ClickHouse | `rinx8oyi4i.us-central1.gcp.clickhouse.cloud:8443` |

Credentials live in `.env` (gitignored, verified untracked). Rotate the Parallel key and
ClickHouse password after the hackathon.

### Built

- Frozen contracts in `schemas/` — `scene`, `entity`, `flag`, `report`
- `scripts/check_forbidden_deps.sh` + PostToolUse hook — blocks non-Google AI SDKs, negative-tested
- `src/greenlight/checks.py` — preflight, separates contest gates from soft dependencies
- `.claude/skills/parallel-search/` — written from an introspected signature and a live response
- `fixtures/cassettes/clearance_brand_disparagement.json` — real captured Parallel response
- Docs: PRD, TECH_SPEC (agentic), STACK, COMPLIANCE, MARKET, DEMO, SETUP
- **Product page live at https://lalitlouis.github.io/greenlight/** — Pages serves `main /docs`,
  redeploys on push. Five UI mockups in HTML/CSS: intake, the four-desk panel streaming tool
  calls, the risk report with a real captured citation, ratings comparables, marked-up script.

### Validated

The core thesis, on day 1. A live Parallel query about a brand depicted negatively returned
dated, sourced legal excerpts stating the governing doctrine (product disparagement) and the
standard remedy (written permission) — directly supporting the flag we would generate.

Bonus finding: the practitioner triage criteria in those results (*prominently featured*,
*suggests endorsement*, *negative light*, *essential to plot*) independently match the
`prominence` and `depicted_negatively` fields in `entity.schema.json`.

## Phase 1 — COMPLETE (day 2, ahead of schedule)

`make run` works end to end: parse -> Triage -> ClearanceCounsel as a genuine LoopAgent with
live Parallel research -> real cited flags. First full run: 15 entities, 6 flags in 125.7s, and
the desk split "Hallelujah" into sync (Sony/ATV) and master (Columbia/Sony Music) on its own —
the ownership chase is real. It researched the Stephen Foster trap and correctly declined to
flag it. Cached run in `runs/`. New-project Gemini 429s are ridden out by ADK retry_config; a
crashed run salvages partial state.

Original goal, for reference:

1. [x] **Original demo screenplay** in `fixtures/` — must be our own work (contest rule), ~15 pages,
   seeded with one instance of every flag category **plus one verifier trap**: an entity where
   surface search results look supportive but do not actually support the obvious claim. The
   rejected-flag demo moment cannot be scripted, only harvested — the trap raises the odds, and
   the cached run committed to `runs/` must be *selected* for containing a rejection. Open
   question: dense checklist vs. a genuine short film that happens to be dense. Leaning genuine
   short film — the video is the only thing most judges experience.
2. [x] **Fountain parser** -> `Scene[]` with `raw_span` char offsets.
3. [x] **Triage** (Gemini 2.5 Flash, structured output) -> `Entity[]` + per-desk worklists.
4. [x] **ClearanceCounsel as a real LoopAgent** — tools (`read_scene`, `find_in_script`, `research`,
   `file_flag`, `done`), live Parallel calls, terminating on its own. Build one desk as a genuine
   loop rather than four as prompts; the other three are then repetition.

## Phase 2 — panel, verification, adjudication: BUILT (day 2, same day)

The full agent graph runs end to end on live APIs:
triage -> four concurrent desks (ParallelAgent) -> blinded per-flag verification (runtime
fan-out) -> Adjudicator on Pro (structured merge/conflict plan, applied deterministically with
guards) -> deterministic report with multiplicative Greenlight Score.

Calibration was the real work, driven by `make eval` (SEEDS.md as executable assertions):
- Verifier v1 over-rejected: it faulted web excerpts for not containing script facts, and a
  silent scene-text truncation made it reject true findings ("not in the script"). Fixed:
  scenes passed as marked ground truth, premise-focused standard, marked truncation.
- Research cache keyed per entity+question — entity-only keying looped the ownership chase.
- Desks now work worst-first (budget dies from the bottom of the list), never file "no
  clearance needed" opinions (a wrong PD assertion about Nighthawks proved why), and territory
  no longer pads (21 flags -> ~9).
- Flag ids and budgets are per-desk — shared counters raced under the ParallelAgent.

Rejected-flag moments occur naturally (~3-4/run, all genuine kills on inspection). Demo
moments #1, #2, #4 are all observable in cached runs; #3 (comparables) awaits the corpus.

**Demo record selected by eval, not hope:** `runs/run_*_demo.json` scores 18/18 on
`make eval` — every seed found, both traps clean, sync+master as separate flags, the climax
flagged, two genuine verifier rejections on camera, Greenlight Score 13/100. The replay
harness serves it. Selection runs cost ~5 min each; rerun and reselect after any calibration
change.

**Still open in Phase 2:** ClickHouse corpus ingest (blocked on DATA_SOURCES.md sign-off —
analysis written, recommendation: Wikipedia-sourced facts, no CARA scraping); Adjudicator
AgentTool re-entry into desks (deliberately deferred — not one of the four demo moments).

Then Phase 3 (product + deploy), Phase 4 (submission). See the plan in
`docs/PRD.md` and `docs/TECH_SPEC.md`. Phase 3 has started: the web UI (FastAPI + SSE, four
live desk columns, report, marked-up script, replay harness) is being built by a parallel
agent against the stable `pipeline.run(on_event=...)` interface.

## Open items needing a human

- [ ] **Add teammate to the Devpost project** — team members must be listed there
- [ ] **Sign off `docs/DATA_SOURCES.md`** — gates the comparables corpus (demo moment #3)
- [ ] `docs/DATA_SOURCES.md` — provenance check on MPA/CARA rating rationales before ingesting.
      **Do this week, not with Phase 2 ingest** — demo moment #3 (the comparables beat, the
      "most defensible thirty seconds") dies with no replacement time if this check fails late.
- [x] Decide screenplay fixture style — **decided 2026-08-24: genuine short film.** *Slack Tide*,
      ~13 pp, written; seed map in `fixtures/SEEDS.md`

## Known gotchas

- A new GCP project denies `aiplatform.endpoints.predict` **even to the owner** until
  `roles/aiplatform.user` is granted explicitly. Failure sequence is 403 -> grant -> 404 for ~60s
  while IAM propagates -> success. Do not chase model names.
- Parallel returns the same page at different URL casing (`/library/` vs `/Library/`). Dedup
  citations on a normalized URL or reports look padded.

## Honest risk assessment

Scope is four gatekeepers **and** a polished deployed UI — full scope, chosen deliberately. The
agentic redesign raised the ceiling and the difficulty at the same time: loop agents are harder to
debug than pipelines (non-deterministic, intermittent failures, "the agent stopped early" can eat
a day).

**Odds, assuming we fully ship:** ~40% to place, ~12–15% for first. Top-decile on all four
criteria, with Idea and Impact at roughly top 5%. Unconditionally it is nearer 15%, and the whole
gap is execution risk.

Criteria read: strongest are **Quality of the Idea** and **Potential Impact**. Weakest is
**Design (25%, still zero product UI)**. Technological Implementation moved from a liability to a
strength with the redesign — but only once the loops actually run.

Biggest non-execution risk: **taste mismatch.** This is called *Agentic Cinema* and judges may want
creative magic, not legal ops. Fixed entirely in presentation — see `docs/DEMO.md`.

### Deployed — 2026-08-24 (day 9 gate cleared on day 3)

**https://greenlight-219740804594.us-central1.run.app** — Cloud Run, us-central1, scales to
zero, 1Gi/1cpu, max 3 instances. Ships the full multi-page site + the demo record; replay works
with zero credentials, live runs use env-var creds and the compute SA's `aiplatform.user`
grant. Redeploy: `gcloud run deploy greenlight --source . --region us-central1` (env file
regenerated from `.env`; see Dockerfile/.dockerignore — scratch runs and secrets never ship).

### Protect these three

1. **A thin end-to-end run by day 7** — one desk, one loop, real citations, ugly HTML. Teams that
   get a complete skeleton early and thicken it beat teams that integrate on day 15.
2. **Deploy by day 9**, ugly. Hosted URL is a hard gate and deploy always fights you.
3. **Two full days for the video.**

Revise up to ~25% unconditional if a one-desk loop with real citations works by day 5. Revise down
to ~5% if there is no end-to-end run by day 10.

**2026-08-24: the tripwire hit on day 2 — one-desk loop, real citations, self-terminating.
Unconditional revised to ~25% per the rule above.** Remaining gap to the conditional number is
the panel, verification, corpus, UI, and deploy — integration risk, no longer feasibility risk.

### Preference

When Lalit asks about winning chances, he means **assuming the product fully ships** — give the
conditional number, not the execution-risk-adjusted one.
