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


class SupportSpan(BaseModel):
    citation_number: int = Field(ge=1)
    quote: str = Field(min_length=1)


class EntailmentCheck(BaseModel):
    check_index: int
    entailed: bool
    reason: str


class EntailmentResult(BaseModel):
    checks: list[EntailmentCheck]


# The only unsupported-by-a-source remedy we can accept mechanically: gathering
# input facts, with no embedded obligation, specialist, equipment or method advice.
PRODUCTION_INQUIRY = (
    "Confirm casting, filming jurisdiction and staging method before specifying "
    "production requirements."
)


class ClaimCheck(BaseModel):
    field: Literal["finding", "remedy", "severity"]
    quote: str = Field(min_length=1)
    basis: Literal["script", "production", "source", "planning", "inquiry"]
    status: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    reason: str
    citation_numbers: list[int]
    support_spans: list[SupportSpan]


CLAIM_CHECK_INSTRUCTIONS = """\
Return claim_checks covering EVERY material assertion in BOTH finding and remedy,
plus the severity. Use a separate check for each asserted obligation or production
fact; one supported precaution cannot support the entire paragraph. quote is an exact
substring of that field (for severity, quote the level itself). For remedy quotes
use the detail prose only, excluding the action label. basis distinguishes script
facts, production facts, outside-world source claims, and planning advice.
For every source/planning claim (except severity), and EVERY remedy prescription,
provide support_spans: citation_number plus an EXACT verbatim quote from that numbered
excerpt. citation_numbers must match the receipt indexes. Choose the operative clause,
not the title, index listing, URL or scope heading. Do not quote from the whole document
from memory: only the supplied excerpt is available. Text merely being present does
not mean it entails the claim. Match the action, object, force and conditions:
- maintaining firearms-related LICENSES does not establish maintaining or controlling
  FIREARMS; do not substitute one object for the other;
- a minor's entitlement to a stunt double does not prescribe water/fire specialists,
  studio teachers, PPE or working hours;
- compliance with applicable laws does not establish a particular permit or authority;
- a guideline's title/scope does not establish its operative safety procedures.
Split compound prescriptions into separate checks. Check each duty, piece of equipment,
specialist, permit and condition independently, even within one sentence. A span for
one does not cover its neighbors. Do not call an unsourced prescription 'standard
practice', 'planning', or 'advice' to approve it. Recommendations also need evidence.
Without an entailing span mark that claim UNKNOWN/UNSUPPORTED with empty support_spans.
Script/production facts and severity judgement may have empty spans. Never transfer
an attribute from a fictional character to a performer, or from a depicted effect
to a practical shoot.
Check conditions independently in the remedy: 'if cast with a minor' in the finding
does NOT qualify an unconditional studio-teacher or permit requirement in the remedy.
General compliance language does not establish permits from specific authorities.
Planning advice must distinguish a recommendation from a mandatory requirement.
Mark unknown casting, jurisdiction or method asserted as fact UNKNOWN, even if a
safe production could plausibly choose it. SUPPORTED requires every material check
SUPPORTED. Any UNKNOWN/UNSUPPORTED clause prevents overall SUPPORTED.
"""

CLAIM_CHECK_INSTRUCTIONS += (
    "\nFor a remedy that only requests unknown input facts, basis=inquiry is allowed "
    "WITHOUT external support only for this exact text: "
    + PRODUCTION_INQUIRY
    + " No other prescription can use inquiry. Do not relabel a remedy as a script "
    "fact or production fact to bypass supporting spans.\n"
)


