"""Targeted re-verification for a finished record (run-16 feature).

A transient verifier failure marks its finding unverified and correctly
withholds the score — but the only remedy the UI offered was a full re-run:
paying feature-run money to fix a few cents of failed Flash calls. This module
retries ONLY the unverified findings against the stored record + script,
applies the verdicts with the same semantics as the live pipeline, and rebuilds
the report so the score computes (or stays withheld, honestly, if the verifier
is still down).

Deterministic everywhere except the verifier calls themselves; the parser
re-derives scene coordinates from the stored script (same deterministic parse
that anchored the original run).
"""

from __future__ import annotations

import os
from typing import Any

from greenlight import parser
from greenlight import report as report_mod
from greenlight.agents.verification import (
    _RETRY_HTTP,
    MODEL,
    Verdict,
    _blinded_prompt,
    _scene_context,
    _search_context,
    apply_verdicts,
    demotion_entries,
)


async def _verify_once(client: Any, flag: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One verifier call, no ladder — the caller decides retry policy. Raises on
    transport failure (the caller keeps the honest unverified state)."""
    from google.genai import types

    res = await client.aio.models.generate_content(
        model=MODEL,
        contents=_blinded_prompt(flag, _scene_context(flag, state), _search_context(flag, state)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Verdict,
            temperature=0.0,
        ),
    )
    v = Verdict.model_validate_json(res.text)
    return {"verdict": v.verdict, "reason": v.reason, "failure_mode": v.failure_mode}


async def reverify_record(record: dict[str, Any], script_text: str, verify=None) -> dict[str, Any]:
    """Retry every verification_unavailable finding in `record`, in place.

    Returns a summary {"retried", "verified", "still_unavailable", "rejected",
    "score"}. `verify` is injectable for tests; default builds a genai client.
    """
    targets = [f for f in record.get("flags") or [] if f.get("verification_unavailable")]
    summary = {
        "retried": len(targets),
        "verified": 0,
        "still_unavailable": 0,
        "rejected": [],
        "score": (record.get("report") or {}).get("greenlight_score"),
    }
    if not targets:
        return summary

    _meta, scenes = parser.parse_fountain(script_text)
    state = {"script_text": script_text, "scenes": scenes}

    if verify is None:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            http_options=_RETRY_HTTP,
        )

        async def verify(flag: dict[str, Any]) -> dict[str, Any]:
            return await _verify_once(client, flag, state)

    flags = list(record.get("flags") or [])
    verdicts = dict(record.get("verdicts") or {})
    for f in targets:
        fid = f["flag_id"]
        try:
            v = await verify(f)
        except Exception:
            summary["still_unavailable"] += 1
            continue  # still down — the honest unverified state stands
        verdicts[fid] = v
        f.pop("verification_unavailable", None)
        kept_one, dropped_one = apply_verdicts([f], {fid: v})
        if dropped_one:
            flags = [x for x in flags if x["flag_id"] != fid]
            record["rejected_flags"] = list(record.get("rejected_flags") or []) + dropped_one
            summary["rejected"].append(fid)
            # a sourcing-failure rejection demotes to an open question, exactly
            # as the live pipeline would have done
            for key, entries in demotion_entries(dropped_one).items():
                desk = key.split(":", 1)[1]
                oq = record.get("open_questions") or {}
                oq[desk] = list(oq.get(desk) or []) + entries
                record["open_questions"] = oq
        else:
            # PARTIAL marking / severity semantics from apply_verdicts
            flags = [kept_one[0] if x["flag_id"] == fid else x for x in flags]
            summary["verified"] += 1

    record["flags"] = flags
    record["verdicts"] = verdicts
    old_rep = record.get("report") or {}
    record["report"] = report_mod.build_report(
        record.get("script_title") or "Untitled",
        flags,
        page_count=old_rep.get("page_count"),
        rating_prediction=old_rep.get("rating_prediction"),
        incomplete_desks=record.get("desks_incomplete") or [],
    )
    manifest = list(record.get("guard_manifest") or [])
    manifest.append(
        {
            "guard": "reverify",
            "stage": "post_run",
            "outcome": f"{summary['verified']} verified, {summary['still_unavailable']} still "
            f"unavailable, {len(summary['rejected'])} rejected",
        }
    )
    record["guard_manifest"] = manifest
    summary["score"] = record["report"].get("greenlight_score")
    return summary
