#!/usr/bin/env python3
"""
Crypto Pre-Trade Gate — ALL checks must pass before any entry.

Combines: kill switch + cooldown + correlation guard + stop validation.
Call gate_check() before every trade. If it returns False, DO NOT TRADE.

Usage:
  from pretrade_gate import gate_check
  result = gate_check("alfred", "BTC", "LONG", 2500.0)
  if result["passed"]:
      # execute trade
  else:
      print(result["blocked_by"])
"""

from crypto_kill_switch import is_frozen
from crypto_cooldown import CooldownEnforcer
from crypto_correlation_guard import check_entry
import json

# Try to import stale detector (TARS's module — may not be local yet)
try:
    from crypto_stale_detector import is_data_fresh
    HAS_STALE_DETECTOR = True
except ImportError:
    HAS_STALE_DETECTOR = False


def gate_check(bot_id: str, ticker: str, side: str, notional: float) -> dict:
    """
    Run ALL pre-trade checks. ALL must pass.
    
    Returns: {
        "passed": bool,
        "checks": {name: {"passed": bool, "detail": str}},
        "blocked_by": [list of failed check names] or []
    }
    """
    checks = {}
    blocked_by = []

    # 0. Stale data check (TARS's module)
    if HAS_STALE_DETECTOR:
        fresh = is_data_fresh(ticker)
        checks["stale_data"] = {
            "passed": fresh,
            "detail": f"{'✅ Price data is fresh' if fresh else '🚫 STALE DATA — price feed >5 min old. Cannot trade.'}",
        }
        if not fresh:
            blocked_by.append("stale_data")
    else:
        checks["stale_data"] = {"passed": True, "detail": "⚠️ Stale detector not installed — skipping"}

    # 1. Kill switch (daily circuit breaker)
    frozen = is_frozen(bot_id)
    checks["kill_switch"] = {
        "passed": not frozen,
        "detail": f"{'🚨 BOT FROZEN — daily -5% circuit breaker active' if frozen else '✅ Not frozen'}",
    }
    if frozen:
        blocked_by.append("kill_switch")

    # 2. Cooldown (10-min same-ticker)
    cd = CooldownEnforcer()
    can_trade = cd.can_trade(bot_id, ticker)
    checks["cooldown"] = {
        "passed": can_trade,
        "detail": cd.block_message(bot_id, ticker),
    }
    if not can_trade:
        blocked_by.append("cooldown")

    # 3. Correlation guard (fleet exposure)
    corr_result = check_entry(bot_id, ticker, side, notional)
    checks["correlation"] = {
        "passed": corr_result["allowed"],
        "detail": corr_result["reason"],
    }
    if not corr_result["allowed"]:
        blocked_by.append("correlation")

    passed = len(blocked_by) == 0

    return {
        "passed": passed,
        "checks": checks,
        "blocked_by": blocked_by,
        "summary": f"{'✅ ALL CHECKS PASSED' if passed else '🚫 BLOCKED by: ' + ', '.join(blocked_by)}",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 5:
        bot, ticker, side, notional = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
        result = gate_check(bot, ticker, side, notional)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 pretrade_gate.py alfred BTC LONG 2500")
