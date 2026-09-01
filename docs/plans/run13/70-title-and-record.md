# Title derivation — draft metadata, never an inferred release year

Files: `src/greenlight/server.py` (upload path), `src/greenlight/pipeline.py`
(title into record). Item 6e.

## Current behavior
The report header renders "The Hangover 2009" over a 2007 spec draft, in the
web report and the PDF — while the provenance line beneath it claims
draft-specific validity (pages + SHA). The year is an inferred *release* year
attached to a *draft*; the two lines contradict each other. (Side cost: a
famous-title-plus-year string also invites contamination in research queries.)

## Root cause (located, verified)
`server.py:875-876`: the run title is the **uploaded filename**, title-cased
(`"the-hangover-2009.pdf"` → "The Hangover 2009"). There is no year inference
in code — the filename simply wins over the draft's own title page, which the
parser already extracts (`strip_title_page` returns the Fountain/PDF title
metadata) and which the pipeline ignores in favor of the filename-derived
string.

## Planned change
1. Title precedence, deterministic:
   1. the draft's own title-page metadata (already parsed by
      `strip_title_page` — Fountain `Title:` / PDF title-page first line);
   2. else the uploaded filename, cleaned (current behavior, as fallback only).
2. Pipeline/server wiring: the parse's title metadata flows back into
   `script_title` when present; the filename-derived title is used only when
   the draft has no title page.
3. Pin with tests: metadata wins over filename; filename fallback intact; the
   fixture screenplay's title unchanged (and the parser baseline untouched —
   title derivation reads existing parse output, it must not alter parsing).
4. Existing records are not rewritten (frozen artifacts); the fix applies to
   new runs.

## Regression contract
Deterministic. Tests: title-page metadata wins; filename fallback; no year
injection; the fixture screenplay's title renders unchanged (byte-identical
on the cached run's parse — title derivation must not disturb the parser
baseline).
