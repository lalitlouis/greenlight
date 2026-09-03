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

## Batch 4 (from the live Hangover read-off, 2026-09-01 late) — before roll 5

Owner reviewed the live Hangover report on 00212. Fixed at class:
- Coverage set contradicted the desk, the comparables and the corpus ({PG-13} over a profile
  carrying 'pervasive language', R 99%): dominant-descriptor FLOOR — a rating one descriptor
  carries at >=90% of >=50 films stays in the set (`set_floor` persisted, schema additive);
  the set is RECOMPUTED deterministically when a rating finding is rejected or demoted, dropping
  the descriptor only that finding supplied (`conformal_set_recomputed` in the manifest);
  the divergence line renders when the desk's call sits outside the SET, not only when it
  differs from the neighbour majority; an empty reason renders as an honest sentence.
- "Descriptors evaluated" leaked `sexual_content` / `unmodified` — humanised.
- Withdrawn-finding notices split from Open questions on web, binder, PDF (own count; no
  nested "(later rejected…)" annotation inside the template).
- Header: "67 entities researched: 14 carry findings, 53 cleared" beside the 53 + 14 items line.
- Prose scene counts must not exceed the coordinates (filing gate + eval).
- Spread caution only when no rating holds a clear plurality (<5 of 8), tool + renderer.
- Bulletin numbers verify only from csatf.org or the local index, not third-party mentions.
- Ratings prompt: 'thematic elements' is CARA's mature-subject PG/PG-13 wording, never adult
  venues; alcohol is its own family, never 'drugs'.
- Eval: three new invariants (floor honoured; no descriptor from a rejected-only family;
  prose scene count <= coordinates) → 50 checks. Old records: roll 4 and roll 2 re-graded below.

## Roll 5 predictions

- S1 exit 0; 50/50.
- S2 The fixture profile (language / drugs / violence) has no >=90% descriptor unless the desk
  writes "pervasive language" — `set_floor` empty or names exactly that; set {R} or {PG-13, R}.
- S3 If any rating finding is rejected, `conformal_set_recomputed` appears and `descriptors`
  no longer carries its family; divergence line present whenever predicted ∉ set.
- S4 No "N scenes" claim above the chips; no third-party bulletin verification; withdrawn
  notices (if any) render apart from open questions.
- S5 Everything roll 4 held (scene structure, tattoo/Nighthawks separate, pyro BLOCKER with
  csatf excerpts, licensor traceability) holds again.

## Roll 5 read-off (run_20260902_001843, 00:06–00:18 PDT, exit 0, $1.85) — 49/50

S1 ✗ by one: rightsholder traceability MISS on F1014 ("Sony Music Entertainment"). The
licensor gate fired twice (CNHI, Prelinger — correct rejections) and ATTACHED a Sony
press-release span for F1014, but the span's word-boundary trim had cut the name off the edge
of the registered text, so the attached excerpt did not contain the owner it was attached for.
Fix: `_licensor_span` trims outside the match only and re-checks the name survives; file_flag
re-checks every named licensor against the citations that actually render, after repair and
pruning. Tests pin both edges.
S2 held the honest way: set {PG-13}, predicted R, divergence reason present; no floor (bare
'language' is ~80% R — the F-word count is not in the vocabulary; logged residual).
S3 n/a (0 rejections). S4 ✓ (no scene-count claims; bulletin numbers only from csatf.org or
the local index — three `bulletin_cite_attached`). S5 ✓ except granularity: the desk filed
four stunt_pyro flags for the S008–S011 sequence and code dedupe folded them (same category,
entity-less, overlapping scenes — the rule working) into one BLOCKER carrying 13 citations,
incl. epa.gov, a South Carolina film office, and a studio-teacher mirror. Fix: merged
citations are deduped, background-pruned, and capped at 6 on both merge paths. The minor and
water hazards live in that finding's prose this run rather than as their own lines — desk
granularity variance, stated.

## Roll 6 predictions

- T1 exit 0; 50/50 — every licence finding traces its owners after repair and pruning.
- T2 No kept finding carries more than 6 citations; merged findings keep their strongest.
- T3 Everything roll 5 held holds again (scene structure, tattoo/Nighthawks, pyro BLOCKER with
  csatf excerpts, no scene-count claims, divergence present whenever predicted ∉ set).

