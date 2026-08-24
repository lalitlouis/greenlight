# Status

Last updated: **2026-08-23**. Deadline **2026-09-09, 2:00 PM PT** — treat Sept 8 as real.

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
- Docs: PRD, TECH_SPEC, STACK, COMPLIANCE, MARKET, SETUP

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
4. **ClearanceCounsel** — one gatekeeper, live Parallel calls -> `Flag[]` with real citations.

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

Scope is four gatekeepers **and** a polished deployed UI — full scope, chosen deliberately over a
cut-down version. The schedule has no slack.

Strongest criteria: Potential Impact and Quality of the Idea. Weakest: **Design (25% of score,
currently zero UI)**. Biggest risk is not finishing, not concept.

Three things to protect: deploy by day 9 (not day 15); the ClickHouse ratings-comparables demo
moment; two full days for the video.
