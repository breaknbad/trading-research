#!/usr/bin/env python3
"""
Crypto Correlation Guard — Prevents overexposure to correlated assets.

BTC/ETH/SOL are 80%+ correlated. Going long all three = one bet with 3x exposure.
This module blocks new entries when fleet-wide correlated exposure exceeds thresholds.

Usage:
  from crypto_correlation_guard import CorrelationGuard
  cg = CorrelationGuard()
  result = cg.check_entry("alfred", "SOL", "LONG", 2500.0)
  if result["allowed"]:
      # proceed
  else:
      print(result["reason"])
"""

import json
import os
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    key_path = os.path.expanduser("~/.supabase_service_key")
    if os.path.exists(key_path):
        SUPABASE_KEY = open(key_path).read().strip()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# ── Correlation Groups ──────────────────────────────────────────────────────
# Assets within the same group are considered highly correlated (>0.7)
# Updated empirically — adjust as correlations shift
CORRELATION_GROUPS = {
    "layer1": ["BTC", "ETH", "SOL", "AVAX", "ADA", "DOT"],  # Major L1s move together
    "defi": ["LINK", "UNI", "AAVE", "MKR"],
    "meme": ["DOGE", "SHIB", "PEPE", "BONK"],
}

# ── Thresholds ──────────────────────────────────────────────────────────────
MAX_CORRELATED_EXPOSURE_PCT = 30.0    # Max 30% of fleet capital in one correlation group
MAX_SAME_ASSET_BOTS = 3              # Max 3 bots in the same asset
FLEET_CAPITAL = 100_000.0            # 4 bots × $25K (adjust if changed)
BOTS = ["alfred", "tars", "vex", "eddie_v"]


def get_ticker_group(ticker: str) -> str:
    """Find which correlation group a ticker belongs to."""
    ticker = ticker.upper().replace("USDT", "").replace("USD", "")
    for group_name, members in CORRELATION_GROUPS.items():
        if ticker in members:
            return group_name
    return "uncorrelated"


def get_all_open_positions() -> list:
    """Fetch all open crypto positions across all bots."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={"status": "eq.OPEN", "select": "*"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def check_entry(bot_id: str, ticker: str, side: str, notional: float) -> dict:
    """
    Check if a new entry is allowed given fleet-wide correlation exposure.
    
    Returns: {"allowed": bool, "reason": str, "group": str, "exposure_pct": float}
    """
    ticker = ticker.upper().replace("USDT", "").replace("USD", "")
    group = get_ticker_group(ticker)

    positions = get_all_open_positions()

    # Check 1: Same asset across fleet
    same_asset_bots = set()
    for pos in positions:
        pos_ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
        if pos_ticker == ticker:
            same_asset_bots.add(pos.get("bot_id", ""))

    if len(same_asset_bots) >= MAX_SAME_ASSET_BOTS and bot_id not in same_asset_bots:
        return {
            "allowed": False,
            "reason": f"🚫 {MAX_SAME_ASSET_BOTS} bots already hold {ticker}. "
                      f"Fleet concentration limit reached.",
            "group": group,
            "bots_in_asset": list(same_asset_bots),
        }

    # Check 2: Correlation group exposure
    if group != "uncorrelated":
        group_members = CORRELATION_GROUPS.get(group, [])
        group_exposure = 0.0

        for pos in positions:
            pos_ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            if pos_ticker in group_members:
                pos_notional = abs(float(pos.get("quantity", 0)) * float(pos.get("avg_entry", 0)))
                group_exposure += pos_notional

        new_total = group_exposure + notional
        exposure_pct = (new_total / FLEET_CAPITAL) * 100

        if exposure_pct > MAX_CORRELATED_EXPOSURE_PCT:
            return {
                "allowed": False,
                "reason": f"🚫 Correlated group '{group}' exposure would be "
                          f"{exposure_pct:.1f}% (>${MAX_CORRELATED_EXPOSURE_PCT}%). "
                          f"Current: ${group_exposure:,.0f} + new ${notional:,.0f}.",
                "group": group,
                "exposure_pct": exposure_pct,
            }

        return {
            "allowed": True,
            "reason": f"✅ {ticker} ({group}) — fleet exposure {exposure_pct:.1f}% within limits.",
            "group": group,
            "exposure_pct": exposure_pct,
        }

    return {
        "allowed": True,
        "reason": f"✅ {ticker} — uncorrelated asset, no group limits.",
        "group": group,
        "exposure_pct": 0.0,
    }


def fleet_exposure_report() -> dict:
    """Generate a full fleet correlation exposure report."""
    positions = get_all_open_positions()
    report = {}

    for group_name, members in CORRELATION_GROUPS.items():
        group_exposure = 0.0
        group_positions = []

        for pos in positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            if ticker in members:
                notional = abs(float(pos.get("quantity", 0)) * float(pos.get("avg_entry", 0)))
                group_exposure += notional
                group_positions.append({
                    "bot": pos.get("bot_id"),
                    "ticker": ticker,
                    "notional": notional,
                })

        report[group_name] = {
            "exposure": group_exposure,
            "exposure_pct": (group_exposure / FLEET_CAPITAL) * 100,
            "positions": group_positions,
            "limit_pct": MAX_CORRELATED_EXPOSURE_PCT,
            "status": "🚨 OVER" if (group_exposure / FLEET_CAPITAL) * 100 > MAX_CORRELATED_EXPOSURE_PCT else "✅ OK",
        }

    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 5 and sys.argv[1] == "check":
        bot, ticker, side, notional = sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
        result = check_entry(bot, ticker, side, notional)
        print(json.dumps(result, indent=2))
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        report = fleet_exposure_report()
        print(json.dumps(report, indent=2))
    else:
        print("Usage:")
        print("  python3 crypto_correlation_guard.py check alfred BTC LONG 2500")
        print("  python3 crypto_correlation_guard.py report")