def _support_problem(check: ClaimCheck, citations: list[dict[str, Any]]) -> str | None:
    """Validate provenance, never pretend substring matching proves entailment."""
    if check.basis == "inquiry" and (check.field != "remedy" or check.quote != PRODUCTION_INQUIRY):
        return "Only the fixed production-facts inquiry may omit external support"
    needs_span = check.basis in {"source", "planning"} and check.field != "severity"
    needs_span |= check.field == "remedy" and check.basis != "inquiry"
    if needs_span and not check.support_spans:
        return "No exact supporting span for this external claim or prescription"
    indexes = {span.citation_number for span in check.support_spans}
    if indexes != set(check.citation_numbers):
        return "Citation indexes and supporting spans do not match"
    for span in check.support_spans:
        if span.citation_number > len(citations):
            return "Supporting span references a nonexistent citation"
        excerpt = citations[span.citation_number - 1].get("excerpt") or ""
        if not span.quote.strip() or span.quote not in excerpt:
            return "Supporting span is not verbatim in the cited excerpt"
    return None


def _cover_additive_joins(body: str, covered: list[bool]) -> None:
    """Allow conjunctions between audited clauses, never omitted substantive text."""
    coverage = "".join("1" if hit else "0" for hit in covered)
    for gap in re.finditer("0+", coverage):
        start, end = gap.span()
        if (
            start > 0
            and end < len(body)
            and re.fullmatch(r"[\W_]*and(?:\s+that)?[\W_]*", body[start:end])
        ):
            covered[start:end] = [True] * (end - start)


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
        if check.status == "SUPPORTED":
            problem = _support_problem(check, flag["citations"])
            if problem:
                check.status = "UNKNOWN"
                check.reason = problem + ". Original assessment: " + check.reason
    # A correct receipt for one sentence cannot hide an unaudited tail. This is
    # coverage, not semantic parsing: atomicity/entailment still need judgement.
    for field, body in fields.items():
        covered = [False] * len(body)
        if field == "finding" and (prefix := re.match(r"\[partially supported\]\s*", body)):
            covered[: prefix.end()] = [True] * prefix.end()
        for check in checks:
            if check.field != field:
                continue
            start = body.find(check.quote)
            while start != -1:
                covered[start : start + len(check.quote)] = [True] * len(check.quote)
                start = body.find(check.quote, start + len(check.quote))
        # Atomic checks commonly omit a conjunction between two audited clauses.
        # Accept only internal additive joins; never swallow an unaudited clause,
        # a leading/trailing fragment, alternatives, exceptions or negation.
        _cover_additive_joins(body, covered)
        gaps = [i for i, char in enumerate(body) if char.isalnum() and not covered[i]]
        if gaps:
            checks.append(
                ClaimCheck(
                    field=field,
                    quote=body[gaps[0] : gaps[-1] + 1],
                    basis="source",
                    status="UNKNOWN",
                    reason="Material text was omitted from the claim audit",
                    citation_numbers=[],
                    support_spans=[],
                )
            )
    verdict = {
        **verdict,
        "claim_checks": [c.model_dump() for c in checks],
        "support_span_version": 1,
    }
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


