# Data sources — provenance and status

Status: **current as of 2026-09-07.** Every corpus and reference asset the runtime reads, where
it came from, how it was collected, and the legal basis we rely on. The 2026-08-24 analysis that
approved the content-profile corpus is kept below for the record; the 2026-08-28 harvest of
official rating reasons **superseded its "no filmratings.com scraping" recommendation**, and
this file said the opposite of what shipped until this revision. That contradiction is fixed
here, not hidden.

## What the runtime reads

| Asset | Used for | Source and collection | Basis |
|---|---|---|---|
| `cara_rationales` (ClickHouse, 4,733 rows) | Report comparables and base rates (run 17, 2026-09-01) | Official CARA rating reasons as listed on the MPA's filmratings.com search results; collected once by `scripts/harvest_rationales.py` (one request per film, 0.7 s spacing, backoff, identified user agent); robots.txt permits crawling; source URL per row | Facts about films plus short formulaic phrases — outside copyright (*Feist*; 37 CFR 202.1). The site's terms of use prohibit automated access and license content for internal non-commercial use; we treat this as a contract exposure, disclosed here, and the production path is a licensed feed from the MPA |
| `rating_boundary.json` (4,544 parsed rationales) | Per-descriptor marginals, the multinomial model, the conformal coverage set | Derived from the same harvest by `scripts/build_boundary_asset.py`; our own aggregate, cited by name in the report | Same as above; the derived statistics are ours |
| `rating_rationales` (ClickHouse, 6,302 rows) | First Look pitch comparables (topical similarity) | Wikidata P1657 ratings (CC0) + Wikipedia lead/plot via the official MediaWiki API; embedded with `text-embedding-005`; source URL per row | Facts from CC0 data; Wikipedia prose is CC BY-SA and we store embeddings and a short attributed display line with its URL |
| `mpa_rating_rules.json` | `rating_rules()` — the desks may state a rating RULE only beside this text | One download of the MPA's published *Classification and Rating Rules* PDF (effective July 24, 2020; SHA-256 on the asset) by `scripts/harvest_mpa_rules.py`; the five rating provisions and the expletive sentences, verbatim | Quotation of a published rule for reference and criticism, attributed; the MPA is not affiliated with and does not endorse this product |
| `csatf_bulletins.json` | `csatf_bulletin()` — bulletin numbers and titles | One-time harvest of the official CSATF safety-bulletin index (csatf.org) | Titles and numbers of public industry safety bulletins; substantive text is retrieved live and cited |
| BBFC cuts records | `bbfc_cut_precedent()` — UK cuts precedents | Harvested from the BBFC's public classification records (`scripts/harvest_bbfc.py`), 436 records | Regulator's public decisions; facts |
| USPTO TSDR | `verify_trademark()` — live status/owner of a registration | Live official API at runtime | Official public register |
| Parallel Search / Extract / Task | Every web citation | Live at runtime via the `parallel-web` SDK | Partner API under its terms |

## Trademark and attribution

"MPA", "CARA", "BBFC", and the rating marks are certification marks; reporting that a film was
rated R is nominative use. The product states the prediction is ours and that we are not
affiliated with or endorsed by the MPA (cases page; report footer copy in `web/static`).
No third-party logo is displayed in the product or the demo video.

## What changed, and when

- 2026-08-24 — content-profile corpus approved (Wikidata + Wikipedia); "no filmratings.com
  scraping" recommended because the rationale strings could not be found in Wikipedia prose.
- 2026-08-28 — Track B: the official rating reasons were harvested from filmratings.com
  (4,755 rows; DECISIONS.md "Track B delivers") because they are the only authority for CARA's
  own wording; the descriptor boundary and conformal model were built on them.
- 2026-09-01 — run 17 moved the report's comparables from the content-profile corpus to the
  rationale corpus after the What-If Swearnet diagnosis (docs/plans/run17-rationale-space.md).
- 2026-09-02 — the MPA rules PDF became a local tool so the expletive-count rule can be cited
  from the official text (DECISIONS.md 2026-09-02).
- 2026-09-07 — this file corrected to describe the above; it had still claimed no harvest.

---

## Original analysis (2026-08-24), kept for the record — superseded where noted above

## What the Ratings Board corpus is

One row per released film: `title, year, rating, rationale, embedding`. The rationale is the
short official phrase attached to every MPA rating certificate — e.g. *"Rated R for language
throughout, brief violence and drug use."* kNN over embedded rationales gives "your nearest
released comparables and their actual ratings."

## Provenance analysis

**The facts themselves.** A film's rating and its rationale are facts about the world.
Copyright does not protect facts (*Feist v. Rural*, 499 U.S. 340). The rationale phrases are
short, formulaic descriptors ("brief strong language", "thematic elements") — the kind of short
phrase that fails the originality threshold for copyright (37 CFR 202.1 explicitly excludes
short phrases). CARA's *house style* is not protectable; individual certificate lines are the
weakest possible copyright subject matter.

**Compilation copyright.** A curated database of ratings could carry thin compilation
protection in its selection/arrangement. We avoid inheriting anyone's selection by choosing our
own film set (e.g. top-grossing + festival titles per year, a criterion we define), gathering
each film's rating individually.

**Terms of service.** filmratings.com is the official CARA search tool. Bulk scraping it is a
ToS/CFAA gray zone we do not need to enter: rating + rationale for any given film is
reproduced in dozens of secondary sources (Wikipedia infoboxes, IMDb parental guides, Box
Office Mojo, press kits). Wikipedia text is CC BY-SA; the *facts* extracted from it (title,
year, rating, rationale) are not subject to the share-alike obligation because facts are not
copyrightable, and we store facts, not article prose.

**Trademark.** "MPA", "CARA", and the rating marks are certification marks. Nominative use —
reporting that a film was rated R — is exactly what certification marks exist for. We must not
imply MPA endorsement of GREENLIGHT; the UI already labels the prediction as ours.

## Recommendation

1. ~~Ingest rationale strings from Wikipedia prose~~ **Superseded by the pilot** — see the
   status block above. Film set: ~2,500 titles, 1985–present, ranked by Wikidata sitelink
   count so the comparables are films a judge will recognize. No filmratings.com scraping.
2. Store `source_url` per row so every comparable in the report is itself citable — matching
   the product invariant.
3. Embeddings: Vertex `text-embedding-005` (same model at ingest and query — already assumed
   by `query_precedent`).
4. Attribution line in the report footer: "Rating data compiled from public sources; MPA and
   CARA are trademarks of the Motion Picture Association. GREENLIGHT is not affiliated with or
   endorsed by the MPA."

## Sign-off

- [x] Lalit: approved the content-profile pivot, 2026-08-24
