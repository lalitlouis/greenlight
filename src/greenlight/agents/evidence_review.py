"""Bounded repair of compound claims, with independent verification before use.

Only judgement/text crosses the model boundary. Identity, citations and coordinates
stay fixed; estimates for a changed remedy become unknown rather than stale totals.
The verdict carries the audit trail without extending the public flag schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, Field

from greenlight.agents.evidence import PRODUCTION_EVIDENCE, RATINGS_EVIDENCE
from greenlight.contracts import validate
from greenlight.models import FLASH_MODEL


class ClaimCheck(BaseModel):
    field: Literal["finding", "remedy", "severity"]
    quote: str = Field(min_length=1)
    basis: Literal["script", "production", "source", "planning"]
    status: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    reason: str
    citation_numbers: list[int]


CLAIM_CHECK_INSTRUCTIONS = """\
Return claim_checks covering EVERY material assertion in BOTH finding and remedy,
plus the severity. Use a separate check for each asserted obligation or production
fact; one supported precaution cannot support the entire paragraph. quote is an exact
substring of that field (for severity, quote the level itself). For remedy quotes
use the detail prose only, excluding the action label. basis distinguishes script
facts, production facts, outside-world source claims, and planning advice.
For source-based SUPPORTED checks, citation_numbers must identify the numbered
excerpts that entail the assertion; an index/title alone does not establish a rule.
Other checks may use an empty citation_numbers list. Never transfer an attribute from
a fictional character to a performer, or from a depicted effect to a practical shoot.
Check conditions independently in the remedy: 'if cast with a minor' in the finding
does NOT qualify an unconditional studio-teacher or permit requirement in the remedy.
General compliance language does not establish permits from specific authorities.
Planning advice must distinguish a recommendation from a mandatory requirement.
Mark unknown casting, jurisdiction or method asserted as fact UNKNOWN, even if a
safe production could plausibly choose it. SUPPORTED requires every material check
SUPPORTED. Any UNKNOWN/UNSUPPORTED clause prevents overall SUPPORTED.
"""


def checked_verdict(verdict: dict[str, Any], flag: dict[str, Any]) -> dict[str, Any]:
    """Validate the audit's anchors; a positive label cannot override failed clauses."""
    checks = [ClaimCheck.model_validate(c) for c in verdict["claim_checks"]]
    if {c.field for c in checks} != {"finding", "remedy", "severity"}:
        raise ValueError("claim audit must cover finding, remedy and severity")
    fields = {
        "finding": flag["finding"],
        "remedy": flag["remedy"]["detail"],
        "severity": flag["severity"],
    }
    for check in checks:
        if check.quote not in fields[check.field]:
            raise ValueError("claim audit quote is not in its field")
        if any(i < 1 or i > len(flag["citations"]) for i in check.citation_numbers):
            raise ValueError("claim audit references a nonexistent citation")
        if check.basis == "source" and check.status == "SUPPORTED" and not check.citation_numbers:
            raise ValueError("supported source claim has no citation reference")
    issues = [c for c in checks if c.status != "SUPPORTED"]
    if issues and verdict["verdict"] == "SUPPORTED":
        verdict = {
            **verdict,
            "verdict": "PARTIAL",
            "reason": "Claim audit requires correction: " + "; ".join(c.reason for c in issues),
        }
    return verdict


