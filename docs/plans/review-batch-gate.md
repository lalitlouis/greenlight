# Gate run — review batch (commit ea21a58), pre-registered 2026-09-01

Written BEFORE the fixture run starts, per the anti-oscillation policy (run13/00-MASTER):
the read-off is judged against these lines, not retrofitted to them.

## What changed since the last green gate (35/35 on run 17)

Prompts (ratings one-call/one-descriptor rule, LANGUAGE MATH removed; safety anchor scoped,
firearms bulletin via lookup; territory NO_ACTION line; cleared-item-is-silence moved to
COMMON; PD-year placeholder), parser (EST./.45 no longer headings; shooting numbers
captured), census regexes, filing gates (phantom scene ids rejected; statute auto-attach
requires a quotable span; cost span rejects $0–>$1,000; normative regex tightened;
sync/master phrase list), rating tools (canonical descriptors, marginal selection, one
rounding rule, distance-0 weight, cut list dropped at target), verification (no full flip on
sourcing grounds; gates on re-source/refile/fact-prop), assembly (absorbed-id rewrite, OQ
follow-ups, items_examined), eval (46 checks via scripts/eval_invariants.py).

## Predictions

- P1 Run exits 0 (no abort, no salvage), 10–15 min, ~$2–5.
- P2 Eval 46/46. If not, the misses are one of the named soft spots below, and each is a
  real desk defect to fix at its class — not a reason to relax an assertion.
- P3 Scene structure identical to run_20260901_182958 (12 scenes, same headings and pages).
- P4 Census unchanged on this fixture: 'fucking' ×3 at S003/S006/S011, no slurs.
- P5 Rating: predicted R; `descriptors` present, one per category (language / drugs /
  violence); conformal set {R} or {PG-13, R}; 8/8 comparables R with official "Rated R for"
  excerpts; base rate shows 56.2% of 4,733 on the panel and one-decimal marginals on cards.
- P6 Every rating finding's marginal names the descriptor its prose names (no "unmodified"
  where the finding says "brief").
- P7 Expected casualty: the Gloucester Daily Times publication_clearance finding (F1004
  class) either files with an on-topic citation or falls to Open questions. It must NOT
  render as verified on a prop-design blog. Kept-flag count may be 18 rather than 19.
- P8 guard_manifest may show new filing gates firing (prose_scene_missing, statute attach
  refusal, cost-span $0) with no refile loop (retry caps hold; no desk hits its iteration
  ceiling on a rejection loop).
- P9 No overturn flips a citation_offtopic / premise_unsupported verdict; any overturn on
  record is a stated-fact or absence overturn with a number-anchored ground.
- P10 Soft spots (a MISS here is information, not regression): rightsholder-name
  traceability (desk names a licensor no excerpt carries); year+term arithmetic (desk
  writes 2038 for Nighthawks again — the prompt now says 2037).
- P11 Cleared section: ratings census row routes to "counted there" (cites F2002-class);
  header reads "N entities + M script-wide checks"; no row cites an absorbed id.

## Decision rule

Green (46/46, exit 0, P3/P9 hold) → `make deploy` via safe_deploy, then the scale gate as
budget allows. Red → fix at the class, pin with a test, roll again. No deploy on a red.

## Roll 1 read-off (run_20260901_222041, 22:11–22:20 PDT, exit 0, $1.55) — 45/46 as graded then

P1 ✓ · P3 ✓ (scene_meta identical) · P4 ✓ (three 'fucking', S003/S006/S011) · P6 ✓ (F2003 card =
'brief drugs', prose = 'brief drugs') · P7 ✓ (F1008 publication_clearance rejected as off-topic,
demoted to an open question; no false overturn; 18 kept) · P8 ✓ (statute attach + one OQ routed;
no refile loop) · P9 ✓ (zero overturns) · P11 ✓ (31 entities + 13 script-wide checks; one
follow-up under F1001).
P5 ✗ in part: predicted R, but conformal set {PG, PG-13} — the desk added "thematic elements"
to the profile and the joint model reads that profile as PG-13; divergence reason stated;
set reproduces from the persisted descriptors (invariant passed). Residual desk variance:
the vocabulary cannot encode F-word COUNT, so "language" is ambiguous between one-F-word
PG-13 and three-F-word R. Logged, not changed.
P10 fired: rightsholder traceability MISS — F1001 named Sony Music Publishing beside an
excerpt saying only "Composed by Leonard Cohen"; F1002 named Columbia/Sony Music
Entertainment on generic licensing text (both genuine); F1003's "Black Entertainment" was the
extractor reading a case citation (false positive).
NOT predicted: code dedupe merged the Krane tattoo flag (E009, SUPPORTED) into the Nighthawks
flag (E001) — same desk, same category, shared S002 — and the tattoo seed check passed on
category alone. A verified finding vanished; the grader hid it (and had hidden the same seed's
rejection on the previous record).

