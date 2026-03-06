#!/usr/bin/env python3
# CALLED BY: execute_trade.py, heartbeat stop checks
"""
Pre-trade gate for Vex trading bot.
Checks cooldown, signal kill, and price sanity before allowing trades.

Usage: python pre_trade_checker.py [--test]
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

STOP_HISTORY_PATH = Path("/tmp/stop_history.json")
SCRIPTS_DIR = Path(__file__).resolve().parent

# Graceful imports of sibling modules
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import signal_kill_check
    HAS_SIGNAL_KILL = True
except Exception:
    HAS_SIGNAL_KILL = False

try:
    import price_sanity_gate
    HAS_PRICE_SANITY = True
except Exception:
    HAS_PRICE_SANITY = False


def _load_stop_history():
    """Load stop history from JSON file."""
    if not STOP_HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(STOP_HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_stop_history(data):
    """Save stop history to JSON file."""
    STOP_HISTORY_PATH.write_text(json.dumps(data, indent=2))


def check_cooldown(ticker, session_date):
    """
    Check if ticker is in cooldown (2+ consecutive stops today).

    Args:
        ticker: Stock symbol
        session_date: Date string 'YYYY-MM-DD'

    Returns:
        (bool, str): (True, "ok") or (False, "cooldown")
    """
    history = _load_stop_history()
    key = f"{ticker}:{session_date}"
    stops = history.get(key, [])
    if len(stops) >= 2:
        return False, "cooldown"
    return True, "ok"


def record_stop(ticker, session_date):
    """
    Record a stop-loss hit for a ticker on a given date.

    Args:
        ticker: Stock symbol
        session_date: Date string 'YYYY-MM-DD'
    """
    history = _load_stop_history()
    key = f"{ticker}:{session_date}"
    if key not in history:
        history[key] = []
    history[key].append({
        "time": datetime.now().isoformat(),
        "ticker": ticker,
    })
    _save_stop_history(history)


def check_all_gates(ticker, price, session_date):
    """
    Run all pre-trade gates: cooldown, signal kill, price sanity.

    Args:
        ticker: Stock symbol
        price: Current price
        session_date: Date string 'YYYY-MM-DD'

    Returns:
        (pass_all: bool, reasons: list[str])
    """
    reasons = []
    pass_all = True

    # 1. Cooldown
    ok, msg = check_cooldown(ticker, session_date)
    if not ok:
        pass_all = False
        reasons.append(f"cooldown: {ticker} has 2+ stops today")

    # 2. Signal kill check
    if HAS_SIGNAL_KILL:
        try:
            if hasattr(signal_kill_check, "is_killed"):
                killed = signal_kill_check.is_killed(ticker)
            elif hasattr(signal_kill_check, "check"):
                killed = not signal_kill_check.check(ticker)
            elif hasattr(signal_kill_check, "signal_killed"):
                killed = signal_kill_check.signal_killed(ticker)
            else:
                killed = False
                reasons.append("signal_kill_check: no recognized function found (non-blocking)")
            if killed:
                pass_all = False
                reasons.append(f"signal_kill: {ticker} signal is killed")
        except Exception as e:
            reasons.append(f"signal_kill_check error (non-blocking): {e}")
    else:
        reasons.append("signal_kill_check: module not available (degraded)")

    # 3. Price sanity
    if HAS_PRICE_SANITY:
        try:
            if hasattr(price_sanity_gate, "check_price"):
                ok = price_sanity_gate.check_price(ticker, price)
            elif hasattr(price_sanity_gate, "is_sane"):
                ok = price_sanity_gate.is_sane(ticker, price)
            elif hasattr(price_sanity_gate, "check"):
                ok = price_sanity_gate.check(ticker, price)
            else:
                ok = True
                reasons.append("price_sanity_gate: no recognized function found (non-blocking)")
            if not ok:
                pass_all = False
                reasons.append(f"price_sanity: {ticker} @ ${price} failed sanity check")
        except Exception as e:
            reasons.append(f"price_sanity_gate error (non-blocking): {e}")
    else:
        reasons.append("price_sanity_gate: module not available (degraded)")

    if not reasons:
        reasons.append("all gates passed")

    return pass_all, reasons


def _run_test():
    """Run self-test with mock data."""
    print("=" * 50)
    print("  PRE-TRADE CHECKER — TEST MODE")
    print("=" * 50)
    today = datetime.now().strftime("%Y-%m-%d")

    # Test cooldown (should pass — no stops yet)
    ok, msg = check_cooldown("TEST", today)
    print(f"  {'✅' if ok else '❌'} cooldown check (no stops): {msg}")

    # Record 2 stops and test again
    record_stop("TEST", today)
    record_stop("TEST", today)
    ok, msg = check_cooldown("TEST", today)
    print(f"  {'✅' if not ok else '❌'} cooldown check (2 stops): {msg}")

    # Test all gates
    pass_all, reasons = check_all_gates("AAPL", 150.0, today)
    status = "✅ PASS" if pass_all else "❌ BLOCKED"
    print(f"  {status} all gates for AAPL @ $150:")
    for r in reasons:
        print(f"    — {r}")

    # Clean up test data
    history = _load_stop_history()
    test_key = f"TEST:{today}"
    if test_key in history:
        del history[test_key]
        _save_stop_history(history)
        print("  🧹 Cleaned up TEST stop history")

    print("=" * 50)
    print(f"  signal_kill_check: {'✅ loaded' if HAS_SIGNAL_KILL else '⚠️  not available'}")
    print(f"  price_sanity_gate: {'✅ loaded' if HAS_PRICE_SANITY else '⚠️  not available'}")
    print("=" * 50)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_test()
    else:
        print("Usage: python pre_trade_checker.py --test")
        print("Import check_all_gates() from execute_trade.py for production use.")
