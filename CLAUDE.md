# GREENLIGHT / ScriptRisk

Multi-agent screenplay clearance and production-risk analysis. Four gatekeeper agents read a
screenplay and emit a marked-up script plus a Production Risk Report where every flag carries a
citation, a remedy, and a cost/schedule estimate. Live at scriptrisk.com.

**This is a business, not a hackathon entry** (pivot 2026-08-28 — the Devpost submission was
abandoned; repo is PRIVATE). The former contest rules are dissolved; what follows replaces them.

---

## OPERATING PRINCIPLES

### 1. Stack is a choice, reviewed on evidence — currently Gemini + Parallel + GCP

Runtime AI is Vertex Gemini (3.7-flash desks/verifiers, 2.5-pro adjudicator) because it is
measured and gated, not because a rule requires it. `scripts/check_forbidden_deps.sh` is kept
as deliberate stack discipline — adding an AI dependency is an architecture decision made in
docs/DECISIONS.md, never a casual import. The Gemini-only constraint's death unlocks one
specific priority: CROSS-MODEL verification and k-pass diversity to attack correlated
blindness (the measured recall ceiling). That change goes through the same gates as any other.

### 2. Nothing ships ungated

Behavior changes (prompts, tool contracts, models) pass the 21-check fixture eval before
deploy. `scripts/safe_deploy.sh` is the only sanctioned deploy path (tests + lint + compliance
+ refuses while a customer analysis runs). Never gate a shell chain on `check | tail` — the
pipe's exit code lies (this has shipped red three times).

### 3. Paid-product error doctrine

Model mistakes are conversation, transient faults are patience (retries + timeouts on EVERY
external client), dependency outages are loud aborts, silence is never success. A desk with a
worklist and no dispositions is an error surface, not a clean bill. Run failures page the
operator by email within minutes.

### 4. The three business numbers

Everything serves: (1) consistency, measured (k=3 agreement); (2) recall, honestly bounded;
(3) calibration, guaranteed (conformal). Plus repeat value — the revision-aware rescan is the
subscription product. The methodology page publishing these numbers IS the product's proof.

### 5. Customer trust is structural

Fernet-before-GCS encryption, per-user storage prefixes, script-free logs, real deletion,
/security page that shows evidence and claims no unearned badges. TPN Blue is the next
certification; SOC 2 at enterprise stage.

### 6. Cadence

The contest deadline is replaced by weekly measured milestones with the same gate discipline.
Commit and push continuously; the decision log (docs/DECISIONS.md) is the memory of why.

---

## Architecture

Agentic, not a pipeline. An earlier design — extract entities, one search each, four prompts,
dedupe — was deliberately killed on 2026-08-23 because it cannot produce a correct clearance
report. **Do not regress to it.** Full reasoning in `docs/TECH_SPEC.md`, which is the
authoritative spec; if this diagram and TECH_SPEC ever disagree, TECH_SPEC wins.

```
GreenlightPipeline                  SequentialAgent
├── ScriptParser                    deterministic Python, not an LLM — Fountain/PDF -> Scene[]
├── Triage                          LlmAgent -> Entity[] + per-desk worklists
├── GatekeeperPanel                 ParallelAgent — the desks run concurrently
│   ├── ClearanceDepartment         ParallelAgent of ≤4 batch LoopAgents
│   │                               (clearance_counsel__bN, ~25-item slices,
│   │                               fresh conversations; caches/provenance shared,
│   │                               all mutable state keys per-agent)
│   ├── RatingsBoard                LoopAgent(max_iterations=4)
│   ├── SafetyUnderwriter           LoopAgent(max_iterations=6)
│   └── TerritoryCensor             LoopAgent(max_iterations=8)
├── VerificationPanel               fan-out — one blinded verifier per filed flag; can REJECT
├── Adjudicator                     LoopAgent(max_iterations=3) — merge, resolve conflicts,
│                                   re-enter a desk via AgentTool when remedies interact
└── ReportWriter                    deterministic Python -> Report + marked-up script
```

Each desk is a `LoopAgent` over an `LlmAgent` with the shared toolbelt (`read_scene`,
`find_in_script`, `research`, `query_precedent`, `file_flag`, `note_open_question`, `done`),
deciding for itself what to investigate, how deep to chase ownership (cap 3), and when to stop.
Verifiers are blinded — claim and citation, not the desk's reasoning — and an UNSUPPORTED flag
never reaches the report.

Governing principle, applied twice: **never let the model assert what you could retrieve.**
Parallel for the outside world, ClickHouse for the comparison set. Gemini does judgement only.

The fan-out is not decoration. A studio really does run four independent desks that do not talk
to each other, and a producer reconciles them. The architecture mirrors the domain — say so.

## Data contracts

`schemas/` holds the frozen JSON Schemas: `scene`, `entity`, `flag`, `report`. They are the
interface between the agent workstream and the data/UI workstream. **Do not change a schema
without saying so out loud** — someone else is coding against it right now.

Invariant: **a Flag without a citation does not render.** That is the entire product thesis. If
an agent cannot cite it, it is not a finding.

## Conventions

- Python 3.11, `src/greenlight/`, `ruff` for lint/format, `pytest` for tests.
- Agents live in `src/greenlight/agents/<name>.py`, one agent per file, each exporting `agent`.
- Every LlmAgent writes to session state via `output_key`; downstream agents read state, they do
  not re-parse text.
- Tools are plain typed Python functions with docstrings. ADK reads the signature — the docstring
  is the tool spec, so write it for a model, not a human.
- Model tiers: `gemini-3.7-flash` for extraction and per-entity work (global endpoint only;
  overridable via `GREENLIGHT_FLASH_MODEL`, every change gated on the 21-check eval), `gemini-2.5-pro` for the
  Adjudicator only. Budget is $100 total; Flash is the default and Pro is a deliberate choice.
- Never call a live API in a unit test. Cache fixtures under `fixtures/cassettes/`.

## Cost discipline

Cost is COGS now, not a credit ceiling: track per-run model+search cost (scripts/costs.py)
against the pricing ladder (free 1-pass / paid k=3 / enterprise). Cache aggressively — brand,
music, and trademark lookups repeat across scripts. Keep a cached end-to-end run in `runs/`
so demos work with no network.

## Commands

```bash
make dev        # local ADK dev UI
make run        # end-to-end on the fixture screenplay
make test
make check      # ruff + forbidden-dependency scan
```

## Demo material

- The demo screenplay in `fixtures/` is **original work we wrote**. Never use a real screenplay
  in fixtures or marketing. Case studies use scripts of released films for analysis only.
