# Demo plan

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

## Runbook against the shipped product (2026-08-24)

Everything below is recordable today from https://scriptrisk.com (or `make serve` locally —
same bits). Record from **replay**, never live: /run?replay=1 streams the committed 18/18 demo
record with realistic pacing. `?pace=` scales speed if a beat needs tightening.

- 0:00 open on the LANDING (black, "Every screenplay hides a six-figure surprise") — 3 seconds,
  then Enter. It states the problem faster than narration can.
- The money-on-a-page beat: /script?run=latest — the funeral scene with the sync-license flag
  in the gutter. Then /report?run=latest, open F101: verbatim citation, remedy, $10–50k.
- The ownership chase: during replay, the Clearance column's research() calls stream by —
  composition owner, then master, then the license requirement.
- The comparables beat: the Rating prediction card — R vs PG-13 target, 7 of 8 comparables R,
  the cut list naming exact scenes ("keep Danny's in S011").
- The rejected flag: report's "Rejected in verification" section — struck through, with the
  verifier's reason. Also visible live in the replay's pipeline log.
- Bonus if time allows (it likely won't — protect the four moments): 5 seconds of the Writer's
  Room example (/writer?run=latest) to show breadth: coverage verdict + retrieved comps.

## Beat sheet

| Time | Beat |
|---|---|
| 0:00–0:20 | The problem, as a number. $1–3k, 7 days, mandatory for E&O, nobody has automated it |
| 0:20–0:35 | Drop the screenplay in |
| 0:35–1:20 | The four desks run concurrently. Tool calls streaming. **The ownership chase** |
| 1:20–2:10 | The report. Greenlight Score, open a BLOCKER, click through to the real citation, show the remedy and cost. **The rejected flag** |
| 2:10–2:35 | **The comparables.** Rating prediction with evidence and the beats to cut |
| 2:35–3:00 | Architecture — ADK loop agents, Parallel, ClickHouse — then close |

## Production notes

- Always have a **pre-computed run in `runs/`**. Never demo live against the network.
- Show the desks finishing at **different times after different numbers of turns**. That asymmetry
  is the visual proof of autonomy; a progress bar proves nothing.
- Both of the above require a **replay harness**: the UI must replay a recorded run with realistic
  streaming and timing. A cached JSON alone does neither. Small feature, real feature — scope it
  in Phase 3, not day 14.
- The rejected flag (moment 4) is **harvested, not scripted** — the fixture screenplay seeds a
  verifier trap, and the run committed to `runs/` is selected for containing a real rejection.
- The fixture screenplay is **our own original work**. Never a real or leaked script.
- Label cost figures as estimates on screen, as the product does.