async def check_entailment(client, flag, verdict):
    """One narrow independent batch: can these exact spans support these claims?

    No screenplay, severity or previous reasoning is shown, so an obvious hazard
    cannot distract the reviewer into approving unrelated mandatory precautions.
    Full excerpt context prevents a receipt from hiding a negation or exception.
    Source metadata identifies attribution; it cannot supply an operative rule.
    """
    if verdict["verdict"] != "SUPPORTED":
        return verdict  # already goes to correction/rejection; do not spend twice
    claims = []
    for index, check in enumerate(verdict["claim_checks"]):
        # Severity is a judgement made by the script-aware audit. A model may
        # attach receipts voluntarily; that must not turn HIGH into a purported
        # verbatim source assertion for this intentionally script-blind review.
        if check["field"] == "severity" or not check["support_spans"]:
            continue  # script facts, severity or the fixed production inquiry
        claims.append(
            {
                "check_index": index,
                "claim": check["quote"],
                "support": [
                    {
                        **span,
                        "excerpt_context": flag["citations"][span["citation_number"] - 1][
                            "excerpt"
                        ],
                        "source_attribution": {
                            key: flag["citations"][span["citation_number"] - 1].get(key)
                            for key in ("title", "url")
                        },
                    }
                    for span in check["support_spans"]
                ],
            }
        )
    if not claims:
        return verdict
    prompt = (
        "Independently assess textual entailment, using ONLY the supplied evidence. "
        "source_attribution contains the cited title and URL solely to identify the "
        "source. Use it to assess attribution such as 'SAG-AFTRA guidance'; the excerpt "
        "need not repeat its publisher's name. Metadata cannot establish an operative "
        "rule, duty, scope of applicability or precaution missing from the excerpt. "
        "Do not infer publisher endorsement from a name mentioned only in a title; "
        "consider the URL as well, and do not follow links or use remembered page text. "
        "For each check_index decide whether its exact supporting quote(s), read in "
        "their excerpt context, establish ALL of the claim. Do not use industry knowledge "
        "or the plausibility of precautions. Titles, scope headings and index entries "
        "cannot establish an operative requirement. A general duty to obey applicable "
        "laws does not establish named permits, specialists or equipment. Maintaining "
        "licenses is not maintaining/control of firearms. Entitlement to a stunt double "
        "does not prescribe other specialists, PPE or labor obligations. A recommendation "
        "is not exempt: 'should', 'consider' and 'standard planning' still require support "
        "for the prescribed precaution. Evaluate EACH duty/object/condition in a compound "
        "claim; if ANY is unsupported, entailed=false and name the unsupported part. "
        "Do not strengthen 'may' into 'must', omit an exception, or approve a quote that "
        "is negated by its context. Reasonable application to a stated hypothetical is "
        "allowed only if the source actually supplies that rule or safeguard. Never "
        "treat a nearby related topic as entailment. Return every check_index exactly "
        "once, with entailed and a concise reason.\n\n" + json.dumps(claims)
    )
    try:
        response = await client.aio.models.generate_content(
            model=FLASH_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EntailmentResult,
                temperature=0.0,
            ),
        )
        result = EntailmentResult.model_validate_json(response.text)
        wanted = {claim["check_index"] for claim in claims}
        got = [check.check_index for check in result.checks]
        if len(got) != len(set(got)) or set(got) != wanted:
            raise ValueError("entailment review omitted, repeated or invented a check")
    except Exception as exc:
        return unresolved_verdict(
            verdict, f"span entailment review unavailable ({type(exc).__name__})"
        )
    checks = [dict(c) for c in verdict["claim_checks"]]
    failures = []
    for result_check in result.checks:
        if not result_check.entailed:
            failures.append(result_check.reason)
            checks[result_check.check_index] = {
                **checks[result_check.check_index],
                "status": "UNSUPPORTED",
                "reason": "Independent span review: " + result_check.reason,
            }
    return {
        **verdict,
        "claim_checks": checks,
        "entailment_review": result.model_dump(),
        **(
            {"verdict": "PARTIAL", "reason": "Independent span review: " + "; ".join(failures)}
            if failures
            else {}
        ),
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
        + "\nWhen only production facts need confirmation, use this exact remedy: "
        + PRODUCTION_INQUIRY
        + "\nCorrect this partially supported finding AND remedy. Preserve the supported "
        "hazard/exposure; remove unsupported obligations and qualify actual casting, method "
        "and jurisdiction assumptions in BOTH fields. Do not invent sources or requirements. "
        "Every external prescription needs an operative supporting span in the supplied "
        "citations. Removing 'must' or calling it planning advice does not fix absent support. "
        "A license-maintenance rule does not support firearms maintenance, and entitlement "
        "to a stunt double does not establish other specialists or equipment. "
        "Remove prescriptions whose action/object/conditions the excerpts do not establish. "
        "If only a depicted hazard and unknown production facts remain, preserve that "
        "supported concern and use the fixed production-facts inquiry as the remedy. "
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
