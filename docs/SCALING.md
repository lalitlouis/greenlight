# Scaling review: what breaks at which order of magnitude

An honest architect's pass over the system (2026-08-26), written against the question
"could this withstand thousands of requests per second?" The first duty of that review
is to split the question, because this product has two very different units of work:

- **Page/API traffic** (reports, case studies, What-If, SSE viewers) — cheap requests,
  where thousands of RPS is a real and reachable target.
- **Analysis runs** — 10–30 minute jobs consuming 200–400 Gemini calls and 30–60
  Parallel searches each. "Thousands per second" of these is not a web-scale problem,
  it is an LLM-quota-and-cost problem; the architecture's job is to *absorb spikes
  gracefully* and execute at the rate the model quota allows.

## What already scales

| Piece | Why it holds |
|---|---|
| Web tier | Cloud Run autoscales horizontally; sessions are stateless signed cookies |
| Run execution | One Cloud Run Job per run — runs are isolated, deploy-immune, horizontally unbounded except by quota |
| Journal | Firestore chunked appends (~1.5s cadence); separate docs per chunk stay under per-doc write limits |
| Records/scripts | GCS, immutable after write — infinitely cacheable |
| Ratings kNN | ClickHouse over 6,302 rows — thousands of QPS is trivial for this shape |
| Research cache | Shared across runs AND users (GCS, 7-day TTL) — at scale this is a cost moat: the Nth analysis of a popular script era is mostly cache hits |

## The bottleneck ladder — in the order they would actually break

1. **SSE relay read amplification** (~hundreds of concurrent viewers). Today every
   viewer's connection independently polls the run's Firestore journal. N viewers ×
   M chunks = N×M reads. Fix: per-instance multiplexing — ONE journal tail per run per
   instance broadcasting to all its viewers (an in-process pub/sub dict; ~an afternoon).
   Beyond that: Firestore snapshot listeners instead of polls.
2. **Static serving from the app container** (~1k RPS). FastAPI serves every asset.
   Fix: Cloud CDN or Firebase Hosting in front — versioned asset paths already exist
   (`/static/v-{n}/`), so cacheability is designed in; this is wiring, not surgery.
3. **Dispatch admission** (~tens of submissions/sec). The fleet cap counts running
   Firestore docs at dispatch time — a read-then-act race under burst, and a hard
   refusal when full. Fix: a queue (Cloud Tasks) between accept and execute — accept
   thousands of submissions per second cheaply, enqueue, execute at quota rate, and
   show an honest queue position instead of a refusal. This is the single most
   load-bearing change for spikes.
4. **Per-run job dispatch overhead** (~hundreds of concurrent runs). Jobs cost ~10s
   to start and have per-project execution quotas. Fix at that scale: a warm worker
   pool draining the queue (Cloud Run service, concurrency=1) — same worker code,
   different trigger.
5. **In-memory cross-cutting state** (any multi-instance scale). Rate limits
   (`_whatif_rate`) and the live-run handle map are per-instance dicts. Fix:
   Redis/Memorystore or Firestore-backed counters when instance count grows.
6. **Gemini throughput — the real wall** (always). Every prior fix just delivers
   traffic to this wall faster. Levers, in order: shared research cache (built),
   bounded per-call context (built — batching bounds it by construction), Provisioned
   Throughput purchase (researched, deliberately deferred), and multi-region quota.

## Resilience gap worth naming

A killed worker today means a dead run (salvage keeps its filed flags, but the run
does not resume). The journal is already an event log; a checkpoint/resume feature —
worker restarts, replays state from the journal, continues from the last desk turn —
is the difference between "a crash costs a run" and "a crash costs a minute." Queued
behind the hackathon.

## What we deliberately do NOT build now

CDN, queue, worker pool, Redis, resume: none are needed below ~50 concurrent runs or
~1k RPS of page traffic, and the hackathon's binding constraint is the demo video,
not throughput. This document exists so scaling is a to-do list, not a redesign.
