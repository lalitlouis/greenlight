# Run 17 — main-report comparables move to rationale-space

Owner-approved 2026-09-01 ("yeah i'm okay with it"), following the What-If
Swearnet-neighbors diagnosis. Pre-registered before implementation, per the
anti-oscillation policy (run13/00-MASTER).

## The change

`query_precedent` switches corpus: `rating_rationales` (Wikipedia lead+plot
"content profiles", the documented 2026-08 pivot) → `cara_rationales` (4,733
official filmratings.com rationale strings, embedded in rationale-space by
`scripts/ingest_cara_corpus.py`). Coupled changes that MUST land together —
a table swap alone would recreate the cross-domain mismatch the What-If had:

1. Tool spec (docstring): the query text becomes a CARA-style descriptor
   profile (the rationale the desk would file), NOT the genre capsule. The
   genre capsule exists because the old corpus was plot text.
2. Ratings desk step 2b rewritten to match: derive intensities from the
   measured census, query with descriptor phrasing.
3. Base rates (`_corpus_base_rates`) computed over the same table the
   comparables come from.
4. Citation semantics flip: the profile line returned per film IS the
   official CARA wording now — cite verbatim as such (before, it was a
   Wikipedia lead sentence and the spec forbade presenting it as CARA's).
5. Report copy: corpus described as films with official CARA rationales;
   no stale "6,302" in comparables/base-rate lines.
6. NEW eval assertion (fail-visible): every comparable's rationale excerpt
   must carry its own rating token ("Rated R for ..." on an R row). The
   pre-switch fixture record FAILS this (leads, not rationales) — the check
   bites; post-switch it must pass.

## Predictions (registered before the gate run)

- P1 (positive): fixture gate run still predicts R; comparables' excerpts
  are official "Rated R for ..." strings; new eval assertion passes.
- P2 (positive): comparable distances shrink vs the old corpus (short
  same-language strings), and the distance spread stays meaningful.
- P3 (negative control): a pervasive-language+violence query stays R-heavy;
  the boundary conformal set for the fixture's descriptors must contain the
  kNN vote (instruments agree or the divergence is stated).
- P4 (predicted casualty): comparables lose GENRE affinity — neighbors are
  rating-profile matches, possibly tonally unlike the script. Accepted
  trade: rating-relevant similarity over topical similarity. The desk
  instruction stops promising genre neighbors.
- P5 (predicted casualty): films without an official rationale (~1,569,
  mostly pre-1990/limited) can no longer appear as comparables.
- P6 (predicted casualty): base-rate percentages shift (denominator 4,733).
- P7: frozen case-study records keep old-corpus comparables until
  regenerated; that is record-consistency, not a defect.

## Rollback

Single-commit revert; old table untouched; What-If (already rationale-space)
unaffected either way.
