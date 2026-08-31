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
    category: str = Field(
        description="Normalized category slug for the survivor. NEVER normalize "
        "defamation_false_light, trade_libel_venue, or underlying_rights into a broader "
        "category — they are distinct legal theories and must survive as filed."
    )
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"] = Field(
        description="Final severity — the highest severity among the merged flags unless "
        "a stated conflict resolution justifies otherwise."
    )
    rationale: str = Field(description="One line: why these are one finding.")


class Conflict(BaseModel):
    flag_ids: list[str]
    resolution: str = Field(description="How the remedies interact and which should proceed first.")
    target_path_moot_flag_ids: list[str] = Field(
        default_factory=list,
        description="Flags whose remedy COST becomes moot when the production follows the "
        "stated resolution toward its target rating (e.g. a music license only needed if the "
        "scene survives in the R cut). The flags still render; their cost moves to the "
        "as-written path. Empty when the remedies merely order.",
    )


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

REJECTED IN VERIFICATION (context only — you cannot revive these; the rejection
reasons' factual statements are authoritative):

{rejected_summary}

Produce an adjudication plan:

1. MERGES. Fold duplicates into one flag: identical findings filed twice by one desk, and
   same-issue flags from one desk covering the same scenes (an unpermitted burn and the
   property destruction it causes are one finding). Do NOT merge across desks — a safety flag
   and a territory flag on the same scene are different findings by design. Do NOT merge
   distinct RIGHTS in the same work: a synchronization license (the composition, from the
   publisher) and a master-use license (the recording, from the label) are separate licenses
   from separate licensors and stay separate flags even for the same song. The survivor's
   severity is the highest among the merged unless you state why not.
2. CATEGORY NORMALIZATION. Categories follow desk conventions: clearance and safety use plain
   slugs ("sync_license", "stunt_pyro"); territory uses "territory_<cc>_<issue>" with cc in
   us/uk/cn/uae; ratings uses "rating_<driver>". Normalize drifted categories in your merge
   actions (a merge of one flag with an empty merged_flag_ids list is a rename).
3. CONFLICTS. Where two remedies touch the same lines or scenes (ratings wants a line cut,
   clearance wants it rewritten; a territory cut would remove a scene other flags anchor to),
   record the interaction and state which remedy should proceed and why. When your resolution
   makes another flag's remedy COST moot on the target-rating path (cutting a song for the
   rating removes the need to license it), list those flag ids in target_path_moot_flag_ids —
   the report shows a two-path cost total from exactly this field.
4. SEVERITY DISCIPLINE. Severity is triage and must use the full scale: a remedy that is a
   free, local fix (a dialogue swap, renaming a background prop) is LOW; awareness-only
   items with NO_ACTION are FYI. A report where every finding sits at MEDIUM or above
   cannot be triaged. When a filed severity is plainly inflated relative to its remedy,
   downgrade it one step via a single-flag merge action with the rationale on record.
   BLOCKER means production stops or the film is undeliverable in its PRIMARY market — a
   secondary-market alt-cut deliverable labeled BLOCKER is mislabeled; downgrade it to
   HIGH with the deliverables framing in your rationale.
5. VERIFIER CONSISTENCY. When a rejection reason above factually refutes a rule or
   standard that a SURVIVING flag also asserts (the same premise, kept in one flag and
   killed in another), the surviving flag must not carry the refuted premise at full
   strength: downgrade it one step via a single-flag merge whose rationale states the
   corrected rule, so the report never asserts what its own verification disproved.
   This applies to refuted RULES AND STANDARDS only — never downgrade a flag because a
   rejection claimed something is absent from the script; absence claims in rejections
   have been wrong before, and script-fact policing is the verifier's job, not yours.
   A rejection marked OVERTURNED does not exist for your purposes.

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


_SCENE_CAP = 8  # mirrors file_flag's anchor cap — merges must not resurrect umbrellas


def _cap_scenes(flag: dict[str, Any], prior: list[str]) -> None:
    """Union results keep the survivor's original anchors first, then fill from
    the merged flag, capped — except cumulative categories (ratings/territory),
    whose script-wide scene lists are the finding."""
    if flag["category"].startswith(("rating_", "territory_")):
        return
    if len(flag["scene_ids"]) > _SCENE_CAP:
        ordered = [s for s in prior if s in flag["scene_ids"]]
        ordered += [s for s in flag["scene_ids"] if s not in ordered]
        flag["scene_ids"] = ordered[:_SCENE_CAP]


