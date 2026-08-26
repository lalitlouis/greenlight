"""Adjudicator: reconciles the four desks' surviving flags into one coherent report.

The desks are independent by design, so they duplicate and collide: two desks flag
the same scene, one desk files the same finding twice, categories drift. The
Adjudicator — the producer of the panel — reads everything and emits a structured
plan: merges, category normalization, conflict resolutions. The plan is APPLIED
DETERMINISTICALLY in code; the model proposes, the code disposes, and a flag the
plan does not mention survives untouched.

Runs on Pro: it is the only task reasoning across all four desks' output at once.
Re-entry into desks via AgentTool (remedy interaction) is a planned extension —
see docs/TECH_SPEC.md.
"""

from __future__ import annotations

from typing import Any, Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from greenlight.agents.common import GEN_CONFIG, PRO, tool_error_shield


class MergeAction(BaseModel):
    surviving_flag_id: str = Field(description="The flag that absorbs the others.")
    merged_flag_ids: list[str] = Field(
        description="Flags folded into the survivor (duplicates or same finding split up)."
    )
    category: str = Field(description="Normalized category slug for the survivor.")
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"] = Field(
        description="Final severity — the highest severity among the merged flags unless "
        "a stated conflict resolution justifies otherwise."
    )
    rationale: str = Field(description="One line: why these are one finding.")


class Conflict(BaseModel):
    flag_ids: list[str]
    resolution: str = Field(description="How the remedies interact and which should proceed first.")


class AdjudicationPlan(BaseModel):
    merges: list[MergeAction]
    conflicts: list[Conflict]
    notes: list[str] = Field(
        description="Observations for the producer that are not themselves flags."
    )


INSTRUCTION = """\
You are the Adjudicator — the producer who reconciles the four clearance desks' findings into
one report. The desks worked independently and did not see each other's output.

VERIFIED FLAGS (already citation-checked; you cannot reject or invent flags):

{verified_flags}

Produce an adjudication plan:

1. MERGES. Fold duplicates into one flag: identical findings filed twice by one desk, and
   same-issue flags from one desk covering the same scenes (an unpermitted burn and the
   property destruction it causes are one finding). Do NOT merge across desks — a safety flag
   and a territory flag on the same scene are different findings by design. The survivor's
   severity is the highest among the merged unless you state why not.
2. CATEGORY NORMALIZATION. Categories follow desk conventions: clearance and safety use plain
   slugs ("sync_license", "stunt_pyro"); territory uses "territory_<cc>_<issue>" with cc in
   us/uk/cn/uae; ratings uses "rating_<driver>". Normalize drifted categories in your merge
   actions (a merge of one flag with an empty merged_flag_ids list is a rename).
3. CONFLICTS. Where two remedies touch the same lines or scenes (ratings wants a line cut,
   clearance wants it rewritten; a territory cut would remove a scene other flags anchor to),
   record the interaction and state which remedy should proceed and why.

Be conservative: when unsure whether two flags are one finding, leave them separate.
"""

agent = LlmAgent(
    name="adjudicator",
    model=PRO,
    description="Reconciles verified flags: merges duplicates, normalizes, resolves conflicts.",
    instruction=INSTRUCTION,
    output_schema=AdjudicationPlan,
    output_key="adjudication",
    include_contents="none",
    generate_content_config=GEN_CONFIG,
    on_tool_error_callback=tool_error_shield,
)


def merge_exact_duplicates(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Code-level dedupe BEFORE the model sees anything: same desk + same
    category + overlapping scenes is one finding, full stop. Keeps the higher
    severity, unions scenes and citations. (A run shipped two identical
    territory_cn_supernatural flags — the model adjudicator is a judgment
    layer, not a uniqueness guarantee; this is.)"""
    sev_rank = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}
    kept: list[dict[str, Any]] = []
    for flag in flags:
        merged = False
        for existing in kept:
            same_cat = (
                existing["agent"] == flag["agent"] and existing["category"] == flag["category"]
            )
            # rating drivers are SCRIPT-WIDE claims by nature — same category
            # consolidates even across disjoint scenes (a run filed 17 separate
            # rating_language flags, one per instance; the count is one finding)
            script_wide = flag["category"].startswith(("rating_", "territory_"))
            if same_cat and (script_wide or set(existing["scene_ids"]) & set(flag["scene_ids"])):
                existing["scene_ids"] = sorted(set(existing["scene_ids"]) | set(flag["scene_ids"]))
                seen = {c["excerpt"] for c in existing["citations"]}
                existing["citations"] += [c for c in flag["citations"] if c["excerpt"] not in seen]
                if sev_rank[flag["severity"]] < sev_rank[existing["severity"]]:
                    existing["severity"] = flag["severity"]
                merged = True
                break
        if not merged:
            kept.append(dict(flag))
    return kept


def apply_plan(
    flags: list[dict[str, Any]], plan: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply an adjudication plan deterministically. Unknown ids are ignored; a flag
    the plan does not touch survives unchanged. Returns (flags, applied_notes)."""
    by_id = {f["flag_id"]: f for f in flags}
    absorbed: set[str] = set()
    notes: list[str] = []
    sev_rank = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}

    for action in plan.get("merges", []):
        survivor = by_id.get(action["surviving_flag_id"])
        if survivor is None or action["surviving_flag_id"] in absorbed:
            continue
        merged_real = [
            fid for fid in action["merged_flag_ids"] if fid in by_id and fid not in absorbed
        ]
        for fid in merged_real:
            other = by_id[fid]
            survivor["scene_ids"] = sorted(set(survivor["scene_ids"]) | set(other["scene_ids"]))
            seen_excerpts = {c["excerpt"] for c in survivor["citations"]}
            survivor["citations"] += [
                c for c in other["citations"] if c["excerpt"] not in seen_excerpts
            ]
            absorbed.add(fid)
        # Severity: highest among participants. The plan may downgrade by at most one
        # step (with its rationale on record) — never upgrade past the evidence, never
        # bury a BLOCKER below HIGH.
        ranks = ["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]
        participants = [survivor, *(by_id[fid] for fid in merged_real)]
        max_rank = min(sev_rank[p["severity"]] for p in participants)
        plan_rank = sev_rank.get(action.get("severity", ""), max_rank)
        final_rank = plan_rank if plan_rank in (max_rank, max_rank + 1) else max_rank
        survivor["severity"] = ranks[min(final_rank, len(ranks) - 1)]
        if action.get("category"):
            survivor["category"] = action["category"]
        if merged_real or action.get("category"):
            notes.append(
                f"{action['surviving_flag_id']}: absorbed {merged_real or 'none'} "
                f"({action.get('rationale', '')})"
            )

    result = [f for f in flags if f["flag_id"] not in absorbed]
    notes += [f"conflict: {c['resolution']}" for c in plan.get("conflicts", [])]
    return result, notes