## Roll 6 read-off (run_20260902_004149, 00:24–00:41 PDT, exit 0, $1.68) — 50/50, GREEN

T1 ✓ (every licence finding traces its owners; `licensor_cite_attached` ×2 with the name
verified inside the span) · T2 ✓ (max 3 citations on any finding; the one absorption is two
same-category safety flags) · T3 ✓ (scene_meta identical; tattoo F1007/E005 and Nighthawks
F1003/E001 separate; pyro BLOCKER on its csatf #16 excerpt; no scene-count claims; 0
rejections, 0 overturns; set {PG, PG-13} vs predicted R with the divergence reason on the
record — the F-word-count residual, stated). 21 kept, score 28, cost $127k–368k. Deploy follows.

## Scale gate (fixtures/scale_gate.fountain, 100 scenes, ~95 entities) — on 00213, pre-registered

The wide-coverage check for the census, parser, prompt, and filing-gate changes; the last
scale-gate grade on record is 20/23 (2026-08-29) before eval_scale gained the shared invariants.

- U1 Run exits 0 without abort or salvage; 12–20 min; ~$5–10.
- U2 Structural tier clean: no id collision, no rejection loop, 0 unexamined, 0 collapsed desks,
  rating filed with comparables, territory 12 axis sweeps by id.
- U3 Shared invariants all green (citations, phantom ids, prose scenes, cut-list direction,
  vote recompute, floor, rejected-only descriptors, scene counts, reconciliation).
- U4 Seed grade: every k=3 pass-1 miss class stays green (music sync+master split, Nighthawks,
  tattoo, Coors disparagement); the controlled-venue location remedy remains the known soft
  seed (has failed most runs).
- U5 Soft spots that are information, not regression: rightsholder traceability on a
  brand-dense script (many licence findings); kept-findings floor (>=10).

## Scale gate attempt 1 (00:49–03:43 PDT) — ABORTED on infrastructure, not evidence

`RUN ABORTED — ClientConnectorDNSError: cannot connect to aiplatform.googleapis.com`
(the Mac lost its network overnight; caffeinate keeps the CPU awake, not the Wi-Fi).
Elapsed 10,448 s, $1.96, salvaged with 15 kept / 1 rejected, clearance at 82 of 112 work
items, 30 unexamined — the salvage grade (39/49) is struck as evidence per the standing
rule; every seed miss is an item clearance had not reached. Ops follow-up (logged, not
fixed): the run breathed for ~2.5 h on a dead network before the DNS error surfaced —
the 900 s inactivity watchdog should bound a network-unreachable stall the same way it
bounds a silent one. Re-launched at the time stamp below with the same predictions U1–U5.

## Scale gate attempt 2 (run_20260902_130947, 12:54–13:10 PDT, exit 0, $3.32) — 49/49 after a grader fix

U1 ✓ (15.7 min) · U2 ✓ (0 unexamined, 0 collapsed, clearance 113/113 work items, territory
17/17, rating filed with comparables) · U3 ✓ (every shared invariant green, incl. floor,
rejected-only descriptors, scene counts, vote recompute) · U4 ✓ (sync + master split, Nighthawks,
serpent tattoo, Coors disparagement, AND the controlled-venue remedy — the seed that had failed
most runs) · U5 ✓ (licensor gate fired twice; every licence finding traces its owners).
Rating: predicted R, set {PG-13, R} ∋ R, majority R. 23 kept / 0 rejected, score 34.
The single MISS as first graded (48/49) was the GRADER: the "neutral Springsteen story NOT
defamation-flagged" counterweight used `flags_about`, which unions category OR text, so the
doctrine-correct right_of_publicity flag on the Springsteen tribute POSTER (S045) counted as
a defamation flag; the anecdote (S011) was not flagged and the finding says so. Negative
checks are now conjunctive (`flags_matching`). No product code changed; nothing to deploy.

## Case-study regeneration on 00213 (owner go 2026-09-02 ~13:20 PDT) — pre-registered