## Fixes at the class before roll 2 (commit follows)

- Licensor-name FILING gate (`_uncited_licensor_problem`, toolbelt): names in licence/clearance
  findings must appear in the flag's excerpts; retrieved-but-unquoted → auto-attached with its
  source URL; unretrieved → rejected with a "quote the repertory line" message. Extractor shared
  with both evals via `greenlight/names.py`; case citations ("v. X") excluded.
- `merge_exact_duplicates` and the plan-merge refusal require the same entity_id.
- Entity seed checks (tattoo, Nighthawks, Springsteen, Jaws) match on TEXT, not category.
  Re-graded: old record 43/46 (its tattoo flag had been rejected), roll 1 44/46.

## Roll 2 predictions

- R1 exit 0; 46/46.
- R2 A Krane tattoo artwork_license flag renders as its OWN line (E009), Nighthawks separate;
  `absorbed_into` empty or same-entity only.
- R3 Licence findings either quote the licensor (possibly via `licensor_cite_attached`) or
  name no owner; `uncited_licensor` may appear in the guard manifest with no refile loop.
- R4 Scene structure identical; census identical; no overturn of a sourcing rejection.
- R5 Soft spot: the tattoo seed is desk+verifier dependent (rejected on 182958, merged on
  222041) — a third failure mode would be a plain miss; that would be red, and the fix would
  be at the desk/citation class, not the grader.

## Roll 2 read-off (run_20260901_223815, 22:28–22:38 PDT, exit 0, $1.89) — 46/46

R1 ✓ · R2 ✓ (Krane tattoo F1007/E005 renders on its own line; Nighthawks F1004/E001 separate;
the only absorption is two entity-less safety flags of one category) · R3 ✓ (`uncited_licensor`
fired once at filing; every licence finding now traces Sony / Columbia / Universal to its own
excerpts) · R4 ✓ (scene_meta identical; census identical; zero overturns) · R5 held (the
tattoo filed and survived).
Rating: predicted R, set {PG-13}, descriptors persisted ("thematic" included again), 5/8 comps
R, divergence stated — the same residual as roll 1.
NOT predicted, and the reason this green is not a clean bill: the stunt_pyro BLOCKER (the
seeded climax, kept as PARTIAL in every prior run) was REJECTED on the merits — its ONLY
citation was a 33 CFR 100.501 definition line ("Captain of the Port Representative means…");
the CSATF #16/#19 excerpts it carried in roll 1 were gone. Re-source attempted 2, recovered 0;
the new re-source gate did not fire (no `resource_gate` manifest entry), so the batch did not
cause the loss. It demoted honestly to an open question; score 43 (was 29–30), cost
$87k–258k (was $179k–449k). Likely mechanism: the statute gate demanded the "100" of
"33 CFR Part 100" in an excerpt and the desk REPLACED its bulletin citations with the CFR line
instead of adding to them. The climax seed passed via the water stunt, so the grader did not
see the pyro finding go. Next class fixes (not yet built): a bulletin-number gate mirroring
the statute/licensor rule; rejection messages that say ADD, never replace; a climax seed that
names the pyro burn.

## Batch 3 (built after deploy 00211, before roll 3) — the pyro fragility at its class

