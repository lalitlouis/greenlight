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


_CTX_SEQ = iter(range(10**6))


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
                    "url": "https://www.copyright.gov/clearance",
                    "title": "Clearance overview",
                    "excerpts": [RESEARCH_EXCERPT],
                }
            ],
        },
    }
    base.update(state)
    return SimpleNamespace(
        agent_name=agent_name,
        state=FakeState(base),
        actions=SimpleNamespace(escalate=False),
        invocation_id=f"test-inv-{next(_CTX_SEQ)}",  # isolate process-local registries per test
    )


GOOD_CITATION = {
    "title": "Clearance overview",
    "url": "https://www.copyright.gov/clearance",
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
    assert msg.startswith("Filed F1001")
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
    assert file_good_flag(ctx).startswith("Filed F1002")


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
    assert c1.startswith("Filed F1001") and t1.startswith("Filed F4001")


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
    from types import SimpleNamespace

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
    ctx = SimpleNamespace(
        agent_name="clearance_counsel", state={"flags:clearance_counsel": [{"entity_id": "E1"}]}
    )
    req = SimpleNamespace(contents=list(contents))
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
    from types import SimpleNamespace

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
    ctx = SimpleNamespace(agent_name="clearance_counsel", state={})
    req = SimpleNamespace(contents=list(contents))
    common.prune_stale_tool_results(ctx, req)

    def payload(c):
        return str(c.parts[0].function_response.response)

    resps = [c for c in req.contents if c.parts[0].function_response is not None]
    # open-entity research is working memory: the 40-exchange ceiling must NOT
    # touch it — only the absolute bound (120) may, and 50 < 120.
    assert all("trimmed" not in payload(c) for c in resps)


def test_prune_absolute_bound_and_entityless_ceiling():
    from types import SimpleNamespace

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
    ctx = SimpleNamespace(agent_name="clearance_counsel", state={})
    req = SimpleNamespace(contents=list(contents))
    common.prune_stale_tool_results(ctx, req)
    resps = [c for c in req.contents if c.parts[0].function_response is not None]

    def payload(c):
        return str(c.parts[0].function_response.response)

    assert sum("trimmed" in payload(c) for c in resps) == 10  # 130 - 120
    # entity-less bulky results (read_scene) DO trim at the 40 ceiling
    contents = []
    for i in range(50):
        contents.extend(resp_pair("read_scene", {"scene_id": f"S{i:03d}"}, "z" * 4000))
    req = SimpleNamespace(contents=list(contents))
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
                "url": "https://www.copyright.gov/clearance",
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
            {
                "source_type": "web",
                "url": "https://www.copyright.gov/clearance",
                "excerpt": near_miss,
            }
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
                    "excerpt": "words resembling nothing retrieved in this run at all",
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

    wl = _worklist(50)
    slice1_ids = [w["entity_id"] for w in wl[:25]]
    state = FakeState(
        {
            "triage": {"entities": [], "clearance_counsel": wl},
            "research_budget:clearance_counsel": 40,
            # every slice-1 entity carries a disposition (flags + clearances)
            "flags:clearance_counsel__b1": [
                {"flag_id": f"F{i}", "entity_id": eid} for i, eid in enumerate(slice1_ids[:20], 101)
            ],
            "cleared:clearance_counsel__b1": [
                {"entity_id": eid, "reasoning": "no issue"} for eid in slice1_ids[20:]
            ],
        }
    )
    b1 = SimpleNamespace(
        agent_name="clearance_counsel__b1", state=state, actions=SimpleNamespace(escalate=False)
    )
    assert toolbelt.done("batch finished", b1).startswith("Desk closed")
    assert b1.actions.escalate is True
    # a fresh batch with nothing done and budget in hand is refused BY NAME —
    # the Summers rule: unaddressed entities are enumerated, never averaged away
    b2 = SimpleNamespace(
        agent_name="clearance_counsel__b2", state=state, actions=SimpleNamespace(escalate=False)
    )
    msg = toolbelt.done("lazy", b2)
    assert msg.startswith("NOT CLOSED") and "E026" in msg


def test_flag_ids_stable_across_fresh_state_wrappers():
    # ADK hands tools a fresh state wrapper per call; ids must not reset.
    from types import SimpleNamespace

    base = make_ctx().state
    ids = []
    for i in range(3):
        ctx = SimpleNamespace(
            agent_name="clearance_counsel",
            state=FakeState(base),  # new wrapper object each call, same content
            actions=SimpleNamespace(escalate=False),
        )
        ctx.invocation_id = "inv-stable-ids"
        base = ctx.state
        msg = toolbelt.file_flag(
            scene_ids=["S002"],
            severity="LOW",
            category="trademark_use",
            finding=f"finding {i}",
            citations=[dict(GOOD_CITATION)],
            remedy_action="NO_ACTION",
            remedy_detail="n/a",
            confidence=0.5,
            tool_context=ctx,
            entity_id="E001",
        )
        assert msg.startswith("Filed F")
        ids.append(msg.split()[1])
    assert len(set(ids)) == 3, ids


def test_contract_rejections_hit_the_retry_cap_too():
    # The E030 loop: 62 identical schema-invalid retries sailed past the
    # provenance-only cap. Every rejection path now shares one ledger.
    ctx = make_ctx()

    def attempt():
        return toolbelt.file_flag(
            scene_ids=["S002"],
            severity="FYI",
            category="organization_clearance",
            finding="x",
            citations=[
                {"source_type": "instruction", "url": "https://x", "excerpt": RESEARCH_EXCERPT}
            ],
            remedy_action="NO_ACTION",
            remedy_detail="n/a",
            confidence=0.5,
            tool_context=ctx,
            entity_id="E030",
        )

    msgs = [attempt() for _ in range(toolbelt._PROV_RETRY_LIMIT + 1)]
    assert all(m.startswith("REJECTED") for m in msgs)
    assert "DO NOT retry" in msgs[toolbelt._PROV_RETRY_LIMIT - 1]
    assert "DO NOT retry" in msgs[-1]


# ---- calibration-batch guards (2026-08-27 review: A1, A2, A3) ----


def test_umbrella_flag_rejected_beyond_scene_cap():
    """A1: a clearance finding spanning the whole script swallows real entities
    (the F101 failure: 137 scenes, twelve people, one finding)."""
    ctx = make_ctx()
    msg = file_good_flag(ctx, scene_ids=[f"S{i:03d}" for i in range(1, 11)])
    assert "REJECTED" in msg and "PER" in msg.upper()
    assert not ctx.state.get("flags:clearance_counsel")


def test_ratings_findings_may_aggregate_scenes():
    """Cumulative-content categories legitimately anchor to many scenes."""
    ctx = make_ctx(
        agent_name="ratings_board",
        **{
            "research_budget:ratings_board": 3,
            "research_keys:ratings_board": ["research:E001:seeded"],
        },
    )
    msg = file_good_flag(
        ctx,
        category="rating_language",
        scene_ids=[f"S{i:03d}" for i in range(1, 10)],
        # rating_ categories demand a ratings authority, not just any .gov
        citations=[{**GOOD_CITATION, "url": "https://www.filmratings.com/rules"}],
    )
    assert msg.startswith("Filed"), msg


def test_background_only_sources_rejected_at_medium_plus():
    """A3: fan wikis and forums cannot carry a legal conclusion alone."""
    ctx = make_ctx(
        **{
            "research:E001:seeded": {
                "objective": "seeded",
                "search_id": "s0",
                "results": [
                    {
                        "url": "https://rating-system.fandom.com/wiki/R",
                        "title": "Fan wiki",
                        "excerpts": [RESEARCH_EXCERPT],
                    }
                ],
            },
        }
    )
    bg_cite = {
        "title": "Fan wiki",
        "url": "https://rating-system.fandom.com/wiki/R",
        "excerpt": RESEARCH_EXCERPT,
    }
    msg = file_good_flag(ctx, citations=[bg_cite])
    assert "REJECTED" in msg and "authoritative" in msg
    # the same evidence is acceptable at background severity
    msg2 = file_good_flag(ctx, citations=[bg_cite], severity="FYI")
    assert msg2.startswith("Filed"), msg2


def test_record_clearance_counts_and_requires_reasoning():
    """A2: examined-and-fine work becomes visible, and bare 'cleared' is refused."""
    ctx = make_ctx()
    assert "REJECTED" in toolbelt.record_clearance("E001", "  ", ctx)
    msg = toolbelt.record_clearance("E001", "Public domain since 1922; no recording used.", ctx)
    assert msg.startswith("Recorded")
    (entry,) = ctx.state["cleared:clearance_counsel"]
    assert entry["entity_id"] == "E001"
    assert toolbelt.desk_cleared(ctx.state, "clearance_counsel")


def test_rating_prediction_must_follow_or_rebut_comps():
    """'Evidence, not opinion' is a contract: contradicting the comparables'
    weighted majority without a stated reason is rejected."""
    ctx = make_ctx(agent_name="ratings_board")
    comps = [
        {"rating": "PG-13", "distance": 0.30},
        {"rating": "PG-13", "distance": 0.32},
        {"rating": "R", "distance": 0.45},
    ]
    ctx.state["last_precedent:ratings_board"] = comps
    msg = toolbelt.file_rating_prediction("R", "for pervasive language", [], ctx)
    assert "REJECTED" in msg and "majority" in msg
    msg = toolbelt.file_rating_prediction(
        "R",
        "for pervasive language",
        [],
        ctx,
        divergence_reason="comps match setting but the F-word count alone forces R per CARA",
    )
    assert msg.startswith("Prediction filed")
    pred = ctx.state["rating_prediction"]
    assert pred["comps_majority"] == "PG-13" and pred["divergence_reason"]
    # following the evidence needs no reason
    ctx2 = make_ctx(agent_name="ratings_board")
    ctx2.state["last_precedent:ratings_board"] = comps
    assert toolbelt.file_rating_prediction("PG-13", "for thematic elements", [], ctx2).startswith(
        "Prediction filed"
    )


def test_unverified_registration_number_rejected(monkeypatch):
    """Review item #8: a cited registration number must resolve on the register."""
    ctx = make_ctx()
    msg = file_good_flag(
        ctx, finding="Bubble-Yum is a registered trademark (Reg. #1001109) owned by Hershey."
    )
    assert "REJECTED" in msg and "verify_trademark" in msg
    # after a successful verification this run, the same filing goes through
    monkeypatch.setattr(
        toolbelt, "_tsdr_lookup", lambda d: {"number": d, "mark": "BUBBLE YUM", "status": "LIVE"}
    )
    assert toolbelt.verify_trademark("1001109", ctx)["mark"] == "BUBBLE YUM"
    msg = file_good_flag(
        ctx, finding="Bubble-Yum is a registered trademark (Reg. #1001109) owned by Hershey."
    )
    assert msg.startswith("Filed"), msg


def test_csatf_bulletin_lookup_and_no_guessing():
    ctx = make_ctx(agent_name="safety_underwriter")
    hits = toolbelt.csatf_bulletin("open flame", ctx)["matches"]
    assert "19" in hits
    res = toolbelt.csatf_bulletin("zzz nonexistent topic", ctx)
    assert res["matches"] == {} and "guessing" in res["guidance"]


def test_prediction_outside_conformal_set_needs_reason():
    """The measured boundary is part of the evidence contract."""
    ctx = make_ctx(agent_name="ratings_board")
    comps = [{"rating": "R", "distance": 0.30}, {"rating": "R", "distance": 0.35}]
    ctx.state["last_precedent:ratings_board"] = comps
    ctx.state["boundary_set:ratings_board"] = ["R"]
    msg = toolbelt.file_rating_prediction("PG-13", "for language", [], ctx)
    assert "REJECTED" in msg and "conformal" in msg
    msg = toolbelt.file_rating_prediction(
        "PG-13",
        "for language",
        [],
        ctx,
        divergence_reason="every counted instance is recounted dialogue, not depiction",
    )
    assert msg.startswith("Prediction filed")


def test_rating_boundary_returns_marginals_and_set():
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["pervasive language"], ctx)
    assert r["marginals"]["pervasive language"]["distribution"].popitem()[0] in ("R", "PG-13")
    assert r["conformal_prediction_set"] == ["R"]
    assert ctx.state["boundary_set:ratings_board"] == ["R"]


