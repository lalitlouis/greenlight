"""Toolbelt tests. No live APIs — research is monkeypatched with the real cassette."""

import asyncio
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


RESEARCH_EXCERPT = (
    "If the product appears in a negative light, you may be sued for product disparagement."
)


def make_ctx(agent_name="clearance_counsel", **state):
    _, scenes = parser.parse_fountain(SOURCE)
    base = {
        "script_text": SOURCE,
        "scenes": scenes,
        "research_budget:clearance_counsel": 3,
        "research_budget:territory_censor": 3,
        # provenance: filed excerpts must exist in retrieved material
        "research_keys:clearance_counsel": ["research:E001:seeded"],
        "research:E001:seeded": {
            "objective": "seeded",
            "search_id": "s0",
            "results": [
                {
                    "url": "https://example.com/clearance",
                    "title": "Clearance overview",
                    "excerpts": [RESEARCH_EXCERPT],
                }
            ],
        },
    }
    base.update(state)
    return SimpleNamespace(
        agent_name=agent_name, state=FakeState(base), actions=SimpleNamespace(escalate=False)
    )


GOOD_CITATION = {
    "title": "Clearance overview",
    "url": "https://example.com/clearance",
    "excerpt": RESEARCH_EXCERPT,
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


class _AdkishState:
    """Mimics ADK State: get/set/contains but NO .keys()/iteration — the shape
    that crashed provenance in production."""

    def __init__(self, base):
        self._d = dict(base)

    def get(self, k, default=None):
        return self._d.get(k, default)

    def __getitem__(self, k):
        return self._d[k]

    def __setitem__(self, k, v):
        self._d[k] = v

    def __contains__(self, k):
        return k in self._d


def test_provenance_survives_enumeration_hostile_state():
    from types import SimpleNamespace

    _, scenes = parser.parse_fountain(SOURCE)
    state = _AdkishState(
        {
            "script_text": SOURCE,
            "scenes": scenes,
            "research_keys:clearance_counsel": ["research:E001:seeded"],
            "research:E001:seeded": {
                "results": [{"url": "u", "title": "t", "excerpts": [RESEARCH_EXCERPT]}]
            },
        }
    )
    ctx = SimpleNamespace(
        agent_name="clearance_counsel", state=state, actions=SimpleNamespace(escalate=False)
    )
    msg = file_good_flag(ctx)
    assert "Filed F" in msg, msg


def test_flag_with_fabricated_excerpt_is_rejected():
    ctx = make_ctx()
    msg = file_good_flag(
        ctx,
        citations=[{**GOOD_CITATION, "excerpt": "A confabulated quote that no tool returned."}],
    )
    assert "not filed" in msg and "verbatim" in msg
    assert ctx.state.get("flags:clearance_counsel") in (None, [])


def test_flag_with_empty_excerpt_is_rejected():
    ctx = make_ctx()
    msg = file_good_flag(ctx, citations=[{**GOOD_CITATION, "excerpt": "   "}])
    assert msg.startswith("REJECTED")


def test_flag_with_bogus_scene_is_rejected():
    ctx = make_ctx()
    msg = file_good_flag(ctx, scene_ids=["S999"])
    assert msg.startswith("REJECTED")
    # ids are allocated process-locally (parallel batch writers can't share a
    # state counter); a rejection leaves a harmless gap, never a collision
    assert file_good_flag(ctx).startswith("Filed F102")


def test_rejection_reports_all_errors_at_once():
    ctx = make_ctx()
    msg = file_good_flag(ctx, severity="CATASTROPHIC", remedy_action="PANIC")
    assert msg.count("\n-") >= 2


def test_research_budget_and_cache(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    calls = []

    def fake_search(objective, queries, **kw):
        calls.append(objective)
        return CASSETTE

    monkeypatch.setattr(toolbelt, "_live_search", fake_search)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 2})

    r1 = asyncio.run(
        toolbelt.research("Is the brand cleared?", ["brand clearance film"], "E001", ctx)
    )
    assert r1["cached"] is False and r1["budget_remaining"] == 1
    assert r1["results"] and r1["results"][0]["excerpts"]

    r2 = asyncio.run(
        toolbelt.research("Is the brand cleared?", ["brand clearance film"], "E001", ctx)
    )
    assert r2["cached"] is True
    assert len(calls) == 1  # cache hit did not spend budget

    asyncio.run(toolbelt.research("q2", ["q"], "E002", ctx))
    r4 = asyncio.run(toolbelt.research("q3", ["q"], "E003", ctx))
    assert "error" in r4 and "budget" in r4["error"]
    assert len(calls) == 2


