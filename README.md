# GREENLIGHT

**Multi-agent screenplay clearance and production-risk analysis.**

Before a single frame is shot, a studio spends weeks clearing a screenplay: four separate desks —
rights counsel, the ratings board, the safety underwriter, and territory censors — each read the
same script looking for different ways it will cost money or fail to release. It is manual,
serial, and expensive.

GREENLIGHT runs those four desks concurrently as agents, and every finding it returns carries a
citation, a concrete remedy, and a cost/schedule estimate.

> **Status:** in development for the Agentic Cinema hackathon (Parallel track).

## What it produces

- A **marked-up script** with every flag anchored to its scene.
- A **Production Risk Report**: severity-ranked flags, each with sourced citations and a remedy.
- A **Greenlight Score** (0–100) and an evidence-based MPA rating prediction with comparable films.

## Stack

| Layer | Technology |
|---|---|
| Agent framework | Google Agent Development Kit (`google-adk`) |
| Models | Gemini 2.5 Flash / Pro on Vertex AI |
| Hosting | Google Cloud (Agent Engine + Cloud Run) |
| Research | **Parallel Search API** (`parallel-web`) — per-entity clearance research |
| Precedent corpus | ClickHouse Cloud — kNN over MPA rating rationales |

All AI/model inference at runtime is **Gemini on Google Cloud**. No other AI models, agent
frameworks, or AI APIs are used anywhere in this project.

## Architecture

```
GreenlightPipeline (SequentialAgent)
├── ScriptParser        Fountain/PDF -> Scene[]        (deterministic)
├── EntityExtractor     -> Entity[]                    (Gemini)
├── GatekeeperPanel     ParallelAgent — four desks, concurrent
│   ├── ClearanceCounsel     Parallel Search  -> Flag[]
│   ├── RatingsBoard         ClickHouse kNN   -> Flag[]
│   ├── SafetyUnderwriter    rules + Parallel -> Flag[]
│   └── TerritoryCensor      ClickHouse + Parallel -> Flag[]
├── Adjudicator         dedupe, reconcile, score       (Gemini)
└── ReportWriter        -> Report + marked-up script   (deterministic)
```

The fan-out mirrors the domain: a real clearance process is four independent desks that do not
talk to each other, reconciled at the end by a producer.

## Running locally

```bash
cp .env.example .env      # fill in credentials
make install
make run                  # end-to-end on the fixture screenplay
make dev                  # ADK dev UI
```

See [`docs/SETUP.md`](docs/SETUP.md) for provisioning Google Cloud, Parallel, and ClickHouse.

## Documentation

- [PRD](docs/PRD.md) — problem, users, scope
- [Tech Spec](docs/TECH_SPEC.md) — pipeline, contracts, deployment
- [Stack](docs/STACK.md) — every technology and why it is here
- [Compliance](docs/COMPLIANCE.md) — contest requirements and status

## Data contracts

`schemas/` holds the frozen JSON Schemas (`scene`, `entity`, `flag`, `report`) that every
component codes against. Core invariant: **a flag without a citation does not render.**

## Demo script

`fixtures/` contains an original screenplay written for this project, seeded with one instance of
every flag category. It is not a real or third-party screenplay.

## License

MIT — see [LICENSE](LICENSE).
