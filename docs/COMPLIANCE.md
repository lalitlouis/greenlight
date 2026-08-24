# Contest compliance

Every rule from the Official Rules that we can fail, and its current status.
**Deadline: 2026-09-09, 2:00 PM PT.** Treat Sept 8 as the real one.

Legend: `DONE` verified · `PENDING` not yet built · `ONGOING` enforced continuously

## Stage One — pass/fail gates

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Public code repository | DONE | github.com/lalitlouis/greenlight |
| 2 | OSS license detectable in the About panel | DONE | `gh repo view --json licenseInfo` -> MIT |
| 3 | Google Cloud imported **and called** at runtime | DONE | `google-adk`, `google-genai`; live Gemini call in `greenlight.checks` |
| 4 | Partner product called at runtime | DONE | `parallel-web`, `client.search(...)`; live call returning 10 sourced results |
| 5 | Only Google Cloud AI tooling; no other AI vendor | ONGOING | `scripts/check_forbidden_deps.sh`, wired as a PostToolUse hook |
| 6 | Partner track selected | DONE | **Parallel** |
| 7 | Project runs on web / Android / iOS | PENDING | Cloud Run web app |
| 8 | Hosted project URL | PENDING | after deploy |
| 9 | Demo video ≤3 min, public on YouTube/Vimeo, English | PENDING | |
| 10 | Devpost submission form complete | PENDING | |
| 11 | Text description: features, tech, data sources, learnings | PENDING | draft from `docs/PRD.md` + `docs/STACK.md` |
| 12 | Repo contains all source, assets, and run instructions | ONGOING | `README.md` + `docs/SETUP.md` |
| 13 | New project, created within the contest period | DONE | repo initialized 2026-08-23; contest opened 2026-07-27 |
| 14 | Team ≤ 4, all members added on Devpost | ACTION NEEDED | 2 people — **add teammate to the Devpost project** |

## The rule most likely to disqualify us

> *"Projects may only use Google Cloud artificial intelligence tools... No other AI models, agent
> frameworks, or AI APIs are permitted, regardless of vendor — this includes but is not limited to
> AWS, Microsoft, OpenAI, and Anthropic AI tools."*

One stray dependency is fatal, so this is enforced mechanically rather than by discipline.
`scripts/check_forbidden_deps.sh` scans dependency manifests and shipped source on every file
write and exits non-zero on any of: `anthropic`, `openai`, `langchain`, `langgraph`, `llama-index`,
`crewai`, `autogen`, `litellm`, `cohere`, `mistralai`, `ollama`, `replicate`, `huggingface_hub`,
`azure-ai`, `bedrock-runtime`. Negative-tested: writing `import openai` into `src/` blocks.

**Development tooling is a separate question from the Project.** The rule governs what the Project
uses at runtime; the IBM and Replit tracks *require* an AI coding agent during development, which
confirms the distinction. Regardless, nothing in the shipped repo calls a non-Google model, and
the README states the runtime AI stack unambiguously for automated screening.

## Video constraints

- ≤3 minutes; only the first 3 minutes are evaluated.
- Must show the project **actually functioning** — a demo, not a cinematic trailer.
- Public on YouTube or Vimeo. English or English subtitles.
- **Must not display any third-party advertising, slogan, logo, or trademark.**
- Must be original, unpublished work containing no third-party-owned content.

Consequence for a project *about* trademarks: lead the demo with **music and likeness clearance**
rather than brand flags. Same analytical point, nothing branded on screen. Brand findings stay in
the report as text.

## Assets

- **The demo screenplay is original work written for this project.** Never use a real, leaked, or
  third-party screenplay — it would breach both the originality warranty and the IP warranty.
- **MPA rating rationales** used in the ClickHouse corpus are short factual statements published
  by CARA. Record provenance in `docs/DATA_SOURCES.md` and cite the source in the app. If any
  source's terms prohibit reuse, drop it — the corpus works fine at a few hundred rows.
- Cost estimates are industry rules-of-thumb, **labelled as estimates in the UI**, not quotes.
- The product states it is not legal advice.

## Licensing consequence

Submitting licenses the non-proprietary aspects of the code under an OSI-approved license that
does not restrict commercial use. MIT satisfies this. Everything in the repo is intended to be
public — keep credentials in `.env` only, which is gitignored and verified untracked.

## Pre-submission checklist

Run at day 7 and again at day 16:

```bash
make check                          # lint + forbidden-dependency scan
python -m greenlight.checks all     # all gates green
gh repo view --json licenseInfo     # MIT still detected
git ls-files | grep -i env          # only .env.example
```

Then confirm by hand: hosted URL loads for a logged-out visitor, video is public and under 3:00,
every Devpost field filled, teammate added, track set to **Parallel**.
