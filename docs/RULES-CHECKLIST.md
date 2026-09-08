# Official Rules checklist — Agentic Cinema (Devpost), audited 2026-09-07

Every requirement in the Official Rules and the hackathon overview, one row each, with the
evidence in this repository or the deployment. Deadline **September 9, 2026, 2:00 PM PT**.
Track: **Parallel**. Legend: `DONE` verified with evidence · `ACTION` a switch to flip before
submitting · `PENDING` work not yet produced · `OWNER` only the entrant can do it · `N/A`.

## A. Eligibility and team

| # | Rule | Status | Evidence / owner |
|---|---|---|---|
| A1 | Entrants above age of majority; not in an excluded country; not on OFAC/Denied lists | OWNER | entrant attestation on the Devpost form |
| A2 | Not employees/contractors of Google, Partner Entities, Devpost | OWNER | entrant attestation |
| A3 | Team of at most 4; every member added as a project member on Devpost; one Representative | OWNER · **ACTION** | 2 people — the teammate must be added on Devpost before the deadline |
| A4 | Employer consent in writing if entering as an employee/contractor | OWNER | if applicable |

## B. The project

| # | Rule | Status | Evidence |
|---|---|---|---|
| B1 | Newly created during the Contest Period (2026-07-27 09:00 PT → 2026-09-09 14:00 PT); original, not an extension of existing work | DONE | first commit `779aba1` dated 2026-08-23; full history on `main` |
| B2 | A functional, production-ready AI agent or multi-agent network | DONE | `src/greenlight/pipeline.py`: SequentialAgent → Triage → ParallelAgent of four LoopAgent desks → CompletenessGate → verification fan-out → Adjudicator → deterministic report; live at scriptrisk.com since 2026-08-24; 405 unit tests; two eval gates green (52/52 fixture, 49/49 100-scene) |
| B3 | Solves a bottleneck in the entertainment/media value chain for filmmakers, screenwriters, crews | DONE | screenplay clearance and production-risk analysis (rights, ratings, safety, territory) — `README.md`, `docs/PRD.md` |
| B4 | Integrates a Partner Entity product | DONE | Parallel — see D |
| B5 | Runs on web, Android, or iOS | DONE | web app on Cloud Run (`src/greenlight/server.py`, `web/static/*`) |
| B6 | One Partner track chosen | DONE | Parallel (`docs/SUBMISSION.md`) |

## C. Required technology — Google Cloud and Gemini

| # | Rule | Status | Evidence |
|---|---|---|---|
| C1 | Built using Google Cloud | DONE | Cloud Run service + Cloud Run Job worker, Firestore, GCS, Secret Manager, Vertex AI — `docs/TECH_SPEC.md` "Scaling architecture"; `scripts/safe_deploy.sh` |
| C2 | Gemini models on the Agent Platform (Vertex AI) | DONE | `src/greenlight/models.py` (`gemini-3.7-flash`, `gemini-2.5-pro`); `llmclient.py:25` `vertexai=True`; Cloud Run env `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_LOCATION=global`; embeddings `text-embedding-005` (`toolbelt.py:3116`) |
| C3 | Only accepted packages: google-adk, google-genai, google-generativeai, google-cloud-aiplatform | DONE | `requirements.txt`: `google-adk>=2.8.0`, `google-genai>=2.20.0`, `google-cloud-aiplatform[agent-engines]` — imported and called (`agents/common.py:9-10`, `pipeline.py:34-35`, `verification.py:1121`) |
| C4 | No other AI models, agent frameworks, or AI APIs, any vendor | DONE · ONGOING | `scripts/check_forbidden_deps.sh` scans manifests and shipped source on every `make check` and inside every deploy (exit 0 today); `requirements.txt` carries no other model/agent SDK; ClickHouse is a plain database, permitted; Claude Code is a development tool, not in the shipped path |
| C5 | Google Cloud use is imported and actually called at runtime, not just named | DONE | every desk turn is a Vertex Gemini call through ADK (`agents/common.py:44-48`); verifiers call `genai.Client(vertexai=True)` (`verification.py:1121`) |

## D. Partner track — Parallel

| # | Rule | Status | Evidence |
|---|---|---|---|
| D1 | Actively use Parallel's Search API at runtime via the `parallel-web` SDK | DONE | `requirements.txt` `parallel-web>=1.3.1`; `toolbelt.py:500-508` `import parallel` → `client.search(...)` inside `research()` on the default path of every run; also Extract (`:743-746`) and Task API (`:838-845`) |
| D2 | Partner use demonstrated in code, not the README | DONE | above; every citation in every report is a Parallel result registered as provenance (`_register_results`) — the product's citation invariant depends on it |
| D3 | Live call is the default path, never mocked by default | DONE | the only offline material is one recorded cassette under `fixtures/cassettes/` used by unit tests; no env flag disables the live call (`grep os.getenv toolbelt.py`) |

## E. Submission materials

