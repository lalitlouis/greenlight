# Demo plan

> **Recording script (final, 2026-09-07): `docs/DEMO-SCRIPT.md`** — word-for-word lines with the
> on-screen cue for each, the pre-record setup, and the frames to keep off camera. This file is
> the older runbook and stays for the moment-by-moment rationale.


The 3-minute video is not a judging criterion. It is the **medium through which all four criteria
get judged**, so it carries more weight than its absence from the rubric suggests. Budget two full
days.

## Hard rules (Official Rules)

- Max 3 minutes. Only the first 3 minutes are evaluated.
- Must show the project **actually functioning** — a demo, not a cinematic trailer.
- Public on YouTube or Vimeo. English or English subtitles.
- **No third-party advertising, slogan, logo, or trademark on screen.**
- Original, unpublished work, no third-party-owned content.

Consequence for a product about trademark clearance: **lead with music and likeness, not brands.**
Brand findings stay in the report as text. Nothing branded appears on screen.

## The single biggest risk

The hackathon is called *Agentic Cinema*. Judges are primed for creative magic — trailers,
storyboards, generated shots. We are bringing a legal-ops tool: more useful, less fun.

That is a **taste** risk, not a merit risk, and it is fixed entirely in presentation. Open on a
screenplay page and a verdict that says *"this script cannot be shot as written."* Do not open on
a dashboard. Architecture goes at 2:35, once they already care.

## The four moments that decide it

In priority order. If anything gets cut, cut from the bottom.

**1. The money, on a script page.** Real screenplay, real stakes, a number. Filmmaking, not
enterprise software.

**2. One ownership chase, end to end.** A song resolves to a composition owner, then a master
owner, then an administrator — three deepening Parallel searches on screen. *Parallel judges their
own track*, and this is the story they would want to show off. Make it legible; do not bury it.

**3. The ClickHouse comparables beat.** *"Seven of your eight nearest released films are R. You are
targeting PG-13. Here are the three beats to cut."* Most defensible thirty seconds in the demo —
evidence, not opinion.

**4. A rejected flag, on camera.** The verifier throws out a finding whose source did not support
it. This turns "every claim is checked" from a promise into something the judge watched happen.
Nobody else will do this, and it reads as real engineering judgment.

## Runbook against the shipped product (2026-09-07)

Record from **replay**, never live: `/run?replay=1` streams the committed demo record
`runs/run_20260902_demo.json` (gate roll 12, 52/52 on the fixture eval, 23 findings, 2
rejections) with realistic pacing; `?pace=` scales speed. `/report?run=latest`, `/script`,
`/binder`, and `/onesheet` render the same record. The record must be **deployed** before
recording — the replay serves what is in the image.

- 0:00 open on the LANDING — 3 seconds, then Enter. It states the problem faster than narration.
- The money-on-a-page beat: /script?run=latest — the funeral scene with the sync-license flag
  in the gutter. Then /report?run=latest: open the stunt_pyro **BLOCKER** (the unpermitted
  vessel burn — CSATF #16 quoted) and the sync-license HIGH: verbatim citation, remedy, cost.
- The ownership chase: during replay, the Clearance column's research() calls stream by —
  composition (Sony Music Publishing), then the Columbia master, then the licence requirement —
  and the licensor gate on camera: the desk is refused until the owner's name is in an excerpt.
- The rating beat (replaces "7 of 8"): the Rating prediction card — desk R vs PG-13 target;
  coverage set {PG-13, R}; the **Floor** line: the MPA's own Classification and Rating Rules,
  "more than one such expletive requires an R rating", three spoken uses counted by the census;
  the language finding cites the provision verbatim beside its measured marginal. Evidence AND
  the rule, both quoted, neither an opinion.
- The rejected flag: "Rejected in verification — 2" — government_insignia and stunt_water, each
  with the verifier's reason; the withdrawn notices sit apart from the honest unknowns.
- Bonus if time allows: the What-If — tick a cut, watch the boundary re-evaluate.

## Frames that must stay OFF camera (Official Rules: no profanity, no third-party trademarks)

- The language finding F2001's text and the first cut-list beat quote the three F-word lines.
  Show the rating card and the Floor line; do not scroll into F2001's body or the cut list's
  first beat. The census row in Reviewed & cleared also names the word.
- Brand findings: Coors Light (trademark_disparagement), JAWS (film_clip_license), the
  Gloucester Daily Times masthead, the Springsteen photo. Keep them below the fold.
- Rights-holder names in music findings (Sony, Columbia) are informational text in a clearance
  report, not advertising — acceptable, but do not linger on them.

## Beat sheet

| Time | Beat |
|---|---|
| 0:00–0:20 | The problem, as a number. $1–3k, 7 days, mandatory for E&O, nobody has automated it |
| 0:20–0:35 | Drop the screenplay in |
| 0:35–1:20 | The four desks run concurrently. Tool calls streaming. **The ownership chase** |
| 1:20–2:10 | The report. Greenlight Score, open a BLOCKER, click through to the real citation, show the remedy and cost. **The rejected flag** |
| 2:10–2:35 | **The rating.** Coverage set with the MPA rule quoted, the measured marginal, the beats to cut |
| 2:35–3:00 | Architecture — ADK loop agents, Parallel, ClickHouse — then close |

## Production notes

- Always have a **pre-computed run in `runs/`** shipped as `run_*_demo.json` (the only run files the image keeps). Never demo live against the network.
- Show the desks finishing at **different times after different numbers of turns**. That asymmetry
  is the visual proof of autonomy; a progress bar proves nothing.
- Both of the above require a **replay harness**: the UI must replay a recorded run with realistic
  streaming and timing. A cached JSON alone does neither. Small feature, real feature — scope it
  in Phase 3, not day 14.
- The rejected flag (moment 4) is **harvested, not scripted** — the fixture screenplay seeds a
  verifier trap, and the run committed to `runs/` is selected for containing a real rejection.
- The fixture screenplay is **our own original work**. Never a real or leaked script.
- Label cost figures as estimates on screen, as the product does.
