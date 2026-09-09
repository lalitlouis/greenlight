# Devpost submission copy

Paste-ready text for the Devpost form. Facts checked against `docs/RULES-CHECKLIST.md`,
`docs/DATA_SOURCES.md`, and the deployed demo record (`run_20260902_demo`) on 2026-09-08.

## Elevator pitch

Four AI clearance desks read your screenplay the way a studio does, and return a report where every finding is cited, independently verified, and priced.

## About the project

Copy everything below this line into the "About the project" field.

---

## Inspiration

Script clearance is mandatory if you want E&O insurance, and almost nobody does it early.
A clearance attorney costs $1–3k, takes about a week, and delivers a memo after the budget
is already locked. Independent producers mostly skip it and eat the risk. We kept coming
back to the same question: a clearance department is really four specialists reading the
same script and arguing about it later. That's an agent system. So we built the department.

## What it does

Upload a screenplay. Four desks — rights, ratings, physical safety, territory censors —
read it concurrently, research the outside world live, and file findings. A flag without a
citation is structurally impossible: the filing tool rejects it. Every flag then goes to a
blinded verifier that only sees the claim and its evidence, not the desk's reasoning, and
rejections stay visible in the report with reasons. The Ratings Board treats the rating as
evidence, not opinion: your nearest neighbours among 4,733 official CARA rating rationales
("4 of your 8 closest comparables are rated R"), a measured descriptor boundary with a 90%
coverage set, and the MPA's own rule quoted when one applies (more than one spoken F-word
means R), with a cut list you can test in the What-If simulator. Everything lands in a
marked-up script plus a risk report where each finding has a remedy and a price. Any
finding can propose its own fix; accept it and the revised script exports to Fountain or
Final Draft with revision marks.

## How we built it

Google ADK end to end: a SequentialAgent pipeline whose middle is a ParallelAgent fanning
out four LoopAgents, Gemini Flash on the desks, Pro reserved for the adjudicator. Parallel
Search API is the desks' only window to the web — music ownership chains, insurer rules,
censorship law — grouped per run with session ids. ClickHouse Cloud holds the comparison
sets: 4,733 official CARA rationales for the rating instrument, and 6,302 Wikidata/Wikipedia
content profiles for the First Look comparables. FastAPI and SSE on Cloud Run stream the
whole run live, scene by scene. The demo screenplay is an original short we wrote ourselves,
seeded with known traps and an answer key, so the eval gate grades the pipeline against
ground truth: 52/52 on the fixture, 49/49 on a 100-scene stress script, 405 unit tests.

## Challenges we ran into

Our first architecture was a tidy pipeline: extract entities, one search each, four prompts,
merge. We killed it on day two. It couldn't chase an ownership chain (song → composition
owner → master owner) or decide when to stop digging. The desks had to become agents with
budgets, not scripts.

The verifier was the hardest part. Early on it kept rejecting our best flags — it would
claim a lyric "wasn't in the script" because we'd silently truncated the scene we handed it.
The fix was philosophical as much as technical: scene text is ground truth, truncation must
be visible, and a verifier judges the premise, not the prose.

Then consistency. The same script scored 37, 63, and 46 on three runs. We diffed the runs:
category names drifted, severities flipped, duplicates inflated counts, and the verifier saw
different evidence each time. Fixed with fixed category vocabularies, severity anchors,
temperature 0, deterministic dedupe, and a durable research cache.

The ratings corpus took three tries. The first failed outright — 1% extraction yield, plus a
regex that happily matched "PG" inside "PG-13". The second, Wikipedia content profiles,
worked for topical similarity but wasn't the rating board's own evidence. The third is the
official CARA rationales themselves, which is what the instrument runs on now.

## Accomplishments that we're proud of

A report that cannot contain an uncited finding, a verifier that can and does reject the
desks' own work in public, and a rating call backed by the MPA's own rationales and rules
rather than a model's opinion. Live at scriptrisk.com since August 24, with six public case
studies on real screenplays.

## What we learned

Never let the model assert what you can retrieve. Gemini does judgment; Parallel does the
world; ClickHouse does the comparisons. Every reliability problem we hit traced back to
violating that rule somewhere.

## What's next

A deep-scan tier that runs the panel three times and reconciles, PDF reports for insurers,
and partnerships on the E&O side — the report is already shaped like what underwriters ask
for.
