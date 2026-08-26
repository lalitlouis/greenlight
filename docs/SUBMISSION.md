# Devpost submission draft

Copy-adjust into the Devpost form. Track: **Parallel**.

## Elevator (short description field)

Four AI clearance desks read your screenplay the way a studio does — rights, ratings, safety,
territory — and return a Production Risk Report where every finding carries a verbatim citation,
an independent verification, a concrete remedy, and a price. Before the budget locks.

## Inspiration

Script clearance is mandatory for E&O insurance, costs $1–3k, takes a week, and lands as a PDF
memo after the budget is locked. Independent producers mostly skip it and absorb the risk. We
asked: what does a clearance department look like as an agent system — not a chatbot with
opinions, but desks that research, cite, and get checked?

## What it does

- Parses a screenplay (Fountain or PDF) deterministically; triages every entity to four desks.
- The desks run concurrently as ADK LoopAgents, researching on the live web via **Parallel
  Search** — music ownership chains, insurer requirements, censorship rules — and file findings
  through a tool that structurally rejects any flag without a citation.
- An independent, blinded verifier re-reads every citation and rejects unsupported claims —
  rejections appear in the report with reasons.
- The Ratings Board predicts the MPA rating from evidence: kNN over 2,487 released films'
  content profiles in ClickHouse ("7 of 8 nearest comparables are R"), with the exact cut list
  to hit a target rating.
- A Pro-tier adjudicator merges duplicates and resolves conflicting remedies deterministically.
- **The What-If simulator**: the cut list is interactive — checking cuts re-runs the real
  evidence pipeline (rationale rewritten, re-embedded, re-searched against all 2,487 films),
  and it will honestly disagree with its own cut list ("closer, not clear: 1 → 3 of 8").
- **Production artifacts**: a downloadable Clearance Binder (the standard studio clearance
  log as PDF/CSV), a one-sheet PDF poster, and accepted fixes exported as a revised
  .fountain or Final Draft .fdx with revision marks.
- **Anti-hallucination at the tool layer**: filed citation excerpts must exist VERBATIM in
  material the run actually retrieved — a confabulated quote is structurally unfileable.
- The Writer's Room adds coverage (PASS/CONSIDER/RECOMMEND), a pitch package with retrieved,
  cited comparables, and a format check.

## How we built it

Google ADK on Vertex AI Gemini (Flash for desks, Pro for adjudication/coverage);
`parallel-web` for every web citation; ClickHouse Cloud for the comparables corpus (Wikidata
CC0 ratings + Wikipedia content profiles via official APIs, embedded with text-embedding-005);
FastAPI + SSE on Cloud Run — analyses execute as **Cloud Run Jobs** (deploy-immune workers)
journaling every event to Firestore, so runs survive deploys, restarts, and closed laptops,
and any instance can relay any run's live stream. The demo screenplay is an original short
film seeded with every flag category and deliberate traps for the verifier, graded by an
answer key (`make eval`).

## Challenges

Verifier calibration was the real engineering: our first verifier rejected true findings because
web excerpts can never contain script facts — the fix separates script-facts (checked against
scene text as ground truth) from the legal premise (which must come from the citation). Research
caching keyed per-entity looped the music ownership chase; per-question keys fixed it. Every
lesson is a commit.

## Accomplishments

An eval harness (`make eval`) that scores runs against the fixture's seeded ground truth —
18/18 on the shipped demo record, including both traps correctly declined and real rejections
on camera. Deployed day 3 of 16.

## External review (adversarial testing)

We put the pipeline through seven rounds of external review on real feature-length scripts
(The Social Network, The Hangover spec draft, and indie two-handers), fixing what each
round exposed and re-running to validate. Quotes from the reviews, in sequence:

- *"This is a night-and-day difference… The prompt overrides did exactly what they needed
  to do."* — after the worker architecture + doctrine overhaul
- *"Flawless deduplication… the right of publicity filter is now flawless."*
- *"This output is exactly the high-signal, low-noise data that production managers look
  for… you have transitioned this from a neat AI trick into a viable commercial product."*
- *"This corrected report looks like a legitimate, professional-grade coverage output."*

The last two "misses" reviewers reported turned out not to exist in the analyzed drafts —
verified against the actual uploaded text. The full decision log of every fix is in
`docs/DECISIONS.md`.

## What's next

Per-jurisdiction expansion (more territories and non-English screenplays, each calibrated
and eval-gated before shipping — see DECISIONS.md for the roadmap), budget-line export to
Movie Magic, draft-over-draft change tracking on stable finding IDs, and carrier
integrations for real underwriting quotes.

## Try it (judges)

- **Live**: https://scriptrisk.com — *Watch a recorded analysis* needs no credentials.
- **Repo**: https://github.com/lalitlouis/greenlight — `make install && make serve`.
- The Parallel Search integration is `research()` in `src/greenlight/tools/toolbelt.py`
  (`_live_search`), on the default path of every live run.

## Checklist before submitting

- [ ] Team members added on Devpost
- [ ] Video uploaded (max 3 min, public, English) — see docs/DEMO.md
- [ ] Repo public, LICENSE at root (done)
- [ ] Hosted URL in the form: https://scriptrisk.com
- [ ] No third-party logos/trademarks on screen in the video
