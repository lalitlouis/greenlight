# PRD — GREENLIGHT

## Problem

Before a film shoots, the screenplay goes through clearance: four separate desks read the same
script looking for different ways it will cost money or fail to release.

- **Rights counsel** — brands, music, real people, artwork, locations.
- **Ratings board** — what MPA rating the content will draw.
- **Safety underwriter** — stunts, pyro, animals, minors; what the insurer will require.
- **Territory censors** — what gets cut or banned in each release market.

The work is manual, serial, and expensive. Findings arrive as a PDF memo weeks later, by which
point the budget is locked. The people who most need it — independent producers — cannot afford
it at all.

## Users

**Primary:** independent producers and line producers deciding whether a script is affordable to
shoot, and what it will cost to fix.
**Secondary:** screenwriters who want to know what will get flagged before they submit.

## What GREENLIGHT does

Takes a screenplay. Runs the four desks concurrently as agents. Returns:

1. **Marked-up script** — every flag anchored to its scene.
2. **Production Risk Report** — severity-ranked findings, each with a citation, a concrete
   remedy, and a cost/schedule estimate.
3. **Greenlight Score** (0–100) plus an evidence-based MPA rating prediction with comparable
   released films.

## The one non-negotiable product rule

**A finding without a citation does not render.**

This is the whole differentiator. Anyone can ask a model "what's risky in this script" and get a
confident paragraph. GREENLIGHT returns claims a producer can hand to a lawyer, each backed by
verbatim sourced text. The `flag` schema enforces `citations` with `minItems: 1`, so this is a
structural guarantee rather than a matter of prompt discipline.

## Scope

**In:**
- Fountain and PDF screenplay input
- Four gatekeeper agents, running concurrently
- Live web research per entity, with citations
- Precedent-based rating prediction with comparables
- Deployed web app: upload → live progress → report → marked-up script

**Out (explicitly, and stated in the UI):**
- Cost figures are industry rules-of-thumb, **not live quotes**. Labelled as estimates.
- Four territories (US, UK, China, UAE), not every market.
- Underwriting is heuristic, not a carrier API.
- No auth, no multi-user, no persistence between sessions.
- Not legal advice. Stated in the product.

## Success criteria

1. End-to-end run on a feature-length screenplay in under three minutes.
2. Every rendered flag has at least one working citation link.
3. A film professional reading the report finds at least one thing they would not have caught.
4. The four gatekeepers visibly run concurrently — the fan-out is legible in the UI.

## Demo narrative

Music clearance leads, not brands: a script uses a well-known song over a funeral. Two
rightsholders, ~$45k, six-week negotiation — surprising, specific, and puts no third-party logo
on screen (a hard rule for the submission video).

The strongest single moment is the Ratings Board: *"your nearest comparables are these eight
released films, seven rated R. You are targeting PG-13. Here are the three beats to cut."*
That is evidence, not an opinion.