def test_rating_boundary_emits_a_citable_sentence_registered_as_provenance():
    """The marginal's number must travel to the report in a CITATION the verifier can
    trace, not loose in the desk's prose (where an untraceable '57% of 125' was rejected
    as unsupported). The tool returns a ready sentence carrying the numbers, attributes
    it to our derived corpus by name, and registers it so a verbatim cite passes."""
    ctx = make_ctx(agent_name="ratings_board")
    r = toolbelt.rating_boundary(["pervasive language"], ctx)
    cite = r["marginals"]["pervasive language"]["citation"]
    assert "187" in cite and "99%" in cite  # the numbers live here
    assert "ScriptRisk CARA descriptor corpus" in cite  # our corpus, not filmratings.com
    assert "filmratings.com" not in r["source"].split(":")[0]  # named as ours in the headline
    registered = [orig for _, orig in toolbelt._prov_bucket(ctx)]
    assert cite in registered  # a verbatim cite of this sentence passes provenance


# --- Night Counter review fixes -------------------------------------------


def test_strip_json_escapes():
    from greenlight.tools.toolbelt import _strip_json_escapes

    assert _strip_json_escapes("He\\'ll be back") == "He'll be back"
    assert _strip_json_escapes('a \\"quoted\\" word') == 'a "quoted" word'
    assert _strip_json_escapes("C:\\network\\path") == "C:\\network\\path"
    assert _strip_json_escapes("") == ""


