"""Coverage and Pitch desks: two LlmAgents on Pro, structured output, run in
parallel. Both read the same annotated script from session state.

Coverage speaks in professional reader house style and must anchor every note
to scene ids — an unanchored note is an opinion, an anchored one is feedback.
The pitch package leaves comps EMPTY on purpose: comparables come from the
ratings corpus by retrieval afterwards (cited), never from the model's memory.
"""

from __future__ import annotations

from typing import Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from greenlight.agents.common import GEN_CONFIG, PRO, tool_error_shield


class AnchoredNote(BaseModel):
    scene_ids: list[str] = Field(description="Scenes the note is about, e.g. ['S004'].")
    note: str = Field(description="One tight paragraph. Specific, not generic.")


class Coverage(BaseModel):
    logline_as_read: str = Field(
        description="The story as it actually reads, one sentence. Not a sales line."
    )
    synopsis: str = Field(description="One paragraph, 4-7 sentences, present tense.")
    genre: str
    tone: str
    strengths: list[AnchoredNote] = Field(description="3-5, each anchored to scenes.")
    weaknesses: list[AnchoredNote] = Field(
        description="3-5, each anchored to scenes. Honest — a soft read helps nobody."
    )
    character_notes: list[str] = Field(description="One line per principal character.")
    dialogue_note: str
    pacing_note: str
    verdict: Literal["PASS", "CONSIDER", "RECOMMEND"] = Field(
        description="Industry coverage verdict. RECOMMEND is rare and must be earned."
    )
    verdict_reason: str = Field(description="Two sentences a busy exec will actually read.")


COVERAGE_INSTRUCTION = """\
You are a professional script reader writing coverage for a production company. You have read
thousands of screenplays; your name is on this report, and executives act on your verdicts.

Below is the screenplay, scene ids marked like [S004]. Write coverage in house style:

- The logline_as_read is the story as it sits on the page, not what it aspires to be.
- Strengths and weaknesses are anchored to specific scenes and specific craft: structure,
  character want/need, escalation, dialogue distinctiveness, imagery. "The dialogue is good"
  is not a note; "Crow's eulogy in S004 does character work the flashback never could" is.
- Be honest about weaknesses. Writers pay for the note that stings and fixes the script.
- Verdict: PASS (not for us / not ready), CONSIDER (real strengths, real reservations),
  RECOMMEND (exceptional — rare). Calibrate like a reader whose RECOMMENDs are tracked.

SCREENPLAY:

{script_annotated}
"""

coverage_agent = LlmAgent(
    name="coverage_desk",
    model=PRO,
    description="Professional script coverage: logline, synopsis, anchored notes, verdict.",
    instruction=COVERAGE_INSTRUCTION,
    output_schema=Coverage,
    output_key="coverage",
    include_contents="none",
    generate_content_config=GEN_CONFIG,
    on_tool_error_callback=tool_error_shield,
)


class Pitch(BaseModel):
    logline_options: list[str] = Field(
        description="2-3 distinct sales loglines: protagonist + goal + obstacle + stakes."
    )
    one_page_synopsis: str = Field(
        description="3-4 paragraphs, present tense, ends on the emotional promise — a selling "
        "document, not a beat sheet."
    )
    genre: str
    tone: str
    target_audience: str = Field(description="Who buys a ticket, in one concrete sentence.")
    why_now: str = Field(description="One sentence: why this story lands in today's market.")


PITCH_INSTRUCTION = """\
You are a development executive packaging a screenplay for the market. Below is the script,
scene ids marked like [S004]. Build the pitch materials a producer attaches to a query:

- Loglines sell without lying: what actually happens in this script, sharpened.
- The synopsis is the read-this-instead-of-the-script document. Voice matters.
- Do NOT invent comparable films — comparables are attached separately from a released-film
  database, with sources. Your job is the words, not the comps.

SCREENPLAY:

{script_annotated}
"""

pitch_agent = LlmAgent(
    name="pitch_desk",
    model=PRO,
    description="Pitch package: loglines, one-page synopsis, audience, positioning.",
    instruction=PITCH_INSTRUCTION,
    output_schema=Pitch,
    output_key="pitch",
    include_contents="none",
    generate_content_config=GEN_CONFIG,
    on_tool_error_callback=tool_error_shield,
)
