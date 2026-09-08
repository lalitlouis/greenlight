# Demo script — word for word, with what is on screen (3:00)

Deck first (about 1:00), then the product (about 2:00). Speak at a natural pace; the
words below run ~2:45 read aloud, which leaves room for clicks and pauses. Record in one
take if you can; the deck is `ScriptRisk-demo-deck.pptx`, the product is
https://scriptrisk.com.

## Before you press record

1. Deploy is done and the live replay serves the roll-12 record (`/run?replay=1` shows
   "SLACK TIDE · Replay · recorded run").
2. Runs are unpaused, and you are signed in as admin (Propose a fix and What-If are
   sign-in gated).
3. Browser at 1280×720 or 1440×900, dark theme, 100% zoom, bookmarks bar hidden. Tabs open
   in this order: `scriptrisk.com/run?replay=1&pace=6`, `scriptrisk.com/report?run=latest`,
   `scriptrisk.com/script?run=latest`.
4. Keep OFF camera: the language finding's body text and the first cut-list beat (they
   quote the three F-word lines), and the brand findings (Coors Light, JAWS, the newspaper
   masthead, the Springsteen photo) — they sit in the Informational fold; do not expand it.
   Rights-holder names in the music findings are fine.
5. No third-party logos anywhere on screen. The site has none; check your dock and menu bar
   are out of frame.

## PART 1 — the deck (0:00–1:00)

**[Slide 1 — title] (0:00)**
> Every screenplay hides a six-figure surprise. This is ScriptRisk: four AI clearance desks
> that read a script the way a studio does, and return a report where every finding is
> cited, independently verified, and priced.

**[Slide 2 — the bottleneck] (0:12)**
> Before a frame is shot, a studio pays four desks — rights, ratings, safety, territory — to
> read the whole script. It's mandatory for insurance, it costs thousands, it takes a week,
> and it lands as a memo after the budget locks. Independent producers mostly skip it and
> absorb the risk.

**[Slide 3 — what it produces] (0:26)**
> ScriptRisk runs those four desks concurrently as agents and hands back a Production Risk
> Report: severity-ranked findings, each with a verbatim citation, a remedy, and a cost; a
> rating prediction built from evidence; a clearance binder, a one-sheet, and fixes exported
> straight back into the screenplay.

**[Slide 4 — architecture] (0:38)**
> Under the hood it's an agent system, not a pipeline. A deterministic parser anchors every
> scene. Triage hands entities to four Google ADK loop agents on Vertex Gemini, running in
> parallel with a shared toolbelt. Parallel's Search API is the source of every citation.
> ClickHouse holds four thousand seven hundred official CARA rating rationales. A
> completeness gate refuses to advance while any entity is undispositioned. Then a blinded
> verifier re-reads every citation and can reject a finding, and a Pro-tier adjudicator
> reconciles the desks.

**[Slide 5 — enforced honesty] (0:52)**
> The rules live in the tools, not the prompts: a finding without a citation cannot be
> filed, an excerpt must exist word for word in what was retrieved, and two evaluation gates
> — fifty-two checks and forty-nine checks — are green on the deployed code.

**[Slide 6 — requirements] (1:00, hold two seconds while you switch to the browser)**
> Google Cloud and Gemini through ADK at runtime, Parallel Search on every run, a public MIT
> repository, and a live web app. Let me show you.

## PART 2 — the product (1:00–3:00)

**[Tab 1: the run page, replay already streaming] (1:04)**
Click **Show** on the desk feeds if they are hidden. Let the columns scroll for a moment.
> This is a recorded analysis of our own short screenplay, Slack Tide. Four desks are
> investigating at once — each one reads scenes, searches the live web through Parallel,
> and files findings through a tool that will refuse anything uncited. Watch the clearance
> column: it's working a song — who owns the composition, then who owns the master, then
> what a licence requires. And look at the network on the right: Parallel and ClickHouse are
> nodes in the graph, not footnotes.

Scroll down once to show the scene strip filling with pinned findings and the live agent
network, then switch tabs.

**[Tab 2: the report — top of page] (1:34)**
> The report. A risk index, the clearance cost by remedy path, and the counts by severity.
> Twenty-three findings, two rejected in verification, thirty-five entities researched —
> every number here reconciles with the findings below.

**[Scroll to the BLOCKER card; click Read more] (1:46)**
> The blocker: an unpermitted vessel burn with fireworks on open water. The safety desk
> quotes the industry's own safety bulletin, verbatim, and prices the coordinator, the
> permits, and the effects work.

**[Scroll to the Sync License card] (1:58)**
> The music. Composition and master are two rights, two owners, two findings — and the desk
> had to quote the publisher's name from a source before it could file either.

**[Click "Rating + simulator" in the nav; stop with the Floor line on screen] (2:08)**
> The rating, as evidence. This script's descriptor profile against the official rationale
> corpus; a measured boundary with a ninety-percent coverage set. And a rule you can check:
> three spoken uses of one word, counted by a regex, and the MPA's own Classification and
> Rating Rules quoted — more than one such expletive requires an R. The set keeps R.

**[Tick one cut in the What-If list — pick the drug-use cut, not the language one] (2:24)**
> Cuts are levers, not promises — tick one and the boundary re-measures.

**[Click "Rejected" in the nav; open "Show the 2 rejected draft findings"] (2:32)**
> And the part nobody else shows you: an independent verifier read every citation blind and
> threw out two findings whose sources didn't hold. They stay on the report, struck
> through, with the reason.

**[Scroll back up to any HIGH finding; click Propose a fix] (2:42)**
> Every finding can propose its own fix — a revised line you can accept and export back into
> the screenplay as Fountain or Final Draft.

**[Tab 3: the marked-up script, briefly] (2:52)**
> Every finding anchored to its scene, both ways. Cited, verified, priced — before the
> budget locks. ScriptRisk.

## Timing guide

| Segment | Target | Words |
|---|---|---|
| Deck (6 slides) | 0:00–1:02 | ~230 |
| Run page replay | 1:04–1:34 | ~90 |
| Report: hero, blocker, music | 1:34–2:08 | ~95 |
| Rating card + What-If | 2:08–2:32 | ~75 |
| Rejected + Propose a fix + script | 2:32–3:00 | ~70 |

If you run long, drop the What-If beat first, then the marked-up script beat. Never drop the
rating card or the rejected findings.