Six cases, case-grade budgets, sequential (~10–20 min each, ~$2–3 each). Predictions:
- V1 All six complete without abort; each record carries rationale-space comparables
  ("Rated X for …" excerpts), `descriptors`, and a coverage set that contains R for every
  R-rated film whose profile carries a >=90% descriptor (Wolf: graphic nudity / pervasive
  language; Hangover: pervasive language) — the floor is visible in `set_floor`.
- V2 Scores move only through findings: HIGH tier stable per case vs the 2026-09-01 records
  (music chains, controlled venues, pyro/stunts); LOW/MEDIUM tail and category slugs drift.
- V3 Little Miss Sunshine and Wolf show page-number shifts vs their prior records (OCR'd cues
  now read as speakers); scene ids and headings identical for all six.
- V4 No finding carries >6 citations; no prose scene count above its chips; every licence
  finding traces its owners; withdrawn notices render apart from open questions.
- V5 Soft spots (information): the conformal set on The Social Network (released PG-13,
  predicted R in the prior record) — the floor and the reconciled descriptors may move it.
Publishing: the case records ship in the image — the owner reviews six summary lines, then
`safe_deploy` publishes /cases; the landing hero's Reservoir Dogs number is checked against
the new record.

## Case regen read-off (2026-09-02 13:48–15:10 PDT, six cases, $20.25, REGEN_EXIT=0)

