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
from greenlight.agents.quote_anchor import anchor_quote
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
    basis: Literal[
        "script", "production", "source", "planning", "application", "script_edit", "inquiry"
    ]
    status: Literal["SUPPORTED", "UNSUPPORTED", "UNKNOWN"]
    reason: str
    citation_numbers: list[int]
    support_spans: list[SupportSpan]
    script_spans: list[str] = Field(default_factory=list)


CLAIM_CHECK_INSTRUCTIONS = """\
Return claim_checks covering EVERY material assertion in BOTH finding and remedy,
plus the severity. Use a separate check for each asserted obligation or production
fact; one supported precaution cannot support the entire paragraph. quote is an exact
substring of that field (for severity, quote the level itself). For remedy quotes
use the detail prose only, excluding the action label. basis distinguishes script
facts, production facts, outside-world source claims, and planning advice.
Use basis=application for applying a sourced rule to a screenplay fact or an explicitly
conditional production choice. Use basis=script_edit ONLY for a proposed change to
on-screen content that removes/reduces a cited trigger, not for equipment, specialists,
permits or rightsholder assertions. Such an edit need not be prescribed verbatim by
the source; the source must establish the trigger/rule and the edit must address it.
Never promise clearance, permission, safety or a final rating from a proposed edit.
For application/script_edit include script_spans: EXACT substrings of supplied SCENE
TEXT anchoring the relevant content. They cannot assert production facts. Separate
pure rule assertions from script facts when possible; don't demand that sources name
fictional characters, dialogue or props. A sourced ownership link still needs a source;
it cannot be inferred from a name in the script or the label's corporate parent.
For every source/planning/application/script_edit claim (except severity), and every
remedy prescription,
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
Without support for the rule/trigger mark that claim UNKNOWN/UNSUPPORTED with empty support_spans.
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

CLAIM_CHECK_INSTRUCTIONS += """
Use basis=inquiry ONLY for questions requesting missing input or a user decision
relevant to this desk and finding. No external support is required for the question;
it must not smuggle in an obligation, an unconfirmed factual premise or a prescription.
Ratings questions concern target/content decisions; clearance questions concern intended
use, permission status and ownership evidence; territory questions concern distribution
markets/version; safety questions concern casting, method and shooting jurisdiction.
Do not replace a supported useful remedy with a generic question. Production casting
questions cannot repair rating, copyright or distribution findings. Judge relevance
and usefulness as well as entailment. Do not relabel prescriptions as inquiries.
Check that the remedy action matches the detail: CUT/REPLACE for content edits,
OBTAIN_LICENSE/OBTAIN_RELEASE only with supported permission requirements,
ADD_SPECIALIST only for sourced specialist work. NO_ACTION may accompany an unresolved
input question; it must not disguise a content edit or mandatory production work.
"""


def _support_problem(check: ClaimCheck, flag: dict[str, Any], script_context: str) -> str | None:
    """Validate provenance and anchor display quotes back to immutable raw sources."""
    if check.field == "severity":
        return None  # field, not a model-chosen basis, defines this judgement
    if check.basis == "inquiry" and check.field != "remedy":
        return "An inquiry must be a remedy question, not an asserted finding"
    if (
        check.field == "remedy"
        and check.quote == PRODUCTION_INQUIRY
        and flag.get("agent") != "safety_underwriter"
    ):
        return "Production-input inquiry is irrelevant to this desk"
    citations = flag["citations"]
    if check.basis == "script_edit" and check.field != "remedy":
        return "A proposed script edit belongs in the remedy"
    if check.basis in {"application", "script_edit"} and not check.script_spans:
        return "An application or edit needs exact screenplay evidence"
    if any(not s.strip() or s not in script_context for s in check.script_spans):
        return "Script evidence is not verbatim in the supplied scene text"
    needs_span = (
        check.basis in {"source", "planning", "application", "script_edit"}
        and check.field != "severity"
    )
    needs_span |= check.field == "remedy" and check.basis != "inquiry"
    if needs_span and not check.support_spans:
        return "No exact supporting span for this external claim or prescription"
    indexes = {span.citation_number for span in check.support_spans}
    if indexes != set(check.citation_numbers):
        return "Citation indexes and supporting spans do not match"
    anchored = []
    for span in check.support_spans:
        if span.citation_number > len(citations):
            return "Supporting span references a nonexistent citation"
        excerpt = citations[span.citation_number - 1].get("excerpt") or ""
        quote = anchor_quote(span.quote, excerpt)
        if quote is None:
            return "Supporting span is not verbatim in the cited excerpt"
        anchored.append(quote)
    # Apply only after every receipt passes; citations themselves never change.
    for span, quote in zip(check.support_spans, anchored, strict=True):
        span.quote = quote
    return None


def _cover_clause_joins(body: str, covered: list[bool]) -> None:
    """Allow conjunctions between audited clauses, never omitted substantive text."""
    coverage = "".join("1" if hit else "0" for hit in covered)
    for gap in re.finditer("0+", coverage):
        start, end = gap.span()
        if (
            start > 0
            and end < len(body)
            and re.fullmatch(r"[\W_]*(?:and(?:\s+that)?|or|and/or)[\W_]*", body[start:end])
        ):
            covered[start:end] = [True] * (end - start)


def checked_verdict(
    verdict: dict[str, Any], flag: dict[str, Any], script_context: str = ""
) -> dict[str, Any]:
    """Validate the audit's anchors; a positive label cannot override failed clauses."""
    checks = [ClaimCheck.model_validate(c) for c in verdict["claim_checks"]]
    if {c.field for c in checks} != {"finding", "remedy", "severity"}:
        raise ValueError("claim audit must cover finding, remedy and severity")
    fields = {
        "finding": flag["finding"],
        "remedy": flag["remedy"]["detail"],
        "severity": flag["severity"],
    }
    reanchors = []
    for check_index, check in enumerate(checks):
        if check.quote not in fields[check.field]:
            raise ValueError("claim audit quote is not in its field")
        if check.status == "SUPPORTED":
            submitted = [s.quote for s in check.support_spans]
            problem = _support_problem(check, flag, script_context)
            reanchors.extend(
                {
                    "check_index": check_index,
                    "span_index": span_index,
                    "citation_number": span.citation_number,
                    "submitted_quote": before,
                    "raw_quote": span.quote,
                }
                for span_index, (before, span) in enumerate(
                    zip(submitted, check.support_spans, strict=True)
                )
                if before != span.quote
            )
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
        # Internal joins are reviewed in the complete claim context downstream;
        # never swallow an unaudited clause, exception, condition or negation.
        _cover_clause_joins(body, covered)
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
        "support_span_version": 2,
        **({"support_span_reanchors": reanchors} if reanchors else {}),
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

    Only exact scene receipts accompany rule applications/edits; no previous
    reasoning or severity is shown. Script evidence cannot supply external duties.
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
        fixed_safety_inquiry = (
            check["basis"] == "inquiry"
            and check["quote"] == PRODUCTION_INQUIRY
            and flag.get("agent") == "safety_underwriter"
        )
        if check["field"] == "severity" or fixed_safety_inquiry:
            continue
        if not check["support_spans"] and check["basis"] != "inquiry":
            continue  # script facts, severity or the fixed production inquiry
        claims.append(
            {
                "check_index": index,
                "claim": check["quote"],
                "claim_context": flag["remedy"]["detail"]
                if check["field"] == "remedy"
                else flag["finding"],
                "basis": check["basis"],
                **(
                    {"remedy_action": flag["remedy"].get("action")}
                    if check["field"] == "remedy"
                    else {}
                ),
                "script_evidence": check.get("script_spans", [])
                if check["basis"] in {"application", "script_edit", "inquiry"}
                else [],
                **(
                    {"desk": flag.get("agent"), "finding_context": flag["finding"]}
                    if check["basis"] == "inquiry"
                    else {}
                ),
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
        "For basis=source/planning, the excerpts must establish the external assertions. "
        "claim_context is the original full field, supplied only to preserve operators, "
        "conditions and alternatives between atomic quotes. It is NOT additional evidence. "
        "Assess the quoted clause as used in that full sentence, not in isolation. Do not "
        "strengthen an optional alternative into a required action or let one supported "
        "option hide an unsupported one. Preserve each option's applicability conditions. "
        "For basis=application, combine the exact script_evidence with the sourced rule. "
        "Script evidence establishes only fictional content, not permits, real casting, "
        "shooting jurisdiction, practical method, ownership or permission. Sources need "
        "not name screenplay characters or dialogue. Retain conditions on unknown facts. "
        "For basis=script_edit, verify that the proposed on-screen change addresses a "
        "trigger established by the source and present in script_evidence. The source "
        "need not literally instruct an editor or name replacement dialogue. Reject "
        "guaranteed clearance, permission, safety or rating outcomes; an edit addressing "
        "one issue does not establish resolution of all issues. Do not accept new "
        "equipment, specialist, permit, labor or ownership assertions as script edits. "
        "Replacement labels alone do not establish permission to use replacement assets. "
        "For basis=inquiry, check that it only requests relevant missing input or a "
        "user decision for the supplied desk/finding. Reject irrelevant generic casting "
        "questions on rating/clearance/territory findings, concealed prescriptions or "
        "unconfirmed factual premises. finding_context is context for relevance only, "
        "not evidence that its assertions are true. "
        "When remedy_action is supplied, reject a CUT/REPLACE edit or mandatory "
        "production work labelled NO_ACTION; an unresolved input question may use it. "
        "For each check_index decide whether the evidence establishes the claim or "
        "justifies the conditional edit/inquiry under these rules. Do not use industry knowledge "
        "or the plausibility of precautions. Titles, scope headings and index entries "
        "cannot establish an operative requirement. A general duty to obey applicable "
        "laws does not establish named permits, specialists or equipment. Maintaining "
        "licenses is not maintaining/control of firearms. Entitlement to a stunt double "
        "does not prescribe other specialists, PPE or labor obligations. A recommendation "
        "for production work is not exempt: 'should', 'consider' and 'standard planning' "
        "still require source support for the prescribed precaution. Evaluate EACH "
        "duty/object/condition in a compound "
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
        + "\nDESK: "
        + str(flag.get("agent"))
        + "\nKeep source rules, their application to verified screenplay facts, and proposed "
        "content edits distinct. A proposed CUT or REPLACE can remove a cited trigger "
        "without the source literally naming the scene or instructing an editor. Explain "
        "what the edit changes; do not promise a final rating, permission or clearance. "
        "Production duties, ownership, licenses and specialists still need operative "
        "source support. If necessary, ask only for missing input relevant to this desk "
        "and finding. Do not replace a useful supported edit with an unrelated question. "
        "Casting/method inquiries belong to safety, not to ratings, clearance or territory. "
        + "\nCorrect this partially supported finding AND remedy. Preserve the supported "
        "hazard/exposure; remove unsupported obligations and qualify actual casting, method "
        "and jurisdiction assumptions in BOTH fields. Do not invent sources or requirements. "
        "Every external prescription needs an operative supporting span in the supplied "
        "citations. Removing 'must' or calling it planning advice does not fix absent support. "
        "A license-maintenance rule does not support firearms maintenance, and entitlement "
        "to a stunt double does not establish other specialists or equipment. "
        "Remove prescriptions whose action/object/conditions the excerpts do not establish. "
        "If only a depicted safety hazard and unknown production facts remain, preserve "
        "the concern and ask what casting/method/jurisdiction is planned. Other desks "
        "must ask relevant missing-use, permission, distribution or content questions. "
        "Choose an action consistent with the remedy; do not put a content edit or "
        "mandatory production work under NO_ACTION. "
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
