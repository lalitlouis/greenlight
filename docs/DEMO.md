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
- The fixture screenplay is **our own original work**. Never a real or leaked script.
- Label cost figures as estimates on screen, as the product does.
