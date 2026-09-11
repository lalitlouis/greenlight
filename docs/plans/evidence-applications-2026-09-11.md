# Evidence applications and useful remedies — September 11, 2026

The support-span full gate (`runs/run_20260911_015915.json`, build `51d7e82`)
failed 45/54 checks: all nine clearance findings were lost, and five of the six
kept findings carried the same production-input question. Stricter source matching
prevented unsupported assertions but also rejected script-specific applications and
derived edits. It did not produce a useful enough report.

## This batch

- Internal `ClaimCheck` adds optional `script_spans` and the bases `application` and
  `script_edit`. Public flag/report schemas and the runtime model are unchanged.
- Script receipts must be exact substrings of the scene context already supplied to
  the first independent auditor. Applications/edits require both script receipts and
  source receipts. The second reviewer sees only those scene receipts, source context
  and the claim, never the first auditor's reasoning or severity. Script evidence
  cannot establish ownership, permits, actual performer age or shooting method.
- A content edit may address a cited trigger without the source literally prescribing
  an edit or naming the screenplay. It cannot invent production duties, assert an
  owner or promise a final rating/clearance. All source duties remain strictly cited.
- Inquiries may request missing facts/decisions relevant to the desk. Nonstandard
  inquiries receive independent semantic review even without citations; relabelling
  a hiring obligation as a question is not a bypass. The old fixed production inquiry
  is mechanically refused on ratings, clearance and territory findings. The primary
  auditor must also preserve useful supported remedies instead of unnecessary questions.
- The secondary reviewer receives the remedy action for consistency with the detail.
  The UI no longer treats a NO_ACTION code as proof that no follow-up is needed.
- Safety instructions no longer demand an invented universal staged-gag method or
  unsupported rule-of-thumb costs. Thin excerpts should trigger the existing fetch_page
  tool within the existing research budget. No new per-desk API or budget is introduced.

Source quote formatting/Markdown mapping and complete runtime cost accounting are
separate unresolved items; this batch does not claim to fix them. Existing saved
reports keep their recorded text and verdicts.

## Pre-registered validation

Free checks first: all unit tests, lint/dependency scan, and new regressions covering
missing/forged script receipts, missing source evidence, concealed inquiry duties,
cross-desk production questions and prompt isolation. Scripted responses establish
mechanics only, not semantic accuracy.

Then at most **22 logical live calls**, using the same model and exact saved sources:

1. Twelve isolated secondary-review probes in `evidence_applications_20260911.json`
   and `evidence_edits_inquiries_20260911.json` (six per file). Six positives and six
   negatives cover rating edits/guarantees, clip applications/removal, missing recording
   ownership, fictional age versus performer age, relevant/irrelevant inquiries,
   concealed hiring duties, production obligations disguised as edits, territory edits
   with uncertain approval and conditional firearms guidance. Expected labels and their
   reasoning are withheld from the model. Source/script hashes and exact receipts are
   checked before any spend. These are developer-authored diagnostic expectations,
   not expert legal labels or a representative accuracy benchmark.
2. If those probes pass manual review, two whole-flag audit/repair/check attempts on
   F1001 (JAWS clip) and F2001 (language rating) from the saved failed full run. At most
   five calls per finding, with the existing 240-second case deadline. Verify useful,
   desk-relevant remedies and honest unknown ownership/final-rating outcomes.

Expected returned-token estimate below $0.25; interrupted calls/SDK transport retries
may add billed usage. Timings are client-observed, including retries. Do not rerun
timeouts or spend on a new full screenplay gate in this batch. Persist every outcome,
including false approvals, false rejections and unavailable reviews. A negative test
does not pass merely because the model was unavailable.

No deployment. The previous full gate remains a failure until a subsequent full
validation preserves supported findings and produces relevant remedies.
