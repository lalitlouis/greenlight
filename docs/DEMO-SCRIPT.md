# Demo script — 3:00, spoken by Lalit, with what is on screen for every line

Team **Four Desks** — Lalit Somavarapha and Shruthi Kashyap. Deck: `ScriptRisk-demo-deck.pptx`
(7 slides, ~1:15). Product: https://scriptrisk.com (~1:40). About 450 spoken words: 2:45 at a
natural pace, leaving ~15 s for clicks. Rehearse once against a timer; if you run long, cut the
lines listed at the end, in order. Devpost evaluates only the first 3:00.

Every claim below was checked against the deployed record (`run_20260902_demo`, live on
scriptrisk.com) and the Official Rules on 2026-09-07.

## Before you press record (10 minutes)

1. **Sign in** to scriptrisk.com with the admin Google account. *Propose a fix* and *Accept* need
   a session; the runs pause switch does not affect them.
2. **Three tabs, in this order**, dark theme, 100% zoom, bookmarks bar hidden, dock off screen,
   window at least 1440 px wide:
   - Tab 1 `scriptrisk.com/run?replay=1` — **reload it on slide 7**, right before you switch, so
     the desks are visibly starting when you arrive (the replay runs ~90 s and restarts on load).
   - Tab 2 `scriptrisk.com/report?run=latest` — **pre-draft the fix**: scroll to the *Master Use
     License* card (third card), click **Propose a fix**, wait ~20 s for the three-patch diff.
     Do **not** click *Accept this fix* yet — that is the live click on camera.
   - Tab 3 `scriptrisk.com/script?run=latest`.
3. **Keep off camera** — none of these are on the path below, but know where they are:
   - the *Rating Language* card (last of the nine HIGH cards) — quotes the three F-word lines;
   - the **cut list** under the comparables in the Rating section — quotes the same lines. Do not
     scroll below the eight comparable films, and do not touch the What-If checkbox;
   - the **Informational fold line** just above the *Rejected* header (names Coors Light, JAWS,
     Springsteen, Nighthawks) — after clicking *Rejected* in the nav, scroll down one notch.
   - The music cards name the song, the writer, the performer and the two rights holders. That is
     the finding doing its job — a rights report names rights holders — and it is not advertising,
     a logo, or an endorsement, which is what the Rules prohibit. Keep it. (Zero-exposure fallback:
     do the music beat over the *Estimated clearance exposure* table, which shows the two licences
     and their prices without names, and run *Propose a fix* on the *Firearms Blanks* card instead.)
4. Deck in full-screen presenter view; switch to the browser on the cue.

---

## Deck — 0:00 to 1:15

### 0:00 · Slide 1 — Team
> Hi, I'm Lalit Somavarapha. With Shruthi Kashyap, we're Team Four Desks, and this is ScriptRisk,
> for the Parallel track.

### 0:08 · Slide 2 — Title
> Every screenplay hides a six-figure surprise. A song that costs seventy-five thousand dollars to
> clear. A scene China won't screen. A stunt no insurer will touch.

### 0:18 · Slide 3 — The bottleneck (four stat cards)
> Studios pay four desks to read the whole script: rights, ratings, safety, territory. It's
> mandatory for insurance, it takes a week, and the memo lands after the budget locks. Independents
> mostly skip it.

### 0:31 · Slide 4 — What it produces (desks, report, artifacts)
> So we built the clearance department as an agent system. Four desks read your script at once and
> return a report where every finding is cited, verified independently, and priced. Plus the
> binder, the one-sheet, and fixes that go back into the script.

### 0:46 · Slide 5 — Architecture (point left to right)
> It's agents, not a pipeline. Four Google ADK loop agents on Vertex Gemini run in parallel with a
> shared toolbelt. Parallel Search is where every citation comes from. ClickHouse holds
> forty-seven hundred official rating rationales. A blinded verifier can throw any finding out; a
> Gemini Pro adjudicator reconciles the desks.