def test_open_question_rejects_determinations():
    from greenlight.tools.toolbelt import _reads_as_determination

    assert _reads_as_determination(
        "Name sweep complete: all fictional names cleared, no distinctive collisions."
    )
    assert _reads_as_determination("No sync license required; composition is public domain.")
    assert not _reads_as_determination("Chain of title unclear beyond the second assignee.")
    assert not _reads_as_determination("Who controls the 1988 remaster?")


def test_unexamined_entities_accounting():
    from greenlight.tools.toolbelt import unexamined_entities

    state = {
        "triage": {
            "entities": [
                {"entity_id": "E001", "surface": "Red Bull", "scene_ids": ["S001"]},
                {"entity_id": "E002", "surface": "Nighthawks", "scene_ids": ["S002"]},
                {"entity_id": "E003", "surface": "Baba O'Riley", "scene_ids": ["S003"]},
                {"entity_id": "E004", "surface": "Coors", "scene_ids": ["S004"]},
            ]
        },
        "flags:clearance_counsel": [{"entity_id": "E001"}],
        "cleared:clearance_counsel__sweep": [{"entity_id": "E002"}],
        "open_questions:territory_censor": ["Who controls Baba O'Riley sync in CN?"],
    }
    out = unexamined_entities(state)
    assert [u["entity_id"] for u in out] == ["E004"]  # sweeper + OQ-by-surface count


