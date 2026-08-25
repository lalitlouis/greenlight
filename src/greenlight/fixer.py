"""The fix desk: turn a finding's remedy into concrete, minimal script patches.

Every patch is an exact-match find/replace inside one scene, validated here
before it ever reaches the page: the `find` text must occur exactly once in
that scene, so applying a patch is deterministic and previewing it is honest.
The writer stays the author — these are proposals with a rationale, not edits.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pydantic import BaseModel, Field

MODEL = "gemini-2.5-pro"
MAX_SCENE_CHARS = 9000
_ATTEMPTS = 2


class Patch(BaseModel):
    scene_id: str = Field(description="Scene the patch applies to, e.g. 'S004'.")
    find: str = Field(
        description="VERBATIM text copied from the scene — the exact lines to replace, "
        "unique within that scene. Include enough surrounding words to be unambiguous."
    )
    replace: str = Field(description="The replacement text, matching screenplay format.")
    rationale: str = Field(description="One line: why this specific change clears the finding.")


class FixProposal(BaseModel):
    summary: str = Field(
        description="Two sentences to the writer: what the fix does and what it preserves."
    )
    patches: list[Patch]


PROMPT = """\
You are a working script doctor hired to clear one specific production-risk finding with the
smallest possible change to the screenplay. You respect the writer's voice above all: match
their rhythm, formatting, and character diction exactly. Never fix anything beyond this
finding.

THE FINDING ({severity}, {category}):
{finding}

THE PRESCRIBED REMEDY: {remedy_action} — {remedy_detail}

RULES:
- Each patch's `find` must be copied VERBATIM from the scene text below and be unique within
  its scene. Patches that do not match exactly will be discarded.
- Smallest change that clears the finding. Replacing a real brand or song: invent ONE fictional
  substitute and use it consistently across every patch.
- CUT remedies: remove or rewrite the specific beat, keeping the surrounding action coherent.
- Keep screenplay formatting (caps for character cues, action in prose).

THE SCENES:

{scenes}
"""


def validate_patches(
    patches: list[dict[str, Any]], scene_texts: dict[str, str]
) -> list[dict[str, Any]]:
    """Only patches that apply deterministically survive: known scene, non-empty
    find, exactly one occurrence, and an actual change."""
    valid = []
    for p in patches:
        scene = scene_texts.get(p.get("scene_id", ""))
        find = p.get("find", "")
        if not scene or not find.strip():
            continue
        if scene.count(find) != 1:
            continue
        if p.get("replace", "") == find:
            continue
        valid.append(p)
    return valid


async def propose_fix(flag: dict[str, Any], scene_texts: dict[str, str]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    scenes_block = "\n\n".join(
        f"[{sid}]\n{text[:MAX_SCENE_CHARS]}" for sid, text in scene_texts.items()
    )
    remedy = flag.get("remedy") or {}
    prompt = PROMPT.format(
        severity=flag.get("severity", ""),
        category=flag.get("category", ""),
        finding=flag.get("finding", ""),
        remedy_action=remedy.get("action", "REVIEW"),
        remedy_detail=remedy.get("detail", ""),
        scenes=scenes_block,
    )

    last_error = "no valid patches"
    for _ in range(_ATTEMPTS):
        try:
            res = await client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FixProposal,
                    temperature=0.3,
                ),
            )
            proposal = FixProposal.model_validate_json(res.text)
            patches = validate_patches([p.model_dump() for p in proposal.patches], scene_texts)
            if patches:
                return {"summary": proposal.summary, "patches": patches}
            last_error = "the drafted patches did not match the scene text"
        except Exception as e:
            last_error = f"{type(e).__name__}"
            await asyncio.sleep(5)
    return {"error": f"Could not draft a clean fix ({last_error}). Try again."}