| # | Rule | Status | Evidence / action |
|---|---|---|---|
| E1 | Code repository URL (GitHub/GitLab/Bitbucket), **public and open source** | **ACTION** | https://github.com/lalitlouis/greenlight — PRIVATE since 2026-08-28 (`gh repo view`); flip to public before submitting. Hygiene verified 09-07: no tracked secrets (`git ls-files` shows only `.env.example`), no third-party screenplay tracked, `.cache/` and `runs/*` ignored, case records ship stripped of script text |
| E2 | Open-source license file detectable at the top of the repository page | DONE | `LICENSE` (MIT) at root; `gh repo view --json licenseInfo` → MIT |
| E3 | Repo includes all source, assets, and running instructions | DONE | `src/`, `web/static`, `schemas/`, `src/greenlight/data/*.json` (boundary, MPA rules, CSATF index, BBFC cuts), `fixtures/` (original screenplays), `Dockerfile`, `Makefile`, `.env.example`, `README.md` "Run it", `docs/SETUP.md` |
| E4 | Hosted project URL, publicly accessible and functional for judging and testing | **ACTION** | https://scriptrisk.com is up (200 on every page). Replays, case studies, and reports need no sign-in. Running an analysis requires Google sign-in (permitted — judges have Google accounts) but **new analyses are PAUSED by the operator kill switch set 2026-09-01** (`/api/admin/pause`, stored flag `admin:runs_paused`) → a judge's upload returns 503. Unpause before submitting. The invite gate (`REQUIRE_INVITE`) is off in production |
| E5 | Text description: features and functionality, technologies, third-party data sources, findings and learnings | DONE (draft) | `docs/SUBMISSION.md` rewritten 2026-09-07 — includes the third-party data disclosure; paste into the form |
| E6 | Demo video ≤ 3 minutes, on YouTube or Vimeo, public, English or English subtitles, shows the project functioning | PENDING | not recorded; plan in `docs/DEMO.md` |
| E7 | Video content: no derogatory/profane/sexual content; no third-party advertising, logos, trademarks, or sponsorships; original and unpublished; no third-party IP | PENDING (constraint) | the fixture report quotes the three F-word lines (language finding, cut list) and names Coors Light, Jaws, Springsteen, Nighthawks — keep those frames off camera; lead with music and likeness (`docs/DEMO.md`) |
| E8 | Partner track selected on the form | OWNER | Parallel |
| E9 | Form completed before 2:00 PM PT September 9; late = disqualified | OWNER | plan to submit by the morning of the 9th |

## F. Third-party integrations, data, and IP

| # | Rule | Status | Evidence |
|---|---|---|---|
| F1 | Authorized to use any third-party SDKs, APIs, data; comply with licensing | DISCLOSED | `docs/DATA_SOURCES.md` (corrected 2026-09-07). Parallel and Google under their terms; USPTO TSDR is an official public API; Wikidata CC0 + Wikipedia via the official API; CSATF index and BBFC records are public regulator/industry documents. **The 4,733-row CARA rationale corpus (report comparables, base rates) and the 4,544-rationale descriptor asset (marginals, coverage set) were collected once from the MPA's filmratings.com listings** at one request per 0.7 s with an identified user agent; robots.txt permits crawling; the site's terms restrict automated access and license content for internal non-commercial use — a contract exposure we disclose rather than conceal. Rating reasons are facts and short phrases outside copyright. The MPA rules PDF is quoted for reference with attribution. Production path: a licensed feed from the MPA |
| F2 | License the non-proprietary aspects and source under an OSI-approved license that does not limit commercial use | DONE | MIT |
| F3 | Submission is original work; no infringement of third-party IP, publicity, privacy | DONE | demo screenplays are original works written for this project (`fixtures/SEEDS.md`); case-study records never ship the real scripts' text (`scripts/case_study.py`); no third-party logos in product or video |
| F4 | Video license to Google for evaluation and promotion | OWNER | accepted by submitting |
| F5 | Cost figures labelled as estimates; product states it is not legal advice | DONE | report copy and site footer ("Cost figures are rule-of-thumb estimates, not quotes. ScriptRisk is a research tool, not legal advice.") |

## G. Judging alignment (Stage Two, equal weights)

| Criterion | Where the case is made |
|---|---|
| Technological Implementation — how well built, how effectively Google Cloud and the Partner are used | four concurrent ADK desks with a shared toolbelt; Parallel Search/Extract/Task as the source of every citation; blinded verification fan-out; Cloud Run Jobs + Firestore journal; two eval gates and 405 tests; `docs/TECH_SPEC.md`, `docs/DECISIONS.md` |
| Design — a complete, coherent product, not a proof of concept | report, marked-up script, clearance binder (page/CSV/PDF), one-sheet, What-If simulator, Writer's Room, case studies, methodology page with measured numbers |
| Potential Impact — a credible, specific case for a real audience | independent producers and production counsel; clearance today is manual, $1–3k, a week, after the budget locks; `docs/PRD.md`, `docs/MARKET.md` |
| Quality of the Idea — creative, non-obvious use; genuine understanding of the problem | a clearance department as an agent system with mechanical honesty: citation invariant, blinded verifier, measured rating boundary with a coverage guarantee, the MPA's own rules as a tool, every learning in the decision log |

## H. Pre-submission run (morning of September 9)

```bash
make check                                  # lint + forbidden-dependency scan
.venv/bin/pytest -q                         # 405 tests
python -m greenlight.checks all             # live gates: Vertex, Parallel, ClickHouse
gh repo view --json visibility,licenseInfo  # PUBLIC + MIT
git ls-files | grep -i env                  # only .env.example
curl -s https://scriptrisk.com/api/metrics-lite
```

Then by hand: unpause runs and confirm a signed-in upload starts; the hosted URL loads for a
logged-out visitor; the video is public and under 3:00; every Devpost field filled; teammate
added; track set to Parallel.

## Open actions, in order

1. Flip the repository public (`gh repo edit --visibility public`).
2. Unpause new analyses (`POST /api/admin/pause {"paused": false}` as the admin) and test one
   signed-in upload end to end.
3. Record and publish the 3-minute video per `docs/DEMO.md`, keeping profanity and brand names off
   camera.
4. Add the teammate on Devpost; paste `docs/SUBMISSION.md`; select the Parallel track; submit.