### 1:03 · Slide 6 — Enforced in tools (don't read the cards)
> The rules live in the tools, not the prompts. No citation, no finding. Two evaluation gates,
> both green.

### 1:09 · Slide 7 — Requirements (two seconds, then switch to Tab 1)
> Google Cloud and Gemini at runtime. Parallel on every run. Public MIT repo, live web app. Let me
> show you.

---

## Product — 1:15 to 2:58

### 1:15 · Tab 1 — Run page, replay streaming
**Show:** the four desk columns filling. Click **Show** on the feeds if they're collapsed. After
the first sentence, scroll once so the scene strip and the agent network are in frame.
> This is a recorded analysis of our own short film, Slack Tide. Four desks working at once: read
> a scene, search, file, move on. Every search runs through Parallel, and a citation has
> to exist word for word in something the run actually retrieved.

### 1:35 · Tab 2 — Report, top
**Show:** the hero — score ring, "Not cleared — 1 blocker", the counts, the cost.
> The report. Not cleared, one blocker. Twenty-three findings, two rejected in verification, and
> a six-figure clearance cost ranked by driver.

### 1:45 · The blocker
**Show:** scroll to the first card, *Stunt Pyro*. The PARTIAL badge and the CSATF bulletin
citation are visible without expanding.
> The blocker: an unpermitted boat burn with fireworks on open water. The safety desk quotes the
> industry's own safety bulletin, verbatim, and prices the fix. Even here, the verifier's caveat
> stays on the card.

### 1:57 · The music, and the fix
**Show:** scroll to *Sync License* and *Master Use License* (cards two and three). The
pre-drafted diff is open on the Master Use card. On "Accept it", click **Accept this fix** — the
export bar appears at the bottom: "1 fix accepted — revised script with revision marks", Fountain
and Final Draft.
> The music. Composition and master: two rights, two owners, two findings. The desk couldn't file
> either until it had quoted the publisher's name from a source. We asked it to propose a fix. It
> swapped the track for a fictional song, across both scenes. Accept it, and the revised script
> exports to Fountain or Final Draft.

### 2:20 · The rating
**Show:** click **Rating + simulator** in the nav. Stop there: coverage set PG-13/R, the desk's
call, the target, the rationale line, the descriptors, the Floor line. Do not scroll past the
comparables.
> The rating, as evidence. This profile against the official corpus, a measured boundary, a
> ninety-percent coverage set. And a rule you can check: three spoken F-words, counted by a regex,
> and the MPA's own rule quoted. More than one means R.

### 2:37 · The rejections
**Show:** click **Rejected** in the nav, scroll down one notch, click **Show the 2 rejected draft
findings**. Scroll to the bottom of the first card — the line "Rejected in verification — The
cited statute (14 U.S.C. § 933) … 'vessel or aircraft' … pickup truck".
> The part nobody else shows you. The verifier threw out two findings. This one cited a Coast
> Guard statute about vessels against a pickup truck. Wrong standard, out, and the reason stays
> on the record.

### 2:50 · Tab 3 — The marked-up script, and close
**Show:** the script page, findings in the gutter.
> Cited, verified, priced, before the budget locks. Thanks. I'm Lalit, and this is ScriptRisk.

---

## If you run long, cut in this order

1. Slide 6 entirely (6 s) — slide 5 already made the point.
2. "Even here, the verifier's caveat stays on the card." (3 s)
3. "The desk couldn't file either until it had quoted the publisher's name from a source." (5 s)
4. The Tab 3 close — end on the rejections with "…and the reason stays on the record. Thanks."

Never cut the rating beat or the rejections: they are the two things no other entry will show.

## Timing budget

| Block | Window | Words |
|---|---|---|
| Slides 1–3 | 0:00–0:31 | ~85 |
| Slides 4–7 | 0:31–1:15 | ~125 |
| Run page | 1:15–1:35 | ~50 |
| Report: hero, blocker, music + fix | 1:35–2:20 | ~120 |
| Rating, rejections, close | 2:20–2:58 | ~90 |
