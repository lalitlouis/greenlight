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
├── GatekeeperPanel                 ParallelAgent — four desks, concurrent
│   ├── ClearanceCounsel            LoopAgent(max_iterations=8)
│   ├── RatingsBoard                LoopAgent(max_iterations=4)
│   ├── SafetyUnderwriter           LoopAgent(max_iterations=6)
│   └── TerritoryCensor             LoopAgent(max_iterations=6)
├── VerificationPanel               ParallelAgent — one verifier per filed flag
├── Adjudicator                     LoopAgent(max_iterations=3)
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
| `query_precedent(text, k)` | ClickHouse kNN over MPA rating rationales. |
| `file_flag(flag)` | Emit a finding. Schema-validated on the way in; a flag without a citation is rejected at the tool boundary. |
| `note_open_question(text)` | Record something the desk could not resolve. Surfaced in the report — an honest unknown beats a confident guess. |
| `done(reason)` | Self-terminate. Sets `tool_context.actions.escalate = True`, which is how a `LoopAgent` exits early. |

Tools are plain typed Python functions. ADK reads the signature and docstring as the tool spec, so
docstrings are written for a model, not a human.

## Loop termination

Three independent stops, because a research loop that cannot end is a bill:

1. **Self-termination** — the desk calls `done()` and escalates.
2. **`max_iterations`** — a hard ceiling per desk.
3. **Research budget** — a per-run cap on `research()` calls, enforced in the tool. When exhausted
   the tool returns "budget spent, file what you have," which the desk handles gracefully.

Chase depth is capped at 3 (entity -> rightsholder -> administrator). Deeper than that is a human's
job and the report says so.

## Verification

Every filed flag fans out to an independent verifier that receives **the claim and the citation,
but not the desk's reasoning**, and answers one question: does this source actually support this
claim?

- `SUPPORTED` — flag stands.
- `PARTIAL` — flag stands, severity capped at MEDIUM, marked "partially supported."
- `UNSUPPORTED` — flag is dropped and logged. It never reaches the report.

Withholding the desk's reasoning is deliberate: a verifier shown the argument tends to ratify it.

Implementation note: ADK's `ParallelAgent` takes a static sub-agent list, and flag count is not
known until the desks finish — so the VerificationPanel is built at runtime (or run as a fan-out
inside a custom agent), not declared as a fixed `ParallelAgent`. Same class of care applies to the
Adjudicator's `AgentTool` re-entry: a re-entered desk appends to `flags:<desk>` and must not
double-file findings it already made.

This pass is the product thesis made mechanical. Rejected-flag count is a metric we report to
ourselves — if it is zero, the verifier is not doing its job.

## Adjudication

A `LoopAgent` that reconciles surviving flags:

- Merges duplicates found by different desks on the same scene.
- Resolves conflicting remedies (Ratings Board wants a line cut; Clearance Counsel wants the same
  line rewritten).
- **Detects interaction.** When a remedy changes a scene another desk scored, it calls that desk
  again through `AgentTool` with the proposed change. That re-entry is why this is a loop.

Terminates when a pass produces no new merges, conflicts, or re-checks.

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
| Triage | Flash | High-volume extraction |
| The four desks | Flash | Many tool-calling turns; Flash is the default and cost driver |
| Verifiers | Flash | Narrow, single-question judgement |
| Adjudicator | Pro | The only task reasoning across four desks' conflicting output |

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
- **Verifier regression set:** hand-labelled flag/citation pairs, including deliberately
  unsupported ones. If the verifier stops rejecting those, it has silently broken.
- `make check` runs lint plus the forbidden-dependency scan.

## Risks

| Risk | Mitigation |
|---|---|
| Research loops burn the budget | Three independent stops; shared cache; depth cap |
| Desks under-investigate and file thin flags | Verifier rejection rate is monitored; instruction tuning |
| Agent Engine deploy fights us | Cloud Run fallback; ADK runs either way |
| Live demo network failure | Pre-computed run committed to `runs/` |
| Latency on a feature script | Concurrent desks; per-entity research cache |
