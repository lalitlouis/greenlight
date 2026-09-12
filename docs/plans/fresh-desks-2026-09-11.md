# Fresh desk diagnostics — September 11, 2026

Latest full release gate: failed 45/54, `runs/run_20260911_015915.json`.
Recent isolated verifier improvements do not show whether fresh desk findings are
useful. This batch evaluates the revised desks with their real tools.

## Preregistered scope and limits

Two isolated cases, full unchanged original SLACK TIDE script and identical parsed
coordinates. Hand-assigned worklists bypass triage explicitly; this does not measure
triage recall, desk interaction, whole-script coverage or repeatability.

- Clearance: the E004 JAWS television clip in S002. Keep a cited use-specific issue
  visible, give a useful supported remedy, and keep any missing work-to-licensor link
  explicit. No inferred named licensor, rights guaranteed by royalty-free/PD labels,
  or irrelevant casting question. A well-supported generic rule and content edit can
  be useful even while ownership is an open question.
- Safety: the vessel fire/fireworks and child in the adjacent night skiff in S009–S011.
  Keep the stacked hazard visible. Source each production prescription; preserve
  uncertainty about casting, jurisdiction and practical/effects method. No assumed
  child performer, unsupported permits/PFDs/teachers, invented costs or BLOCKER based
  on plot danger. Prefer a useful supported conditional remedy over an irrelevant rule.

Use existing desk factory, Gemini model, prompts and shared tools. Clearance uses its
first real batch configuration; safety uses its normal desk configuration. Per case:
12 ADK model calls, 4 live Parallel search/extract calls including failures, 360-second
deadline. No deep Task API. Session caching remains; durable GCS cache is disabled only
inside this explicit diagnostic to test fresh retrieval without modifying shared data.
No production runtime defaults change. SDK transport retries may still add billed work.
Save every model event, returned usage, raw Parallel response, failure and disposition.
Completion is labelled `completed_unreviewed`, never an accuracy PASS.

Free suite first, commit the harness, then one attempt per case. No timeout retries.
Manual review all filings, including filing-gate refusals and open questions. If one
candidate per case warrants review, independently verify it with the existing harness
(up to five Gemini calls each, 240-second deadline, maximum ten total). Preserve negative
and unavailable outcomes. Targeted diagnostics only; no full gate or deployment in this
batch. Expected diagnostic spend is small relative to a full run; captured-token estimates
are not invoices and interrupted calls can lack returned usage.
