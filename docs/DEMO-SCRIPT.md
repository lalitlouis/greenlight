# Demo script — 3:00, spoken by Lalit, with what is on screen for every line

Team **Four Desks** — Lalit Somavarapha and Shruthi Kashyap. Deck: `ScriptRisk-demo-deck.pptx`
(7 slides, ~1:15). Product: https://scriptrisk.com (~1:45). Read at a natural pace; the words
run about 2:50 aloud, which leaves room for clicks. It is written to sound like you talking,
not a voiceover — contractions, short sentences, one idea at a time.

## Before you press record

- Signed in to scriptrisk.com as admin (Propose a fix and What-If are sign-in gated; the pause
  switch does not affect them).
- Three tabs open, in order: `scriptrisk.com/run?replay=1&pace=6` · `scriptrisk.com/report?run=latest`
  · `scriptrisk.com/script?run=latest`. Dark theme, 100% zoom, bookmarks bar hidden, dock out of frame.
- Keep OFF camera: the body of the "Rating Language" finding and the first cut-list beat (both
  quote the three F-word lines), and the Informational fold (Coors Light, JAWS, the newspaper,
  the Springsteen photo). Music findings naming Sony or Columbia are fine.
- Deck in presenter view or full screen; switch to the browser on the cue.

---

## 0:00 — Slide 1 · Team

**Show:** the team slide.

> Hi, I'm Lalit Somavarapha. With Shruthi Kashyap, we're Team Four Desks, and we built
> ScriptRisk for the Parallel track.

## 0:09 — Slide 2 · Title

**Show:** "Every screenplay hides a six-figure surprise."

> Here's the problem we went after. Every screenplay hides a six-figure surprise — a song that
> costs seventy-five thousand dollars to clear, a scene China won't screen, a stunt no insurer
> will touch.

## 0:21 — Slide 3 · The bottleneck

**Show:** the four stat cards.

> Before a frame is shot, a studio pays four desks to read the whole script — rights, ratings,
> safety, territory. It's mandatory for insurance, it takes about a week, and the memo lands
> after the budget is locked. Independent producers mostly just skip it.

## 0:35 — Slide 4 · What it produces

**Show:** the four desks, the report card, the five artifacts.

> So we asked what a clearance department looks like as an agent system. ScriptRisk runs those
> four desks at the same time and hands back a report where every finding is cited, checked by
> an independent verifier, and priced — plus the clearance binder, a one-sheet, and fixes you
> can push straight back into the script.

## 0:50 — Slide 5 · Architecture

**Show:** the agent graph; point left to right as you speak.

> Under the hood it's an agent system, not a pipeline. A deterministic parser anchors every
> scene. Four Google ADK loop agents on Vertex Gemini run in parallel with a shared toolbelt.
> Parallel's Search API is where every citation comes from. ClickHouse holds forty-seven
> hundred official CARA rating rationales. A completeness gate won't let the run move on until
> every entity has an answer. Then a blinded verifier re-reads every citation and can throw a
> finding out, and a Pro-tier adjudicator reconciles the desks.

## 1:08 — Slide 6 · Enforced in tools

**Show:** the five cards; don't read them.

> The important part: the rules live in the tools, not the prompts. No citation, no finding.
> And two evaluation gates keep it honest — both green on what's deployed today.

## 1:16 — Slide 7 · Requirements

**Show:** the requirements table for two seconds, then switch to the browser.

> Google Cloud and Gemini at runtime, Parallel on every run, a public MIT repo, a live web app.
> Let me show you.

---

## 1:22 — Tab 1 · The run page (recorded replay)

**Show:** the replay streaming. Click **Show** on the desk feeds if they're hidden. Let it run.

> This is a recorded analysis of our own short film, Slack Tide. Four desks are working at
> once. Watch the clearance column — it's chasing a song: who owns the composition, then who
> owns the master, then what a licence actually requires. Every one of those searches goes
> through Parallel, and every result gets registered — so a citation has to exist word for word
> in something the run really retrieved. If a desk names an owner it can't quote, the tool
> refuses it.

**Show:** scroll down once to the scene strip and the live agent network.

> And there's the network. Parallel and ClickHouse are nodes in the graph, not footnotes.

## 1:50 — Tab 2 · The report, top

**Show:** the hero: score ring, "Not cleared — 1 blocker", counts, cost.

> The report. A risk index, the clearance cost by remedy path, and the counts. Twenty-three
> findings, two rejected in verification — and every number up here reconciles with the
> findings below.

## 2:00 — The blocker

**Show:** scroll to the first card, Stunt Pyro; click **Read more**; the CSATF citation.

> The blocker: an unpermitted boat burn with fireworks on open water. The safety desk quotes
> the industry's own safety bulletin, verbatim, and prices the coordinator, the permits, and
> the effects work.

## 2:10 — The music

**Show:** scroll to the Sync License card.

> The music. Composition and master are two rights, two owners, two findings. And the desk
> couldn't file either one until it had quoted the publisher's name from a source.

## 2:19 — The rating

**Show:** click **Rating + simulator** in the nav; stop with the coverage set and the Floor line on screen.

> The rating, as evidence. This script's profile against the official rationale corpus, a
> measured boundary, a ninety-percent coverage set. And a rule you can check: three spoken
> F-words, counted by a regex, and the MPA's own rule quoted — more than one requires an R.
> So the set keeps R.

**Show:** tick the drug-use cut in the What-If list (not the language one).

> Cuts are levers, not promises — tick one and it re-measures.

## 2:38 — The rejections

**Show:** click **Rejected** in the nav; open "Show the 2 rejected draft findings".

> And here's the part nobody else shows you. The verifier threw out two findings whose sources
> didn't hold. They stay on the report, struck through, with the reason.

## 2:47 — Propose a fix

**Show:** scroll up to any HIGH finding; click **Propose a fix**; let the draft appear.

> Any finding can propose its own fix — a revised line you accept and export back into the
> screenplay as Fountain or Final Draft.

## 2:54 — Tab 3 · The marked-up script, then close

**Show:** the script page with findings in the gutter.

> Cited, verified, priced — before the budget locks. Thanks — I'm Lalit, this is ScriptRisk.

---

## If you run long

Drop the What-If line first (saves 5 s), then the network line on the run page (5 s), then the
marked-up script beat (6 s). Never drop the rating card or the rejections.

## Timing

| Block | Window | Words |
|---|---|---|
| Team + title + bottleneck | 0:00–0:35 | ~80 |
| Product, architecture, tools, requirements | 0:35–1:22 | ~150 |
| Run page | 1:22–1:50 | ~85 |
| Report: hero, blocker, music, rating, What-If | 1:50–2:38 | ~135 |
| Rejections, fix, close | 2:38–3:00 | ~55 |