def _same_disposition(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """A NO_ACTION 'fine as written' finding is NOT the same finding as one that
    demands a cut, even in the same category. Merging across that line buried an
    R-rated S064 violence driver (bloody head trauma, gunfire, a vehicular
    impact) inside a MEDIUM 'No Action' bat-attack note (run 8, F2008), so the
    report cleared the exploding-lip scene."""
    na = "NO_ACTION"
    return (a["remedy"].get("action") == na) == (b["remedy"].get("action") == na)


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
            # — BUT only when they share a disposition: a NO_ACTION finding and
            # an actionable one are two findings, not one.
            script_wide = flag["category"].startswith(("rating_", "territory_"))
            if (
                same_cat
                and _same_disposition(existing, flag)
                and (script_wide or set(existing["scene_ids"]) & set(flag["scene_ids"]))
            ):
                prior = list(existing["scene_ids"])
                existing["scene_ids"] = sorted(set(existing["scene_ids"]) | set(flag["scene_ids"]))
                _cap_scenes(existing, prior)
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
    flags_category_before = {f["flag_id"]: f["category"] for f in flags}
    absorbed: set[str] = set()
    notes: list[str] = []
    sev_rank = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "FYI": 4}

    for action in plan.get("merges", []):
        survivor = by_id.get(action["surviving_flag_id"])
        if survivor is None or action["surviving_flag_id"] in absorbed:
            continue
        sev_before = survivor["severity"]
        merged_real = [
            fid for fid in action["merged_flag_ids"] if fid in by_id and fid not in absorbed
        ]
        for fid in merged_real:
            other = by_id[fid]
            prior = list(survivor["scene_ids"])
            survivor["scene_ids"] = sorted(set(survivor["scene_ids"]) | set(other["scene_ids"]))
            _cap_scenes(survivor, prior)
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
        if max_rank == 0:
            # a BLOCKER may drop exactly ONE step, to HIGH, and only when the
            # plan asks for exactly that with the rationale on record — the
            # mislabeled secondary-market alt-cut correction (run 5). A wilder
            # proposal (MEDIUM or below) is refused outright, not clamped.
            final_rank = 1 if plan_rank == 1 and action.get("rationale") else 0
        survivor["severity"] = ranks[min(final_rank, len(ranks) - 1)]
        if action.get("category"):
            survivor["category"] = action["category"]
        # PARTIAL is a confidence marker, not a severity cap (run-3 decision) —
        # merges apply the highest-severity rule above and nothing else.
        rationale = action.get("rationale", "")
        sid = action["surviving_flag_id"]
        sev_changed = survivor["severity"] != sev_before
        cat_changed = action.get("category") and action["category"] != flags_category_before.get(
            sid
        )
        # Only note what ACTUALLY happened. A note said "F2008: severity upgraded
        # from MEDIUM" while apply_plan's own rule REFUSED the upgrade — the
        # report claimed a change that never occurred. A single-flag action that
        # changed nothing produces no note.
        if merged_real:
            notes.append(f"{sid}: absorbed {', '.join(merged_real)} ({rationale})")
        elif cat_changed and sev_changed:
            notes.append(
                f"{sid}: category -> {action['category']}, "
                f"severity -> {survivor['severity']} ({rationale})"
            )
        elif cat_changed:
            notes.append(f"{sid}: category normalized to {action['category']} ({rationale})")
        elif sev_changed:
            notes.append(f"{sid}: severity -> {survivor['severity']} ({rationale})")

    result = [f for f in flags if f["flag_id"] not in absorbed]
    for c in plan.get("conflicts", []):
        notes.append(f"conflict: {c['resolution']}")
        # Two-path cost: the flags the resolution moots on the target path keep
        # rendering, but the report's target-path total excludes their cost.
        for fid in c.get("target_path_moot_flag_ids") or []:
            if fid in by_id and fid not in absorbed:
                by_id[fid]["cost_excluded_on_target_path"] = True
    return result, notes
