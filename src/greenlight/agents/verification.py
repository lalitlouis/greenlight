"""VerificationPanel: one blinded verifier per filed flag, fanned out at runtime.

ADK's ParallelAgent takes a static sub-agent list and the flag count is unknown
until the desks finish, so this is a custom BaseAgent that builds the fan-out per
run (see docs/TECH_SPEC.md). Each verifier sees the claim and its citations — never
the desk's reasoning — and answers one question: does this source support this claim?

- SUPPORTED    flag stands
- PARTIAL      flag stands, severity capped at MEDIUM, marked partially supported
- UNSUPPORTED  flag is dropped and logged; it never reaches the report

Rejected-flag count is a metric we watch: if it is always zero, the verifier is
not doing its job.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any, Literal

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import BaseModel

from greenlight.tools.toolbelt import DESKS

MODEL = "gemini-2.5-flash"
_CONCURRENCY = 10
_MAX_ATTEMPTS = 5

SEVERITY_ORDER = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


class Verdict(BaseModel):
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    reason: str


VERIFIER_PROMPT = """\
You are an independent citation verifier for a screenplay clearance report. You are shown one
claim, the screenplay scenes it anchors to, and the source excerpts cited for it — never the
desk's reasoning. You did not write the claim and you owe its author nothing.

A claim has two halves. Its SCRIPT FACTS (what happens on the page) are verified against the
scene text below, which is authoritative — script facts need no citation, but a claim that
misstates the script fails. Its PREMISE — the legal, regulatory, or industry rule it applies,
and the remedy it asserts — must be supported by the cited excerpts. Excerpts can never contain
the screenplay; never fault them for that.

Answer exactly one question: do the scene text and the cited excerpts together support this
claim?

- SUPPORTED: the script facts are accurate AND the excerpts state or directly entail the
  claim's premise. A general rule genuinely covering this case counts.
- PARTIAL: script facts accurate, but the excerpts support only a weaker, narrower, or
  adjacent premise than the one asserted — or only part of a compound claim.
- UNSUPPORTED: the claim misstates the script, or NO material part of the premise is
  supported — the excerpts are off-topic, contradict it, or the claim reads something into
  them that is not there. If the excerpts genuinely support a material part of the premise,
  that is PARTIAL, not UNSUPPORTED. When a single indivisible assertion sits between PARTIAL
  and UNSUPPORTED, choose UNSUPPORTED: an unsupported severity in this report costs more than
  a lost flag.

REJECT ABSENCE-PREMISED CLAIMS: a finding whose substance is that a hazard, element,
or person is NOT in the script ("no minor present", "no weapons used as written") or
that is conditional on unwritten changes ("if a live animal is added...") asserts
nothing about the screenplay and must be REJECTED regardless of its citations.

REJECT MULTI-STEP INFERENCE: a claim that depends on an assumed fact the script does
not state — a character's age inferred from "college student", commercial injury
inferred from casual dialogue, casting or staging choices the text leaves open — fails
its premise even if the assumption is plausible. The desk asserts; the text decides.

The premise must come from the excerpts, not from your own knowledge. If the premise is true
but these excerpts do not show it, that is not SUPPORTED.

Two cautions on script facts. The scene text shows only the scenes this claim anchors to,
never the whole screenplay, and a scene marked TRUNCATED continues beyond what you see —
absence from shown text is only a misstatement if the shown text positively contradicts the
claim. Never rule "not in the script" against a truncated scene.

CLAIM (severity {severity}, category {category}):
{finding}

REMEDY ASSERTED: {remedy}

SCRIPT CONTEXT (authoritative, scenes {scene_ids}):
{script_context}

CITED EXCERPTS:
{citations}
"""

_MAX_CONTEXT_CHARS = 12000


def _scene_context(flag: dict[str, Any], state: Any) -> str:
    """The flag's anchor scenes, fairly truncated. A truncation is MARKED — a verifier
    concluding "not in the script" from text this function silently cut would reject
    true findings (it happened; see the F204/F301 postmortem in the git history)."""
    text = state.get("script_text", "")
    by_id = {s["scene_id"]: s for s in state.get("scenes", [])}
    scenes = [by_id[sid] for sid in flag["scene_ids"] if sid in by_id]
    if not scenes:
        return "(scene text unavailable)"
    per_scene = _MAX_CONTEXT_CHARS // len(scenes)
    chunks: list[str] = []
    for scene in scenes:
        start, end = scene["raw_span"]
        chunk = text[start:end].strip()
        if len(chunk) > per_scene:
            chunk = chunk[:per_scene] + "\n[... SCENE TRUNCATED — text continues ...]"
        chunks.append(chunk)
    return "\n\n".join(chunks)


def _blinded_prompt(flag: dict[str, Any], script_context: str) -> str:
    citations = "\n\n".join(
        f'[{i + 1}] {c.get("title") or c.get("url") or "untitled"}\n"{c["excerpt"]}"'
        for i, c in enumerate(flag["citations"])
    )
    remedy = f"{flag['remedy']['action']} — {flag['remedy']['detail']}"
    return VERIFIER_PROMPT.format(
        severity=flag["severity"],
        category=flag["category"],
        finding=flag["finding"],
        remedy=remedy,
        scene_ids=", ".join(flag["scene_ids"]),
        script_context=script_context,
        citations=citations,
    )


def apply_verdicts(
    flags: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure function: (surviving flags, rejected flags). PARTIAL caps severity at
    MEDIUM and marks the finding; UNSUPPORTED drops the flag. Missing verdicts keep
    the flag untouched — a broken verifier must not silently delete findings."""
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for flag in flags:
        v = verdicts.get(flag["flag_id"])
        if v is None or v["verdict"] == "SUPPORTED":
            kept.append(flag)
            continue
        if v["verdict"] == "PARTIAL":
            capped = dict(flag)
            if SEVERITY_ORDER.index(capped["severity"]) < SEVERITY_ORDER.index("MEDIUM"):
                capped["severity"] = "MEDIUM"
            capped["finding"] = "[partially supported] " + capped["finding"]
            kept.append(capped)
        else:
            rejected.append({**flag, "rejection_reason": v["reason"]})
    return kept, rejected


