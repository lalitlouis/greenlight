# GREENLIGHT

Multi-agent screenplay clearance and production-risk analysis. Four gatekeeper agents read a
screenplay and emit a marked-up script plus a Production Risk Report where every flag carries a
citation, a remedy, and a cost/schedule estimate.

This is a product. The north star for every change is a single one:

> **Make the report more ACCURATE and more CONSISTENT.** A finding that is right, cited
> honestly, counted correctly, and would look the same on a second read is the whole product.
> Every action — a parser fix, a prompt line, a schema field, a renderer tweak — earns its
> place by moving accuracy or consistency forward, and is judged against that.

Accuracy and consistency are different failures and both are fatal. Accuracy: is the finding
true, is the citation real, does the scene it names contain what it claims? Consistency: would
two reads of the same script agree, do the numbers reconcile, does the report contradict
itself? A false finding and a self-contradicting report each destroy the credibility the
product sells.

---

## Runtime stack

The product's runtime AI is **Google's Gemini via the ADK agent framework**, with **Parallel**
for outside-world retrieval and **Google Cloud** for infrastructure. This is a deliberate,
coherent single-runtime architecture — not an accident to be worked around.

- Runtime AI is Gemini only. `scripts/check_forbidden_deps.sh` (part of `make check`) keeps the
  shipped runtime free of other model SDKs (`anthropic`, `openai`, `langchain*`, `llama-index`,
  `crewai`, `autogen`, `litellm`, `cohere`, `mistralai`, `ollama`, `replicate`, Bedrock,
  `azure-ai-*`). Keep it green. Allowed AI/agent packages: `google-adk`, `google-genai`,
  `google-cloud-aiplatform`. (Claude Code is a *development* tool and out of scope for the
  runtime scanner — it never enters the shipped path.)
- **Parallel is genuinely called at runtime**, via the official `parallel-web` SDK — it is the
  source of every citation, which is the product's entire credibility claim. `fixtures/` may
  hold cached Parallel responses for offline dev, but the live call is the default path; never
  let a refactor make it optional, mocked-by-default, or dead.
- **ClickHouse** holds the comparison corpus (released-film rating profiles) for the What-If
  and rating work.

## Architecture

Agentic, not a pipeline. An earlier design — extract entities, one search each, four prompts,
dedupe — was deliberately killed because it cannot produce a correct clearance report. **Do not
regress to it.** Full reasoning in `docs/TECH_SPEC.md`, which is the authoritative spec; if this
diagram and TECH_SPEC ever disagree, TECH_SPEC wins.