def flag_fingerprint(flag: dict[str, Any]) -> str:
    """Bind a repair to the exact claim, remedy, sources and coordinates reviewed."""
    fields = {
        k: flag.get(k)
        for k in (
            "flag_id",
            "agent",
            "scene_ids",
            "category",
            "finding",
            "remedy",
            "citations",
            "severity",
        )
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


class CorrectedClaim(BaseModel):
    finding: str = Field(min_length=1, max_length=4000)
    remedy_detail: str = Field(min_length=1, max_length=4000)
    remedy_action: Literal[
        "REPLACE",
        "OBTAIN_LICENSE",
        "OBTAIN_RELEASE",
        "RESHOOT",
        "ADD_DISCLAIMER",
        "ADD_SPECIALIST",
        "CUT",
        "NO_ACTION",
    ]
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW", "FYI"]


def corrected_flag(flag: dict[str, Any], correction: dict[str, Any]) -> dict[str, Any]:
    """Apply only reviewed text/action/severity; discard superseded estimates."""
    patch = CorrectedClaim.model_validate(correction)
    if not patch.finding.strip() or not patch.remedy_detail.strip():
        raise ValueError("empty correction")
    mentioned = set(re.findall(r"\bS\d{3,4}\b", patch.finding + " " + patch.remedy_detail))
    if mentioned - set(flag["scene_ids"]):
        raise ValueError("repair names a scene outside the reviewed coordinates")
    new = {
        **flag,
        "finding": patch.finding.strip(),
        "severity": patch.severity,
        "remedy": {
            "action": patch.remedy_action,
            "detail": patch.remedy_detail.strip(),
            "est_cost_usd": None,
            "est_added_days": None,
        },
    }
    # Rejections and transient markers belong to the superseded version.
    for key in (
        "rejection_reason",
        "failure_mode",
        "recoverable",
        "verification_unavailable",
        "verification_blocked",
        "cost_excluded_on_target_path",
    ):
        new.pop(key, None)
    return validate("flag", new)


def unresolved_verdict(original: dict[str, Any], reason: str, **trail: Any) -> dict[str, Any]:
    return {
        "verdict": "UNSUPPORTED",
        "failure_mode": "premise_unsupported",
        "reason": "Evidence correction unresolved: " + reason,
        "evidence_review_unresolved": True,
        "evidence_review": {"before": original, **trail},
    }


async def repair_partial(client, flag, context, search, original, verify_once):
    """One correction + one blinded check. No recursive repair or new retrieval."""
    # A censored verifier has not checked the script. It cannot approve a repair.
    if original.get("content_filtered"):
        return unresolved_verdict(original, "script verification was blocked")
    prompt = (
        PRODUCTION_EVIDENCE
        + "\n"
        + RATINGS_EVIDENCE
        + "\nCorrect this partially supported finding AND remedy. Preserve the supported "
        "hazard/exposure; remove unsupported obligations and qualify actual casting, method "
        "and jurisdiction assumptions in BOTH fields. Do not invent sources or requirements. "
        "Review severity against the surviving hazard, not the removed assumptions; it may "
        "remain HIGH for a serious hazard. Costs and days will be withheld because the "
        "remedy changed. Return the corrected finding, remedy_detail, remedy_action, severity. "
        "If no supported exposure remains, return an empty finding (repair will be refused).\n\n"
        + "FLAG:\n"
        + json.dumps(flag)
        + "\nVERIFICATION:\n"
        + json.dumps(original)
        + "\nSCENE TEXT:\n"
        + context
        + "\nFULL-SCRIPT SEARCH:\n"
        + search
    )
    try:
        res = await client.aio.models.generate_content(
            model=FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CorrectedClaim,
                temperature=0.0,
            ),
        )
        correction = CorrectedClaim.model_validate_json(res.text).model_dump()
        candidate = corrected_flag(flag, correction)
        from greenlight.agents.verification import _refile_gate_problem

        gate = _refile_gate_problem(candidate, check_authority=False)
        if gate:
            return unresolved_verdict(original, gate, correction=correction)
        # Deliberately omit original reasoning/audit: the second check is blinded.
        after = await verify_once(client, candidate, context, search)
    except Exception as exc:
        return unresolved_verdict(original, f"repair/check unavailable ({type(exc).__name__})")
    if (
        after.get("verdict") != "SUPPORTED"
        or after.get("fail_open")
        or after.get("content_filtered")
    ):
        return unresolved_verdict(
            original,
            "corrected claim did not pass independent verification",
            correction=correction,
            after=after,
        )
    return {
        **after,
        "evidence_review": {"before": original, "after": after},
        "correction": correction,
        "correction_input": flag_fingerprint(flag),
    }


def review_incomplete(verdicts: dict[str, Any]) -> bool:
    return any(
        v.get("evidence_review_unresolved")
        for fid, v in verdicts.items()
        if ":" not in fid and isinstance(v, dict)
    )