async def _verify_flag(
    client: Any, flag: dict[str, Any], script_context: str, sem: asyncio.Semaphore
) -> dict:
    async with sem:
        delay = 10.0
        for attempt in range(_MAX_ATTEMPTS):
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=_blinded_prompt(flag, script_context),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=Verdict,
                        temperature=0.0,
                    ),
                )
                v = Verdict.model_validate_json(res.text)
                return {"verdict": v.verdict, "reason": v.reason}
            except Exception:
                if attempt == _MAX_ATTEMPTS - 1:
                    # Fail open with a marker: never silently drop a flag
                    # because the VERIFIER errored.
                    return {"verdict": "SUPPORTED", "reason": "verifier unavailable"}
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)


async def verify_standalone(
    flags: list[dict[str, Any]], state: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """The same blinded fan-out, runnable outside the agent tree. The salvage
    path uses this when a run aborts after desks filed but before verification —
    a partial report must still be a VERIFIED partial report."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(f: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return f["flag_id"], await _verify_flag(client, f, _scene_context(f, state), sem)

    results = await asyncio.gather(*[_one(f) for f in flags])
    return dict(results)


class VerificationPanel(BaseAgent):
    """Runtime fan-out: one Gemini verifier per flag, concurrently, blinded."""

    async def _verify_one(
        self, client: Any, flag: dict[str, Any], script_context: str, sem: asyncio.Semaphore
    ) -> dict:
        async with sem:
            delay = 10.0
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    res = await client.aio.models.generate_content(
                        model=MODEL,
                        contents=_blinded_prompt(flag, script_context),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=Verdict,
                            temperature=0.0,
                        ),
                    )
                    v = Verdict.model_validate_json(res.text)
                    return {"verdict": v.verdict, "reason": v.reason}
                except Exception:
                    if attempt == _MAX_ATTEMPTS - 1:
                        # Fail open with a marker: never silently drop a flag
                        # because the VERIFIER errored.
                        return {"verdict": "SUPPORTED", "reason": "verifier unavailable"}
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        from google import genai

        state = ctx.session.state
        flags = [f for d in DESKS for f in state.get(f"flags:{d}", [])]
        if not flags:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(role="model", parts=[types.Part(text="No flags to verify.")]),
            )
            return

        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
        sem = asyncio.Semaphore(_CONCURRENCY)

        async def _one(f: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            return f, await self._verify_one(client, f, _scene_context(f, state), sem)

        # Stream each verdict as it lands: the challenge-and-ruling is the part
        # of the run worth watching, so it must not arrive as one silent batch.
        verdicts: dict[str, dict[str, Any]] = {}
        for fut in asyncio.as_completed([_one(f) for f in flags]):
            f, v = await fut
            verdicts[f["flag_id"]] = v
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"⚖ {f['flag_id']}|{f['category']}|{f['severity']}|"
                            f"{v['verdict']}|{v['reason'][:160]}"
                        )
                    ],
                ),
            )
        kept, dropped = apply_verdicts(flags, verdicts)

        rejected = [fid for fid, v in verdicts.items() if v["verdict"] == "UNSUPPORTED"]
        summary = (
            f"Verified {len(flags)} flags: "
            f"{sum(v['verdict'] == 'SUPPORTED' for v in verdicts.values())} supported, "
            f"{sum(v['verdict'] == 'PARTIAL' for v in verdicts.values())} partial, "
            f"{len(rejected)} rejected" + (f" ({', '.join(rejected)})" if rejected else "") + "."
        )
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(
                state_delta={
                    **{f"verdicts:{fid}": v for fid, v in verdicts.items()},
                    "verified_flags": kept,
                    "rejected_flags": dropped,
                }
            ),
            content=types.Content(role="model", parts=[types.Part(text=summary)]),
        )


agent = VerificationPanel(
    name="verification_panel",
    description="Blinded per-flag citation verification; can reject flags.",
)
