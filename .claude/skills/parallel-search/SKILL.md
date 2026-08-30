---
name: parallel-search
description: How GREENLIGHT calls the Parallel Search API. Load before writing or editing any code that researches an entity, builds a citation, or touches the parallel-web SDK. Contains the verified SDK signature and response shape — do not write these calls from memory.
---

# Parallel Search in GREENLIGHT

Parallel is the **partner track requirement**: the Search API must be genuinely called at
runtime. It is also the source of every citation, which is the product's entire credibility
claim. Both reasons mean this integration is never mocked on the default path.

Verified against `parallel-web==1.3.0` by introspection and a live call.

## The call

```python
import parallel

client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])

res = client.search(
    search_queries=[...],   # REQUIRED. Concise keyword queries, 3-6 words each. Give 2-3.
    objective="...",        # Natural-language description of the real question. Self-contained.
    mode="advanced",        # turbo | fast | basic | advanced. Default advanced.
    max_chars_total=6000,   # Upper bound on total excerpt characters across all results.
    session_id=None,        # WIRED: research() passes a per-run id so chained questions share context.
)
```

Everything except `search_queries` is keyword-only and optional.

### search_queries vs objective — the distinction that matters

They are not redundant, and using only one wastes the API.

- `search_queries` are **keyword retrieval strings**. Short. No sentences.
- `objective` is the **actual clearance question**, in full prose, with enough context to stand
  alone. This is where the entity's script context belongs.

A gatekeeper agent should build the objective from the `Entity.context` field — the surrounding
script text is precisely the disambiguating context `objective` is designed to consume.

Good:
```python
search_queries=["music sync license cost feature film", "master recording license fee film"]
objective=("A screenplay uses a well-known 1970s rock song over a funeral scene. Determine "
           "what licenses are required, from which rightsholders, and the typical cost and "
           "negotiation timeline for a mid-budget feature.")
```

## The response

```
SearchResult
  .results: list[WebSearchResult]
  .search_id: str          # log this — it makes a citation reproducible
  .session_id: str
  .usage: list[UsageItem] | None
  .warnings: list[Warning] | None

WebSearchResult
  .url: str
  .title: str | None
  .publish_date: str | None
  .excerpts: list[str]     # VERBATIM source text
```

## Mapping to `schemas/flag.schema.json`

The response maps onto our citation object almost one-to-one — this is why the partner choice
fits the product rather than being bolted on:

| Parallel | Flag citation |
|---|---|
| `result.url` | `citation.url` |
| `result.title` | `citation.title` |
| `result.excerpts[i]` | `citation.excerpt` — **verbatim, never paraphrased** |
| `result.publish_date` | context for weighting recency |
| — | `citation.via = "parallel_search"` |
| — | `citation.source_type = "web"` |

**Never** let a model rewrite an excerpt before it lands in a citation. The excerpt's value is
that it is quotable and checkable. Paraphrasing it destroys the only thing that distinguishes
this project from an LLM asserting things confidently.

## Known behaviours

- **Duplicate pages come back at different URL casing** (`/library/` and `/Library/` were both
  returned as separate results in the same response). Always dedup citations on a normalized URL
  — lowercase host and path, strip trailing slash and query — before rendering. Undeduped
  citations make a report look padded, which costs us exactly the credibility we are selling.
- Typical response is ~10 results for a two-query search.
- `publish_date` is frequently `None`. Do not require it.

## Offline development

Cached real responses live in `fixtures/cassettes/*.json` (`SearchResult.model_dump()`). Use them
in tests so the suite is deterministic and free. Never let a cassette become the default runtime
path — the live call is what satisfies the track requirement.

## Cost discipline

One search per entity, not per entity per agent. Multiple gatekeepers needing the same entity
share one result set via session state. `mode="fast"` is fine for smoke tests; `advanced` for
real analysis.

### What a run costs (working rates, keep current with invoices — see scripts/costs.py)

- **Parallel**: ~$0.009 per `advanced` search. A clearance run on the 12-scene fixture spends
  19–26 searches ≈ **$0.20/run**. `searches_spent` in the worker's `run_summary` log line is
  the measured count; each `search_id` in the record is one billed search.
- **Gemini**: ~$3.70/run — back-calculated from the Aug 2026 billing console ($170 of
  post-discount Gemini/storage spend over 46 runs), not per-run measured. Flash intro pricing
  $0.75/$3.75 per MTok runs through 2026-12-31, then doubles. Per-run `usage_metadata`
  capture is the planned fix; until it lands, budget ≈ **$3.90 total per clearance run**
  (all cash — the $100 GCP credit is exhausted as of 2026-08-29).
- Never add a per-desk search: any change that multiplies searches multiplies the only
  metered per-run cost that scales with entity count.
