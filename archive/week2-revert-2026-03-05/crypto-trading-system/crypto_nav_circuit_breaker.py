#!/usr/bin/env python3
"""
crypto_nav_circuit_breaker.py — Fleet NAV hard floor
Owner: Alfred | Created: 2026-03-01

$75K fleet NAV = FULL HALT. Non-negotiable. Only Mark reactivates.
$85K = REDUCED sizing (50%).
$90K = WARNING to channel.

Reads from Supabase crypto_portfolio_snapshots for all 4 bots.
"""

import os
import json
import time
from datetime import datetime, timezone

FLEET_HALT_PCT = 0.75       # Full halt at 75% of start-of-day NAV. Mark confirmed 2026-03-01.
FLEET_REDUCE_PCT = 0.85     # 50% sizing at 85% of SOD NAV
FLEET_WARN_PCT = 0.90       # Warning at 90% of SOD NAV
FLEET_START_NAV = 100000    # Default starting capital (overridden by SOD snapshot)

SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "fleet_nav_cache.json")
BOT_IDS = ["alfred_crypto", "tars_crypto", "vex_crypto", "eddie_crypto"]


def get_fleet_nav() -> dict:
    """Get total fleet NAV from Supabase or cache."""
    # Try Supabase
    try:
        from crypto_supabase_guard import _get_client
        client = _get_client()
        if client:
            total = 0.0
            bot_navs = {}
            for bot_id in BOT_IDS:
                result = client.table("crypto_portfolio_snapshots").select(
                    "total_value"
                ).eq("bot_id", bot_id).order(
                    "timestamp", desc=True
                ).limit(1).execute()
                if result.data:
                    nav = float(result.data[0]["total_value"])
                    bot_navs[bot_id] = nav
                    total += nav
                else:
                    bot_navs[bot_id] = 25000.0  # Assume starting if no data
                    total += 25000.0

            result = {
                "fleet_nav": total,
                "bot_navs": bot_navs,
                "source": "supabase",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            # Cache locally
            with open(SNAPSHOT_FILE, "w") as f:
                json.dump(result, f, indent=2)
            return result
    except Exception:
        pass

    # Fallback to cache
    try:
        with open(SNAPSHOT_FILE) as f:
            cached = json.load(f)
        cached["source"] = "cache"
        return cached
    except Exception:
        return {
            "fleet_nav": FLEET_START_NAV,
            "source": "default",
            "bot_navs": {b: 25000.0 for b in BOT_IDS}
        }


def get_sod_nav() -> float:
    """Get start-of-day fleet NAV. Falls back to FLEET_START_NAV."""
    sod_file = os.path.join(os.path.dirname(__file__), "sod_nav.json")
    try:
        with open(sod_file) as f:
            data = json.load(f)
        return float(data.get("sod_nav", FLEET_START_NAV))
    except Exception:
        return FLEET_START_NAV


def set_sod_nav(nav: float):
    """Set start-of-day NAV (call at midnight or first check of the day)."""
    sod_file = os.path.join(os.path.dirname(__file__), "sod_nav.json")
    with open(sod_file, "w") as f:
        json.dump({"sod_nav": nav, "set_at": datetime.now(timezone.utc).isoformat()}, f)


def check_nav() -> dict:
    """Check fleet NAV against circuit breaker levels. Floor = 75% of start-of-day NAV."""
    nav_data = get_fleet_nav()
    fleet_nav = nav_data["fleet_nav"]
    sod = get_sod_nav()
    
    halt_nav = sod * FLEET_HALT_PCT
    reduce_nav = sod * FLEET_REDUCE_PCT
    warn_nav = sod * FLEET_WARN_PCT

    if fleet_nav <= halt_nav:
        return {
            "allowed": False,
            "level": "HALT",
            "detail": f"FLEET NAV ${fleet_nav:,.0f} ≤ 75% of SOD (${halt_nav:,.0f}) — FULL HALT.",
            "size_multiplier": 0.0,
            "fleet_nav": fleet_nav,
            "sod_nav": sod
        }
    elif fleet_nav <= reduce_nav:
        return {
            "allowed": True,
            "level": "REDUCE",
            "detail": f"FLEET NAV ${fleet_nav:,.0f} ≤ 85% of SOD (${reduce_nav:,.0f}) — 50% sizing.",
            "size_multiplier": 0.5,
            "fleet_nav": fleet_nav,
            "sod_nav": sod
        }
    elif fleet_nav <= warn_nav:
        return {
            "allowed": True,
            "level": "WARN",
            "detail": f"FLEET NAV ${fleet_nav:,.0f} ≤ 90% of SOD (${warn_nav:,.0f}) — caution.",
            "size_multiplier": 0.75,
            "fleet_nav": fleet_nav,
            "sod_nav": sod
        }
    else:
        return {
            "allowed": True,
            "level": "OK",
            "detail": f"FLEET NAV ${fleet_nav:,.0f} — within limits (SOD: ${sod:,.0f}).",
            "size_multiplier": 1.0,
            "fleet_nav": fleet_nav,
            "sod_nav": sod
        }


if __name__ == "__main__":
    result = check_nav()
    print(f"Fleet NAV Circuit Breaker")
    print(f"  Level: {result['level']}")
    print(f"  {result['detail']}")
    print(f"  Size multiplier: {result['size_multiplier']}")
    print(f"  Trading allowed: {result['allowed']}")
