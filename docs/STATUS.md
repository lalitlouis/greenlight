# Status

Last updated: **2026-08-23**. Deadline **2026-09-09, 2:00 PM PT** — treat Sept 8 as real.

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

## Next — Phase 1 (days 2–4): ugly spine, end to end

Goal: `make run` prints real cited flags from a real screenplay. No UI, no ClickHouse, no fan-out.

1. **Original demo screenplay** in `fixtures/` — must be our own work (contest rule), ~15 pages,
   seeded with one instance of every flag category. Open question: dense checklist vs. a genuine
   short film that happens to be dense. Leaning genuine short film — the video is the only thing
   most judges experience.
2. **Fountain parser** -> `Scene[]` with `raw_span` char offsets.
3. **EntityExtractor** (Gemini 2.5 Flash, structured output) -> `Entity[]`.
4. **ClearanceCounsel as a real LoopAgent** — tools (`read_scene`, `find_in_script`, `research`,
   `file_flag`, `done`), live Parallel calls, terminating on its own. Build one desk as a genuine
   loop rather than four as prompts; the other three are then repetition.

Then Phase 2 (panel + corpus), Phase 3 (product + deploy), Phase 4 (submission). See the plan in
`docs/PRD.md` and `docs/TECH_SPEC.md`.

## Open items needing a human

- [ ] **Add teammate to the Devpost project** — team members must be listed there
- [ ] `docs/DATA_SOURCES.md` — provenance check on MPA/CARA rating rationales before ingesting
- [ ] Decide screenplay fixture style (checklist vs. short film)

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

### Protect these three

1. **A thin end-to-end run by day 7** — one desk, one loop, real citations, ugly HTML. Teams that
   get a complete skeleton early and thicken it beat teams that integrate on day 15.
2. **Deploy by day 9**, ugly. Hosted URL is a hard gate and deploy always fights you.
3. **Two full days for the video.**

Revise up to ~25% unconditional if a one-desk loop with real citations works by day 5. Revise down
to ~5% if there is no end-to-end run by day 10.

### Preference

When Lalit asks about winning chances, he means **assuming the product fully ships** — give the
conditional number, not the execution-risk-adjusted one.
