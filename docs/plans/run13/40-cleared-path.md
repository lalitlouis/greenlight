# Cleared path — suppression by text reference, work-performed phrase ban, cid strip

Files: `src/greenlight/entity_accounting.py`, `src/greenlight/pipeline.py`
(record assembly), `src/greenlight/tools/toolbelt.py` (`record_clearance`
docstring only). Items 1, 6a.

## Item 1a — extend suppression to text-referenced entities

### Current behavior
The cleared section already suppresses determinations for entities that carry
findings — rendered as "N further determinations concern entities that carry
findings — they are counted there, not here." The suppression keys on the
finding's **structured `entity_id` slot only**. F1016 names Alan Mervish,
Jimmy Lang, and Doug Billings in its *body*; their cleared rows rendered
anyway, producing the contradiction: a "negative check confirmed" row beside a
finding about the same person.

### Planned change
At record assembly (pipeline, where cleared determinations are folded using
`entity_accounting.account()`): an entity whose canonical surface appears on a
word boundary in any kept flag's finding or remedy text joins the suppressed
set, exactly as if the flag's entity slot named it. Same rendering path, same
"counted there, not here" note — the three run-13 rows collapse into F1016
with no desk-output change.

Precision guards (this is display-only, so favor precision — each one exists
because of a named false-positive it prevents):
- **Body only, never remedy.** A remedy mentioning an entity operationally
  ("negotiate with MGM management") is not a finding ABOUT them; matching
  remedies would suppress MGM's legitimate cleared row. The finding body names
  its subjects; the remedy names counterparties.
- Match the **canonical folded surface** (post-`fold`), word-boundary, case-
  insensitive — never single-token surfaces shorter than 4 chars (a "Doug"
  substring inside an unrelated word must not suppress).
- The harm being prevented is CONTRADICTION (a "no issue" row beside a finding
  about the same subject), so suppression applies only to determinations whose
  text is a no-issue/negative-check shape — a determination recording a
  different fact about the same entity stands.
- Suppression is recorded in the manifest-adjacent accounting (counts must
  still reconcile: distinct entities = shown determinations + suppressed).

## Item 1b — ban the work-performed claim shape

### Current behavior
Cleared determinations assert completed searches — "negative check confirmed",
"search confirms no real-world …" — including for entities with **no research
trace in the record**. A claimed action nothing backs; same contract violation
as a normative rule.

### Planned change
Deterministic sweep at record assembly over cleared determination text:
- Phrase class: "negative check confirmed", "confirmed no real-world",
  "search confirms no", "verified (that )?no" (list pinned in tests).
- **Receipt check — batch sweeps count.** An entity has a research receipt if
  the record carries a per-entity `research:{entity_id}:*` key **or** any
  research entry whose stored query/objective text names the entity's surface
  (word-boundary). Name-commonality sweeps are often ONE batch call covering
  twenty names with entity_id='' — without the text-match arm, every entity a
  real sweep covered would have its TRUE determination rewritten to "sweep
  recommended," destroying honest work (the Clark-County failure mode applied
  to receipts).
- With a receipt: text stands (the claim is true — do not weaken honest work).
- Without: rewrite to what the evidence supports —
  "Fictional character; name-commonality sweep recommended — see F####"
  (the flag reference comes from the same text-reference index as item 1a;
  absent any flag, "…sweep recommended" stands alone).
- Every rewrite is manifest-recorded (guard: `cleared_rephrase`).

### Why record assembly, not the desk prompt
The desk prompt cannot hold a phrasing line (runs 10–12 lesson); the record
assembly rewrite is deterministic, testable, and leaves desk behavior — and
the raw state — untouched.

## Item 6a — `(cid:NN)` strip in entity display

### Current behavior
PDF extraction artifacts like `I (cid:60) ROGER` render as entity names in the
informational rollup and table columns (4 runs running). The body text
resolves the same glyph correctly, so the raw extraction must not be touched —
display only.

### Planned change
Entity **display** normalization (the same display-only layer as
`entity_accounting`): strip `\(cid:\d+\)` from rendered entity surfaces,
collapse the double space. Raw worklists, state, and matching keep the raw
surface (matching against script text needs it).

## Regression contract
- All three changes are deterministic and display-only; before/after on the
  cached fixture record must show: identical flags, identical counts except
  the intended suppression/rewrite, headline reconciliation intact
  (distinct = shown + suppressed — the run-5 "97 vs 72" class must not
  reopen).
- Unit tests: suppression via body reference (positive + short-token negative
  control), receipt-gated rewrite (with/without receipt), cid strip (display
  vs raw).