V1 ✓ all six complete; every comparable excerpt official; `descriptors` + `set_floor` on every
record (pervasive language floors R on five; strong bloody violence on Reservoir Dogs).
V2 partial: HIGH tiers largely stable with visible churn (Hangover lost firearms/minor/fall
HIGHs to MEDIUM and gained a location HIGH; LMS gained several; TSN gained sync/artwork/pyro).
Scores: RD 37→32, Clerks 29→30, LMS 36→24, TSN 29→21, Wolf 21→25, Hangover 20→25.
V3 ✓ scene ids and headings identical on all six; page shifts LMS 29 scenes, Wolf 90 scenes
(OCR'd cues now read as speakers); RD and Wolf now carry the script's own scene numbers.
V4 ✗ on Wolf: two licence findings (F1009 Universal Studios, F1014 "Warner Bros.
Entertainment Inc") named owners their excerpts do not carry — both RE-SOURCED flags: the
re-source gate checked authority/statute/sync-master/normative but not licensor traceability
(added after that gate was written), and the Warner name is the PLAINTIFF of a case citation the
extractor did not skip. Fixed: licensor traceability on the refile gate; plaintiff-position case
names and sentence-initial words excluded from the extractor. Wolf re-run below; the other five
show no untraced owners.
V5 as predicted but the other way: TSN's set moved {PG-13} → {R} because the desk wrote
"pervasive language" (floor) for a film CARA rated PG-13 — the floor is only as good as the
desk's intensity word; logged as desk-descriptor judgment, not a code defect.

## Wolf re-run (15:15–15:29 PDT, $3.64) — clean

No untraced owners across seven licence/clearance findings (`uncited_licensor` ×2 fired,
`licensor_cite_attached` ×3); max 3 citations; 0 unexamined; set {R} with three floors
(pervasive language, strong sexual content, graphic nudity), 8/8 comparables R; 34 kept /
2 rejected (Bo Dietl publicity and a UK language flag, both on citation grounds), score 21.
All six case records are now clean on every shared invariant; publish = safe_deploy (the
records ship in the image). Case regen total: $23.89 for seven runs.

## Batch 6 (from the published Hangover case read-off, 2026-09-02) — before roll 7

- Internal ids (E###, P###, XX-W###, axis/census/sweep ids) stripped from every reader-facing
  text at assembly, punctuation repaired ("For E030 (CC-W030, Limp Bizkit cue in S032), …" →
  "Limp Bizkit cue in S032: …").
- A rating finding's severity is bounded by its own marginal: under half its films ABOVE the
  production target → capped at LOW at filing (manifest `rating_severity_bounded`); eval
  invariant added (51 checks). CONSEQUENCE, stated: under an R target every R-band driver is
  at-target and files LOW — rating findings on R-target scripts (five of the six cases) will
  read as informational when those cases are next regenerated; the composite score on those
  pages will rise accordingly. The published cases are unchanged until regenerated.
- Ratings prompt: slurs and offensive jokes are LANGUAGE, never thematic elements.

## Roll 7 predictions

- W1 exit 0; 51/51.
- W2 Fixture (target PG-13): language HIGH stays (R ~80% above target); 'brief drugs' stays
  (R 76%); 'some violence' stays (R 65%); a 'thematic' driver, if filed, is LOW.
- W3 No E###/P###/work-item id in any open question, follow-up, cleared row, or finding.
- W4 Everything roll 6 held holds again.

## Roll 7 read-off (run_20260902_174803, 17:38–17:48 PDT, exit 0, $1.74) — 50/51

W1 ✗ by one: Nighthawks not flagged — the desk filed the artwork claim on ONE citation, an
exhibition-date line ("Edward Hopper, Nighthawks, 1942…"), the verifier rejected the premise
(correctly), re-source attempted 3 / recovered 0, and no gate on this batch was involved
(no `resource_gate` entry). Rolls 4–6 had cited the Whitney "© … Licensed by ARS" line. Fix at
the class: a licence/clearance finding must carry at least one excerpt that speaks to
licensing, copyright, permission, or rights (`claim_class_support`, filing + re-source gate) —
the CSATF "index verifies the number, substance comes from the bulletin text" rule applied
to licences. W2 ✓ (language HIGH, drugs MEDIUM, violence LOW; no thematic driver filed).
W3 ✓ (no internal id in any reader text). W4 ✓ (scene structure; pyro BLOCKER; tattoo separate;
max 4 cites; 0 overturns; set {PG-13} vs R with divergence — the residual). Roll 8 follows.

## Roll 8 read-off (run_20260902_180714, 17:49–18:07 PDT, exit 0, $3.16) — 50/51

Same seed missing, different failure: the desk filed Nighthawks as `artwork_display` (also
`tattoo_artwork`, `trademark_prop` this run) — slugs outside the vocabulary the prompt says to
use "EXACTLY" — so the licence gates keyed on `license|clearance` never saw it, and the
verifier rejected a product-credit-line citation on the merits. Fix at the class: the desk
category vocabulary is enforced at filing with the closest admissible slug named
(`category_vocabulary`); ratings admits its six slugs plus rating_<family> for any CARA
descriptor family. Everything else held (no internal ids; severity bound; pyro BLOCKER;
scene structure; 0 overturns). Re-source recovered 2 of 5 this run.

## Roll 9 predictions

- X1 exit 0; 51/51 — Nighthawks files as artwork_license with a licensing-class excerpt.
- X2 `category_vocabulary` may fire at filing with no refile loop; no drifted slug in the
  kept or rejected set.
- X3 Everything roll 8 held holds again.

## Roll 9 read-off (run_20260902_181556, 18:10–18:16 PDT, exit 0, $1.53) — 51/51 as graded, but not clean

X1 ✓ Nighthawks filed as artwork_license with an art-law licensing excerpt (the licensor
gate had first refused an uncited 'Artists Rights Society'). X2 ✓ no drifted slug anywhere.
X3 ✓. TWO things the checks did not name: (a) my severity bound left a private
`_severity_bounded` key on the flag and the contract re-check rejected the language finding
TWICE (`contract_after_gates` ×2) before the desk refiled at LOW on its own — fixed (no marker;
the note derives from the severity delta) and the eval now asserts `contract_after_gates`
never fires; (b) the rating prediction read PG-13 for the first time in nine runs of this
script: the desk wrote 'strong language' (PG-13 89%) for the three F-words instead of bare
'language' (R 80%), the set became {PG-13}, and the prediction followed with a reasoned
divergence from its R-majority neighbours. Same script, nine runs: R ×8, PG-13 ×1 — the
F-word-count residual, now visible at the headline. Owner decision logged below.

## Roll 10 predictions

- Y1 exit 0; 52/52; `contract_after_gates` absent from the manifest.
- Y2 The rating call is the desk's: R or PG-13 depending on the language descriptor it
  chooses; whichever it is, set ∋ prediction or a divergence reason is present.
- Y3 Everything roll 9 held holds again.

## Roll 10 read-off (run_20260902_182645, 18:18–18:26 PDT, exit 0, $1.91) — 52/52, GREEN

Y1 ✓ (`contract_after_gates` absent; `claim_class_support` fired once at filing; licensor
attach ×4) · Y2 R vs target PG-13, set {PG, PG-13}, divergence present (residual) · Y3 ✓
(scene_meta identical; Nighthawks MEDIUM + Krane tattoo LOW as two artwork_license findings;
pyro BLOCKER; max 3 citations; 0 overturns; 0 unexamined; no drifted slug; no internal id).
22 kept / 1 rejected (a second pyro filing on citation grounds; re-source recovered 2 of 3).
Deploy follows: batches 6–7 (id strip, severity bound, claim-class support, vocabulary
enforcement, contract-fire assertion) on top of 00214.

## Batch 8 — MPA rating-rules tool (owner go 2026-09-02 ~18:45) — before roll 11

`rating_rules('expletive')` serves the official provision verbatim (asset harvested from the
filmratings.com PDF, effective July 24, 2020, sha256 b73004023110…); rule-shaped rating
claims are admissible only beside that citation (filing, refile, eval); the census carries a
spoken F-word count and `rating_boundary` floors R into the set at >=2 uses with the rule
cited. Ratings prompt: bare 'language' for repeated uses.

## Roll 11 predictions

- Z1 exit 0; 52/52.
- Z2 The coverage set CONTAINS R (the fixture has three spoken uses; `set_floor` carries the
  MPA rule note with "3 spoken uses"); the language finding may now state the rule beside a
  `rules_table` citation, or keep the observation shape — either passes.
- Z3 Predicted R (the desk's call; PG-13 would need a divergence reason against an R-majority
  and an R-containing set).
- Z4 Everything roll 10 held holds again.

## Roll 11 read-off (run_20260902_214110, 21:26–21:41 PDT, exit 0, $1.93) — 50/52, the tool works

Z2 ✓ set {PG-13, R}; `set_floor` = the MPA rule with "3 spoken uses counted"; the language
finding quotes the provision verbatim (rules_table / local, filmratings.com URL) beside its
marginal and states the rule legitimately. Z3 ✓ predicted R, inside the set, no divergence.
Z4 ✓ scene structure, pyro BLOCKER, 0 overturns, no drift, no leaked id.
Two misses, both fixed at class before roll 12: (a) the eval's "set reproduces from the
persisted descriptors" check re-ran boundary_eval without the count floor — it now adds R
when the floor note is on record, and `spoken_f_words` is persisted on the prediction (schema
additive) so the What-If baseline applies the same floor (lifted only by a cut that targets
the expletive); (b) Nighthawks rejected again — filed with a PROVENANCE line as its only
surviving citation because the claim-class support gate ran before repair/pruning removed
the licensing excerpt; the support check now re-runs after pruning, like the licensor one.

## Roll 12 predictions

- AA1 exit 0; 52/52 with the reproduction check honouring the floor.
- AA2 Set ∋ R via the MPA floor; predicted R; language finding cites the rule.
- AA3 Nighthawks files with a licensing-class excerpt that survives pruning, or the desk is
  told so at filing (no provenance-only artwork claim reaches the verifier).

## Roll 12 read-off (run_20260902_221612, 21:44–22:16 PDT, exit 0, $4.94) — 52/52, GREEN

AA1 ✓ · AA2 ✓ (set {PG-13, R} on the MPA floor, `spoken_f_words` 3 on the record, predicted
R inside the set, language finding cites the provision beside its marginal) · AA3 ✓
(Nighthawks LOW with the artic copyright page + a licensing excerpt; tattoo separate).
Scene structure identical; pyro BLOCKER; max 3 citations; 0 overturns; no drift; no leaked
id. The run took 32 min / $4.94 (double the norm): seven filing rejections vs six on roll
11 (no loop), plus one completeness-gate round that retried a desk with zero own
dispositions — the known collapse-and-retry class, not the new gates. Deploy follows.