def test_unexamined_is_desk_scoped():
    """Safety clearing a clearance-worklist item does NOT cover it — the
    wrong desk answering the wrong question was the first live validation's
    failure (Nighthawks 'no physical hazard')."""
    from greenlight.tools.toolbelt import unexamined_entities

    state = {
        "triage": {
            "entities": [{"entity_id": "E001", "surface": "Nighthawks", "scene_ids": ["S001"]}],
            "clearance_counsel": [{"entity_id": "E001", "note": "artwork rights"}],
        },
        "cleared:safety_underwriter": [{"entity_id": "E001"}],
    }
    out = unexamined_entities(state)
    assert len(out) == 1 and out[0]["desks"] == ["clearance_counsel"]
    state["cleared:clearance_counsel__b2"] = [{"entity_id": "E001"}]
    assert unexamined_entities(state) == []


# --- work-item identity -----------------------------------------------------


def _wi_state():
    return {
        "triage": {
            "entities": [],
            "territory_censor": [
                {"entity_id": "", "work_item_id": "TC-AX-CN-SUPERNATURAL", "note": "sweep S003"}
            ],
        }
    }


def test_done_refuses_scene_item_then_closes_on_work_item_id():
    """The original bug: entity_id='' items were permanently unsatisfiable."""
    from unittest.mock import MagicMock

    from greenlight.tools.toolbelt import done, record_clearance

    state = _wi_state()
    state["research_budget:territory_censor"] = 10
    ctx = MagicMock()
    ctx.state = state
    ctx.agent_name = "territory_censor"
    out = done("finished", ctx)
    assert "NOT CLOSED" in out and "TC-AX-CN-SUPERNATURAL" in out
    record_clearance(
        "", "find_in_script ghost — 0 matches", ctx, work_item_id="TC-AX-CN-SUPERNATURAL"
    )
    assert done("finished", ctx).startswith("Desk closed")


def test_unexamined_tracks_scene_level_items_and_sweeper_credit():
    from greenlight.tools.toolbelt import unexamined_entities

    state = _wi_state()
    out = unexamined_entities(state)
    assert [u["work_item_id"] for u in out] == ["TC-AX-CN-SUPERNATURAL"]
    assert out[0]["scene_ids"] == ["S003"]
    state["wi_done:clearance_counsel__sweep"] = ["TC-AX-CN-SUPERNATURAL"]
    assert unexamined_entities(state) == []


def test_file_flag_rejection_marks_nothing():
    from unittest.mock import MagicMock

    from greenlight.tools.toolbelt import file_flag

    ctx = MagicMock()
    ctx.state = {"scenes": []}
    ctx.agent_name = "territory_censor"
    ctx.invocation_id = "t"
    out = file_flag(
        scene_ids=["S001"],
        severity="HIGH",
        category="territory_cn_supernatural",
        finding="x",
        citations=[],
        remedy_action="CUT",
        remedy_detail="y",
        confidence=0.9,
        tool_context=ctx,
        work_item_id="TC-W001",
    )
    assert "REJECTED" in out
    assert not ctx.state.get("wi_done:territory_censor")


