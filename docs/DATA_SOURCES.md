# Data sources — provenance check

Status: **approved 2026-08-24 (content-profile pivot).** A 250-film pilot
(`scripts/ingest_ratings.py pilot`) measured a 1% extraction rate for CARA rationale strings in
English Wikipedia prose — articles rarely quote them (8 of 94 top articles even mention the
MPAA). The rationale-string plan is dead; the corpus pivots to **content profiles**:

- **Ratings** from Wikidata P1657 (validated by the pilot: clean, structured, CC0, scales).
- **Embedding text** from each film's Wikipedia article lead + plot section via the official
  MediaWiki API — a richer content signal than a one-line rationale in any case.
- **Display line** per comparable: a short attributed quote from the article lead, with the
  source URL. Every comparable shown in the report is itself citable.
- The demo beat is unchanged in substance: "your screenplay's content profile sits nearest
  these released films — seven of eight are rated R." The evidence is the neighbors' rating
  distribution, not CARA's phrasing.

Original analysis below, kept for the record.

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
