# Data sources — provenance check

Status: **analysis complete, needs Lalit's sign-off before ingest.** The comparables beat
(DEMO.md moment #3) depends on this corpus; the go/no-go is needed this week.

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

1. **Ingest from Wikipedia infobox/prose statements of MPA ratings + rationales** for a film
   set we select (~2,000–4,000 titles, 1990–present, skewed to titles a judge will recognize).
   No filmratings.com scraping.
2. Store `source_url` per row so every comparable in the report is itself citable — matching
   the product invariant.
3. Embeddings: Vertex `text-embedding-005` (same model at ingest and query — already assumed
   by `query_precedent`).
4. Attribution line in the report footer: "Rating data compiled from public sources; MPA and
   CARA are trademarks of the Motion Picture Association. GREENLIGHT is not affiliated with or
   endorsed by the MPA."

## Sign-off

- [ ] Lalit: approve ingest per the recommendation above
