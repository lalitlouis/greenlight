# Verification panel — coordinate completion, guard manifest, remedy scoring

File: `src/greenlight/agents/verification.py`. Items 4, 5, 2b, 6b.

## Item 4 — coordinate completion moves upstream (pre-verification)

### Current behavior
- `_stated_fact_overturn` (~line 530) is a **post-verification rescue**: it reads
  the verifier's rejection reason, anchors proper nouns to claimed numbers
  (reason first, then the finding), scans scenes for co-occurrence with a 40-char
  proximity guard, and — on a hit — widens coordinates and overturns (or, on
  mixed grounds, strikes only the false ground).
- A downstream cousin exists: `pipeline.py` (~line 484) unions prose-named
  scene ids into `scene_ids` at record assembly — but that runs **after**
  verification, so the verifier already judged against the narrow window.
- Run-10 failure: false rejection (evidence outside the window). Run-11 failure:
  silent pass (a number from S004 asserted under S084). Same root cause, two
  presentations.

### Planned change
1. **New pre-verification pass** in `_run_async_impl`, before the fan-out:
   for every filed flag, resolve each numeric + proper-noun claim in the
   finding body to a scene using the existing machinery
   (`_propers_near_numbers`, `_num_near_name` — note the upstream version
   anchors on the FINDING text directly, a cleaner input than a rejection
   reason). If a claim resolves to a scene outside the declared coordinates,
   **widen the coordinates before the verifier sees the flag.** Same precision
   guards as today: ≥2 distinctive names, number-beside-name within 40 chars,
   ambiguous above 3 matching scenes.
2. **Keep the post-verification overturn as a backstop** (rejections phrased on
   grounds the upstream pass can't parse). Expected fire rate after relocation:
   ~zero; the manifest records both stages so that expectation is checkable.
3. **New verifier rule in `VERIFIER_PROMPT`**: a claim containing a figure that
   load-bears on severity (an age triggering a work-hour cap, a count crossing
   a threshold) must resolve inside the finding's coordinates. Unresolved is
   UNSUPPORTED, not PARTIAL.
4. `pipeline.py`'s post-assembly prose-union stays as the final belt — cheap,
   deterministic, and the prose-vs-coordinates eval assertion still enforces it.

### Regression contract
- The widening pass is deterministic (pure text analysis): pinned with unit
  tests ported from the current overturn tests (`test_verifier_window.py`),
  including the wrong-ages, single-name, ubiquitous-name, and true-absence
  negative controls.
- Verdict changes on previously narrow-windowed findings are the intended
  effect, not a regression; each is manifest-recorded.
- The absence overturn (assertion 1, run-6) is untouched.

## Item 5 — guard manifest (internal sidecar)

### Current behavior
Guard fires are visible only as live-stream events; the record keeps verdict
flags (`overridden`, `ground_overturned`, `fact_reconciled`) but no queryable
trail. "Did it fire anywhere besides minor-safety?" is unanswerable from the
deliverable — run 11 shipped an unaudited softener exactly this way.

### Planned change
`record["guard_manifest"]`: one entry per guard fire, written by pipeline from
state the verification panel emits. Entry shape:

```
{guard, stage, flag_id, entity, matched, distance, coords_before, coords_after,
 verdict_before, verdict_after}
```

Guards covered: coordinate-completion widening (pre), absence overturn,
stated-fact overturn/ground-strike (post), fact-propagation re-verify/drop,
normative filing-gate rejections, marginal hard-gate demotions (item 3).
Internal only — report.js does not render it; the record JSON carries it for
the owner/reviewer diff. OVERTURNED surfaces as a distinct state in the
manifest rather than collapsing into PARTIAL.

### Regression contract
Additive record field (no schema conflict — record is not the frozen flag
schema; announce anyway per data-contract convention). Zero effect on rendered
surfaces; pinned by a unit test asserting manifest entries for a synthetic
overturn.

## Item 2b — verifier scores remedy text

### Current behavior
`_blinded_prompt` shows the verifier the claim and citations; the remedy's
`detail` travels with the flag but the prompt never directs judgment at it —
a remedy can assert anything. That is the migration path the normative language
took.

### Planned change
`VERIFIER_PROMPT` addition: the REMEDY is part of the claim. A remedy that
asserts a rule or fact the excerpts do not support caps the verdict at PARTIAL
(and is named in the reason); a remedy that only prescribes an action needs no
support. Non-deterministic layer: the mechanical check is the field-agnostic
validator (30-filing-gates.md) plus the eval assertion — the prompt is
belt-and-suspenders, not the guarantee.

## Item 6b — rejection-reason truncation

### Current behavior
Renderable rejection text passes through several `[:200]` caps (overturn
rewrite reasons, `rejected_summary` lines). F1006's rendered reason cut
mid-clause.

### Planned change
Audit every cap that feeds a **rendered** surface and raise it to carry a full
sentence (target: no cap on `rejection_reason` as stored; caps stay only on
internal prompt context like `rejected_summary`, which exists for token
budget). The one field whose job is explaining a rejection is never ellipsized
in the deliverable.

### Regression contract
Deterministic; before/after diff on the cached record shows only longer reason
strings, no structural change.
