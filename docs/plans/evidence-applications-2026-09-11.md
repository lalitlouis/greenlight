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

## Results

Build `badbd34`: 500 offline tests passed; lint/dependency checks and JavaScript syntax
checks passed. The two probe sets matched **12/12** pre-registered expectations, with
all twelve calls returning usage. Manual review agreed with each supplied-evidence
label. Captured-token estimates sum to $0.0271. This verifies these selected examples,
not the entire verifier or desk accuracy. Artifacts:

- `fixtures/cassettes/evidence_applications_20260911.json`
- `fixtures/cassettes/evidence_edits_inquiries_20260911.json`

Proceed to the two planned whole-finding repair checks at the same build and with
the same saved sources. The preceding failed full gate remains the full-run baseline.

The two whole-finding attempts returned in 101.76 seconds (F1001) and 52.52 seconds
(F2001), six calls and $0.0617 estimated returned-token usage. Neither completed the
secondary stage:

- F1001's corrected remedy had two alternatives separated by an unaudited `or`.
  The coverage check treated the operator as omitted material. The correction also
  still names Universal as the JAWS licensor and offers royalty-free replacement
  footage; those assertions have **not** been accepted and need semantic scrutiny.
- F2001's correction proposes cutting/replacing two of the three expletives, conditional
  on pursuing PG-13 without a special vote. Its auditor labelled severity `application`,
  triggering the new script-receipt requirement on HIGH. Severity is a judgement
  regardless of the chosen basis; that requirement was a deterministic routing bug.

Fix those stops offline: all severity bases bypass receipt requirements while negative
severity judgements still block approval. Internal `or`/`and/or` joins now proceed only
with the complete field supplied as **claim context**, not evidence, to the secondary
reviewer. The reviewer must judge the operator and each alternative's conditions;
one supported option cannot conceal an unsupported option. Missing prescriptions,
conditions and negation still fail coverage. A scripted negative regression checks
that an unsupported alternative still rejects the compound remedy.

Use two of the remaining four reserved calls to complete only the skipped secondary
reviews of the unchanged saved candidates. Source/script hashes, exact receipts and
the absence of a completed prior secondary review are checked first. This is a
continuation after deterministic fixes, not a second correction or a retry of a
negative semantic judgement. Do not reword a candidate to make the test pass.
