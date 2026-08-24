"""Toolbelt tests. No live APIs — research is monkeypatched with the real cassette."""

import json
from pathlib import Path
from types import SimpleNamespace

from greenlight import parser
from greenlight.tools import toolbelt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "fixtures" / "slack_tide.fountain").read_text()
CASSETTE = json.loads(
    (ROOT / "fixtures" / "cassettes" / "clearance_brand_disparagement.json").read_text()
)


class FakeState(dict):
    pass


def make_ctx(agent_name="clearance_counsel", **state):
    _, scenes = parser.parse_fountain(SOURCE)
    base = {
        "script_text": SOURCE,
        "scenes": scenes,
        "research_budget:clearance_counsel": 3,
        "research_budget:territory_censor": 3,
    }
    base.update(state)
    return SimpleNamespace(
        agent_name=agent_name, state=FakeState(base), actions=SimpleNamespace(escalate=False)
    )


GOOD_CITATION = {
    "title": "Clearance overview",
    "url": "https://example.com/clearance",
    "excerpt": (
        "If the product appears in a negative light, you may be sued for product disparagement."
    ),
}


def file_good_flag(ctx, **overrides):
    kwargs = dict(
        scene_ids=["S002"],
        severity="HIGH",
        category="trademark_disparagement",
        finding="A beer brand is disparaged on screen.",
        citations=[GOOD_CITATION],
        remedy_action="REPLACE",
        remedy_detail="Rename to a fictional brand.",
        confidence=0.9,
        tool_context=ctx,
    )
    kwargs.update(overrides)
    return toolbelt.file_flag(**kwargs)


def test_file_flag_happy_path():
    ctx = make_ctx()
    msg = file_good_flag(ctx)
    assert msg.startswith("Filed F101")
    (flag,) = ctx.state["flags:clearance_counsel"]
    assert flag["agent"] == "clearance_counsel"
    assert flag["citations"][0]["via"] == "parallel_search"


def test_flag_without_citation_is_rejected():
    """THE product invariant, tested at the boundary that enforces it."""
    ctx = make_ctx()
    msg = file_good_flag(ctx, citations=[])
    assert msg.startswith("REJECTED")
    assert "flags:clearance_counsel" not in ctx.state


def test_flag_with_empty_excerpt_is_rejected():
    ctx = make_ctx()
    msg = file_good_flag(ctx, citations=[{**GOOD_CITATION, "excerpt": "   "}])
    assert msg.startswith("REJECTED")


def test_flag_with_bogus_scene_is_rejected():
    ctx = make_ctx()
    msg = file_good_flag(ctx, scene_ids=["S999"])
    assert msg.startswith("REJECTED")
    # and the sequence number was returned, so the next flag is still F101
    assert file_good_flag(ctx).startswith("Filed F101")


def test_rejection_reports_all_errors_at_once():
    ctx = make_ctx()
    msg = file_good_flag(ctx, severity="CATASTROPHIC", remedy_action="PANIC")
    assert msg.count("\n-") >= 2


def test_research_budget_and_cache(monkeypatch):
    calls = []

    def fake_search(objective, queries):
        calls.append(objective)
        return CASSETTE

    monkeypatch.setattr(toolbelt, "_live_search", fake_search)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 2})

    r1 = toolbelt.research("Is the brand cleared?", ["brand clearance film"], "E001", ctx)
    assert r1["cached"] is False and r1["budget_remaining"] == 1
    assert r1["results"] and r1["results"][0]["excerpts"]

    r2 = toolbelt.research("Is the brand cleared?", ["brand clearance film"], "E001", ctx)
    assert r2["cached"] is True
    assert len(calls) == 1  # cache hit did not spend budget

    toolbelt.research("q2", ["q"], "E002", ctx)
    r4 = toolbelt.research("q3", ["q"], "E003", ctx)
    assert "error" in r4 and "budget" in r4["error"]
    assert len(calls) == 2


def test_research_dedups_case_variant_urls(monkeypatch):
    doubled = {
        "results": [
            {"url": "https://x.com/Library/page", "title": "a", "excerpts": ["one"]},
            {"url": "https://x.com/library/page/", "title": "a", "excerpts": ["two"]},
        ],
        "search_id": "s",
    }
    monkeypatch.setattr(toolbelt, "_live_search", lambda o, q: doubled)
    ctx = make_ctx()
    r = toolbelt.research("q", ["q"], "E009", ctx)
    assert len(r["results"]) == 1


def test_done_escalates():
    ctx = make_ctx()
    msg = toolbelt.done("worklist exhausted", ctx)
    assert ctx.actions.escalate is True and "worklist exhausted" in msg


def test_read_scene_and_find():
    ctx = make_ctx()
    text = toolbelt.read_scene("S002", ctx)
    assert "NIGHTHAWKS" in text
    assert "Valid scene ids" in toolbelt.read_scene("S099", ctx)
    hits = toolbelt.find_in_script("Hallelujah", ctx)
    assert hits["total_matches"] >= 3
    assert len(hits["scenes"]) >= 3


def test_open_question():
    ctx = make_ctx(agent_name="territory_censor")
    toolbelt.note_open_question("UAE cut list unclear", ctx)
    assert ctx.state["open_questions:territory_censor"] == ["UAE cut list unclear"]


def test_flag_ids_are_partitioned_per_desk():
    """Two desks filing concurrently must never mint the same flag id."""
    c1 = file_good_flag(make_ctx("clearance_counsel"))
    t1 = file_good_flag(make_ctx("territory_censor"))
    assert c1.startswith("Filed F101") and t1.startswith("Filed F401")


def test_query_precedent_degrades_gracefully(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    out = toolbelt.query_precedent("strong language throughout", 8, make_ctx())
    assert "error" in out and "research()" in out["guidance"]
