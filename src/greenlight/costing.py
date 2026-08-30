"""Per-run token accounting: fold ADK event usage into tiered counters and
price them for the run record. Import-side-effect free — pipeline pulls this
in, but tests and tools can use it without dragging in the ADK stack.

USD per 1M tokens. Flash is intro pricing through 2026-12-31 (then doubles);
cached prompt tokens bill at ~10% of the input rate. Keep current with
invoices — scripts/costs.py reconciles these against the billing console.
"""

from __future__ import annotations

from typing import Any

MTOK_PRICE = {
    "flash": {"in": 0.75, "out": 3.75},
    "pro": {"in": 1.25, "out": 10.00},
}
CACHED_INPUT_FACTOR = 0.1
PARALLEL_SEARCH_USD = 0.009
PRO_AGENTS = {"adjudicator"}  # the one deliberate Pro-tier agent (CLAUDE.md model tiers)


def accumulate_usage(usage: dict[str, dict[str, int]], event: Any) -> None:
    """Fold one ADK event's usage_metadata into per-tier token counters.
    prompt_token_count includes the cached portion; cached is tracked separately
    so cost can price it at the cached rate — and so we learn whether Vertex's
    implicit caching is doing anything for us at all."""
    um = getattr(event, "usage_metadata", None)
    if um is None:
        return
    tier = "pro" if getattr(event, "author", "") in PRO_AGENTS else "flash"
    bucket = usage.setdefault(tier, {"prompt": 0, "cached": 0, "output": 0})
    bucket["prompt"] += getattr(um, "prompt_token_count", 0) or 0
    bucket["cached"] += getattr(um, "cached_content_token_count", 0) or 0
    bucket["output"] += (getattr(um, "candidates_token_count", 0) or 0) + (
        getattr(um, "thoughts_token_count", 0) or 0
    )


def usage_cost_usd(usage: dict[str, dict[str, int]], searches: int) -> float:
    total = searches * PARALLEL_SEARCH_USD
    for tier, b in usage.items():
        price = MTOK_PRICE[tier]
        fresh = max(0, b["prompt"] - b["cached"])
        total += (
            fresh * price["in"]
            + b["cached"] * price["in"] * CACHED_INPUT_FACTOR
            + b["output"] * price["out"]
        ) / 1_000_000
    return round(total, 4)