def test_durable_cache_is_consulted_before_spending(monkeypatch):
    hits = {}
    monkeypatch.setattr(
        toolbelt, "_durable_cache_load", lambda k: {"results": [{"ok": 1}], "search_id": "s1"}
    )
    monkeypatch.setattr(toolbelt, "_live_search", lambda o, q, **kw: hits.setdefault("live", True))
    ctx = make_ctx(**{"research_budget:clearance_counsel": 2})
    r = asyncio.run(toolbelt.research("cached question", ["q"], "E001", ctx))
    assert r["cached"] is True and r["search_id"] == "s1"
    assert "live" not in hits  # no API spend on a durable hit
    assert ctx.state["research_budget:clearance_counsel"] == 2  # budget untouched


def test_research_dedups_case_variant_urls(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    doubled = {
        "results": [
            {"url": "https://x.com/Library/page", "title": "a", "excerpts": ["one"]},
            {"url": "https://x.com/library/page/", "title": "a", "excerpts": ["two"]},
        ],
        "search_id": "s",
    }
    monkeypatch.setattr(toolbelt, "_live_search", lambda o, q, **kw: doubled)
    ctx = make_ctx()
    r = asyncio.run(toolbelt.research("q", ["q"], "E009", ctx))
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
    out = asyncio.run(toolbelt.query_precedent("strong language throughout", 8, make_ctx()))
    assert "error" in out and "research()" in out["guidance"]


def test_rating_prediction_requires_comparables_first():
    ctx = make_ctx("ratings_board", target_rating="PG-13")
    msg = toolbelt.file_rating_prediction("R", "for language throughout", [], ctx)
    assert msg.startswith("REJECTED")
    ctx.state["last_precedent:ratings_board"] = [
        {
            "title": "X",
            "year": 2001,
            "rating": "R",
            "rationale": "r",
            "source_url": None,
            "distance": 0.1,
        }
    ]
    msg = toolbelt.file_rating_prediction(
        "R", "for language throughout", ["cut 2 of 3 F-bombs"], ctx
    )
    assert msg.startswith("Prediction filed: R")
    pred = ctx.state["rating_prediction"]
    assert pred["target"] == "PG-13" and pred["comparables"][0]["title"] == "X"


def test_build_profile_from_fixture():
    from greenlight import profile

    _, scenes = parser.parse_fountain(SOURCE)
    p = profile.build_profile(scenes)
    assert p["scene_count"] == len(scenes)
    assert p["cast_size"] >= 1 and p["top_cast"][0]["lines"] >= 1
    assert 0 <= p["dialogue_pct"] <= 100
    assert p["location_count"] >= 1


def test_language_guard():
    from greenlight import langguard

    assert langguard.probably_english(SOURCE)
    spanish = (
        "INT. CASA DE MARTA - DIA\n\nMarta entra despacio y mira por la ventana rota. "
        "El viento mueve las cortinas viejas mientras ella busca las llaves perdidas "
        "entre los papeles del escritorio de su abuela. Nadie responde cuando llama. "
    ) * 8
    assert not langguard.probably_english(spanish)
    chinese = "内景 老宅 夜 王梅走进房间 看着窗外的雨 她慢慢坐下 拿起桌上的旧照片" * 30
    assert not langguard.probably_english(chinese)
    assert langguard.probably_english("too short to judge")


# --- fetch_page (Parallel Extract) ------------------------------------------

EXTRACT_EXCERPT = (
    "The repertory entry lists the composition as administered by Harbor Lane Music "
    "with a fifty percent writer share registered to the estate."
)


def _fake_extract(urls, objective, **kw):
    return {
        "extract_id": "ex1",
        "errors": [],
        "results": [
            {
                "url": urls[0],
                "title": "Repertory entry",
                "publish_date": None,
                "excerpts": [EXTRACT_EXCERPT],
            }
        ],
    }


def test_fetch_page_spends_budget_caches_and_registers_provenance(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    calls = []

    def fake(urls, objective, **kw):
        calls.append(urls)
        return _fake_extract(urls, objective)

    monkeypatch.setattr(toolbelt, "_live_extract", fake)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 2})
    ctx.invocation_id = "inv-extract-test"

    r1 = asyncio.run(toolbelt.fetch_page("https://repertory.example/song", "who administers", ctx))
    assert r1["cached"] is False and r1["budget_remaining"] == 1
    assert r1["results"][0]["excerpts"] == [EXTRACT_EXCERPT]

    r2 = asyncio.run(toolbelt.fetch_page("https://repertory.example/song", "who administers", ctx))
    assert r2["cached"] is True and len(calls) == 1

    # a filed citation quoting the extracted page must pass the provenance gate
    assert toolbelt._excerpt_exists(EXTRACT_EXCERPT, ctx)