- `_uncited_bulletin_problem` (toolbelt): every CSATF bulletin number a finding names must be
  carried by one of the flag's own citations (csatf.org URL naming the number, "Bulletin #N"
  in an excerpt, or the bulletin's official title line); a number the desk verified with
  csatf_bulletin() auto-attaches its index line as a `via: local` citation; a number in no
  retrieved text — or not in the official index — rejects.
- Statute, licensor, and bulletin rejections now say KEEP every citation and ADD one; roll 2's
  desk had swapped its bulletin excerpts for a CFR definition line to satisfy the statute gate.
- New fixture seed: the vessel burn must be flagged as a pyro/fire hazard on S008/S010/S011
  (firearms excluded). Re-graded: old record 44/47, roll 1 45/47, roll 2 46/47 — the seed
  bites on exactly the run that lost the BLOCKER. 385 tests.

## Roll 3 predictions

- Q1 exit 0; 47/47.
- Q2 A stunt_pyro (or fire) finding on the vessel burn renders, with a csatf.org excerpt or
  the #16 index line beside any bulletin number it names; `uncited_bulletin` may fire at
  filing with no refile loop.
- Q3 The BLOCKER/HIGH tier holds: pyro, water stunt, minor, firearms, sync, master, CN
  supernatural, UAE drug, language. Score back in the 25–35 band; cost back near $150k–450k.
- Q4 Scene structure identical; zero overturns of sourcing rejections; tattoo and Nighthawks
  render as two findings; every licence finding traces its owners.
- Q5 Soft spot (information, not regression): the conformal set may again read {PG-13} or
  {PG, PG-13} against a predicted R when the desk includes "thematic elements"; the
  divergence reason must be present (asserted).

## Roll 3 read-off (23:01–23:15 PDT, RUN_EXIT=1, ~$2) — RED, my defect

The run reached build_report and died on a report contract violation:
`flags/0/citations/3/source_type: 'safety_bulletin' is not one of [web, precedent, statute,
rules_table]`. The bulletin gate's auto-attached index citation used a `source_type` outside
the frozen enum; file_flag had already validated the flag BEFORE the gates appended it, so
nothing caught it until the deterministic report build — a paid run with no record. Before
the crash the log showed the gate doing its job (24 flags verified, 10 supported, 11 partial,
3 rejected and re-sourced; the tattoo and Nighthawks filed separately; the pyro finding was in
flight). Fix at the class (b89d5d9 → this commit): every auto-attach goes through
`_attach_citation`, which validates the citation against the schema's citation shape and
refuses (logged, manifest-noted, treated as not attached) instead of appending; the bulletin
line is `rules_table`; and file_flag re-validates the assembled flag after all gates, so a
deterministic slip surfaces as a refile at filing. Test pins every auto-attach path against
`validate("flag", …)`. 387 tests.

## Roll 4 predictions

- Q1–Q5 as registered for roll 3.
- Q6 No `contract_after_gates` or `refused: citation shape` entry in the guard manifest; the
  bulletin gate attaches `rules_table` index lines or rejects, and the run completes with a
  record.

## Roll 4 read-off (run_20260901_232929, 23:18–23:29 PDT, exit 0, $1.74) — 47/47, GREEN

Q1 ✓ · Q2 ✓ (stunt_pyro F3001 BLOCKER on S008/S010/S011 with csatf #16 PYROTECHNIC and #19
FLAMES excerpts) · Q3 ✓ (BLOCKER 1 / HIGH 9: pyro, sync, master, language, drug use, minor,
water, firearms, CN supernatural, UAE drug; score 28; cost $104k–273k — under the predicted
$150k band because the sync/master quotes came in lower this run, desk cost variance) ·
Q4 ✓ (scene_meta identical; tattoo F1004/E007 and Nighthawks F1003/E001 separate; only
absorption is same-category entity-less safety; zero overturns; `uncited_licensor` fired twice
at filing and every licence finding traces its owners) · Q5 held the good way (set {PG-13, R}
contains R; the desk left "thematic" out; 8/8 comparables R; no divergence needed) ·
Q6 ✓ (no `contract_after_gates`, no refused attach). Rejections: animal_safety (verifier
judged the bulletin excerpts too generic — substance is its call, the number gate only proves
the number) and CN drug use (variance); re-source 0/2. Deploy follows.
