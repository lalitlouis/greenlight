"""Triage: reads the parsed screenplay, emits Entity[] plus per-desk worklists.

An LlmAgent with a structured output schema and no tools — high-volume extraction,
so it runs on Flash. Writes to state key "triage"; desks read state, never prose.
"""

from __future__ import annotations

from typing import Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from greenlight.agents.common import RETRY

MODEL = "gemini-2.5-flash"

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

Fictional people and places invented by the script are NOT entities. A real song performed or
played is. A real person merely mentioned in dialogue still is — note in context that it is a
verbal mention only.

Then write a worklist for each of the four desks. Worklist items reference an entity_id where
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
    retry_config=RETRY,
    include_contents="none",
)