def test_old_style_worklists_unchanged():
    from unittest.mock import MagicMock

    from greenlight.tools.toolbelt import done

    state = {
        "triage": {"territory_censor": [{"entity_id": "E001", "note": "n"}]},
        "cleared:territory_censor": [{"entity_id": "E001"}],
        "research_budget:territory_censor": 10,
    }
    ctx = MagicMock()
    ctx.state = state
    ctx.agent_name = "territory_censor"
    assert done("finished", ctx).startswith("Desk closed")


def test_batch_slices_preserve_work_item_ids():
    from greenlight.tools.toolbelt import clearance_batch_slices

    state = {
        "triage": {
            "entities": [],
            "clearance_counsel": [
                {"entity_id": f"E{i:03d}", "work_item_id": f"CC-W{i:03d}", "note": "n"}
                for i in range(1, 31)
            ],
        }
    }
    slices = clearance_batch_slices(state)
    ids = [it["work_item_id"] for sl in slices for it in sl]
    assert sorted(ids) == [f"CC-W{i:03d}" for i in range(1, 31)]


# --- descriptor honesty ------------------------------------------------------


def _boundary_ctx():
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.state = {}
    ctx.agent_name = "ratings_board"
    ctx.invocation_id = "t"
    return ctx


def test_rating_boundary_reports_unmatched_and_clears_gate():
    from greenlight.tools.toolbelt import rating_boundary

    ctx = _boundary_ctx()
    out = rating_boundary(["strong language", "intense depiction of very bad weather"], ctx)
    assert out["matched_descriptors"] == ["strong language"]
    assert out["unmatched_descriptors"] == ["intense depiction of very bad weather"]
    assert "warning" in out and "coverage_note" not in out
    assert ctx.state["boundary_set:ratings_board"] == []  # advisory, not a gate


def test_rating_boundary_empty_input_no_guarantee():
    from greenlight.tools.toolbelt import rating_boundary

    ctx = _boundary_ctx()
    out = rating_boundary([], ctx)
    assert "warning" in out and "coverage_note" not in out
    assert ctx.state["boundary_set:ratings_board"] == []


def test_rating_boundary_full_match_keeps_gate_and_group_note():
    from greenlight.tools.toolbelt import rating_boundary

    ctx = _boundary_ctx()
    out = rating_boundary(["pervasive language"], ctx)
    assert out["unmatched_descriptors"] == []
    assert "pooled" in out["coverage_note"]
    assert ctx.state["boundary_set:ratings_board"] == out["conformal_prediction_set"]


def test_rating_boundary_vocabulary_normalizes_common_phrasings():
    from greenlight.tools.toolbelt import rating_boundary

    ctx = _boundary_ctx()
    out = rating_boundary(["drug content", "sexual content", "thematic elements"], ctx)
    assert out["unmatched_descriptors"] == []


def test_whatif_and_live_share_one_voting_rule():
    """Same neighbours, same answer — plain plurality vs weighted majority
    once disagreed whenever a near neighbour opposed a far cluster."""
    from greenlight.tools.toolbelt import _comps_weighted_majority, comps_weighted_majority

    comps = [
        {"rating": "R", "distance": 0.05},
        {"rating": "PG-13", "distance": 0.40},
        {"rating": "PG-13", "distance": 0.42},
    ]
    # plurality would say PG-13; the weighted rule says R — and both paths use it
    assert comps_weighted_majority(comps) == "R"
    assert comps_weighted_majority(comps) == _comps_weighted_majority(comps)


# --- collapse retry ---------------------------------------------------------


def test_collapsed_desks_detects_zero_own_dispositions():
    from greenlight.tools.toolbelt import collapsed_desks

    state = {
        "triage": {
            "territory_censor": [
                {"entity_id": "", "work_item_id": "TC-AX-CN-DRUG_USE", "note": "n"}
            ],
            "ratings_board": [{"entity_id": "", "work_item_id": "RB-W001", "note": "n"}],
        },
        "cleared:ratings_board": [{"entity_id": None, "work_item_id": "RB-W001"}],
        # the SWEEPER covering territory's items must NOT count as the desk's own
        "cleared:clearance_counsel__sweep": [
            {"entity_id": None, "work_item_id": "TC-AX-CN-DRUG_USE"}
        ],
    }
    assert collapsed_desks(state) == ["territory_censor"]
    # a retry-instance disposition counts as the desk's own
    state["cleared:territory_censor__retry"] = [
        {"entity_id": None, "work_item_id": "TC-AX-CN-DRUG_USE"}
    ]
    assert collapsed_desks(state) == []


