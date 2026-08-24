"""ReportWriter: deterministic assembly of the Production Risk Report.

No model here, on purpose. A score that moves between runs is not a score, so the
Greenlight Score is a pure function of flag severities, and the report is rendered
from validated objects only.
"""

from __future__ import annotations

import time
from typing import Any

from greenlight.contracts import validate

SEVERITIES = ("BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI")

# Each finding multiplies remaining confidence — deterministic, documented, and it
# keeps the scale meaningful at both ends: a linear penalty pins every dense script
# to 0, which reads as a broken gauge rather than a bad script. A BLOCKER dominates
# by design: one unshootable scene outweighs any pile of routine paperwork.
_FACTOR = {"BLOCKER": 0.70, "HIGH": 0.92, "MEDIUM": 0.97, "LOW": 0.995, "FYI": 1.0}


def greenlight_score(flags: list[dict[str, Any]]) -> int:
    """0-100. Deterministic product of per-severity factors. Never asked of an LLM."""
    score = 100.0
    for f in flags:
        score *= _FACTOR[f["severity"]]
    return round(score)


def _cost_range(flags: list[dict[str, Any]]) -> list[float] | None:
    lows, highs = [], []
    for f in flags:
        rng = f["remedy"].get("est_cost_usd")
        if rng:
            lows.append(rng[0])
            highs.append(rng[1])
    return [sum(lows), sum(highs)] if lows else None


def _added_days(flags: list[dict[str, Any]]) -> float | None:
    days = [
        f["remedy"]["est_added_days"]
        for f in flags
        if f["remedy"].get("est_added_days") is not None
    ]
    # Remedies overlap in schedule; summing them would be dishonest. The critical
    # path is the longest single remedy.
    return max(days) if days else None


DESKS = ("clearance_counsel", "ratings_board", "safety_underwriter", "territory_censor")


def dimension_scores(flags: list[dict[str, Any]]) -> dict[str, int]:
    """The composite, decomposed: each desk scored by its own flags alone. Four
    numbers with a published rubric survive scrutiny where one number invites
    'why 20 and not 35?'."""
    return {desk: greenlight_score([f for f in flags if f["agent"] == desk]) for desk in DESKS}


def build_report(
    script_title: str,
    flags: list[dict[str, Any]],
    page_count: float | None = None,
    rating_prediction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble and validate the Report object. Flags must already be verified."""
    counts = {sev: sum(f["severity"] == sev for f in flags) for sev in SEVERITIES}
    by_agent: dict[str, int] = {}
    for f in flags:
        by_agent[f["agent"]] = by_agent.get(f["agent"], 0) + 1

    report: dict[str, Any] = {
        "script_title": script_title,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "greenlight_score": greenlight_score(flags),
        "dimension_scores": dimension_scores(flags),
        "counts": counts,
        "by_agent": by_agent,
        "est_clearance_cost_usd": _cost_range(flags),
        "est_added_days": _added_days(flags),
        "rating_prediction": rating_prediction,
        "flags": flags,
    }
    if page_count is not None:
        report["page_count"] = page_count
    return validate("report", report)
