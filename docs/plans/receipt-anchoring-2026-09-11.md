# Receipt anchoring and ownership evidence — September 11, 2026

The latest full gate remains the failed 45/54 result in
`runs/run_20260911_015915.json`. This batch addresses source-formatting false
negatives and investigates the missing work-to-licensor links identified by the
independent reviewer. It is not a release gate or deployment.

## Implementation

Receipts first use exact substring matching. A failed exact match may use a narrow
display-text projection: whitespace collapse, complete HTTP(S) Markdown links,
paired bold/underscore emphasis, and standalone 2–6 hash heading markers found in
flattened Parallel PDF text. Case, words, punctuation, order and numbers remain
literal. Truncated/unsupported markup and ambiguous normalized matches fail.
Offsets map the match back to an exact raw substring; citation excerpts never change.
The submitted and raw quotes are retained in internal `support_span_reanchors`.
Public schemas, parser, model, budgets and source-only entailment review are unchanged.

The saved F3006 curfew receipt now anchors across `no ### later`. This establishes
provenance only, not the applicability of the cited labor standard. The F1008 excerpt
ends in `[First`; it remains unresolved because truncated markup is not repaired.

Clearance instructions distinguish a supported use-specific rule from an unresolved
named licensor. Exact work/version and rights type must connect to the party and its
licensing role. Distributor credits and corporate parentage alone are insufficient.
Existing research/fetch_page tools, three-hop cap and budgets remain in place; unresolved
ownership becomes an explicit open question, never an inferred owner or clearance.

## Bounded validation

Run the full free suite and dependency/lint checks. Regression tests cover the saved
formatting examples, immutable citations, source isolation, independent negative
entailment, changed wording/conditions/numbers, and ambiguous or truncated markup.

Then at most two Parallel searches and two follow-up extracts for JAWS clip licensing
and the selected Jeff Buckley Hallelujah recording. Use the existing runtime SDK
wrappers and preserve raw responses, search IDs, exact queries, timestamps and source
code hashes in a cassette. Follow-up extracts must use URLs actually returned by
search. These are evidence discovery checks, not a new desk run or an ownership
assertion. Stop at the budget even if unresolved; do not retry missing evidence until
it agrees with an expected owner. No full run or new Gemini evaluation is planned in
this batch; any candidate evidence still needs independent review before rendering.

## Results

Free validation: **540 tests passed**, lint/format and forbidden-dependency checks
passed. The saved curfew receipt anchors; the incomplete military-uniform receipt
does not. A scripted negative secondary review still rejects a claim even after its
receipt was successfully anchored. These results measure deterministic behavior,
not an improvement in whole-report accuracy.

The planned two searches and two extracts all returned, each reporting one usage
unit (`sku_search` or `sku_extract_excerpts`). Client-observed call times were
1.34/1.57 seconds for searches and 0.99/0.82 seconds for extracts. No Gemini calls or
full screenplay run occurred; this is not an end-to-end performance benchmark or
invoice calculation. Raw artifacts include the execution script, runtime wrapper
hash, exact requests, response IDs, timestamps and usage:

- `fixtures/cassettes/ownership_search_20260911.json`
- `fixtures/cassettes/ownership_extract_20260911.json`

Manual evidence review, limited to the returned excerpts:

- JAWS: Born Licensing's page explicitly names the film and describes representation
  for **advertising and marketing**. It does not establish licensing authority for
  incorporating a clip into the feature screenplay being analyzed. The extract did
  not expand that scope. Other results identify merchandising, public-performance
  licensing or historical distribution; none completes the required film-use chain.
- Hallelujah: the artist's Grace page establishes the selected recording, and a
  historical Sony press release names Columbia. The Legacy artist-page extract has a
  generic sync-inquiry link, but does not identify this master or establish its current
  licensing administrator. Those are useful research leads, not an accepted owner.

Both named-licensor questions remain unresolved. No returned source was added to a
production finding, and no saved report or verdict was upgraded. Clearance instructions
now explicitly separate merchandise/advertising/public-screening roles from film clip
use, and general inquiry links from proof of representation. The prompt change has
not yet been tested in a fresh desk run. The remaining work is a bounded fresh clearance
and safety desk evaluation, useful generic remedies with explicit ownership questions,
and then a full gate only when those results justify it. The latest release gate is
still the prior failure; nothing was deployed.