def test_retry_done_uses_retry_worklist_and_does_not_escalate():
    from unittest.mock import MagicMock

    from greenlight.tools.toolbelt import done

    state = {
        "triage": {
            "territory_censor": [{"entity_id": "E1", "work_item_id": "TC-W001", "note": "n"}]
        },
        "retry_worklist:territory_censor": [],
        "research_budget:territory_censor__retry": 12,
    }
    ctx = MagicMock()
    ctx.state = state
    ctx.agent_name = "territory_censor__retry"
    out = done("empty worklist", ctx)
    assert out.startswith("Desk closed")
    assert ctx.actions.escalate is not True or isinstance(ctx.actions.escalate, MagicMock)


# --- source authority allowlist (run-5 review: blockers rested on Grokipedia
# and a Kiwix Wikipedia dump on a personal domain) --------------------------


def _cit(url):
    return {"source_type": "web", "url": url, "excerpt": "x", "title": "t"}


def test_blocker_requires_allowlisted_authority():
    from greenlight.tools.toolbelt import _authority_problem

    bad = [
        _cit("https://grokipedia.com/x"),
        _cit("https://a.osmarks.net/content/wikipedia_en_all_maxi_2020-08/A/x"),
    ]
    assert _authority_problem("BLOCKER", bad) is not None
    good = [*bad, _cit("https://www.filmratings.com/rules")]
    assert _authority_problem("BLOCKER", good) is None
    assert _authority_problem("BLOCKER", [_cit("https://www.gov.cn/policy/x")]) is None


def test_high_needs_authority_or_corroboration():
    from greenlight.tools.toolbelt import _authority_problem

    one_unknown = [_cit("https://someblog.example/post")]
    assert _authority_problem("HIGH", one_unknown) is not None
    two_independent = [*one_unknown, _cit("https://otherfirm.example/analysis")]
    assert _authority_problem("HIGH", two_independent) is None
    assert _authority_problem("MEDIUM", one_unknown) is None  # gate is BLOCKER/HIGH only


def test_kiwix_dump_counts_as_background():
    from greenlight.tools.toolbelt import _is_background_host

    assert _is_background_host("https://a.osmarks.net/content/wikipedia_en_all_maxi_2020-08/A/x")
    assert _is_background_host("https://grokipedia.com/wiki/thing")
    assert not _is_background_host("https://www.filmratings.com/rules")


def test_county_film_offices_are_authority_municipal_gov_still_banned():
    """A county/city film office IS the filming authority for its jurisdiction —
    named exceptions to the municipal-.gov ban (run 9: the new rule banned Clark
    County, the Las Vegas permitting authority, along with the noise it removed)."""
    from greenlight.tools.toolbelt import _is_authority_host

    assert _is_authority_host("https://clarkcountynv.gov/permits")
    assert _is_authority_host("https://filmla.com/permit")
    assert _is_authority_host("https://www.lvmpd.com/x")
    assert _is_authority_host("https://film.nv.gov/x")  # US-state domain, always was
    assert not _is_authority_host("https://highpointnc.gov/x")  # random municipality


def test_citation_dedup_collapses_www_and_mobile_keeps_distinct_pages():
    """csatf.org / www.csatf.org / m.csatf.org for one page are ONE source; two
    different bulletins on one host stay two (run 8 www, run 9 m.yelp beside yelp)."""
    from greenlight.tools.toolbelt import _dedupe_cits

    cits = [
        _cit("https://www.csatf.org/04_stunts/"),
        _cit("https://csatf.org/04_stunts"),  # same page, non-www + trailing slash
        _cit("https://m.yelp.com/biz/x"),
        _cit("https://yelp.com/biz/x"),  # same page, non-mobile
        _cit("https://www.csatf.org/01_firearms/"),  # distinct page, same host
    ]
    out = _dedupe_cits(cits)
    assert len(out) == 3


def test_prune_keeps_the_derived_marginal_beside_filmratings():
    """The rating_boundary marginal is a URL-less tool citation and the desk's
    strongest, most specific evidence; the prune must not drop it for a generic
    filmratings.com page (run 11: findings survived but cited filmratings, not the
    4,544-rationale corpus, because the marginal read as weak)."""
    from greenlight.tools.toolbelt import _prune_weak_citations

    cits = [
        _cit("https://www.filmratings.com/Content"),
        {
            "via": "rating_boundary",
            "excerpt": "'pervasive language': R 99% across 187 official CARA rationales "
            "(ScriptRisk CARA descriptor corpus)",
        },
    ]
    kept = _prune_weak_citations(cits, "rating_language")
    assert any("ScriptRisk CARA descriptor corpus" in (c.get("excerpt") or "") for c in kept)


