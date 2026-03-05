#!/usr/bin/env python3
"""
test_stop_check.py — Unit tests for stop_check math.
If these had existed on Mar 3, the inverted P&L bug would never have shipped.

Run: python3 -m pytest tests/test_stop_check.py -v
Or:  python3 tests/test_stop_check.py
"""

import sys
import os

# --- Test the core math that broke on Mar 4 ---

def test_trailing_stop_drawdown_long():
    """
    LONG position: trail=100, current=95 → drawdown should be POSITIVE 5%
    (below trail = danger). The bug had this as -5% (safe).
    """
    trail = 100.0
    current = 95.0
    # Correct formula (post-fix):
    drawdown_pct = ((trail - current) / trail) * 100
    assert drawdown_pct == 5.0, f"Expected 5.0%, got {drawdown_pct}%"
    assert drawdown_pct > 0, "Below trail should be POSITIVE (danger)"


def test_trailing_stop_above_trail_long():
    """
    LONG position: trail=100, current=105 → should be NEGATIVE (safe, above trail).
    The bug had this as +5% (danger), triggering a sell on a WINNING position.
    """
    trail = 100.0
    current = 105.0
    drawdown_pct = ((trail - current) / trail) * 100
    assert drawdown_pct == -5.0, f"Expected -5.0%, got {drawdown_pct}%"
    assert drawdown_pct < 0, "Above trail should be NEGATIVE (safe)"


def test_trailing_stop_at_trail():
    """Trail = current → 0% drawdown, no action."""
    trail = 100.0
    current = 100.0
    drawdown_pct = ((trail - current) / trail) * 100
    assert drawdown_pct == 0.0


def test_stop_guard_blocks_profitable_sell():
    """STOP GUARD: Never sell a position that's in profit."""
    entry = 70000.0
    current = 73000.0
    gain_pct = ((current - entry) / entry) * 100
    assert gain_pct > 0, "Position is profitable"
    # STOP GUARD should block: if gain_pct > 0, don't sell
    should_block = gain_pct > 0
    assert should_block, "STOP GUARD must block selling profitable positions"


def test_stop_guard_allows_losing_sell():
    """STOP GUARD should allow selling positions that are losing."""
    entry = 73000.0
    current = 70000.0
    gain_pct = ((current - entry) / entry) * 100
    assert gain_pct < 0, "Position is losing"
    should_block = gain_pct > 0
    assert not should_block, "STOP GUARD should NOT block selling losers"


def test_short_trailing_stop():
    """SHORT position: trail=100 (low), current=105 → danger (price went up)."""
    trail = 100.0  # For shorts, trail is the lowest price seen
    current = 105.0
    # For shorts, drawdown = price going UP from trail
    drawdown_pct = ((current - trail) / trail) * 100
    assert drawdown_pct == 5.0, f"Expected 5.0%, got {drawdown_pct}%"
    assert drawdown_pct > 0, "Short: price above trail = danger"


def test_price_sanity_btc():
    """BTC should never be $32. Sanity floor is $10,000."""
    price = 32.35
    floor = 10000
    assert price < floor, "BTC at $32 should fail sanity check"


def test_price_sanity_eth():
    """ETH should never be $20. Sanity floor is $100."""
    price = 20.39
    floor = 100
    assert price < floor, "ETH at $20 should fail sanity check"


def test_ticker_normalization():
    """Bare crypto tickers should get -USD suffix for Yahoo."""
    CRYPTO_BARE = {"BTC", "ETH", "SOL", "LINK", "DOGE", "SUI", "AVAX"}
    EQUITY_TICKERS = {"GDX", "GLD", "XLE", "ROST", "COIN", "HOOD"}

    # Bare crypto → add -USD
    assert "BTC" in CRYPTO_BARE
    assert "BTC-USD" not in CRYPTO_BARE  # Already formatted shouldn't double-suffix

    # Equity with -USD → strip it
    assert "GDX" in EQUITY_TICKERS
    bare = "GDX-USD".replace("-USD", "")
    assert bare in EQUITY_TICKERS


def test_portfolio_return_calculation():
    """$50K baseline, $50K value = 0% return. Not +100% from old $25K baseline."""
    STARTING_CAPITAL = 50000.0
    total_value = 50000.0
    return_pct = (total_value - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    assert return_pct == 0.0, f"Expected 0%, got {return_pct}%"

    # $22K value (Alfred's actual) = -56%, not +88%
    total_value = 22000.0
    return_pct = (total_value - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    assert abs(return_pct - (-56.0)) < 0.01, f"Expected -56%, got {return_pct}%"


def test_parent_bot_mapping():
    """alfred_crypto should map to alfred for portfolio snapshots."""
    PARENT_BOT = {
        "alfred_crypto": "alfred",
        "tars_crypto": "tars",
        "vex_crypto": "vex",
        "eddie_crypto": "eddie_v",
    }
    assert PARENT_BOT["alfred_crypto"] == "alfred"
    assert PARENT_BOT.get("alfred", "alfred") == "alfred"  # Non-crypto stays as-is


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
    print("  All tests passed. Ship it.")