```
GreenlightPipeline                  SequentialAgent
├── ScriptParser                    deterministic Python, not an LLM — Fountain/PDF -> Scene[]
├── Triage                          LlmAgent -> Entity[] + per-desk worklists
├── GatekeeperPanel                 ParallelAgent — the desks run concurrently
│   ├── ClearanceDepartment         ParallelAgent of ≤4 batch LoopAgents
│   │                               (clearance_counsel__bN, ~25-item slices,
│   │                               fresh conversations; caches/provenance shared,
│   │                               all mutable state keys per-agent)
│   ├── RatingsBoard                LoopAgent(max_iterations=6)
│   ├── SafetyUnderwriter           LoopAgent(max_iterations=6)
│   └── TerritoryCensor             LoopAgent(max_iterations=8)
├── CompletenessGate                LoopAgent(≤3) — deterministic check + sweep desk;
│                                   refuses to advance while any extracted entity lacks
│                                   a disposition (absence must never render as clean)
├── VerificationPanel               fan-out — one blinded verifier per filed flag; can REJECT
├── Adjudicator                     single LlmAgent (Pro) — merges duplicates, normalizes
│                                   categories, states conflicts on the record (desk
│                                   re-entry via AgentTool: deferred roadmap)
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
to each other, and a producer reconciles them. The architecture mirrors the domain.

## Determinism vs. desk judgement — the consistency contract

Two layers, two different guarantees, and knowing which is which is how we keep our promises:

- **Deterministic layer** (parser, renderers, schemas, all the scoring/cost/accounting math):
  same input → byte-identical output, every time. A change here is verified before/after against
  the real script, and a change to the scene structure (which anchors every flag) is a stop-and-
  prove-it moment. We can and do promise no regressions here.
- **Desk output** (what the four LlmAgents choose to flag, clear, or how they rate severity) is
  non-deterministic even at temperature 0 — a dozen compounding model calls. Two runs of the
  same script will differ in the LOW/MEDIUM tail and in category choices; the HIGH findings and
  the top cost drivers are stable. Consistency work targets this: stabilize what can be
  stabilized (deterministic ids, reconciled coordinates, honest counts), and never claim a
  guarantee the desks can't keep.

When a run reveals a defect, separate the two: a deterministic bug is ours to fix and pin with a
test; desk variance is a property to manage, not a regression to blame on the last change.

## Data contracts

`schemas/` holds the frozen JSON Schemas: `scene`, `entity`, `flag`, `report`. They are the
interface between the agent workstream and the data/UI workstream. **Do not change a schema
without saying so out loud** — someone else may be coding against it. Additive, optional fields
are the safe change; announce them.

Invariant: **a Flag without a citation does not render.** That is the entire product thesis. If
an agent cannot cite it, it is not a finding.

## Pre-release assertions

The report must not contradict itself. These deterministic invariants are enforced in the eval
(`scripts/eval_run.py`) and fail the gate mechanically — the calibration statement made
checkable. Add to this set whenever a run surfaces a new self-contradiction class:

- Every kept flag has a citation with a real excerpt.
- No adjudication note references a finding id that does not render.
- A finding's prose names no scene outside its own coordinates.
- Absence never renders as cleanliness (every extracted entity is dispositioned).
- The score is withheld, never inflated, when a desk or the verifier could not do its job.

## Conventions

- Python 3.11, `src/greenlight/`, `ruff` for lint/format, `pytest` for tests.
- Agents live in `src/greenlight/agents/<name>.py`, one agent per file, each exporting `agent`.
- Every LlmAgent writes to session state via `output_key`; downstream agents read state, they do
  not re-parse text.
- Tools are plain typed Python functions with docstrings. ADK reads the signature — the docstring
  is the tool spec, so write it for a model, not a human.
- ADK skips state injection for CALLABLE instruction providers — every `{placeholder}` in a
  desk instruction must be substituted by hand in `common.py`'s `_instruction`, or it reaches the
  model as literal braces.
- Model tiers: `gemini-3.7-flash` for extraction and per-entity work (global endpoint only;
  overridable via `GREENLIGHT_FLASH_MODEL`, every change gated on the accuracy eval),
  `gemini-2.5-pro` for the Adjudicator only. Flash is the default; Pro is a deliberate,
  cost-aware choice.
- Never call a live API in a unit test. Cache fixtures under `fixtures/cassettes/`.

## Cost discipline

Runs cost real money — a fixture run is a couple of dollars, a feature-length script more, and
model spend is the dominant per-run cost. Be deliberate: `make check` and `make test` are free
and expected; a full `make run` or the eval gate is a spend, so batch changes and gate once.
Always keep a cached end-to-end run in `runs/` so development and review work with no network.
`scripts/costs.py` (`make costs`) tracks spend against real invoices.

## Repo & data hygiene

- Public GitHub repo with `LICENSE` (MIT) at root. Commit continuously.
- The demo/test screenplay in `fixtures/` is **original work we wrote** — never commit a real
  copyrighted screenplay to the repo.

## Commands

```bash
make dev        # local ADK dev UI
make run        # end-to-end on the fixture screenplay (a real spend)
make test
make check      # ruff + forbidden-dependency scan (free)
make costs      # spend tracker
```
