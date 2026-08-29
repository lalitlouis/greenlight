# GREENLIGHT

Multi-agent screenplay clearance and production-risk analysis. Four gatekeeper agents read a
screenplay and emit a marked-up script plus a Production Risk Report where every flag carries a
citation, a remedy, and a cost/schedule estimate.

Built for the Agentic Cinema hackathon (Devpost / Google Cloud), **Parallel partner track**.

---

> **Status note (2026-08-28):** a pivot to business-only (abandoning the hackathon) was
> executed and then SUSPENDED the same day — final hackathon decision is due next week.
> Until that decision, every rule below is BACK IN FORCE. One deviation stands: the repo is
> temporarily PRIVATE (owner's privacy preference); it must flip public before submission
> if the hackathon proceeds. See docs/DECISIONS.md for the full sequence.

## NON-NEGOTIABLE CONSTRAINTS

These are contest rules. Violating any one is pass/fail disqualification, not a style problem.

### 1. Runtime AI is Gemini and only Gemini

The rules permit *only* Google Cloud AI tooling at runtime. Non-Google AI SDKs are banned
**by name**, including Anthropic, OpenAI, AWS, and Microsoft.

Never add, import, or call any of:
`anthropic`, `openai`, `langchain*`, `llama-index`, `crewai`, `autogen`, `litellm`,
`cohere`, `mistralai`, `ollama`, `replicate`, `boto3` Bedrock, `azure-ai-*`.

There is no exception. Not for a fallback, not for an eval harness, not "just for a test", not
commented out. `scripts/check_forbidden_deps.sh` enforces this on every file write.

Allowed AI/agent packages: `google-adk`, `google-genai`, `google-cloud-aiplatform`.

Claude Code is used as a *development* tool. That is fine and out of scope for the rule, which
governs the Project. But Stage One screening may be automated, so never write anything into the
shipped repo that reads as a non-Google model being called at runtime.

### 2. Parallel must be genuinely called at runtime

The Parallel track requires the **Search API** to be invoked in code, via the official
`parallel-web` SDK. Naming it in the README does not satisfy the requirement. If a refactor ever
makes the Parallel call optional, mocked-by-default, or dead, the submission fails Stage One.
`fixtures/` may contain cached Parallel responses for offline dev, but the live path is the
default path.

### 3. Google Cloud must be genuinely called at runtime

`google-adk` imported and executing. Same reasoning as above.

### 4. Repo hygiene

- Public GitHub repo with `LICENSE` (MIT) at root so GitHub's About section detects it.
- All source, assets, and run instructions present.
- Commit continuously. "New projects only" is verified; a repo with one commit on the deadline
  looks fabricated.

### 5. Deadline

**2026-09-09, 2:00 PM PT.** Treat Sept 8 as the real deadline.

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
├── CompletenessGate                LoopAgent(≤3) — deterministic check + sweep desk;
│                                   refuses to advance while any extracted entity lacks
│                                   a disposition (absence must never render as clean)
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
  overridable via `GREENLIGHT_FLASH_MODEL`, every change gated on the 24-check eval), `gemini-2.5-pro` for the
  Adjudicator only. Budget is $100 total; Flash is the default and Pro is a deliberate choice.
- Never call a live API in a unit test. Cache fixtures under `fixtures/cassettes/`.

## Cost discipline

$100 of GCP credit covers the entire project. Agent Engine bills for idle replicas — develop
locally against `adk web` and deploy late (day 12+). Always keep a cached end-to-end run in
`runs/` so the demo works with no network.

## Commands

```bash
make dev        # local ADK dev UI
make run        # end-to-end on the fixture screenplay
make test
make check      # ruff + forbidden-dependency scan
```

## Demo and submission constraints

- The demo screenplay in `fixtures/` is **original work we wrote**. Never use a real screenplay.
- The 3-minute video must not display third-party logos or trademarks. Lead with music/likeness
  clearance rather than brand flags — same point, nothing branded on screen.
