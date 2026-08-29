"""VerificationPanel: one blinded verifier per filed flag, fanned out at runtime.

ADK's ParallelAgent takes a static sub-agent list and the flag count is unknown
until the desks finish, so this is a custom BaseAgent that builds the fan-out per
run (see docs/TECH_SPEC.md). Each verifier sees the claim and its citations — never
the desk's reasoning — and answers one question: does this source support this claim?

- SUPPORTED    flag stands
- PARTIAL      flag stands at its filed severity, marked partially supported
- UNSUPPORTED  flag is dropped and logged; it never reaches the report

Rejected-flag count is a metric we watch: if it is always zero, the verifier is
not doing its job.
"""

from __future__ import annotations

import asyncio
import os
import re as _re
from collections.abc import AsyncGenerator
from typing import Any, Literal

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import BaseModel

from greenlight.models import FLASH_MODEL
from greenlight.tools.toolbelt import DESKS

# Same HTTP-layer 429 ladder as the agents (see agents/common.py): the genai
# client defaults to NO retries, and a verifier 429 must not sink a run.
_RETRY_HTTP = types.HttpOptions(
    timeout=480_000,  # per-request wall — a stalled stream retries instead of hanging
    retry_options=types.HttpRetryOptions(
        attempts=8, initial_delay=10, max_delay=120, exp_base=2, jitter=0.5
    ),
)


MODEL = FLASH_MODEL
_CONCURRENCY = 10
_MAX_ATTEMPTS = 5

SEVERITY_ORDER = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


class Verdict(BaseModel):
    verdict: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED"]
    reason: str
    failure_mode: Literal[
        "none", "script_misstatement", "premise_unsupported", "citation_offtopic"
    ] = "none"


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

REJECT WRONG-STANDARD CITATIONS: when a claim's authority is a named standard (a
safety bulletin, statute, or guideline) and the excerpts show that standard governs
a DIFFERENT activity than the one depicted — a vehicle camera-rig bulletin cited
against a character simply driving off — that is UNSUPPORTED with citation_offtopic.
This rule is about citing the WRONG standard, not about weak sourcing: when the
excerpts do support the core obligation (a license is needed, a coordinator is
standard practice) and only an edge of the claim is overstated or under-cited,
PARTIAL remains the correct verdict — do not escalate ordinary sourcing gaps to
UNSUPPORTED.

When you answer UNSUPPORTED, also classify WHY in failure_mode:
- script_misstatement — the claim misstates the screenplay (fatal: the finding is wrong);
- premise_unsupported — the script facts hold but the excerpts do not establish the premise
  (a sourcing failure: the claim may be true with better citations);
- citation_offtopic — the excerpts are about something else entirely (also a sourcing failure).
For SUPPORTED and PARTIAL verdicts, failure_mode is "none".

The premise must come from the excerpts, not from your own knowledge. If the premise is true
but these excerpts do not show it, that is not SUPPORTED.