def test_fetch_page_refunds_on_empty_result(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    monkeypatch.setattr(
        toolbelt,
        "_live_extract",
        lambda urls, objective, **kw: {
            "extract_id": "ex2",
            "errors": [{"url": urls[0], "error_type": "fetch_blocked"}],
            "results": [],
        },
    )
    ctx = make_ctx(**{"research_budget:clearance_counsel": 2})
    r = asyncio.run(toolbelt.fetch_page("https://blocked.example/x", "anything", ctx))
    assert "error" in r
    assert ctx.state["research_budget:clearance_counsel"] == 2  # refunded


# --- deep_research (Parallel Task API) --------------------------------------

DEEP_EXCERPT = (
    "Catalog records show the master recording rights were acquired by Meridian "
    "Audio Holdings in 2019 and are administered worldwide by its licensing arm."
)


def _fake_task(question, processor):
    return {
        "run": {"run_id": "tr1", "status": "completed"},
        "output": {
            "type": "text",
            "content": "The master is controlled by Meridian Audio Holdings.",
            "basis": [
                {
                    "field": "output",
                    "reasoning": "traced catalog sale",
                    "citations": [
                        {
                            "url": "https://trade.example/meridian",
                            "title": "Catalog sale coverage",
                            "excerpts": [DEEP_EXCERPT],
                        }
                    ],
                }
            ],
        },
    }


def test_deep_research_costs_caps_and_registers_provenance(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    monkeypatch.setattr(toolbelt, "_live_task", _fake_task)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 8})
    ctx.invocation_id = "inv-deep-test"

    r1 = asyncio.run(toolbelt.deep_research("who owns the master of X?", "E001", ctx))
    assert r1["cached"] is False and r1["budget_remaining"] == 5
    assert r1["citations"][0]["excerpts"] == [DEEP_EXCERPT]
    assert toolbelt._excerpt_exists(DEEP_EXCERPT, ctx)

    # same question again: cached, no extra spend
    r2 = asyncio.run(toolbelt.deep_research("who owns the master of X?", "E001", ctx))
    assert r2["cached"] is True
    assert ctx.state["research_budget:clearance_counsel"] == 5

    # allowance: 2 per desk
    asyncio.run(toolbelt.deep_research("second hard question", "E002", ctx))
    r4 = asyncio.run(toolbelt.deep_research("third hard question", "E003", ctx))
    assert "error" in r4 and "allowance" in r4["error"]


def test_deep_research_refunds_budget_on_failure(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)

    def boom(q, p):
        raise RuntimeError("api down")

    monkeypatch.setattr(toolbelt, "_live_task", boom)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 8})
    r = asyncio.run(toolbelt.deep_research("hard question", "E001", ctx))
    assert "error" in r
    assert ctx.state["research_budget:clearance_counsel"] == 8  # refunded


