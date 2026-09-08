# Demo script — 3:00, spoken by Lalit, with what is on screen for every line

Team **Four Desks** — Lalit Somavarapha and Shruthi Kashyap. Deck: `ScriptRisk-demo-deck.pptx`
(8 slides: seven up front, ~1:08, and slide 8 as the end card). Product: https://scriptrisk.com
(~1:45). About 480 spoken words, plus three **optional lines in ⟨brackets⟩** (~30 words). The
narration is continuous — every scroll and tab change has a line that covers it, so there is no
dead air and no filler. Rehearse once against a timer: with the bracketed lines you land near
3:00 at a relaxed pace; without them, near 2:50. Devpost evaluates only the first 3:00.

Every claim below was checked against the deployed record (`run_20260902_demo`, live on
scriptrisk.com) and the Official Rules on 2026-09-07.

## Before you press record (10 minutes)

1. **Sign in** to scriptrisk.com with the admin Google account. *Propose a fix* and *Accept* need
   a session; the runs pause switch does not affect them.
2. **Two tabs, in this order**, dark theme, 100% zoom, bookmarks bar hidden, dock off screen,
   window at least 1440 px wide:
   - Tab 1 `scriptrisk.com/run?replay=1` — **reload it on slide 7**, right before you switch, so
     the desks are visibly starting when you arrive (the replay runs ~90 s and restarts on load).
   - Tab 2 `scriptrisk.com/report?run=latest` — **pre-draft the fix**: scroll to the *Master Use
     License* card (third card), click **Propose a fix**, wait ~20 s for the three-patch diff.
     Do **not** click *Accept this fix* yet — that is the live click on camera. Scroll back to
     the top.
3. **Keep off camera** — none of these are on the path below, but know where they are:
   - the *Rating Language* card (last of the nine HIGH cards) — quotes the three F-word lines;
   - the **cut list** under the comparables in the Rating section — quotes the same lines. Do not
     scroll below the comparable films, and do not touch the What-If checkbox;
   - the **Informational fold line** just above the *Rejected* header (names Coors Light, JAWS,
     Springsteen, Nighthawks) — after clicking *Rejected* in the nav, scroll down one notch.
   - The music cards name the song, the writer, the performer and the two rights holders. That is
     the finding doing its job — a rights report names rights holders — and it is not advertising,
     a logo, or an endorsement, which is what the Rules prohibit. Keep it. (Zero-exposure fallback:
     do the music beat over the *Estimated clearance exposure* table, which shows the two licences
     and their prices without names, and run *Propose a fix* on the *Firearms Blanks* card instead.)
4. Deck in full-screen presenter view; switch to the browser on the slide-7 cue, and back to the
   deck (slide 8) for the closing line.

---

## Deck — 0:00 to 1:08

### 0:00 · Slide 1 — Team
> Hi, I'm Lalit Somavarapha. With Shruthi Kashyap, we're Team Four Desks, and this is ScriptRisk,
> for the Parallel track.

### 0:07 · Slide 2 — Title
> Every screenplay hides a six-figure surprise. A song that costs seventy-five thousand dollars to
> clear. A scene China won't screen. A stunt no insurer will touch.

### 0:17 · Slide 3 — The bottleneck (four stat cards)
> Studios pay four desks to read the whole script: rights, ratings, safety, territory. It's
> mandatory for insurance, it takes a week, and the memo lands after the budget locks.

### 0:28 · Slide 4 — What it produces (desks, report, artifacts)
> So we built the clearance department as an agent system. Four desks read your script at once and
> return a report where every finding is cited, verified independently, and priced — plus the
> fixes, which go back into the script.

### 0:42 · Slide 5 — Architecture (point left to right)
> It's agents, not a pipeline. Four Google ADK loop agents on Vertex Gemini run in parallel.
> Parallel Search is where every citation comes from. ClickHouse holds forty-seven hundred
> official rating rationales. A blinded verifier can throw any finding out; a Gemini Pro
> adjudicator reconciles the desks.

### 0:59 · Slide 6 — Enforced in tools (don't read the cards; optional line, or just let it sit for two seconds)
> ⟨The rules live in the tools, not the prompts. No citation, no finding.⟩

### 1:04 · Slide 7 — Requirements (two seconds, then switch to Tab 1)
> Google Cloud and Gemini at runtime, Parallel on every run. Let me show you.

---

## Product — 1:08 to 2:58

