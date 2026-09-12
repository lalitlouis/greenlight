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

## Results at b49ce03

Both desks completed their assigned worklist, but **neither case passes manual
accuracy review**. This is a two-case diagnostic, not an accuracy percentage.

| Case | Desk model calls | Parallel calls | Desk time | Verification | Manual outcome |
| --- | ---: | ---: | ---: | --- | --- |
| JAWS clip | 5 | 1 search | 29.81s | 3 calls, 29.57s; rejected | Unresolved ownership, unhelpful failed correction |
| Vessel fire/skiff | 11 | 2 searches + 2 extracts | 53.69s | 4 calls, 82.03s; accepted automatically | False approval: widened pyrotechnic condition |

All 23 model responses returned usage. Captured Gemini estimates total **$0.1602**;
Parallel usage is three search and two extract units, excluded from that number.
These are targeted call timings and token estimates, not full-run performance or
invoice reconciliation. No timeout, retry of a negative judgement, full run or
deployment followed.

Clearance filed a named Universal licensor, SAG-AFTRA obligations, a $5,000–$15,000
price and an absolute fair-use claim without operative support for those assertions.
It recorded no ownership question. Independent repair removed price/talent assertions
but retained the missing JAWS-to-licensor link; the subsequent auditor rejected it.
The initial auditor also wrongly accepted that ownership link. No unsupported corrected
clearance finding was accepted by the complete verification path.

Safety retrieved operative CSATF text and recorded a relevant production-method/casting
question. Its original filing nevertheless prescribed named authorities, marine/stunt
staff, rescue craft, equipment, $25,000–$75,000 and two days without supporting those
specifics. Repair removed most unsupported details and withheld numeric estimates.
However, the accepted remedy says **'If practical pyrotechnics or open flames are
utilized'** before prescribing a licensed pyrotechnic operator. The supplied receipt
only addresses pyrotechnic special effects. Script fireworks support one branch, not
the additional open-flame branch; the remedy also loses the explicit 'as applicable'
license qualification. Both automated auditors accepted that combined clause. This
is an observed false approval, not a successful safety repair or a production-ready
recommendation. Raw automated results remain unchanged for auditability.

Saved desk, retrieval and independent-review traces are the `fresh_clearance*` and
`fresh_safety*` cassettes dated 20260911. A separate hash-bound manual-review artifact
records the rejected manual outcomes. Six new `production_scope_20260911.json` probes
pin this exact false approval alongside two supported controls and other scope/duty
expansions. Offline checks validate evidence identity and exact receipts; these six
semantic labels have **not** been tested live and are developer-authored.

## Changes made after observing the failures

- Removed contradictory clearance instructions to name a best ownership lead in the
  finding and supply a rule-of-thumb cost. Missing links belong explicitly in open
  questions; generic supported requirements can remain useful.
- Replaced the blanket mention/use exemption rule with a requirement to research the
  actual use. Removed automatic permission conclusions from that research checklist
  and unsupported music-budget price bands.
- Removed the safety prompt's prescribed specialist/permit checklist. Its examples now
  explain the difference between a general rule and a specific duty or authority,
  and require conditions in both finding and remedy.
- Updated the shared filing tool's estimate instructions: a stated sourced basis is
  required; absent evidence means omitted/-1 amounts and days, never an invented range
  or zero. This is an instruction change, **not** a new deterministic estimate validator.

Public schemas, parser, runtime models and production budgets are unchanged. These
prompt/tool-description changes are not yet live validated. Numeric estimates that
appear only in structured fields remain an audit gap worth addressing separately.
Next priority is independently checking each applicability branch so a supported
pyrotechnic branch cannot conceal an unsupported alternative, using the saved false
approval and contrastive probes before another fresh desk run. The prior 45/54 full
release gate remains a failure.
