"""Shared evidence boundaries for desks and their independent verifiers.

These are instructions about the input's evidentiary scope, not legal rules.
Keep them shared so a desk cannot be punished for respecting that scope.
"""

PRODUCTION_EVIDENCE = """\
SCRIPT FACTS AND PRODUCTION FACTS ARE DIFFERENT:
- The screenplay establishes fictional events, character ages, story locations and dialogue.
  It does not establish the production's permits, shooting jurisdiction/date, insurance
  terms, performer ages, or practical-effects plan. These are unconfirmed in this input.
- A character saying 'we have no permit', a fictional burn ban, or an illegal act in the
  story is NOT evidence that the film crew lacks permission or will violate a rule.
  Flag the actual depicted hazard and the planning it needs; leave the production's
  compliance status unknown. Story geography is not the shooting jurisdiction.
- A child character is not proof of a child performer. Preserve the depicted hazard,
  recommend confirming casting/staging, and make minor-performer safeguards conditional
  on actual casting. Never turn a character age into a confirmed work-hour violation.
- Depiction does not prove live execution: a gunshot may use a prop/VFX, and fire or a
  fall may use effects/doubles. Recommend a safe method supported by the source without
  asserting that live ammunition, practical pyro, or an exposed performer is confirmed.
- A conditional safeguard for an EXISTING depicted hazard is legitimate planning advice.
  A finding about a hazard that would exist ONLY after an unwritten change is not.
- Distinguish a cited law, recommended industry practice, and an insurer's own condition.
  A safety bulletin is not itself proof of illegality or denial of insurance.
"""

RATINGS_EVIDENCE = """\
RATINGS EVIDENCE CONTRACT:
- Count parsed dialogue separately from action prose. Voiceover/off-screen dialogue and
  lyrics formatted as dialogue belong to the dialogue count. Profanity in description
  is not spoken dialogue. Visible text and audio/lyrics described in action need a scene
  read to establish presentation; do not silently add them to the dialogue-only census.
- The whole-text census is a review inventory, not an audience-heard count. A zero dialogue
  count is not proof of zero audible content when action describes speech or a recording.
- Distinguish depicted content from discussion, recollection, threat, metaphor or negation.
  Sexual references remain sexual references; drug discussion remains drug references.
  Do not automatically relabel discussion as 'thematic elements' or assign it a rating.
- Descriptor marginals describe observed associations, not mandatory classification rules.
  A rule claim needs the operative MPA rule quoted in its OWN citations, including relevant
  exceptions. Preserve the special-vote exception for the expletive rule; do not promise R
  solely from a count or PG-13 solely from reducing it. Comparables support the overall
  prediction, not a mandatory threshold for one driver.
- Estimates and proposed cuts are conditional screenplay forecasts. Official-rationale
  calibration does not establish end-to-end screenplay accuracy or guarantee a cut's rating.
"""
