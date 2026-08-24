# Stack — and why each piece is here

Submitted to the **Parallel** partner track.

## Required by the contest

| Requirement | How GREENLIGHT satisfies it | Verified |
|---|---|---|
| Powered by Gemini | `gemini-2.5-flash` (extraction, per-desk analysis), `gemini-2.5-pro` (adjudication) on Vertex AI | live call returns |
| Google Cloud Agent Builder | `google-adk` 2.7.1 — `SequentialAgent` + `ParallelAgent`, deployed to Vertex AI Agent Engine | installed, pipeline built on it |
| Partner product called at runtime | `parallel-web` 1.3.0, `client.search(...)` — one research task per script entity | live call, 10 sourced results |
| Runs on web | FastAPI + Cloud Run, public URL | pending deploy |
| Public repo, OSS license | MIT, detected by GitHub in the About panel | `gh repo view` confirms |

## Every dependency, and the reason

| Technology | Role | Why this and not something else |
|---|---|---|
| **Google ADK** (`google-adk`) | Agent framework | `ParallelAgent` gives real concurrent fan-out with shared session state. The hackathon resources explicitly discourage wrapper libraries, and ADK is the native Google Cloud path. |
| **Gemini 2.5 Flash / Pro** | Extraction, analysis, adjudication | Flash is the default for cost; Pro is reserved for the one task that genuinely needs reasoning across four desks' conflicting output. |
| **Vertex AI Agent Engine** | Agent hosting | The managed runtime for ADK agents — "Agent Builder" in the contest's language. |
| **Parallel Search API** (`parallel-web`) | Per-entity clearance research | The partner track choice, and a genuine fit — see below. |
| **ClickHouse Cloud** | MPA rating precedent corpus, kNN | Fast vector + analytical queries over a few hundred CARA rationales. Used as a plain database, which the rules permit on a non-ClickHouse track. |
| **Cloud Run** | Web app hosting | Scales to zero — matters on a $100 budget. |
| **FastAPI + SSE** | API and live progress streaming | The four-desk concurrency has to be *visible*; SSE streams per-desk events as they land. |
| **pdfplumber** | PDF screenplay parsing | Preserves character offsets, which the marked-up script view depends on. |

**No non-Google AI.** No OpenAI, Anthropic, AWS, Microsoft, LangChain, CrewAI, or any other model
or agent framework, anywhere in the project. Enforced mechanically — see `docs/COMPLIANCE.md`.

## Why Parallel is load-bearing, not decorative

A clearance report is, concretely, a paralegal running dozens of independent research questions
and writing down what they found with sources. That is the shape of the Parallel Search API.

Three specifics that make the fit real rather than convenient:

1. **`objective` takes the actual question in prose.** Clearance questions are not keywords —
   they are *"a screenplay shows this brand's product exploding; can it clear?"* We build the
   objective from each entity's surrounding script text, which is exactly the disambiguating
   context the parameter is designed to consume.

2. **`excerpts` are verbatim.** Our product rule is that a finding without a quotable citation
   does not render. Parallel returns source text we can put in a report unaltered. A search API
   returning only URLs and summaries could not support this product.

3. **Fan-out is the workload.** A feature script yields dozens of clearance-relevant entities,
   each needing its own independent research task. That is the scale Parallel is built for, and
   it maps onto ADK's `ParallelAgent` without adapting either side.

Validated on the first live call: a query about a brand depicted negatively returned dated,
sourced legal excerpts stating the governing doctrine (product disparagement) and the standard
remedy (written permission) — directly supporting the flag we would generate.

## Why ClickHouse earns its place

MPA rating rationales are public and formulaic (*"Rated R for strong bloody violence, language
throughout..."*). Ingest a few hundred, embed them, and rating prediction stops being a model's
guess and becomes a nearest-neighbour lookup over released films: *"your comparables are these
eight titles, seven rated R."*

That is a different and more defensible claim than asking a model what rating a script will get.

## How this maps to the judging criteria

- **Technological Implementation** — ADK's `ParallelAgent` used for genuine concurrency; Parallel
  and ClickHouse each doing work the other could not.
- **Design** — a deployed product with live per-desk progress, a marked-up script, and clickable
  citations; not a notebook.
- **Potential Impact** — clearance is a real, costly, pre-production bottleneck that independent
  producers currently cannot afford at all.
- **Quality of the Idea** — most entries generate media. This does citable analysis of a
  bottleneck that is invisible unless you have worked in production.
