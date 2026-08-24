# Tech Spec — GREENLIGHT

## Pipeline

```
ScriptParser      deterministic Python      screenplay -> Scene[]
      |
EntityExtractor   Gemini 2.5 Flash          Scene[] -> Entity[]
      |
ResearchCache     Parallel Search           one search per Entity, shared across agents
      |
GatekeeperPanel   ADK ParallelAgent         four desks, concurrent
  |- ClearanceCounsel    Parallel   -> Flag[]
  |- RatingsBoard        ClickHouse -> Flag[] + rating_prediction
  |- SafetyUnderwriter   rules      -> Flag[]
  |- TerritoryCensor     ClickHouse -> Flag[]
      |
Adjudicator       Gemini 2.5 Pro            dedupe, reconcile, assign severity
      |
ReportWriter      deterministic Python      -> Report + marked-up script
```

The fan-out mirrors the domain: a real clearance process is four independent desks that do not
consult each other, reconciled at the end by a producer.

## Design decisions

**Parsing and scoring are deterministic, not model calls.** A parser that hallucinates a scene
number breaks every downstream anchor, and a Greenlight Score that varies run-to-run is not a
score. Models are used only where judgment is genuinely required: entity extraction, per-desk
analysis, and adjudication.

**One search per entity, not per entity per desk.** `ResearchCache` runs the Parallel search
once and shares results through ADK session state. Four desks researching the same song
independently would quadruple cost and latency for identical results.

**Citations pass through untouched.** A model may decide *whether* an excerpt supports a finding,
never rewrite it. The excerpt's value is that it is quotable and checkable.

**Agents communicate through state, not text.** Every `LlmAgent` writes via `output_key`;
downstream agents read structured state. Nothing re-parses another agent's prose.

## Data contracts

`schemas/` — `scene`, `entity`, `flag`, `report`. Frozen. They are the interface between the
agent workstream and the data/UI workstream; changing one blocks the other person.

Key invariants:
- `flag.citations` has `minItems: 1` — enforced by schema, not prompt.
- `scene.raw_span` is a char offset pair into the source, which is what makes the marked-up
  script view possible.
- `entity.depicted_negatively` is the field that flips a brand from "courtesy letter" to "will
  never clear."

## Components

| Component | Impl | Notes |
|---|---|---|
| ScriptParser | `pdfplumber` + Fountain regex | Emits `raw_span` offsets |
| EntityExtractor | Gemini 2.5 Flash, structured output | Typed against `entity.schema.json` |
| ResearchCache | `parallel-web` | Dedup citations on normalized URL — Parallel returns the same page at different casing |
| RatingsBoard | ClickHouse kNN over CARA rationales | Embeddings via Vertex; returns comparables |
| Adjudicator | Gemini 2.5 Pro | The only Pro call; merges overlapping flags |
| ReportWriter | Python | Score is a pure function of severities |
| Web app | FastAPI + SSE, static frontend | Streams per-desk progress |

## Greenlight Score

Deterministic, never asked of a model:

```
score = 100 - min(100, 30*BLOCKER + 12*HIGH + 5*MEDIUM + 1*LOW)
```

Weights are tunable; the property that matters is that one BLOCKER visibly dominates, because in
production it does.

## Deployment

- **Agents:** Vertex AI Agent Engine. Deployed late (day 12+) — it bills for idle replicas.
- **Web app:** Cloud Run, scales to zero.
- **Dev:** local `adk web`. Agent Engine is not in the inner loop.

Region `us-central1`. Staging bucket `gs://greenlight-clearance-2026-staging`.

## Cost

$100 total. Flash for everything except adjudication. Cassettes in `fixtures/cassettes/` keep
tests free and deterministic. A full cached run lives in `runs/` so the demo survives a dead
network.

## Testing

- Schema validation on every emitted object.
- Parser unit tests against the fixture screenplay.
- Agent tests replay cassettes — no live API calls in the suite.
- `make check` runs lint plus the forbidden-dependency scan.

## Risks

| Risk | Mitigation |
|---|---|
| Agent Engine deploy fights us | Cloud Run fallback; ADK runs either way |
| Live demo network failure | Pre-computed run committed to `runs/` |
| $100 credit exhausted | Budget alerts at 40/75/90%; Flash default |
| Feature-length script too slow | Concurrent fan-out; scene-level batching |
