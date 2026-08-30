#!/usr/bin/env python3
"""Local spend tracker across every service GREENLIGHT touches.

    python scripts/costs.py                    # the table
    python scripts/costs.py set gcp 14.30      # record an actual from a console
    make costs

Measured activity comes from artifacts (run records carry a search_id per live
Parallel call). Estimates use the unit prices below — rules of thumb, edit them
as real invoices arrive. Actuals you record from the consoles live in
costs/ledger.json and always win over estimates in the table.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "costs" / "ledger.json"

# ---- unit prices (USD) — rules of thumb, keep current with invoices ----------
PRICE = {
    "parallel_search_advanced": 0.009,  # per search, advanced processor
    "clearance_run_gemini": 2.20,  # 3.7-flash desks+verifiers + one 2.5-pro adjudication
    # (3.7-flash intro pricing $0.75/$3.75 per MTok through 2026-12-31, then doubles)
    "writer_run_gemini": 0.30,  # two Pro calls + comps embedding
    "corpus_embedding_once": 1.30,  # 6,302 profiles through text-embedding-005
    "dns_zone_month": 0.20,
    "artifact_registry_gb_month": 0.10,
    "cloud_run_warm_day": 3.40,  # 2vCPU/2Gi min-instances=1, always warm
}
UNSAVED_CLEARANCE_RUNS = 4  # aborted/timeout runs that never wrote a record
PREFLIGHT_SEARCHES = 4  # checks.py + cassette capture
MIN_INSTANCES_SINCE = "2026-08-25"  # the day min-instances=1 went on

# Who actually pays for each service. "credit" burns the GCP credit, "cash" is
# real money out of pocket, partner/trial credits are someone else's tab.
FUNDING = {
    "gcp": "gcp credit",
    "gcp-infra": "gcp credit",
    "parallel": "partner credit",
    "clickhouse": "trial credit",
    "domain": "cash",
}


def measure() -> dict:
    searches = set()
    clearance = writer = 0
    for f in glob.glob(str(ROOT / "runs" / "run_*.json")):
        clearance += 1
        r = json.loads(Path(f).read_text())
        for v in (r.get("research") or {}).values():
            if v.get("search_id"):
                searches.add(v["search_id"])
    writer = len(glob.glob(str(ROOT / "runs" / "writer_*.json")))
    return {
        "parallel_searches_recorded": len(searches),
        "parallel_searches_total_est": len(searches)
        + UNSAVED_CLEARANCE_RUNS * 25
        + PREFLIGHT_SEARCHES,
        "clearance_runs": clearance + UNSAVED_CLEARANCE_RUNS,
        "writer_runs": writer,
    }


def _warm_days() -> int:
    from datetime import date

    y, mo, d = (int(x) for x in MIN_INSTANCES_SINCE.split("-"))
    return max(1, (date.today() - date(y, mo, d)).days)


def rows(m: dict, actuals: dict) -> list[tuple]:
    """(service, activity, estimate, actual, where-to-check)"""
    est_gemini = round(
        m["clearance_runs"] * PRICE["clearance_run_gemini"]
        + m["writer_runs"] * PRICE["writer_run_gemini"]
        + PRICE["corpus_embedding_once"],
        2,
    )
    est_parallel = round(m["parallel_searches_total_est"] * PRICE["parallel_search_advanced"], 2)
    return [
        (
            "gcp",
            f"{m['clearance_runs']} clearance + {m['writer_runs']} writer runs, corpus embed",
            est_gemini,
            actuals.get("gcp"),
            "console.cloud.google.com/billing (budget alerts at 40/75/90% of $100)",
        ),
        (
            "gcp-infra",
            f"Cloud Run always-warm since {MIN_INSTANCES_SINCE} "
            f"({_warm_days()}d x ${PRICE['cloud_run_warm_day']}/day) + registry + DNS",
            round(
                _warm_days() * PRICE["cloud_run_warm_day"]
                + PRICE["artifact_registry_gb_month"] * 0.7
                + PRICE["dns_zone_month"],
                2,
            ),
            actuals.get("gcp-infra"),
            "same console; absorbed by the credit while it lasts",
        ),
        (
            "parallel",
            f"~{m['parallel_searches_total_est']} searches "
            f"({m['parallel_searches_recorded']} recorded in run files)",
            est_parallel,
            actuals.get("parallel"),
            "platform.parallel.ai dashboard — hackathon partner credits may cover this",
        ),
        (
            "clickhouse",
            "6,302-row corpus, kNN queries; instance auto-idles",
            0.0,
            actuals.get("clickhouse"),
            "clickhouse.cloud console — own trial credits, separate from GCP",
        ),
        (
            "domain",
            "scriptrisk.com — one-time, renewal disabled, expires 2027-08-24",
            12.0,
            actuals.get("domain", 12.0),
            "Cloud Domains; billed to the GCP billing account (cash, not credit)",
        ),
    ]


def main(argv: list[str]) -> int:
    LEDGER.parent.mkdir(exist_ok=True)
    actuals = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}

    if len(argv) >= 3 and argv[1] == "set":
        actuals[argv[2]] = float(argv[3])
        LEDGER.write_text(json.dumps(actuals, indent=2) + "\n")
        print(f"recorded actual: {argv[2]} = ${float(argv[3]):.2f}")
        return 0

    m = measure()
    table = rows(m, actuals)
    print(f"\n{'service':<11} {'estimate':>9} {'actual':>8}  activity / where to check actuals")
    print("-" * 100)
    total_est = total_act = 0.0
    for svc, activity, est, act, where in table:
        total_est += est
        total_act += act if act is not None else est
        act_s = f"${act:.2f}" if act is not None else "—"
        print(f"{svc:<11} {'$' + format(est, '.2f'):>9} {act_s:>8}  {activity}")
        print(f"{'':<11} {'':>9} {'':>8}  ↳ {where}")
    print("-" * 100)
    print(
        f"{'TOTAL':<11} {'$' + format(total_est, '.2f'):>9} "
        f"{'$' + format(total_act, '.2f'):>8}  (actuals fall back to estimates when unset)"
    )
    # ---- who pays: the number that matters is cash + credit burn, separately
    by_funding: dict[str, float] = {}
    for svc, _act, est, act, _w in table:
        by_funding[FUNDING[svc]] = by_funding.get(FUNDING[svc], 0.0) + (
            act if act is not None else est
        )
    print("\nfunded by:")
    for src in ("gcp credit", "cash", "partner credit", "trial credit"):
        amount = by_funding.get(src, 0.0)
        note = ""
        if src == "gcp credit":
            note = f"  → of the $100 GCP credit ({min(999, round(amount))}% if estimates hold)"
        if src == "cash":
            note = "  → real money out of pocket"
        print(f"  {src:<15} ${amount:>7.2f}{note}")
    print(
        "\nEstimates ≠ invoices. Pull the two real numbers and record them:\n"
        "  GCP:      console.cloud.google.com/billing/012600-29EBC8-C419FB/reports"
        " (filter: greenlight-clearance-2026)\n"
        "            → python scripts/costs.py set gcp <gemini+embed $>  and"
        "  set gcp-infra <cloud run $>\n"
        "  Parallel: platform.parallel.ai usage → python scripts/costs.py set parallel <$>\n"
        "Budgets wired: '$100 Monthly Budget Alert' (50/90/100/150%) and"
        " 'GREENLIGHT hackathon' $200 (40/75/90/100%)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
