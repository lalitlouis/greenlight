# Schema change (announced): structured marginal on rating findings

File: `schemas/flag.schema.json` (+ `report` schema for the cost attribution).
Per CLAUDE.md: **this is the say-it-out-loud doc.** Additive, optional fields
only; nothing existing changes shape.

## flag.schema.json — new optional object `marginal`

```json
"marginal": {
  "type": "object",
  "required": ["descriptor", "n", "distribution", "source"],
  "additionalProperties": false,
  "properties": {
    "descriptor":   {"type": "string"},          // e.g. "pervasive language"
    "n":            {"type": "integer"},          // rationales carrying it
    "distribution": {"type": "object"},           // {"R": "99%", "PG-13": "0%", ...}
    "base_rate":    {"type": ["object", "null"]}, // corpus-wide rating shares
    "source":       {"type": "string"}            // "ScriptRisk CARA descriptor corpus (4,544 rationales)"
  }
}
```

Populated **only** by `file_flag` from the desk's last `rating_boundary`
result (30-filing-gates.md) — never model-supplied. Present only on
`rating_*` findings; its absence on a rating finding triggers the render
hard gate (50-renderer.md).

### Deliberate deviation from the review's field list
The review asked for `neighbors_with_descriptor / n`. Not included: neighbors
come from the **6,302-film comparables corpus** (kNN panel), the marginal from
the **4,544-rationale descriptor corpus**. Mixing both corpora in one struct
recreates the two-corpora confusion the run-9 batch just untangled — the
neighbor count already renders on the kNN panel with its own corpus label.
`base_rate` (from the descriptor corpus' own rating shares) is included.

## report.schema.json — `est_cost_paths.excluded`

```json
"excluded": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["flag_id", "category"],
    "properties": {
      "flag_id":      {"type": "string"},
      "category":     {"type": "string"},
      "est_cost_usd": {"type": ["array", "null"]}
    }
  }
}
```

Names every flag the adjudicator ruled off the target path — the structured
source of the one-line delta attribution (item 7).

## Record (non-frozen) additions, listed for completeness
- `record["guard_manifest"]` — internal audit trail (10-verification.md).
- Cleared determinations may carry `rephrased: true` (40-cleared-path.md).

## Consumers to notify / update in the same batch
- `report.js` (renders `marginal`, `excluded`)
- `pdfgen.py` / `onesheet` (rating findings: print the marginal line if
  present; no layout change otherwise)
- `binder.py` (no change — marginal not in the log)
- `contracts.validate` fixtures in tests