def test_rating_findings_need_a_ratings_authority_not_any_gov():
    """Run 6: committee.nottinghamcity.gov.uk cited for BBFC guidelines —
    government, but not a classification authority."""
    from greenlight.tools.toolbelt import _authority_problem

    council = [_cit("https://committee.nottinghamcity.gov.uk/minutes")]
    assert _authority_problem("HIGH", council, "rating_language") is not None
    bbfc = [_cit("https://www.bbfc.co.uk/about-classification")]
    assert _authority_problem("HIGH", bbfc, "rating_language") is None
    # run-8: a municipal council is not authority for ANY claim, not just
    # rating — a UK national/agency or state source is. The council fails; a
    # national gov (or two independent non-background sources) passes.
    assert _authority_problem("HIGH", council, "territory_uk_violence") is not None
    national = [_cit("https://www.gov.uk/guidance/x")]
    assert _authority_problem("HIGH", national, "territory_uk_violence") is None


# --- B8: citation provenance must not manufacture quotes --------------------


def test_script_quotes_pass_provenance():
    """_exists_in_state checked state['source'], a key NOTHING writes — the
    pipeline seeds script_text. The leg was dead, so a desk quoting the
    screenplay verbatim always failed and fell into the repair path."""
    from greenlight.tools.toolbelt import _exists_in_state, _norm_for_match

    state = {"script_text": "INT. MALL - DAY\n\nSTEVE\nSbarro, over in the Fremont mall.\n"}
    assert _exists_in_state(_norm_for_match("Sbarro, over in the Fremont mall"), state)
    assert not _exists_in_state(_norm_for_match("a tiger prowls the suite"), state)


def test_repair_will_not_substitute_an_unrelated_source():
    """The old test was 60% of the words in ANY ORDER against any registered
    text — shared legal vocabulary alone could match, and the joined blob of a
    whole search scored ~1.0, so the repair filed an arbitrary 800-char prefix
    of a concatenation as the 'verbatim' citation."""
    from greenlight.tools.toolbelt import _best_registry_match, _register_provenance

    ctx = make_ctx()
    unrelated = (
        "A synchronization license is required from the music publisher before "
        "any recording may be used in a motion picture soundtrack."
    )
    _register_provenance(ctx, [unrelated])
    # same vocabulary, different claim, different order — must NOT be repaired
    attempt = (
        "The publisher of the motion picture must license any music recording "
        "used before a required soundtrack synchronization."
    )
    assert _best_registry_match(attempt, ctx) is None


def test_repair_returns_the_aligned_span_verbatim_not_a_prefix():
    """A genuine loose transcription IS repaired — to the aligned span of the
    ORIGINAL text (true casing/punctuation), not the candidate's first 800
    characters and not the lowercased normalized form."""
    from greenlight.tools.toolbelt import _best_registry_match, _register_provenance

    ctx = make_ctx()
    head = "Unrelated opening paragraph about parking permits and street closures. "
    real = "The Rating Board assigns PG-13 when more than one sexual expletive appears."
    _register_provenance(ctx, [head + real])
    attempt = "The Rating Board assigns PG-13 when more than one expletive appears"
    fix = _best_registry_match(attempt, ctx)
    assert fix is not None
    assert "Rating Board" in fix, "must preserve original casing, not the lowercased form"
    assert "parking permits" not in fix, "must return the aligned span, not the prefix"


def test_repaired_citations_are_marked_on_the_record():
    """A rewritten citation is auditable: the text the report presents as
    verbatim was not the desk's own, and the record says so."""
    ctx = make_ctx()
    ctx.invocation_id = "inv-repair-marked"
    toolbelt._register_provenance(ctx, [RESEARCH_EXCERPT])
    near_miss = (
        "If the product appears in a negative light on screen, you may be "
        "sued for product disparagement by them."
    )
    msg = file_good_flag(ctx, citations=[{**GOOD_CITATION, "excerpt": near_miss}])
    assert msg.startswith("Filed"), msg
    cit = ctx.state["flags:clearance_counsel"][-1]["citations"][0]
    assert cit.get("repaired") is True
    assert cit["excerpt"] == RESEARCH_EXCERPT, "must be the true source text"


# --- batch 2: coverage accuracy ---------------------------------------------


