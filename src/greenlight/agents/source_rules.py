"""Small source-bound repair library, activated only by existing Parallel receipts.

This is a development-reviewed wording library, not an authority cache or a legal
applicability engine. It cannot retrieve, add citations or silently follow changes
to a source. A different URL or excerpt disables a card. Novel sources still use
the bounded semantic audit, and every constructed correction is reverified.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

_CARDS_PATH = Path(__file__).resolve().parents[1] / "data/production_rules.json"


class SourceBoundRepair(BaseModel):
    finding: str = Field(min_length=1, max_length=4000)
    rule_ids: list[str] = Field(min_length=1, max_length=4)
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


def available_rules(flag: dict) -> list[dict]:
    """Use only exact reviewed excerpts already retrieved for this desk's flag."""
    if flag.get("agent") != "safety_underwriter":
        return []
    cards = json.loads(_CARDS_PATH.read_text())["rules"]
    available = []
    for card in cards:
        for index, citation in enumerate(flag.get("citations", []), 1):
            excerpt = str(citation.get("excerpt") or "")
            if (
                citation.get("via") not in {"parallel_search", "parallel_extract"}
                or citation.get("url") != card["source_url"]
                or hashlib.sha256(excerpt.encode()).hexdigest() != card["source_sha256"]
            ):
                continue
            available.append({**card, "citation_number": index, "source_quote": excerpt})
            break
    return available


def bound_correction(proposal: SourceBoundRepair, rules: list[dict]) -> tuple[dict, list[dict]]:
    """The model selects applicable cards; it cannot rewrite their conditions/duties."""
    by_id = {rule["rule_id"]: rule for rule in rules}
    if len(set(proposal.rule_ids)) != len(proposal.rule_ids):
        raise ValueError("a repair repeated a source rule")
    if set(proposal.rule_ids) - by_id.keys():
        raise ValueError("a repair invented a source rule")
    # Stable library order, independent of model list ordering.
    selected = [rule for rule in rules if rule["rule_id"] in proposal.rule_ids]
    action = (
        "ADD_SPECIALIST"
        if any(rule["action"] == "ADD_SPECIALIST" for rule in selected)
        else "NO_ACTION"
    )
    return {
        "finding": proposal.finding,
        "remedy_detail": " ".join(rule["remedy_detail"] for rule in selected),
        "remedy_action": action,
        "severity": proposal.severity,
    }, selected