### 1:08 · Tab 1 — Run page, replay streaming
**Show:** the four desk columns filling. Click **Show** on the feeds if they're collapsed. On
"Below the feeds", scroll once so the scene strip and the agent network are in frame.
> A recorded run of our own short film, Slack Tide. Each column is a desk, and they work at the
> same time: read a scene, search, file a finding, move on. Every search runs through Parallel,
> and a citation has to exist word for word in something the run actually retrieved. ⟨Below, the
> scene strip and the agent graph.⟩

### 1:30 · Tab 2 — Report, top
**Show:** switch tabs on "Every run ends in this report." The hero: score ring, "Not cleared —
1 blocker", the counts, the cost. Point at the section nav under the hero on "one long page".
> Every run ends in this report, one long page: the verdict, the cost, the rating, the findings
> by severity, the rejections, and what was cleared. This one is not cleared, one blocker. Twenty-three findings, two rejected, and a six-figure
> clearance cost, ranked by driver.

### 1:47 · The blocker
**Show:** scroll to the first card, *Stunt Pyro*, while saying "Findings read the same way…".
The PARTIAL badge and the CSATF bulletin citation are visible without expanding.
> Every finding reads the same way: scene, severity, desk, claim, citations, and a remedy with a
> cost. The blocker is an unpermitted boat burn with fireworks on
> open water. The safety desk quotes the industry's own safety bulletin, verbatim, and prices the
> fix. ⟨Even the verifier's caveat stays on the card.⟩

### 2:02 · The music, and the fix
**Show:** scroll to *Sync License* and *Master Use License* (cards two and three) on "Next, the
music." The pre-drafted diff is open on the Master Use card. On "Accept it", click **Accept this
fix** — the export bar appears at the bottom: "1 fix accepted — revised script with revision
marks", Fountain and Final Draft.
> Next, the music. Composition and master: two rights, two owners, two findings. The desk
> couldn't file either until it had quoted the publisher's name from a source. Any finding can
> propose its own fix; this one swapped the track for a fictional song, across both scenes.
> Accept it, and the revised script exports to Fountain or Final Draft.

### 2:22 · The rating
**Show:** click **Rating + simulator** in the nav on "Now the rating". Stop there: coverage set
PG-13/R, the desk's call, the target, the rationale line, the descriptors, the Floor line, the
top of the comparables. Do not scroll past the comparables.
> Now the rating, as evidence, not opinion. A measured boundary, a ninety-percent
> coverage set, and the nearest films with their official rationales. And a rule you can check:
> three spoken F-words, counted by a regex, and the MPA's own rule quoted. More than one means R.

### 2:38 · The rejections
**Show:** click **Rejected** in the nav on "And the part nobody else shows you", scroll down one
notch, click **Show the 2 rejected draft findings**. Scroll to the bottom of the first card —
the line "Rejected in verification — The cited statute (14 U.S.C. § 933) … 'vessel or aircraft'
… pickup truck".
> And the part nobody else shows you. The verifier threw out two draft findings, and they stay on
> the report, struck through, with the reason. This one cited a Coast Guard statute about vessels
> against a pickup truck. Wrong standard, so it's out.

### 2:50 · Slide 8 — Try it yourself (end card)
**Show:** switch back to the deck, slide 8: the workflow on the left, the references on the right.
Hold it through the last word so a judge can pause on the links.
> It's all live. Sign in at scriptrisk.com, or use the judge link in our submission, upload a
> screenplay, and the four desks run it. Thanks. I'm Lalit, and this is ScriptRisk.

---

## If you run long

First drop the three ⟨bracketed⟩ lines: slide 6, the scene-strip line on the run page (skip that
scroll too), and the caveat line on the blocker. Then, if still over:

1. "The desk couldn't file either until it had quoted the publisher's name from a source." (5 s)
2. "and the nearest films with their official rationales" in the rating beat (3 s)

Never cut the rating beat or the rejections: they are the two things no other entry will show.

## Timing budget

| Block | Window | Words |
|---|---|---|
| Slides 1–3 | 0:00–0:28 | ~75 |
| Slides 4–7 | 0:28–1:08 | ~90 (+12) |
| Run page | 1:08–1:30 | ~55 (+8) |
| Report: layout, hero, blocker | 1:30–2:02 | ~85 (+8) |
| Music + fix, rating | 2:02–2:38 | ~105 |
| Rejections, slide 8 close | 2:38–3:00 | ~70 |
