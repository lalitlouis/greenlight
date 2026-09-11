# Contrastive accuracy cases

Sixteen original miniature screenplays in eight pairs. No copyrighted screenplay
text or song lyrics are included. Expected outcomes are engineering review criteria,
**not independent professional labels**. Do not report these as a held-out expert benchmark.

The cases cover fictional permits, recounted/depicted falls and gunshots, character
age, nonspoken/spoken profanity, voiceover/visible text, drug references/use, and
song mention/playback. The pairs specify findings to preserve, false findings to
avoid, and uncertainties a reviewer must inspect. They deliberately do not prescribe
an exact final MPA rating.

Run the free parser/channel/count checks:

```bash
.venv/bin/python scripts/eval_accuracy_cases.py
```

An offline PASS means the deterministic inventory matches expectations. It says
nothing about model judgement, citation quality, or professional agreement.

Export an individual case for a separately budgeted live analysis:

```bash
.venv/bin/python scripts/eval_accuracy_cases.py --case permit_dialogue_missing --export /tmp/permit-case.fountain
# This next command spends money; it is not part of the unit suite:
.venv/bin/python -m greenlight.cli run /tmp/permit-case.fountain
.venv/bin/python scripts/eval_accuracy_cases.py --case permit_dialogue_missing --record runs/run_TIMESTAMP.json
```

Saved-run grading verifies the script hash, expected/forbidden finding categories,
verification, citations, absence of safety blockers inferred from screenplay-only
input, and dialogue counts. It also prints the semantic review checklist. These
mechanical checks cannot establish that a source entails a claim or that a judgement
is correct. A failed run is never counted as a clean negative example.

Before using this set to claim accuracy: have clearance/safety/ratings professionals
review the expectations, record disagreements, expand permissioned examples, and
reserve unseen cases. In particular, severity, staging method, classification and
the necessity of a finding require expert adjudication.

Evidence used to frame the engineering expectations:

- The [CSATF bulletin index](https://www.csatf.org/production-affairs-safety/safety-bulletins/)
  and its bulletins distinguish practical production activities and recommended
  safeguards. Applicability requires the real work environment and method.
- The [MPA submission FAQ](https://www.filmratings.com/submit-a-film/) says even liaison
  guidance does not guarantee a target rating; the board screens the film.
- The repository's dated July 24, 2020 MPA rules asset preserves the special-vote
  exception. The [MPA rating-system booklet](https://www.filmratings.com/Content/downloads/cara_about_voluntary_movie_rating.pdf)
  also states it. The live site's “Rating Rules” link currently resolves to an
  advertising handbook; that document must not be substituted for classification rules.
- The [WIPO filmmaker clearance guide](https://www.wipo.int/web-publications/rights-clearance-a-guide-for-independent-filmmakers/en/2-rights-clearance-from-idea-to-distribution.html)
  explains evaluating circumstances of use and required rights. The music pair specifies
  actual playback rather than assuming it from a spoken title.
