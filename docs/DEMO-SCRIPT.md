# Demo script — 3:00, spoken by Lalit, with what is on screen for every line

Team **Four Desks** — Lalit Somavarapha and Shruthi Kashyap. Deck: `ScriptRisk-demo-deck.pptx`
(8 slides: seven up front, ~1:08, and slide 8 as the end card). Product: https://scriptrisk.com
(~1:45). About 556 spoken words, written the way you'd say them out loud — full sentences,
contractions, no taglines. The narration is continuous: every scroll and tab change has a line that
covers it, so there is no dead air and no filler. At a normal presenting pace (165–175 words a
minute) it runs 2:55–3:05, so rehearse and use the cut list if you need it. Rehearse once against a timer; if you're over, the cuts are at the end. Devpost evaluates only the first 3:00.

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

## Deck — 0:00 to 1:15

### 0:00 · Slide 1 — Team
> Hi, I'm Lalit Somavarapha. Shruthi Kashyap and I are Team Four Desks, and this is ScriptRisk,
> our entry for the Parallel track.

### 0:08 · Slide 2 — Title
> Here's the problem. Every screenplay hides a six-figure surprise: a song that costs seventy-five
> thousand dollars to clear, a scene China won't screen, a stunt no insurer will touch.

### 0:19 · Slide 3 — The bottleneck (four stat cards)
> Studios catch those by paying four desks to read the whole script: rights, ratings, safety,
> territory. It's mandatory for insurance, it takes about a week, and the memo lands after the
> budget's locked.

### 0:31 · Slide 4 — What it produces (desks, report, artifacts)
> So we asked what that department looks like as an agent system. ScriptRisk runs all four desks
> at once, and what comes back is a report where every finding is cited, independently verified,
> and priced.

### 0:43 · Slide 5 — Architecture (point left to right)
> Under the hood, it's agents, not a pipeline. Four Google ADK loop agents run in parallel on
> Vertex Gemini. Every citation comes from Parallel's Search API, and ClickHouse holds forty-seven
> hundred official rating rationales for the ratings desk.

### 1:01 · Slide 6 — Enforced in tools (don't read the cards)
> The rules live in the tools, not the prompts: if a desk can't cite it, it can't file it.

### 1:08 · Slide 7 — Requirements (two seconds, then switch to Tab 1)
> This is a recorded run of our own short film, Slack Tide. Each column is a desk, all working at
> once: read a scene, search, file a finding, move on. Every search goes through Parallel, and a
> citation only counts if it exists word for word in what the run pulled back.

---

## Product — 1:15 to 2:58

### 1:15 · Tab 1 — Run page, replay streaming
**Show:** the four desk columns filling. Click **Show** on the feeds if they're collapsed. Scroll
once, slowly, during the last sentence so the scene strip and the agent network pass through frame.
> This is a recorded run of our own short film, Slack Tide. Each column is a desk, all working at
> once: read a scene, search, file a finding, move on. Every search goes through Parallel, and a
> citation only counts if it exists word for word in what the run pulled back.

### 1:35 · Tab 2 — Report, top
**Show:** switch tabs on "Every run ends up in this report." The hero: score ring, "Not cleared —
1 blocker", the counts, the cost. Point at the section nav under the hero on "one long page".
> Every run ends up in this report. It's one long page: the verdict up top, then the cost, the
> rating, the findings by severity, the rejections, and what got cleared. This one's not cleared,
> there's a blocker. Twenty-three findings, two rejected, and a six-figure clearance cost.

### 1:52 · The blocker
**Show:** scroll to the first card, *Stunt Pyro*, while saying "Every finding reads the same
way". The PARTIAL badge and the CSATF bulletin citation are visible without expanding.
> Every finding reads the same way: scene, severity, desk, the claim, the citations, and a remedy
> with a price. The blocker is an unpermitted boat burn with fireworks on open water; the safety
> desk quotes the industry's own safety bulletin, word for word, and prices the fix.

### 2:07 · The music, and the fix
**Show:** scroll to *Sync License* and *Master Use License* (cards two and three) on "Next is the
music." The pre-drafted diff is open on the Master Use card. On "I'll accept it", click **Accept
this fix** — the export bar appears at the bottom: "1 fix accepted — revised script with revision
marks", Fountain and Final Draft.
> Next is the music. A composition and a master recording, two owners, so two findings, and the
> desk couldn't file either until it had quoted the publisher's name from a source. Any finding
> can propose its own fix. This one swapped the track for a fictional song in both scenes. I'll
> accept it, and the revised script exports to Fountain or Final Draft.

### 2:27 · The rating
**Show:** click **Rating + simulator** in the nav on "Now the rating". Stop there: coverage set
PG-13/R, the desk's call, the target, the rationale line, the descriptors, the Floor line, the
top of the comparables. Do not scroll past the comparables.
> Now the rating, and we treat this as evidence, not opinion. A measured boundary, a
> ninety-percent coverage set, and a rule you can check yourself: three spoken F-words, counted by
> a regex, and the MPA's own rule quoted. More than one means R.

### 2:42 · The rejections
**Show:** click **Rejected** in the nav on "And this is the part", scroll down one notch, click
**Show the 2 rejected draft findings**. Scroll to the bottom of the first card — the line
"Rejected in verification — The cited statute (14 U.S.C. § 933) … 'vessel or aircraft' … pickup
truck".
> And this is the part nobody else shows you. The verifier threw out two draft findings, and they
> stay on the report, struck through, with the reason. This one cited a Coast Guard statute about
> vessels against a pickup truck. Wrong standard, so it's out.

### 2:52 · Slide 8 — Try it yourself (end card)
**Show:** switch back to the deck, slide 8: the workflow on the left, the references on the right.
Hold it through the last word so a judge can pause on the links.
> All of this is live. Sign in at scriptrisk.com, or use the judge link in our submission, upload
> a screenplay, and the four desks will run it for you. Thanks for watching.

---

## If you run long, cut in this order

1. Slide 6's line (5 s) — let the slide sit for two seconds instead.
2. "And the desk wasn't allowed to file either one until it had quoted the publisher's name from
   a source." (5 s)
3. "It's one long page: the verdict up top, then the cost, the rating, the findings ranked by
   severity, whatever the verifier rejected, and what got cleared." (8 s) — only if desperate;
   it's the line that makes the page make sense.

Never cut the rating beat or the rejections: they are the two things no other entry will show.

## Timing budget

| Block | Window | Words |
|---|---|---|
| Slides 1–3 | 0:00–0:31 | ~85 |
| Slides 4–7 | 0:31–1:15 | ~125 |
| Run page | 1:15–1:35 | ~55 |
| Report: layout, hero, blocker | 1:35–2:07 | ~100 |
| Music + fix, rating | 2:07–2:42 | ~110 |
| Rejections, slide 8 close | 2:42–3:00 | ~70 |