def test_flag_ids_do_not_collide_past_ninety_nine():
    """The per-desk sequence increments on every ATTEMPT including rejections
    and is shared by four clearance batches plus retry and sweep. At 100
    spacing, clearance's 101st id was F201 — ratings' first — and dedupe-by-id
    would merge two unrelated findings."""
    import itertools

    from greenlight.tools.toolbelt import FLAG_ID_OFFSET

    starts = sorted(FLAG_ID_OFFSET.values())
    assert min(b - a for a, b in itertools.pairwise(starts)) >= 1000
    ids = {d: f"F{off + 150}" for d, off in FLAG_ID_OFFSET.items()}
    assert len(set(ids.values())) == len(ids), "150 flags on one desk must not collide"


def test_sweeper_credit_is_desk_scoped():
    """The sweeper runs under clearance_counsel__sweep for ALL desks, so an
    entity_id alone cannot say which desk's question it answered. A desk-scoped
    id can — which is what makes crediting it across desks safe."""
    from greenlight.tools.toolbelt import sweep_work_item_id

    tc = sweep_work_item_id("territory_censor", "E012")
    assert tc == "SW-TC-E012"
    assert tc != sweep_work_item_id("ratings_board", "E012")


def test_sweeper_disposition_closes_a_non_clearance_entity():
    """Before: the sweeper examined a territory entity, its work landed under
    clearance_counsel__sweep, territory's family never included that name, so
    the item was re-swept every round and rendered NOT EXAMINED despite being
    examined."""
    from greenlight.tools.toolbelt import sweep_work_item_id, unexamined_entities

    tri = {
        "entities": [{"entity_id": "E012", "surface": "Ghostbar", "scene_ids": ["S040"]}],
        "territory_censor": [{"entity_id": "E012", "surface": "Ghostbar"}],
    }
    open_state = {"triage": tri}
    assert [u["entity_id"] for u in unexamined_entities(open_state)] == ["E012"]
    swept = {
        "triage": tri,
        "wi_done:clearance_counsel__sweep": [sweep_work_item_id("territory_censor", "E012")],
    }
    assert unexamined_entities(swept) == [], "the sweeper's work must count"


def test_coverage_credit_requires_a_whole_word():
    """`"ford" in "cannot afford"` credited entity Ford as covered, so a
    short-surfaced entity could be skipped by every desk and never disclosed."""
    from greenlight.tools.toolbelt import _mentions

    assert not _mentions("ford", "the production cannot afford that location")
    assert _mentions("ford", "a ford pickup is parked outside")
    assert _mentions("crazy horse", "the crazy horse brawl needs a release")


def test_eval_assertions_catch_run8_defects():
    """The two run-8 pre-release assertions, exercised directly."""
    import re

    flags = [
        {
            "flag_id": "F2007",
            "finding": "violence in S064 and S099",
            "remedy": {"detail": ""},
            "scene_ids": ["S024"],
        }
    ]
    notes = ["F2008: severity upgraded", "F2007: category normalized"]
    rendered = {f["flag_id"] for f in flags}
    dangling = [n for n in notes if not set(re.findall(r"\bF\d{3,4}\b", n)) <= rendered]
    assert dangling == ["F2008: severity upgraded"]  # F2008 not rendered
    stray = set(re.findall(r"\bS\d{3}\b", flags[0]["finding"])) - set(flags[0]["scene_ids"])
    assert stray == {"S064", "S099"}  # prose names scenes outside coordinates


def test_weak_citations_pruned_when_a_strong_one_exists():
    """A CARA claim citing filmratings AND a municipal .gov reads as
    carelessness (run 8, highpointnc.gov cited 4x). Prune keeps the authority; a
    non-rating finding drops only background-tier sources; dedup collapses
    www/non-www duplicates (csatf.org, www.csatf.org)."""
    from greenlight.tools.toolbelt import _prune_weak_citations

    def c(u):
        return {"url": u, "excerpt": u}

    rating = [
        c("https://www.filmratings.com/a"),
        c("https://www.highpointnc.gov/b"),
        c("https://www.filmratings.com/a"),
    ]
    pr = _prune_weak_citations(rating, "rating_language")
    assert [x["url"] for x in pr] == ["https://www.filmratings.com/a"]
    # non-rating: drop background (bandcamp) but keep mid-tier
    mixed = [c("https://www.revolvermag.com/x"), c("https://natesu.bandcamp.com/y")]
    assert [x["url"] for x in _prune_weak_citations(mixed, "sync_license")] == [
        "https://www.revolvermag.com/x"
    ]
    # dedup www/non-www
    assert (
        len(
            _prune_weak_citations(
                [c("https://csatf.org/x"), c("https://www.csatf.org/x")], "stunt_fall"
            )
        )
        == 1
    )
    # never empties: a lone weak source survives (the invariant holds)
    assert len(_prune_weak_citations([c("https://natesu.bandcamp.com/y")], "sync_license")) == 1
