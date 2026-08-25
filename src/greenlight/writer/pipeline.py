"""The Writer's Room pipeline: format (deterministic) + coverage & pitch (agents,
parallel) + comps by retrieval from the ratings corpus.

Comps are the citation thesis applied to pitching: "X meets Y" is only worth
saying when X and Y came from a database of released films with sources — so the
comps list is retrieved by embedding the pitch synopsis, never asserted."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

import os  # noqa: E402

os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

from google.adk.agents import ParallelAgent, SequentialAgent  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from greenlight import parser  # noqa: E402
from greenlight.writer import agents as writer_agents  # noqa: E402
from greenlight.writer.format_check import format_report  # noqa: E402

APP_NAME = "greenlight_writer"
USER_ID = "writer"
COMPS_K = 6


def _fetch_comps(synopsis: str) -> list[dict[str, Any]]:
    """kNN over the ratings corpus using the pitch synopsis. Degrades to [] —
    the pitch ships without comps rather than with invented ones."""
    try:
        from greenlight.tools.toolbelt import _clickhouse_client, _embed

        vec = _embed(synopsis)
        rows = (
            _clickhouse_client()
            .query(
                """
            SELECT title, year, rating, rationale, source_url,
                   cosineDistance(embedding, %(v)s) AS distance
            FROM rating_rationales ORDER BY distance ASC LIMIT %(k)s
            """,
                parameters={"v": vec, "k": COMPS_K},
            )
            .result_rows
        )
    except Exception:
        return []
    return [
        {
            "title": r[0],
            "year": r[1],
            "rating": r[2],
            "blurb": r[3],
            "source_url": r[4],
            "distance": round(float(r[5]), 4),
        }
        for r in rows
    ]


def build_root_agent() -> SequentialAgent:
    room = ParallelAgent(
        name="writers_room",
        description="Coverage and pitch desks read the script concurrently.",
        sub_agents=[writer_agents.coverage_agent, writer_agents.pitch_agent],
    )
    return SequentialAgent(name="writer_pipeline", sub_agents=[room])


async def run(script_path: str | Path, on_stage: Any = None) -> dict[str, Any]:
    """on_stage(name, info) fires at real checkpoints — the page's progress is
    truth, not a timer: parsed -> format_done -> desks -> comps -> (caller: done)."""

    def stage(name: str, **info: Any) -> None:
        if on_stage is not None:
            on_stage(name, info)

    source = Path(script_path).read_text()
    meta, scenes = parser.parse_fountain(source)
    title = meta.get("title", Path(script_path).stem)
    stage("parsed", title=title, scenes=len(scenes), pages=scenes[-1]["page"] if scenes else 0)

    fmt = format_report(meta, scenes, source)
    stage("format_done", passes=fmt["counts"]["PASS"], warns=fmt["counts"]["WARN"])

    runner = InMemoryRunner(agent=build_root_agent(), app_name=APP_NAME)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={"script_annotated": parser.annotated_script(source, scenes)},
    )
    stage("desks")
    message = types.Content(role="user", parts=[types.Part(text="Read the screenplay.")])
    t0 = time.time()
    error: str | None = None
    try:
        async for _ in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            pass
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"

    final = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    coverage = final.state.get("coverage")
    pitch = final.state.get("pitch")
    stage("comps")
    if pitch and pitch.get("one_page_synopsis"):
        pitch["comps"] = _fetch_comps(pitch["one_page_synopsis"])

    return {
        "kind": "writer",
        "script_title": title,
        "script_path": str(script_path),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_s": round(time.time() - t0, 1),
        "error": error,
        "format": fmt,
        "coverage": coverage,
        "pitch": pitch,
    }


def save_run(record: dict[str, Any]) -> Path:
    out = ROOT / "runs" / f"writer_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record, indent=2))
    return out
