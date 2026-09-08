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
- The desks run concurrently as ADK LoopAgents, researching on the live web via **three
  Parallel APIs** — Search (geo-targeted for the Territory desk, registry-restricted for
  USPTO/PRO/copyright checks), Extract (full-page retrieval of repertory entries and
  regulators' rules), and the Task API (deep multi-source investigation for ownership chains
  that decide a blocker, capped 2 per desk) — and file findings through a tool that
  structurally rejects any flag without a citation.
- An independent, blinded verifier re-reads every citation and rejects unsupported claims —
  rejections appear in the report with reasons.
- The Ratings Board predicts the MPA rating from evidence, not opinion: your script's
  CARA-style descriptor profile against 4,733 released films' official rating rationales in
  ClickHouse ("7 of 8 nearest comparables are R"), a measured per-descriptor boundary (what
  CARA actually did with "pervasive language", "brief drugs"…) with a conformal coverage set
  at 90% per rating group, the MPA's own rating rules quoted where a rule applies (more than
  one spoken F-word), and the exact cut list to reach a target rating.
- A Pro-tier adjudicator merges duplicates and resolves conflicting remedies deterministically.
- **The What-If simulator**: the cut list is interactive — checking cuts re-evaluates the
  revised profile against the measured boundary first and the rationale corpus second, and it
  will honestly disagree with its own cut list when a cut does not move the rating.
- **Production artifacts**: a downloadable Clearance Binder (the standard studio clearance
  log as PDF/CSV), a one-sheet PDF poster, and accepted fixes exported as a revised
  .fountain or Final Draft .fdx with revision marks.
- **Anti-hallucination at the tool layer**: filed citation excerpts must exist VERBATIM in
  material the run actually retrieved — a confabulated quote is structurally unfileable.
- The Writer's Room adds coverage (PASS/CONSIDER/RECOMMEND), a pitch package with retrieved,
  cited comparables, and a format check.

## How we built it

Google ADK on Vertex AI Gemini (Flash for desks and verifiers, Pro for adjudication and
coverage); `parallel-web` for every web citation (Search, Extract, Task); ClickHouse Cloud for
the ratings evidence (official CARA rating rationales embedded with text-embedding-005, plus a
Wikidata/Wikipedia content-profile corpus for pitch comparables); local reference assets for
the MPA rating rules, the CSATF bulletin index, and BBFC cuts records;
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

Two eval gates that score every run against seeded ground truth AND a shared set of report
invariants (a finding may not cite a scene it does not cover, a cleared row may not cite a
rejected finding, a rating claim may not state a rule the MPA text does not, counts and costs
must reconcile…): 52 checks on the demo screenplay, 49 on a 100-scene stress fixture, both
green on the deployed code; 405 unit tests. Deployed on day 3 of 16 and continuously since.
A full-codebase review on 2026-09-01 found 44 accuracy and consistency defects; all were fixed
at their class, each pinned by a test and a gate roll, across twelve gate rolls in two days —
the decision log records every one, including the two rolls that went red on our own bugs.

## Third-party data sources (disclosure)

- **Official CARA rating rationales** (4,733 films) from the MPA's filmratings.com listings,
  collected once at a polite rate with a source URL per row; the descriptor boundary and the
  coverage set are our own statistics over them. Rating reasons are facts and short phrases;
  MPA and CARA are trademarks of the Motion Picture Association, used nominatively — no
  affiliation or endorsement.
- **MPA Classification and Rating Rules** (published PDF, effective July 24, 2020): the five
  rating provisions quoted verbatim so the desks can cite a rule from the official text.
- **Wikidata (CC0) + Wikipedia (official API)** content profiles for 6,302 released films,
  used for pitch comparables.
- **CSATF safety-bulletin index** (csatf.org), **BBFC classification records** (bbfc.co.uk),
  **USPTO TSDR** (live). Full provenance and legal basis: `docs/DATA_SOURCES.md`.

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
- The Parallel integration is `research()` / `fetch_page()` / `deep_research()` in
  `src/greenlight/tools/toolbelt.py` (`_live_search`, `_live_extract`, `_live_task` —
  Search, Extract, and Task APIs), on the default path of every live run.

## Checklist before submitting

- [ ] Team members added on Devpost
- [ ] Video uploaded (max 3 min, public, English) — see docs/DEMO.md; no brands, logos, or
      profanity on screen (the fixture's language finding quotes the lines — keep it off camera)
- [ ] **Repo flipped PUBLIC** (private since 2026-08-28), LICENSE at root (MIT, detected)
- [ ] **Runs UNPAUSED** (`/api/admin/pause`) so a signed-in judge can analyze a screenplay
- [ ] Hosted URL in the form: https://scriptrisk.com
- [ ] Track set to Parallel; text description pasted from this file