def test_research_geo_and_domain_modifiers_reach_live_search(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    seen = {}

    def fake_search(objective, queries, session_id=None, country="", include_domains=None):
        seen["country"] = country
        seen["domains"] = include_domains
        return CASSETTE

    monkeypatch.setattr(toolbelt, "_live_search", fake_search)
    ctx = make_ctx(agent_name="territory_censor")
    asyncio.run(
        toolbelt.research(
            "CN censorship of supernatural",
            ["china film supernatural"],
            "E009",
            ctx,
            country="CN",
            restrict_to_domains=["gov.cn"],
        )
    )
    assert seen == {"country": "CN", "domains": ["gov.cn"]}


def test_research_country_alone_does_not_crash(monkeypatch):
    # The Social Network outage, 2026-08-26: country="CN" with no domain list hit
    # sorted(None) in the cache-key modifier and the TypeError aborted the run.
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    monkeypatch.setattr(toolbelt, "_live_search", lambda o, q, **kw: CASSETTE)
    ctx = make_ctx(agent_name="territory_censor")
    r = asyncio.run(
        toolbelt.research("CN standard", ["china film rule"], "E001", ctx, country="CN")
    )
    assert r["cached"] is False and r["results"]


def test_research_live_failure_refunds_and_returns_error(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)

    def boom(*a, **kw):
        raise RuntimeError("api down")

    monkeypatch.setattr(toolbelt, "_live_search", boom)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 3})
    r = asyncio.run(toolbelt.research("q", ["q"], "E001", ctx))
    assert "error" in r
    assert ctx.state["research_budget:clearance_counsel"] == 3


def test_breaker_aborts_when_api_is_down(monkeypatch):
    # Dependency down = fail loud: consecutive failures with zero successes
    # must raise so the run aborts honestly instead of shipping empty research.
    import pytest

    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)

    def boom(*a, **kw):
        raise RuntimeError("api down")

    monkeypatch.setattr(toolbelt, "_live_search", boom)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 20})
    ctx.invocation_id = "inv-breaker-test"
    for i in range(toolbelt._BREAKER_CONSECUTIVE - 1):
        r = asyncio.run(toolbelt.research(f"q{i}", ["q"], f"E00{i}", ctx))
        assert "error" in r
    with pytest.raises(RuntimeError, match="unreachable"):
        asyncio.run(toolbelt.research("q-last", ["q"], "E009", ctx))
    assert ctx.state["research_failures"] == toolbelt._BREAKER_CONSECUTIVE


