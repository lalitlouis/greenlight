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
- The Writer's Room adds coverage (PASS/CONSIDER/RECOMMEND), a pitch package with retrieved,
  cited comparables, and a format check.

## How we built it

Google ADK on Vertex AI Gemini (Flash for desks, Pro for adjudication/coverage);
`parallel-web` for every web citation; ClickHouse Cloud for the comparables corpus (Wikidata
CC0 ratings + Wikipedia content profiles via official APIs, embedded with text-embedding-005);
FastAPI + SSE on Cloud Run. The demo screenplay is an original short film seeded with every flag
category and two deliberate traps for the verifier.

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

## What's next

More territories, FDX import, budget-line export to Movie Magic, and carrier integrations for
real underwriting quotes.

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
