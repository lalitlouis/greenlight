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

import asyncio
import os
from typing import Any

from greenlight import parser
from greenlight import report as report_mod
from greenlight.agents.evidence_review import review_incomplete
from greenlight.agents.verification import (
    _RETRY_HTTP,
    Verdict,
    _apply_overturns,
    _scene_context,
    _scrub_cutlist,
    _search_context,
    apply_verdicts,
    call_verifier,
    demotion_entries,
)


async def _verify_once(client: Any, flag: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One block-aware verifier call, no ladder — the caller decides retry
    policy. Raises on transport failure (the caller keeps the honest unverified
    state)."""
    return await call_verifier(
        client, flag, _scene_context(flag, state), _search_context(flag, state)
    )


async def reverify_record(  # noqa: PLR0912, PLR0915 - the live panel's post-verdict sequence, mirrored
    record: dict[str, Any], script_text: str, verify=None, reconcile=None
) -> dict[str, Any]:
    """Retry every verification_unavailable finding in `record`, in place.

    Returns a summary {"retried", "verified", "still_unavailable", "rejected",
    "score"}. `verify` is injectable for tests; default builds a genai client.
    `reconcile(pred, kept, dropped) -> {rationale, beats_to_cut} | None` is the
    rating reconcile (injectable; default uses the panel's own Flash call when a
    live client exists).

    Parity with the live panel (review 2026-09-01 A5/D5): the assertion-1
    overturn guards screen every new rejection; a rejected RATING finding
    reconciles the rationale/cut list; and the shared post-verification pass
    (rejected-id annotation, absorbed rewrite, dangling notes, open-question
    routing) runs on the rebuilt record — the same function the pipeline runs.
    """
    targets = [f for f in record.get("flags") or [] if f.get("verification_unavailable")]
    summary = {
        "retried": len(targets),
        "verified": 0,
        "still_unavailable": 0,
        "blocked": 0,
        "rejected": [],
        "score": (record.get("report") or {}).get("greenlight_score"),
    }
    if not targets:
        return summary

    _meta, scenes = parser.parse_fountain(script_text)
    state = {"script_text": script_text, "scenes": scenes}

    manifest = list(record.get("guard_manifest") or [])
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

        if reconcile is None:
            from greenlight.agents import verification as _verification

            async def reconcile(pred, kept, dropped):
                return await _verification.agent._reconcile_rating(
                    client, pred, kept, dropped, asyncio.Semaphore(1)
                )

    flags = list(record.get("flags") or [])
    verdicts = dict(record.get("verdicts") or {})
    dropped_all: list[dict[str, Any]] = []
    for f in targets:
        fid = f["flag_id"]
        try:
            v = await verify(f)
            Verdict.model_validate(v)
        except Exception:
            summary["still_unavailable"] += 1
            continue  # still down — the honest unverified state stands
        if v.get("fail_open") and v.get("content_filtered"):
            # deterministic platform block — retries cannot help; label honestly
            f["verification_blocked"] = True
            verdicts[fid] = v
            summary["blocked"] += 1
            continue
        # assertion 1, exactly as the live fan-out applies it: a rejection that
        # calls a stated script fact absent/unstated is overturned or its false
        # ground struck before the verdict is applied
        one = {fid: v}
        for ofid, note, sid in _apply_overturns([f], one, state):
            manifest.append(
                {
                    "guard": "overturn",
                    "stage": "reverify",
                    "flag_id": ofid,
                    "matched": note,
                    "scene": sid,
                    "verdict_after": one[fid].get("verdict"),
                }
            )
        v = one[fid]
        verdicts[fid] = v
        f.pop("verification_unavailable", None)
        f.pop("verification_blocked", None)
        kept_one, dropped_one = apply_verdicts([f], verdicts)
        if dropped_one:
            flags = [x for x in flags if x["flag_id"] != fid]
            record["rejected_flags"] = list(record.get("rejected_flags") or []) + dropped_one
            dropped_all.extend(dropped_one)
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
            if kept_one[0].get("verification_unavailable"):
                summary["still_unavailable"] += 1
            else:
                summary["verified"] += 1

    record["flags"] = flags
    record["verdicts"] = verdicts
    old_rep = record.get("report") or {}
    pred = old_rep.get("rating_prediction")
    rating_dropped = [d for d in dropped_all if str(d.get("category") or "").startswith("rating_")]
    if pred and rating_dropped:
        # the rationale and cut list must describe the POST-verification finding
        # set — the live panel reconciles; so does reverify, or it says it could not
        revised = await reconcile(pred, flags, rating_dropped) if reconcile else None
        if revised is not None and revised.get("beats_to_cut"):
            scrubbed, misses = _scrub_cutlist(revised["beats_to_cut"])
            revised["beats_to_cut"] = scrubbed
            for beat, matched in misses:
                manifest.append(
                    {
                        "guard": "normative_cutlist_scrub",
                        "stage": "reverify",
                        "outcome": "unstripped",
                        "matched": matched,
                        "beat": beat[:120],
                    }
                )
        if revised is not None and (
            revised.get("rationale") != pred.get("rationale")
            or revised.get("beats_to_cut") != (pred.get("beats_to_cut") or [])
        ):
            pred = {
                **pred,
                **revised,
                "reconciled_after_verification": True,
                "pre_verification": {
                    "rationale": pred.get("rationale"),
                    "beats_to_cut": pred.get("beats_to_cut"),
                },
            }
        elif revised is None:
            manifest.append(
                {
                    "guard": "rating_reconcile",
                    "stage": "reverify",
                    "outcome": "not_run",
                    "flag_ids": [d.get("flag_id") for d in rating_dropped],
                }
            )
    record["report"] = report_mod.build_report(
        record.get("script_title") or "Untitled",
        flags,
        page_count=old_rep.get("page_count"),
        rating_prediction=pred,
        incomplete_desks=record.get("desks_incomplete") or [],
        verification_incomplete=review_incomplete(verdicts),
    )
    from greenlight.pipeline import finalize_record_after_verification

    manifest.extend(finalize_record_after_verification(record))
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
