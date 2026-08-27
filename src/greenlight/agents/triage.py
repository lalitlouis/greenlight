"""Triage: reads the parsed screenplay, emits Entity[] plus per-desk worklists.

An LlmAgent with a structured output schema and no tools — high-volume extraction,
so it runs on Flash. Writes to state key "triage"; desks read state, never prose.
"""

from __future__ import annotations

from typing import Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from greenlight.agents.common import GEN_CONFIG, tool_error_shield
from greenlight.models import FLASH_MODEL

MODEL = FLASH_MODEL

EntityType = Literal[
    "BRAND",
    "TRADEMARK",
    "MUSIC",
    "PERSON",
    "LOCATION",
    "ARTWORK",
    "VEHICLE",
    "FILM_CLIP",
    "PUBLICATION",
    "ORGANIZATION",
]


class Entity(BaseModel):
    """Mirror of schemas/entity.schema.json. Do not drift from it."""

    entity_id: str = Field(description="Sequential id: E001, E002, ...")
    type: EntityType
    surface: str = Field(description="Exact text as written in the script.")
    scene_ids: list[str] = Field(
        description="Scene ids where it appears, using the [S###] ids marked in the script."
    )
    context: str = Field(
        description="The sentence(s) around it — what a researcher needs to disambiguate it."
    )
    depicted_negatively: bool = Field(
        description="True if shown in a negative light. Load-bearing: flips a brand from "
        "'courtesy letter' to 'will never clear'."
    )
    prominence: Literal["BACKGROUND", "FEATURED", "PLOT_CRITICAL"]


class WorklistItem(BaseModel):
    entity_id: str = Field(description="Entity this item concerns, or '' for scene-level work.")
    note: str = Field(description="One line: what the desk should establish, and where to look.")


class TriageOutput(BaseModel):
    entities: list[Entity]
    clearance_counsel: list[WorklistItem] = Field(
        description="Rights/clearance work: brands, music, real people, artwork, clips, insignia."
    )
    ratings_board: list[WorklistItem] = Field(
        description="MPA rating drivers: language, violence, drugs, themes — with scenes."
    )
    safety_underwriter: list[WorklistItem] = Field(
        description=(
            "Physical production risk: stunts, fire/pyro, water, night, minors, animals, weapons."
        )
    )
    territory_censor: list[WorklistItem] = Field(
        description=(
            "Content likely cut or banned in US/UK/CN/UAE: supernatural, drugs, "
            "alcohol, state actors."
        )
    )


INSTRUCTION = """\
You are the triage desk of a screenplay clearance department. Below is a screenplay in which
every scene heading is marked with its scene id, like [S004].

Extract every clearance-relevant entity: real-world brands, trademarks, songs and recordings,
real people, recognizable locations, artworks, vehicles, film/TV clips, publications, and
organizations. For each, record the exact surface text, the scene ids where it appears, enough
surrounding context for a researcher who has not read the script, whether it is depicted
negatively, and its prominence (BACKGROUND set dressing, FEATURED, or PLOT_CRITICAL if the story
depends on it).

A brand a character mocks, insults, or blames IS depicted negatively — dialogue like
"tastes like X" is disparagement even when the tone is comic; set depicted_negatively
accordingly, because it flips the clearance posture entirely.

Fictional people and places invented by the script are NOT entities. A real song performed or
played is. A real person merely mentioned in dialogue still is — note in context that it is a
verbal mention only.

Then write a worklist for each of the four desks. Coverage matters more than brevity — a
hazard or censorship exposure missing from a worklist is invisible to every desk downstream:
- clearance_counsel: every extracted entity that implicates rights — including VISUAL
  WORKS described in action lines: named paintings/prints on walls, murals, sculptures,
  posters, and DISTINCTIVE CUSTOM TATTOOS on characters (especially with a named artist).
  Extract each as an ARTWORK entity; set dressing is still a copyrighted reproduction.
  PLUS every named
  character and every invented business, venue, publication, or address, for the
  name-commonality sweep (does this fictional name collide with a distinctive real person
  or business?). List them even when they look safely fictional; establishing that is the
  desk's job, not yours.
- ratings_board: every language, violence, drug/alcohol, sexuality, and thematic driver.
- safety_underwriter: every stunt, fire/pyro, water scene, night exterior, weapon, animal, and
  every scene where a MINOR is present near any of these.
- territory_censor: any supernatural or occult content (including a ghost played straight),
  drug use, alcohol prominence, sexuality, religious content, and depictions of state
  authority condoning illegal acts — these are the categories censors act on.

Worklist items reference an entity_id where
one applies; for scene-level work (a stunt, a rating beat) use entity_id "" and name the scenes
in the note. Be specific about what the desk must establish; do not pre-judge the answer.

SCREENPLAY:

{script_annotated}
"""

agent = LlmAgent(
    name="triage",
    model=MODEL,
    description="Extracts clearance-relevant entities and builds per-desk worklists.",
    instruction=INSTRUCTION,
    output_schema=TriageOutput,
    output_key="triage",
    generate_content_config=GEN_CONFIG,
    on_tool_error_callback=tool_error_shield,
    include_contents="none",
)
