# Ratings desk — remedies as actions, structured marginal at filing

File: `src/greenlight/agents/ratings_board.py`. Items 2c, 3b (desk side).

## Item 2c — remedies are actions, not justifications

### Current behavior
The instruction (step 2a, CLAIM SHAPE) bans normative rules in the finding and
keeps the number in the citation — but says nothing about the remedy's shape,
so the desk writes justification clauses there: "…retaining at most 1 isolated
non-sexual use to conform to PG-13 language limits." The justification is a
CARA rule restated; it migrated to the one field nothing reads.

### Planned change
Instruction addition (step 4, the remedy step):

- A remedy is an ACTION LIST: what to cut/replace/restage, named by scene.
  "Cut 'fucking' at S024 and S084" needs no rationale clause.
- The rationale is the marginal, it lives in the finding, once. Never restate
  a band rule in the remedy ("to conform to / within / retaining at most N"),
  and never state what CARA permits — the filing gate rejects it
  (30-filing-gates.md) and the refile costs an iteration.
- Naming the TARGET is fine ("…to target PG-13"); asserting the RULE is not.

### Allowed vs banned (the line, pinned)
| Allowed | Banned |
|---|---|
| "Cut X at S024; replace Y at S030." | "…to conform to PG-13 language limits" |
| "…to target PG-13." | "…within PG-13 parameters/tolerances" |
| "Restage the S055 bull as slapstick." | "retaining at most 1 non-sexual use" |
|  | "fits comfortably within PG-13 comedic violence tolerances" |

### Regression contract
Prompt layer — non-deterministic. The mechanical enforcement is the
field-agnostic validator + eval assertion; this instruction reduces refile
churn, nothing more is claimed for it.

## Item 3b — structured marginal is attached by the tool, not the model

### Current behavior
`rating_boundary` returns a citable sentence per marginal; the desk files it as
a citation excerpt. Whether the number renders depends on the desk copying the
sentence and the prune keeping it — three runs of "plumbing works, nothing
came out" (runs 10–12: rejected → mislabeled → hedged prose without the
number).

### Planned change
The structured fields (60-schema.md) are populated **deterministically at
file_flag time** from the desk's most recent `rating_boundary` result
(state-keyed per agent, same pattern as `boundary_set:`), never typed by the
model — consistent with the mint-proofing of the typed citation registry. The
desk's only job is to call `rating_boundary` with the descriptors it counted
before filing; the instruction states that plainly and warns that a rating
finding filed with no boundary call behind it will not render (hard gate,
50-renderer.md).

### Hedge ban (belongs to the desk contract)
"patterns strongly toward / patterns toward / patterns across" are banned in
finding prose **unless the marginal field is populated** — the hedge was
substituting for the number. Enforced in the filing gate (30-filing-gates.md),
stated here so the desk stops producing it.
