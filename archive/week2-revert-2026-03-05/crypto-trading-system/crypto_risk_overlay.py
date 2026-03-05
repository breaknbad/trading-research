#!/usr/bin/env python3
"""
Risk Overlay for Crypto Scans — Attaches risk context to every scan output.

Shows what's tradeable RIGHT NOW without running the full gate:
  BTC: GATE ✅ 1.0x | ETH: GATE ⚠️ 0.5x (corr) | DOGE: GATE 🚫 (tilt+cooldown)

Also pre-computes gate results for top 10 coins and caches them.
When a signal fires, the gate result is already there — zero latency.

Usage:
  from crypto_risk_overlay import get_overlay, get_cached_gate
  overlay = get_overlay("alfred")         # Full overlay for a bot
  gate = get_cached_gate("alfred", "BTC") # Pre-computed gate result
"""

import json
import os
import time
from datetime import datetime, timezone

CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "gate_cache.json")

TOP_COINS = ["BTC", "ETH", "SOL", "AVAX", "ADA", "DOT", "LINK", "DOGE", "XRP", "SHIB"]


def _load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
                # Cache valid for 5 minutes
                if time.time() - data.get("timestamp", 0) < 300:
                    return data
        except Exception:
            pass
    return {}


def _save_cache(data: dict):
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    data["timestamp"] = time.time()
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def precompute_gates(bot_id: str) -> dict:
    """Pre-compute gate results for top 10 coins. Cache for instant lookup."""
    try:
        from pretrade_gate_v2 import gate_check
    except ImportError:
        return {"error": "pretrade_gate_v2 not available"}

    results = {}
    for ticker in TOP_COINS:
        try:
            result = gate_check(bot_id, ticker, "LONG", 2500)
            results[ticker] = {
                "action": result["action"],
                "size_multiplier": result["size_multiplier"],
                "fails": result["total_fails"],
                "blocked_by": result["hard_blocks"] + result["soft_fails"],
            }
        except Exception as e:
            results[ticker] = {"action": "ERROR", "error": str(e)}

    cache = {"bot": bot_id, "gates": results}
    _save_cache(cache)
    return results


def get_cached_gate(bot_id: str, ticker: str) -> dict:
    """Get pre-computed gate result. Returns cached or computes fresh."""
    cache = _load_cache()
    if cache.get("bot") == bot_id and ticker in cache.get("gates", {}):
        return cache["gates"][ticker]
    # Cache miss — compute fresh
    gates = precompute_gates(bot_id)
    return gates.get(ticker, {"action": "UNKNOWN"})


def get_overlay(bot_id: str) -> dict:
    """Generate full risk overlay for a bot."""
    gates = precompute_gates(bot_id)

    # Build overlay lines
    lines = []
    for ticker in TOP_COINS:
        gate = gates.get(ticker, {})
        action = gate.get("action", "?")
        mult = gate.get("size_multiplier", 0)
        blocked = gate.get("blocked_by", [])

        if action == "PASS":
            icon = "✅"
            detail = f"{mult}x"
        elif action == "WARN":
            icon = "⚠️"
            detail = f"{mult}x ({', '.join(blocked)})"
        elif action == "REDUCE":
            icon = "⚠️"
            detail = f"{mult}x ({', '.join(blocked)})"
        else:
            icon = "🚫"
            detail = f"({', '.join(blocked)})" if blocked else "BLOCKED"

        lines.append(f"{ticker}: GATE {icon} {detail}")

    # Get fleet-level stats
    try:
        from crypto_fleet_var import FleetVaR
        fv = FleetVaR()
        var_result = fv.calculate()
        var_status = "🟢" if var_result["within_limit"] else "🔴"
        var_line = f"Fleet VaR: {var_status} ${var_result['portfolio_var_95']:,.0f} / ${var_result['var_limit']:,.0f}"
    except Exception:
        var_line = "Fleet VaR: unavailable"

    try:
        from crypto_drawdown_throttle import DrawdownThrottle
        dt = DrawdownThrottle(bot_id)
        dd = dt.get_risk_multiplier()
        dd_line = f"Drawdown throttle: {dd['tier']} ({dd['multiplier']}x)"
    except Exception:
        dd_line = "Drawdown throttle: unavailable"

    return {
        "bot": bot_id,
        "overlay_lines": lines,
        "overlay_text": " | ".join(lines),
        "fleet_var": var_line,
        "drawdown": dd_line,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


def format_overlay(bot_id: str) -> str:
    """Format overlay as Discord-friendly text."""
    overlay = get_overlay(bot_id)
    lines = [f"**🎩 Risk Overlay ({bot_id})**"]
    lines.extend(overlay["overlay_lines"])
    lines.append(overlay["fleet_var"])
    lines.append(overlay["drawdown"])
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    print(format_overlay(bot))
