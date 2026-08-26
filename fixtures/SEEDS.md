# SLACK TIDE — seed map (ground truth)

What was deliberately planted in `slack_tide.fountain`, desk by desk. This is the eval sheet:
a desk that misses a seed has under-investigated; a desk that flags a trap and survives
verification means the verifier is broken. Do not "fix" the screenplay to make a desk look
better — fix the desk.

The screenplay is original work (contest rule). It *references* real entities, because
researching real entities is the product.

## Clearance Counsel

| Seed | Where | Type | Expected outcome |
|---|---|---|---|
| **"Hallelujah" — Jeff Buckley, Columbia recording** | Eli's letter; the church service; reprise over the climax | MUSIC, PLOT_CRITICAL | **The ownership chase (demo moment #2).** Composition (Leonard Cohen → publisher) and master (Columbia/Sony) are separately owned; the letter demands the specific master, so a soundalike or cover is off the table. Expect BLOCKER/HIGH, sync + master licenses, five-figure estimate, weeks of negotiation. |
| Hopper's *Nighthawks* print, "hanging slightly crooked" | Wheelhouse set dressing; ghost scene dialogue | ARTWORK, FEATURED | Hopper d. 1967; not public domain. Set-dressing clearance or replacement. |
| Polaroid of Eli arm-wrestling Bruce Springsteen | Behind the register | PERSON + photo | Compound flag: living person's likeness AND the photograph's copyright. |
| *Jaws* playing on the bar TV | Wheelhouse, muted VHS | FILM_CLIP, BACKGROUND | Clip license (expensive) or replace with original/licensed footage. |
| Gloucester Daily Times framed front page | Wheelhouse wall | PUBLICATION, BACKGROUND | Masthead + page layout clearance or a fictional prop paper. |
| Coors Light — "tastes like a wet napkin" | Crow, wake scene setup | BRAND, `depicted_negatively: true` | Disparagement — will never clear; remedy is REPLACE with fictional brand. The cassette `clearance_brand_disparagement.json` is this doctrine. |
| Boston Whaler skiff | Climax | VEHICLE, FEATURED, neutral | Low/FYI — neutral depiction, trade-dress courtesy at most. |
| Fenway Park story | Pier scene dialogue | LOCATION, dialogue-only | Verbal reference, not depicted — LOW/FYI at most. A desk that files this as HIGH is over-flagging. |
| U.S. Coast Guard — uniform, marked vehicle, Reyes | Boatyard scene | ORGANIZATION | Federal insignia depiction rules; also an officer shown bending rules — expect a flag. |

| **Crow's schooner tattoo** | S002 — "Teddy Krane's design, inked at his Rockland parlor" | A distinctive custom tattoo by a NAMED artist, prominently described on camera — a copyrighted visual work (the Whitmill v. Warner Bros. scenario). Expect artwork_license with a visual-artist release remedy. Tests the ART ON SCREEN sweep against a depicted (not recounted) design. |

### Verifier traps (harvest the rejected-flag demo moment here)

| Trap | Where | Why the obvious flag is wrong |
|---|---|---|
| **"Hard Times Come Again No More"** — named in action as "the old Stephen Foster hymn" | Crow sings a cappella at the funeral | Stephen Foster d. 1864; composition is public domain. No sync/publishing license exists to obtain. A desk that pattern-matches "song performed → sync license" files a flag whose citations will not support it. Performed live in-scene, so there is no master recording either. |
| **"a dented Thermos"** | Sam's cocoa; reprised at the jetty | "Thermos" was ruled a genericized trademark in the US (*King-Seeley Thermos Co. v. Aladdin*, 1963). A trademark-clearance flag on the word is unsupportable in the US market. (A careful desk might file a LOW territory note instead — genericide is US-specific — which the verifier should sustain.) |

## Ratings Board

Target rating for the demo run: **PG-13**. Seeds are calibrated so comparables say R and the
"beats to cut" are obvious and few (demo moment #3).

| Beat | Where | Note |
|---|---|---|
| **F-bombs: exactly 3** | Mara (pier), Teddy (wake), Danny (climax) | MPA rule of thumb: one non-sexual use survives PG-13. **The cut list is: keep Danny's, cut Mara's and Teddy's** — the emotional argument for which one survives is demo material. |
| Bar fight with blood | The wake | "brief violence" — survivable at PG-13 if language is cut. |
| Shared joint | Pier scene | Post-2007 MPA weighs drug use heavily at PG-13; likely "drug material" descriptor. |
| Pervasive alcohol; a child present in a bar throughout | Wheelhouse scenes | Descriptor material, not rating-driving. |
| Grief/thematic intensity, a ghost | Throughout | "thematic elements." |

## Safety Underwriter

The climax stacks the underwriter's four worst words: **fire, water, night, minor.**

| Seed | Where | Expected |
|---|---|---|
| Vessel burn with diesel accelerant + homemade mortar display | Boatyard prep, climax | BLOCKER as written: licensed marine pyro coordinator, fire marshal permit, safety boats. The script *says* there is no permit — Reyes states it on the page. |
| Night water stunt — Mara dives from a skiff near a burning vessel | Climax | Stunt coordinator, water-safety divers, night-water protocols. |
| Sam (10) in a skiff, at night, near open flame; stands up mid-scene | Climax | Minor on water at night: work-hour limits, guardian, dedicated safety. "Sit DOWN" is on the page — the hazard is textual. |
| Barnacle the dog aboard the skiff | Climax | Animal handler, AHA supervision. |
| Three-volley rifle salute | Churchyard | Blank-firing weapons: armorer, notifications, hearing protection for the minor who is explicitly present covering his ears. |
| Bar-fight glass break + blood | The wake | Breakaway glass, minor stunt flag. |

## Territory Censor

| Seed | Where | Expected |
|---|---|---|
| **Eli's ghost — an actual returned dead person, played straight** | Wheelhouse night scene | China: supernatural depiction is a censorship problem; the scene is the emotional core, so the remedy conversation ("cut it and the film has no heart") is real. Expect HIGH for CN. |
| Cannabis use, casual and unpunished | Pier | UAE/CN cuts; UK 15-cert material. |
| Alcohol-centric setting; profanity | Throughout | UAE edits. |
| A federal officer waving off a legal violation | Boatyard | CN sensitivity to depiction of state officers; worth a LOW/FYI. |

## Adjudicator interaction seed

The F-bomb cut list (Ratings) touches the pier scene and the climax — both scenes carry
clearance/safety flags, and the climax carries the "Hallelujah" reprise. A remedy that trims the
climax dialogue interacts with nothing; a remedy that cut the *scene* would. The designed
interaction: **cutting the ghost scene for China (Territory) removes the scene where the
Nighthawks print is discussed (Clearance)** — the Adjudicator should notice the Nighthawks flag's
scene list shrinks and re-check with Clearance Counsel.

## Bookkeeping

- Exactly **3** instances of the F-word. `grep -c -i fuck` must return 3; if an edit changes
  this, update the Ratings section above.
- The run committed to `runs/` for the demo must contain **at least one verifier rejection**
  (expected source: the two traps above). Harvest, don't script.