def test_breaker_stays_open_after_any_success(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return CASSETTE
        raise RuntimeError("api down")

    monkeypatch.setattr(toolbelt, "_live_search", flaky)
    ctx = make_ctx(**{"research_budget:clearance_counsel": 20})
    ctx.invocation_id = "inv-breaker-open-test"
    assert asyncio.run(toolbelt.research("good", ["q"], "E001", ctx))["cached"] is False
    for i in range(toolbelt._BREAKER_CONSECUTIVE + 2):  # never raises: one success this run
        r = asyncio.run(toolbelt.research(f"bad{i}", ["q"], f"E01{i}", ctx))
        assert "error" in r


def test_tool_error_shield_corrects_hallucinated_tools_but_lets_runabort_kill():
    # The run_code outage: an unknown-tool ValueError must become a corrective
    # message to the model; the deliberate RunAbortError must still abort the run.
    from greenlight.agents.common import tool_error_shield

    r = tool_error_shield(None, {}, None, ValueError("Tool 'run_code' not found."))
    assert r is not None and "no code execution" in r["guidance"]
    assert tool_error_shield(None, {}, None, toolbelt.RunAbortError("api down")) is None


def test_prune_disposition_aware():
    """Archive closed case files; never touch open ones; ceiling bounds monsters."""
    from types import SimpleNamespace as NS

    from google.genai import types as gt

    from greenlight.agents import common

    def pair(entity, i):
        call = gt.Content(
            role="model",
            parts=[
                gt.Part(
                    function_call=gt.FunctionCall(
                        name="research", args={"entity_id": entity, "objective": f"q{i}"}
                    )
                )
            ],
        )
        resp = gt.Content(
            role="user",
            parts=[
                gt.Part(
                    function_response=gt.FunctionResponse(
                        name="research", response={"results": [f"{entity}-" + "x" * 4000]}
                    )
                )
            ],
        )
        return [call, resp]

    # 18 exchanges: alternating FILED (E1) and OPEN (E2) entities
    contents = []
    for i in range(18):
        contents.extend(pair("E1" if i % 2 == 0 else "E2", i))
    ctx = NS(
        agent_name="clearance_counsel", state={"flags:clearance_counsel": [{"entity_id": "E1"}]}
    )
    req = NS(contents=list(contents))
    assert common.prune_stale_tool_results(ctx, req) is None

    def payload(c):
        return str(c.parts[0].function_response.response)

    resps = [c for c in req.contents if c.parts[0].function_response is not None]
    stale, recent = resps[:-12], resps[-12:]
    # dispositioned entity E1: old bulky results trimmed, head preserved
    e1_stale = [c for c in stale if "E1-" in payload(c) or "E1" in payload(c)[:40]]
    assert e1_stale and all("trimmed" in payload(c) for c in e1_stale)
    assert all(payload(c).count("x") >= 200 for c in e1_stale)
    # open entity E2: untouched at any age (below the hard ceiling)
    e2_stale = [c for c in stale if "E2-" in payload(c)]
    assert e2_stale and all("trimmed" not in payload(c) for c in e2_stale)
    # recency floor: nothing recent is touched
    assert all("trimmed" not in payload(c) for c in recent)


def test_prune_hard_ceiling_bounds_open_items():
    from types import SimpleNamespace as NS

    from google.genai import types as gt

    from greenlight.agents import common

    contents = []
    for i in range(50):  # all OPEN (no flags filed) — protected until the absolute bound
        contents.append(
            gt.Content(
                role="model",
                parts=[
                    gt.Part(
                        function_call=gt.FunctionCall(name="research", args={"entity_id": f"E{i}"})
                    )
                ],
            )
        )
        contents.append(
            gt.Content(
                role="user",
                parts=[
                    gt.Part(
                        function_response=gt.FunctionResponse(
                            name="research", response={"results": ["y" * 4000]}
                        )
                    )
                ],
            )
        )
    ctx = NS(agent_name="clearance_counsel", state={})
    req = NS(contents=list(contents))
    common.prune_stale_tool_results(ctx, req)

    def payload(c):
        return str(c.parts[0].function_response.response)

    resps = [c for c in req.contents if c.parts[0].function_response is not None]
    # open-entity research is working memory: the 40-exchange ceiling must NOT
    # touch it — only the absolute bound (120) may, and 50 < 120.
    assert all("trimmed" not in payload(c) for c in resps)


def test_prune_absolute_bound_and_entityless_ceiling():
    from types import SimpleNamespace as NS

    from google.genai import types as gt

    from greenlight.agents import common

    def resp_pair(name, args, payload_text):
        return [
            gt.Content(
                role="model",
                parts=[gt.Part(function_call=gt.FunctionCall(name=name, args=args))],
            ),
            gt.Content(
                role="user",
                parts=[
                    gt.Part(
                        function_response=gt.FunctionResponse(
                            name=name, response={"result": payload_text}
                        )
                    )
                ],
            ),
        ]

    # 130 open-entity exchanges: those beyond the absolute bound trim
    contents = []
    for i in range(130):
        contents.extend(resp_pair("research", {"entity_id": f"E{i}"}, "y" * 4000))
    ctx = NS(agent_name="clearance_counsel", state={})
    req = NS(contents=list(contents))
    common.prune_stale_tool_results(ctx, req)
    resps = [c for c in req.contents if c.parts[0].function_response is not None]

    def payload(c):
        return str(c.parts[0].function_response.response)

    assert sum("trimmed" in payload(c) for c in resps) == 10  # 130 - 120
    # entity-less bulky results (read_scene) DO trim at the 40 ceiling
    contents = []
    for i in range(50):
        contents.extend(resp_pair("read_scene", {"scene_id": f"S{i:03d}"}, "z" * 4000))
    req = NS(contents=list(contents))
    common.prune_stale_tool_results(ctx, req)
    resps = [c for c in req.contents if c.parts[0].function_response is not None]
    assert sum("trimmed" in payload(c) for c in resps) == 10  # 50 - 40


def test_provenance_rejection_hands_back_quotable_excerpts(monkeypatch):
    # The 145-rejection loop: after pruning trims a result the desk paraphrases
    # and fails the verbatim gate forever. The rejection must now include the
    # entity's REAL registered excerpts so the next attempt can copy them.
    ctx = make_ctx()
    ctx.invocation_id = "inv-handback-isolated"  # own registry bucket
    msg = toolbelt.file_flag(
        scene_ids=["S002"],
        severity="MEDIUM",
        category="trademark_use",
        finding="A brand appears prominently.",
        citations=[
            {
                "source_type": "web",
                "url": "https://example.com/clearance",
                "excerpt": "a paraphrased memory of the rule that was never retrieved verbatim",
            }
        ],
        remedy_action="REPLACE",
        remedy_detail="Swap the prop.",
        confidence=0.8,
        tool_context=ctx,
        entity_id="E001",
    )
    assert msg.startswith("REJECTED")
    assert "VERBATIM excerpts on record" in msg
    assert RESEARCH_EXCERPT[:80] in msg  # the seeded registered excerpt is offered back


def test_file_flag_auto_repairs_near_miss_citation():
    # The Winklevoss loop: a paraphrase of a REAL retrieval must be repaired to
    # the registered verbatim text and FILED — form must not kill substance.
    ctx = make_ctx()
    ctx.invocation_id = "inv-repair-isolated"
    toolbelt._register_provenance(ctx, [RESEARCH_EXCERPT])
    # ~70% of the original words survive: below the 90% pass-through tolerance,
    # inside the 60% repair band — the Winklevoss shape.
    near_miss = (
        "If the product appears in a negative light on screen, you may be "
        "sued for product disparagement by them."
    )
    msg = toolbelt.file_flag(
        scene_ids=["S002"],
        severity="MEDIUM",
        category="trademark_disparagement",
        finding="The product is disparaged on screen.",
        citations=[
            {"source_type": "web", "url": "https://example.com/clearance", "excerpt": near_miss}
        ],
        remedy_action="REPLACE",
        remedy_detail="Swap the prop.",
        confidence=0.8,
        tool_context=ctx,
        entity_id="E001",
    )
    assert msg.startswith("Filed F") and "auto-corrected" in msg
    flag = ctx.state["flags:clearance_counsel"][-1]
    # verbatim by construction (registry stores whitespace/case-normalized text)
    assert flag["citations"][0]["excerpt"].lower() in RESEARCH_EXCERPT.lower()


def test_file_flag_retry_limit_breaks_rejection_loops():
    ctx = make_ctx()
    ctx.invocation_id = "inv-retry-limit"

    def attempt():
        return toolbelt.file_flag(
            scene_ids=["S002"],
            severity="LOW",
            category="trademark_use",
            finding="x",
            citations=[
                {
                    "source_type": "web",
                    "url": "https://x.example",
                    "excerpt": "words that resemble nothing retrieved at all in this run whatsoever",
                }
            ],
            remedy_action="NO_ACTION",
            remedy_detail="n/a",
            confidence=0.5,
            tool_context=ctx,
            entity_id="E077",
        )

    msgs = [attempt() for _ in range(toolbelt._PROV_RETRY_LIMIT)]
    assert all(m.startswith("REJECTED") for m in msgs)
    assert "DO NOT retry" in msgs[-1] and "note_open_question" in msgs[-1]


# --- clearance batching -----------------------------------------------------


def _worklist(n):
    return [{"entity_id": f"E{i:03d}", "note": f"item {i}"} for i in range(1, n + 1)]


def test_clearance_batch_slices_priority_and_bounds():
    entities = [
        {"entity_id": f"E{i:03d}", "prominence": ("PLOT_CRITICAL" if i > 55 else "BACKGROUND")}
        for i in range(1, 61)
    ]
    state = {"triage": {"entities": entities, "clearance_counsel": _worklist(60)}}
    slices = toolbelt.clearance_batch_slices(state)
    assert len(slices) == 3  # ceil(60/25)
    assert sum(len(x) for x in slices) == 60
    # PLOT_CRITICAL items (E056-E060) lead batch 1
    assert [it["entity_id"] for it in slices[0][:5]] == ["E056", "E057", "E058", "E059", "E060"]
    # small worklists stay a single batch
    small = {"triage": {"entities": entities[:10], "clearance_counsel": _worklist(10)}}
    assert len(toolbelt.clearance_batch_slices(small)) == 1


def test_batch_budget_partition_and_isolation(monkeypatch):
    monkeypatch.setattr(toolbelt, "_durable_cache_load", lambda k: None)
    monkeypatch.setattr(toolbelt, "_durable_cache_store", lambda k, r: None)
    monkeypatch.setattr(toolbelt, "_live_search", lambda o, q, **kw: CASSETTE)
    shared = FakeState(
        {
            "triage": {"entities": [], "clearance_counsel": _worklist(50)},
            "research_budget:clearance_counsel": 40,
            "scenes": [],
        }
    )
    from types import SimpleNamespace

    b1 = SimpleNamespace(
        agent_name="clearance_counsel__b1", state=shared, actions=SimpleNamespace(escalate=False)
    )
    b2 = SimpleNamespace(
        agent_name="clearance_counsel__b2", state=shared, actions=SimpleNamespace(escalate=False)
    )
    asyncio.run(toolbelt.research("q1", ["q"], "E001", b1))
    asyncio.run(toolbelt.research("q2", ["q"], "E002", b2))
    # 50 items -> 2 batches of 25 -> each gets ceil(40*25/50)=20, minus one spent
    assert shared["research_budget:clearance_counsel__b1"] == 19
    assert shared["research_budget:clearance_counsel__b2"] == 19
    assert shared["research_budget:clearance_counsel"] == 40  # base pool untouched


def test_batch_flags_isolated_and_aggregated():
    from types import SimpleNamespace

    shared = FakeState(make_ctx().state)  # seeded provenance etc.
    b1 = SimpleNamespace(
        agent_name="clearance_counsel__b1", state=shared, actions=SimpleNamespace(escalate=False)
    )
    b2 = SimpleNamespace(
        agent_name="clearance_counsel__b2", state=shared, actions=SimpleNamespace(escalate=False)
    )
    for ctx in (b1, b2):
        msg = toolbelt.file_flag(
            scene_ids=["S002"],
            severity="MEDIUM",
            category="trademark_use",
            finding="brand appears",
            citations=[dict(GOOD_CITATION)],
            remedy_action="REPLACE",
            remedy_detail="swap",
            confidence=0.8,
            tool_context=ctx,
            entity_id="E001",
        )
        assert msg.startswith("Filed F1")
    assert len(shared.get("flags:clearance_counsel__b1")) == 1
    assert len(shared.get("flags:clearance_counsel__b2")) == 1
    agg = toolbelt.desk_flags(shared, "clearance_counsel")
    assert len(agg) == 2
    ids = {f["flag_id"] for f in agg}
    assert len(ids) == 2  # no id collision across parallel batches


def test_done_judges_batch_against_its_slice():
    from types import SimpleNamespace

    state = FakeState(
        {
            "triage": {"entities": [], "clearance_counsel": _worklist(50)},
            "research_budget:clearance_counsel": 40,
            "flags:clearance_counsel__b1": [{"flag_id": f"F{i}"} for i in range(101, 121)],
        }
    )
    b1 = SimpleNamespace(
        agent_name="clearance_counsel__b1", state=state, actions=SimpleNamespace(escalate=False)
    )
    # 20 dispositions of a 25-item slice = 80% coverage -> closes
    assert toolbelt.done("batch finished", b1).startswith("Desk closed")
    assert b1.actions.escalate is True
    # a fresh batch with nothing done and budget in hand is refused
    b2 = SimpleNamespace(
        agent_name="clearance_counsel__b2", state=state, actions=SimpleNamespace(escalate=False)
    )
    assert toolbelt.done("lazy", b2).startswith("NOT CLOSED")