Two cautions on script facts. The scene text shows ONLY the scenes labeled above (===
S### ===), never the whole screenplay, and a scene marked TRUNCATED continues beyond what
you see — absence from shown text is only a misstatement if the shown text positively
contradicts the claim. Never rule "not in the script" against a truncated scene, and NEVER
assert what is or is not in a scene whose labeled text you were not given — a claim
resting on unshown scenes is at most premise_unsupported, never script_misstatement.
Fabricating a specific absence ("X is not mentioned in S023") about unshown text once
killed a true finding.

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
    # The claim's evidence sometimes lives outside its anchor scenes (a desk
    # anchored a Sbarro finding at S019 while quoting S023; the verifier,
    # shown only S019, fabricated "Sbarro is not mentioned in S023" and killed
    # a true finding). Include every scene the FINDING ITSELF references.
    referenced = _re.findall(r"\bS\d{3}\b", str(flag.get("finding") or ""))
    sids = list(dict.fromkeys([*flag["scene_ids"], *referenced]))
    scenes = [by_id[sid] for sid in sids if sid in by_id]
    if not scenes:
        return "(scene text unavailable)"
    # Floor: a wide flag must still give the verifier enough of each scene to
    # judge — 480-char slivers made it (correctly) refuse to rule, which turned
    # the widest flags into the least-verified ones.
    per_scene = max(1200, _MAX_CONTEXT_CHARS // len(scenes))
    chunks: list[str] = []
    for scene in scenes:
        start, end = scene["raw_span"]
        chunk = text[start:end].strip()
        if len(chunk) > per_scene:
            chunk = chunk[:per_scene] + "\n[... SCENE TRUNCATED — text continues ...]"
        chunks.append(f"=== {scene['scene_id']} ===\n{chunk}")
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
            if v is not None and v.get("fail_open"):
                # the verifier never ran — the flag survives, but it must not
                # impersonate a verified finding on any surface
                kept.append({**flag, "verification_unavailable": True})
            else:
                kept.append(flag)
            continue
        if v["verdict"] == "PARTIAL":
            marked = dict(flag)
            # Severity is a RISK judgment and stays untouched: the old MEDIUM
            # cap parked close-proximity blank fire below a location fee in
            # the sort order because its citation carried a caveat. PARTIAL is
            # a visible verification marker, not a risk downgrade.
            marked["finding"] = "[partially supported] " + marked["finding"]
            kept.append(marked)
        else:
            recoverable = v.get("failure_mode") in ("premise_unsupported", "citation_offtopic")
            rejected.append(
                {
                    **flag,
                    "rejection_reason": v["reason"],
                    "failure_mode": v.get("failure_mode", "none"),
                    "recoverable": recoverable and not flag.get("resourced"),
                }
            )
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
                # mirror _verify_one: without failure_mode a salvage-path
                # rejection is permanently mislabeled "none" on the record
                return {"verdict": v.verdict, "reason": v.reason, "failure_mode": v.failure_mode}
            except Exception:
                if attempt == _MAX_ATTEMPTS - 1:
                    # Fail open with a marker: never silently drop a flag
                    # because the VERIFIER errored.
                    return {
                        "verdict": "SUPPORTED",
                        "reason": "verifier unavailable",
                        "fail_open": True,
                    }
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
        http_options=_RETRY_HTTP,
    )
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(f: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return f["flag_id"], await _verify_flag(client, f, _scene_context(f, state), sem)

    results = await asyncio.gather(*[_one(f) for f in flags])
    return dict(results)


_RESOURCE_CAP = 6  # re-source the worst-hit few, not the world
_RESOURCE_CITES = 3  # replacement citations per re-sourced flag


def _fresh_citations(
    flag: dict[str, Any], state: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """One live search aimed at the claim's premise; top verbatim excerpts
    become replacement citations. Module-level so tests can monkeypatch.

    The result passes the SAME tier gate a filed flag faces: a re-sourced
    BLOCKER/HIGH/MEDIUM flag once shipped on background hosts because this
    path bypassed file_flag entirely. Background-host excerpts are dropped
    here for MEDIUM+ severities; the search is grouped under the run's
    Parallel session and counted in run telemetry."""
    from greenlight.tools import toolbelt

    state = state or {}
    cat = str(flag.get("category") or "")
    lead = str(flag.get("finding", ""))[:120]
    # Category-matched retrieval: six of seven rejections in one run shared
    # "right claim, wrong authority class" — a generic query re-found the
    # same wrong class. Aim the re-source at the authority the claim needs.
    if cat.startswith(("location_release", "trade_libel_venue")):
        query_seed = f"filming location agreement rates production {lead}"
    elif cat.startswith("rating_"):
        query_seed = f"CARA MPA rating rationale {cat.removeprefix('rating_')} filmratings {lead}"
    elif cat.startswith(("stunt_", "firearms", "minor_safety", "animal_safety", "weather")):
        query_seed = f"CSATF safety bulletin requirements {cat.replace('_', ' ')} {lead}"
    elif cat.startswith("territory_"):
        query_seed = f"{cat.replace('_', ' ')} media regulation film censorship {lead}"
    elif cat.startswith(("sync_", "master_", "music")):
        query_seed = f"sync master use license practice {lead}"
    else:
        query_seed = f"{cat.replace('_', ' ')} {lead}"
    try:
        res = toolbelt._live_search(
            objective=f"Authoritative support for: {str(flag.get('finding', ''))[:200]}",
            queries=[query_seed],
            session_id=str(state.get("parallel_session_id") or "") or None,
        )
        state["resource_searches"] = int(state.get("resource_searches") or 0) + 1
    except Exception:
        return []
    strict = flag.get("severity") in ("BLOCKER", "HIGH", "MEDIUM")
    cits: list[dict[str, Any]] = []
    for r in res.get("results", []) or []:
        if strict and toolbelt._is_background_host(r.get("url") or ""):
            continue  # the tier gate, applied where file_flag would have applied it
        for ex in (r.get("excerpts") or [])[:1]:
            cits.append(
                {
                    "source_type": "web",
                    "title": r.get("title", ""),
                    "url": r.get("url"),
                    "excerpt": ex,
                    "retrieved_at": None,
                    "via": "parallel_search_resource",
                }
            )
        if len(cits) >= _RESOURCE_CITES:
            break
    return cits


class VerificationPanel(BaseAgent):
    """Runtime fan-out: one Gemini verifier per flag, concurrently, blinded."""

    async def _correct_finding(
        self, client: Any, flag: dict[str, Any], script_context: str, sem: asyncio.Semaphore
    ) -> str | None:
        """Rewrite a misstated finding to state only what the scene text
        supports, preserving the exposure claim. Returns None when the core
        claim does not survive the correction (then the rejection stands)."""
        prompt = (
            "A clearance finding was rejected because it misstates the screenplay. "
            "Rewrite it to state ONLY what the scene text below supports, preserving "
            "the underlying exposure claim if it survives the correction. If the core "
            "claim does not survive, reply with exactly: UNSALVAGEABLE.\n\n"
            f"REJECTED FINDING:\n{flag.get('finding', '')}\n\n"
            f"REJECTION REASON:\n{flag.get('rejection_reason', '')}\n\n"
            f"SCENE TEXT:\n{script_context}\n\n"
            "Reply with the corrected finding text alone (or UNSALVAGEABLE)."
        )
        async with sem:
            try:
                res = await client.aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.0),
                )
            except Exception:
                return None
        fixed = (res.text or "").strip()
        if not fixed or "UNSALVAGEABLE" in fixed[:40].upper():
            return None
        return fixed[:1500]

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
                    return {
                        "verdict": v.verdict,
                        "reason": v.reason,
                        "failure_mode": v.failure_mode,
                    }
                except Exception:
                    if attempt == _MAX_ATTEMPTS - 1:
                        # Fail open with a marker: never silently drop a flag
                        # because the VERIFIER errored.
                        return {
                            "verdict": "SUPPORTED",
                            "reason": "verifier unavailable",
                            "fail_open": True,
                        }
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        from google import genai

        state = ctx.session.state
        from greenlight.tools.toolbelt import desk_flags

        flags = [f for d in DESKS for f in desk_flags(state, d)]
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
            http_options=_RETRY_HTTP,
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

        # A5: a true finding killed by a bad citation goes around ONCE with
        # fresh sourcing — recall must not be capped by citation retrieval.
        recoverable = [r for r in dropped if r.get("recoverable")][:_RESOURCE_CAP]
        resourced_stats = {"attempted": len(recoverable), "recovered": 0}
        if recoverable:
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"↻ re-sourcing {len(recoverable)} rejection(s) whose failure "
                            "was the citations, not the claim: "
                            + ", ".join(r["flag_id"] for r in recoverable)
                        )
                    ],
                ),
            )
        for r in recoverable:
            if r.get("failure_mode") == "script_misstatement":
                # A factual slip (wrong character name) once deleted a whole
                # territory analysis. One correction round: restate the finding
                # to ONLY what the script supports, keep citations, re-verify.
                fixed = await self._correct_finding(client, r, _scene_context(r, state), sem)
                if not fixed:
                    continue
                retry_flag = {**r, "finding": fixed, "resourced": True}
            else:
                new_cits = await asyncio.to_thread(_fresh_citations, r, state)
                if not new_cits:
                    continue
                retry_flag = {**r, "citations": new_cits, "resourced": True}
            retry_flag.pop("rejection_reason", None)
            retry_flag.pop("recoverable", None)
            v2 = await self._verify_one(client, retry_flag, _scene_context(retry_flag, state), sem)
            verdicts[r["flag_id"] + ":resourced"] = v2
            yield Event(
                invocation_id=ctx.invocation_id,
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=f"↻ {r['flag_id']} re-sourced → "
                            f"{v2['verdict']}|{v2['reason'][:120]}"
                        )
                    ],
                ),
            )
            k2, _d2 = apply_verdicts([retry_flag], {r["flag_id"]: v2})
            if k2:
                kept.extend(k2)
                dropped = [d for d in dropped if d["flag_id"] != r["flag_id"]]
                resourced_stats["recovered"] += 1

        rejected = [
            fid for fid, v in verdicts.items() if ":" not in fid and v["verdict"] == "UNSUPPORTED"
        ]
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
                    "resource_stats": resourced_stats,
                }
            ),
            content=types.Content(role="model", parts=[types.Part(text=summary)]),
        )


agent = VerificationPanel(
    name="verification_panel",
    description="Blinded per-flag citation verification; can reject flags.",
)
