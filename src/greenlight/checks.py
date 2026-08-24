"""Preflight credential and compliance checks.

Two of these are contest pass/fail gates: Google Cloud and Parallel must both be
genuinely called at runtime. This module makes "are we eligible?" a single command.

    python -m greenlight.checks all
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[2m",
    "\033[0m",
)


@dataclass
class Result:
    name: str
    ok: bool
    detail: str
    gate: bool = False  # True => contest pass/fail requirement

    def render(self) -> str:
        mark = f"{GREEN}PASS{RESET}" if self.ok else f"{RED}FAIL{RESET}"
        tag = f" {YELLOW}[contest gate]{RESET}" if self.gate else ""
        return f"  {mark}  {self.name}{tag}\n        {DIM}{self.detail}{RESET}"


def _missing(*keys: str) -> list[str]:
    return [k for k in keys if not os.getenv(k)]


def check_google_cloud() -> Result:
    """Verify Vertex AI is reachable and Gemini actually responds."""
    name = "Google Cloud / Vertex AI (Gemini)"
    if miss := _missing("GOOGLE_CLOUD_PROJECT"):
        return Result(name, False, f"missing in .env: {', '.join(miss)}", gate=True)
    try:
        from google import genai

        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Reply with the single word: ready",
        )
        text = (resp.text or "").strip()
        return Result(name, bool(text), f"gemini-2.5-flash replied: {text[:40]!r}", gate=True)
    except Exception as e:
        hint = ""
        if "default credentials" in str(e).lower():
            hint = "  -> run: gcloud auth application-default login"
        return Result(name, False, f"{type(e).__name__}: {str(e)[:180]}{hint}", gate=True)


def check_parallel() -> Result:
    """Verify the Parallel Search API responds. This is the partner track requirement."""
    name = "Parallel Search API"
    if _missing("PARALLEL_API_KEY"):
        return Result(name, False, "missing in .env: PARALLEL_API_KEY", gate=True)
    try:
        import parallel

        client = parallel.Parallel(api_key=os.environ["PARALLEL_API_KEY"])
        res = client.search(
            search_queries=["music sync license cost film"],
            objective=(
                "Determine what it costs and how long it takes to license a popular "
                "song for use in a feature film."
            ),
            mode="fast",
            max_chars_total=2000,
        )
        n = len(res.results)
        top = res.results[0].url if n else "(none)"
        return Result(name, n > 0, f"{n} results, top: {top[:90]}", gate=True)
    except Exception as e:
        return Result(name, False, f"{type(e).__name__}: {str(e)[:180]}", gate=True)


def check_clickhouse() -> Result:
    """Verify the precedent-corpus database is reachable. Not a contest gate."""
    name = "ClickHouse Cloud"
    if miss := _missing("CLICKHOUSE_HOST", "CLICKHOUSE_PASSWORD"):
        return Result(name, False, f"missing in .env: {', '.join(miss)}")
    try:
        import clickhouse_connect

        client = clickhouse_connect.get_client(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.environ["CLICKHOUSE_PASSWORD"],
            secure=os.getenv("CLICKHOUSE_SECURE", "true").lower() == "true",
        )
        version = client.query("SELECT version()").result_rows[0][0]
        return Result(name, True, f"connected, server version {version}")
    except Exception as e:
        return Result(name, False, f"{type(e).__name__}: {str(e)[:180]}")


def check_compliance() -> Result:
    """Repo-level contest requirements that are cheap to break and fatal to miss."""
    name = "Contest compliance (license + forbidden deps)"
    problems = []
    if not (ROOT / "LICENSE").is_file():
        problems.append("LICENSE missing at repo root")
    scan = subprocess.run(
        [str(ROOT / "scripts" / "check_forbidden_deps.sh")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if scan.returncode != 0:
        problems.append("forbidden AI dependency present -- see `make check`")
    if problems:
        return Result(name, False, "; ".join(problems), gate=True)
    return Result(name, True, "LICENSE present; no non-Google AI SDKs in shipped code", gate=True)


CHECKS = {
    "gcp": check_google_cloud,
    "parallel": check_parallel,
    "clickhouse": check_clickhouse,
    "compliance": check_compliance,
}


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else "all"
    if which not in {*CHECKS, "all"}:
        print(
            f"usage: python -m greenlight.checks [{'|'.join(CHECKS)}|all]",
            file=sys.stderr,
        )
        return 2

    selected = CHECKS.values() if which == "all" else [CHECKS[which]]
    print("\nGREENLIGHT preflight\n")
    results = [fn() for fn in selected]
    for r in results:
        print(r.render())

    failed_gates = [r for r in results if not r.ok and r.gate]
    failed_soft = [r for r in results if not r.ok and not r.gate]
    print()
    if failed_gates:
        print(
            f"{RED}BLOCKED{RESET}: {len(failed_gates)} contest gate(s) failing. "
            f"These are pass/fail requirements -- fix before building on top of them.\n"
        )
        return 1
    if failed_soft:
        print(
            f"{YELLOW}Partial{RESET}: all contest gates pass; "
            f"{len(failed_soft)} non-gating service(s) not yet configured.\n"
        )
        return 0
    print(f"{GREEN}All checks pass.{RESET} Cleared for Phase 1.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
