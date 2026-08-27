# Scaling plan: every path, every break point

A solution-architecture pass over the WHOLE system (2026-08-26) — not just the analysis
pipeline: uploads, encryption, exports, simulators, auth, metrics, and lifecycle all
carry load, and a smooth experience is set by the worst of them, not the average.

Two units of work with different physics:
- **Page/API traffic** — cheap requests; thousands/sec is a reachable engineering target.
- **Analysis runs** — 10–30 min jobs, 200–400 Gemini calls each. Their scale is set by
  model quota and dollars; architecture's job is absorbing spikes and never wasting a run.

## Path-by-path inventory

| Path | Today | First break point | Fix when it breaks |
|---|---|---|---|
| **Upload** (Fountain/PDF) | 5MB cap; PDF parse + language guard + Fernet encrypt in-request; GCS write | PDF parsing is sync CPU (~1-3s big PDFs) — blocks an instance thread at ~tens of concurrent uploads | Parse in the worker instead of the web tier: accept → store raw → job parses. Also per-user upload rate cap |
| **Dispatch** | Cloud Run Job per run; fleet cap = Firestore count-read (max 5) | Read-then-act race under burst; hard refusal when full | Cloud Tasks queue between accept and execute; honest queue position UI; quota-rate drain |
| **Execution** | Isolated job per run, deploy-immune, journal checkpoints | Job cold-start (~10s) + execution quotas at ~hundreds concurrent | Warm worker pool (same code, queue-driven); resume-from-journal for crash recovery |
| **Live viewing (SSE)** | Per-viewer Firestore poll loop | N viewers × M chunks reads at ~hundreds of viewers | One journal tail per run per instance, in-process fan-out; then Firestore listeners |
| **Report/record views** | GCS JSON read per view | Fine to ~1k RPS; repeated decrypt+read waste | In-memory LRU per instance (records are immutable); CDN only for public case pages — private reports stay origin-served |
| **Script view** | GCS read + Fernet decrypt per view | Decrypt is ~ms — not a bottleneck; repeated reads are | Same LRU; never CDN (private content) |
| **Exports: binder/one-sheet PDF, CSV** | reportlab generated in-request (~100-300ms CPU each) | CPU starvation on web instances at ~tens/sec; big binders block the event loop via to_thread pool | Generate ONCE at run completion, store to GCS next to the record (immutable) — downloads become GCS reads. Biggest smooth-experience win per line of code |
| **Revised-script export (.fountain/.fdx)** | Computed in-request from record | Same shape as PDFs, lighter | Same fix: cache to GCS keyed by (run, accepted-fix set) |
| **What-If simulator** | Vertex embed (us-central1) + ClickHouse kNN per request; per-IP in-memory rate limit | Embed QPM quota is shared with ingest and pinned to ONE region; per-instance rate limits stop working multi-instance | Cache embeddings by rationale-hash (repeat cuts re-use), shared rate-limit store, embed quota bump |
| **First Look** | Deterministic profile + one Flash call per run | Scales with runs, not viewers — fine | — |
| **Writer's Room** | **Runs in-process on the web instance** (known debt) | A handful of concurrent writer runs degrades EVERY user's page loads | Workerize like clearance (same job pattern); until then, cap concurrent writer runs |
| **Auth/OAuth** | Google OAuth, stateless signed cookies | Nothing before Google's own limits | — |
| **Delete/lifecycle** | Synchronous GCS multi-object delete | Fine | Background with tombstone if object counts grow |
| **Metrics** | Single Firestore doc, atomic increments (fire-and-forget) | ~1 sustained write/sec per doc — counter contention under burst; increments silently drop | Sharded counters (10 shards) or BigQuery sink; drops are silent by design so UX never breaks |

## Cross-cutting

- **Encryption & keys**: Fernet (AES-128-CBC+HMAC) applied app-side before GCS; key in
  Secret Manager. Decrypt cost is negligible (~ms/script) — the scale question is key
  MANAGEMENT, not throughput: rotation needs a key-version prefix on blobs (v1: re-encrypt
  on read), enterprise needs KMS envelope encryption and per-tenant keys. Design now,
  build when the first enterprise conversation demands it.
- **Rate limiting**: per-instance dicts today (What-If, uploads implicitly). Multi-instance
  correctness needs a shared store (Firestore counters short-term, Memorystore at volume).
- **Caching doctrine**: immutable artifacts (records, generated PDFs, versioned static)
  cache aggressively at every layer; private artifacts never leave origin; the research
  cache is the cost moat and already cross-run.
- **Observability**: structured logs exist (run_summary, live-API warnings); missing are
  log-based alerts (run failures, 429 bursts, journal stalls) and p95 dashboards per path
  above. Console work, ~an hour, high leverage.
- **Single region**: us-central1 everywhere (embeddings pinned there). Multi-region is a
  P2 concern; the global Gemini endpoint already decouples model capacity from region.

## Capacity today (honest estimates)

- Web tier: ~100-200 RPS/instance for pages+API; autoscales. PDFs in-request are the
  first CPU cliff.
- Analyses: 5 concurrent (deliberate cap), each ~10-30 min. Quota, not architecture.
- Uploads: seconds each, 5MB cap; dozens concurrent before PDF parse contention.

## Phases

- **P0 — before the hackathon demo** (smooth experience at demo scale):
  ~~generate binder/one-sheet PDFs at run completion~~ (SHIPPED 2026-08-27: worker
  renders both at completion, sealed in GCS under pdfs/; routes serve the artifact
  and fall back to on-demand for old records); ~~What-If embed cache~~ (SHIPPED:
  rationale-hash memo + GCS, repeated cuts never re-bill the embed quota); SSE
  per-instance fan-out; log-based alerts. Upload-time PDF parsing stays web-tier
  for now — seconds each, contended only at tens of concurrent uploads.
- **P1 — first real users**: dispatch queue + queue-position UX; workerize Writer's
  Room; shared rate limits; sharded metrics; embed caching for What-If; CDN for public
  pages; resume-from-journal.
- **P2 — enterprise/thousands-RPS**: warm worker pool; Memorystore; KMS envelope +
  per-tenant keys; multi-region; Provisioned Throughput; managed event fan-out.

The bottleneck ladder ends at the same wall regardless: Gemini throughput. Cache
(built), bounded context (built), batching (in progress), then money (PT). Everything
above exists to deliver a smooth experience up to that wall — and to make sure no
$2 web request ever queues behind a $0.002 one.
