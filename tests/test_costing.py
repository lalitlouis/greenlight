"""Per-run token accounting: ADK event usage folded into tiered counters and
priced for the record. The whole point is replacing the $2.20-guess era with
measured cost — these tests pin the math so a pricing edit can't silently skew
every future run's cost_usd.
"""

from types import SimpleNamespace

from greenlight.costing import accumulate_usage, usage_cost_usd


def ev(author, prompt=0, cached=0, candidates=0, thoughts=0):
    return SimpleNamespace(
        author=author,
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt,
            cached_content_token_count=cached,
            candidates_token_count=candidates,
            thoughts_token_count=thoughts,
        ),
    )


def test_accumulate_splits_tiers_by_author():
    usage: dict = {}
    accumulate_usage(usage, ev("ratings_board", prompt=1000, candidates=100))
    accumulate_usage(usage, ev("ratings_board", prompt=2000, cached=500, thoughts=50))
    accumulate_usage(usage, ev("adjudicator", prompt=10_000, candidates=400))
    assert usage["flash"] == {"prompt": 3000, "cached": 500, "output": 150}
    assert usage["pro"] == {"prompt": 10_000, "cached": 0, "output": 400}


def test_accumulate_ignores_events_without_usage():
    usage: dict = {}
    accumulate_usage(usage, SimpleNamespace(author="x", usage_metadata=None))
    accumulate_usage(usage, SimpleNamespace(author="x"))  # no attribute at all
    none_counts = SimpleNamespace(
        prompt_token_count=None,
        cached_content_token_count=None,
        candidates_token_count=None,
        thoughts_token_count=None,
    )
    accumulate_usage(usage, SimpleNamespace(author="x", usage_metadata=none_counts))
    assert usage == {"flash": {"prompt": 0, "cached": 0, "output": 0}}


def test_cost_prices_cached_tokens_at_cached_rate():
    # 1M fresh prompt + 1M cached prompt + 1M output, flash intro pricing:
    # 0.75 + 0.075 + 3.75 = 4.575; plus 10 searches at $0.009 = 4.665
    usage = {"flash": {"prompt": 2_000_000, "cached": 1_000_000, "output": 1_000_000}}
    assert usage_cost_usd(usage, searches=10) == 4.665


def test_cost_pro_tier_and_empty_usage():
    usage = {"pro": {"prompt": 1_000_000, "cached": 0, "output": 100_000}}
    assert usage_cost_usd(usage, searches=0) == 2.25  # 1.25 in + 1.00 out
    assert usage_cost_usd({}, searches=25) == 0.225  # searches only
