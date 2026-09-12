"""Rule text cannot outrun the exact retrieved source snapshot that enabled it."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from greenlight.agents.source_rules import SourceBoundRepair, available_rules, bound_correction

ROOT = Path(__file__).resolve().parents[1]


def saved_fire_flag():
    return json.loads((ROOT / "fixtures/cassettes/fresh_safety_20260911.json").read_text())[
        "flags"
    ][0]


@pytest.mark.parametrize("change", ["url", "excerpt", "via", "desk", "missing"])
def test_changed_or_missing_source_cannot_activate_a_known_rule(change):
    flag = saved_fire_flag()
    rules = available_rules(flag)
    assert len(rules) == 2
    original = deepcopy(flag)
    if change == "desk":
        flag["agent"] = "clearance_counsel"
    elif change == "missing":
        flag["citations"] = []
    else:
        for citation in flag["citations"]:
            citation[change] = {
                "url": "https://example.invalid",
                "excerpt": "Different rule.",
                "via": "local",
            }[change]
    assert available_rules(flag) == []
    assert all(
        rule["source_quote"] == original["citations"][rule["citation_number"] - 1]["excerpt"]
        for rule in rules
    )


def test_bound_remedy_uses_only_selected_rule_text_in_stable_order():
    flag = saved_fire_flag()
    original = deepcopy(flag)
    rules = available_rules(flag)
    proposal = SourceBoundRepair(
        finding="Depicted fire and night-water hazards.",
        rule_ids=[r["rule_id"] for r in reversed(rules)],
        severity="HIGH",
    )
    correction, selected = bound_correction(proposal, rules)
    assert flag == original
    assert selected == rules
    assert correction["remedy_detail"] == " ".join(r["remedy_detail"] for r in rules)
    assert correction["remedy_action"] == "ADD_SPECIALIST"
    assert "as applicable" in correction["remedy_detail"]
    assert "open flame" not in correction["remedy_detail"]
    assert "Marine Coordinator" not in correction["remedy_detail"]
    assert "lifeguard" not in correction["remedy_detail"]


@pytest.mark.parametrize("bad_id", ["invented", "repeated"])
def test_model_cannot_invent_or_repeat_rule_cards(bad_id):
    rules = available_rules(saved_fire_flag())
    first = rules[0]["rule_id"]
    proposal = SourceBoundRepair(
        finding="Fire hazard.",
        rule_ids=[first, "invented" if bad_id == "invented" else first],
        severity="HIGH",
    )
    with pytest.raises(ValueError):
        bound_correction(proposal, rules)


def test_water_only_selection_remains_a_specific_input_question_without_inventing_a_hire():
    rules = available_rules(saved_fire_flag())
    proposal = SourceBoundRepair(
        finding="Night-water exposure.", rule_ids=[rules[1]["rule_id"]], severity="HIGH"
    )
    correction, selected = bound_correction(proposal, rules)
    assert len(selected) == 1
    assert correction["remedy_action"] == "NO_ACTION"
    assert correction["remedy_detail"].startswith("Confirm whether cast or crew will work in water")
    assert "Pyrotechnic" not in correction["remedy_detail"]
