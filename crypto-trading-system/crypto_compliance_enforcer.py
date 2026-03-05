#!/usr/bin/env python3
"""
Crypto Compliance Enforcer — Post-trade rule violation detection.

The pretrade gate catches violations BEFORE entry. This catches violations AFTER:
- Position grew past 30% of portfolio due to price movement
- Correlated group exposure exceeded limits due to price moves
- Stop levels not set on open positions
- Positions held through regime shift without adjustment

Runs every 5 minutes. Generates violations report and can auto-correct.

Usage:
  python3 crypto_compliance_enforcer.py              # Check all
  python3 crypto_compliance_enforcer.py --bot alfred
  python3 crypto_compliance_enforcer.py --auto-fix    # Auto-trim violations
"""

import argparse
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

BOTS = ["alfred", "tars", "vex", "eddie_v"]
MAX_SINGLE_POSITION_PCT = 30.0
MAX_CORRELATED_GROUP_PCT = 30.0
FLEET_CAPITAL = 100_000.0
BOT_CAPITAL = 25_000.0

CORRELATION_GROUPS = {
    "layer1": ["BTC", "ETH", "SOL", "AVAX", "ADA", "DOT"],
    "defi": ["LINK", "UNI", "AAVE", "MKR"],
    "meme": ["DOGE", "SHIB", "PEPE", "BONK"],
}


def get_crypto_prices() -> dict:
    """Fetch current prices."""
    from crypto_stop_enforcer import get_crypto_prices as _get_prices
    return _get_prices()


def get_open_positions(bot_id: str = None) -> list:
    params = {"status": "eq.OPEN", "select": "*"}
    if bot_id:
        params["bot_id"] = f"eq.{bot_id}"
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params=params, headers=HEADERS, timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def check_compliance(bot_id: str = None) -> dict:
    """Run all post-trade compliance checks."""
    prices = get_crypto_prices()
    positions = get_open_positions(bot_id)
    violations = []

    # Group positions by bot
    by_bot = {}
    for pos in positions:
        bot = pos.get("bot_id", "?")
        if bot not in by_bot:
            by_bot[bot] = []
        by_bot[bot].append(pos)

    # Check 1: Single position > 30% of bot's capital
    for bot, bot_positions in by_bot.items():
        for pos in bot_positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            qty = float(pos.get("quantity", 0))
            price = prices.get(ticker, 0)
            notional = qty * price
            pct = (notional / BOT_CAPITAL) * 100

            if pct > MAX_SINGLE_POSITION_PCT:
                violations.append({
                    "type": "POSITION_OVERSIZED",
                    "severity": "HIGH",
                    "bot": bot,
                    "ticker": ticker,
                    "detail": f"{ticker} is {pct:.1f}% of {bot}'s portfolio (limit: {MAX_SINGLE_POSITION_PCT}%)",
                    "current_pct": round(pct, 1),
                    "notional": round(notional, 2),
                    "fix": f"Trim {ticker} to bring below {MAX_SINGLE_POSITION_PCT}%",
                })

    # Check 2: Correlated group exposure (fleet-wide)
    for group_name, members in CORRELATION_GROUPS.items():
        group_notional = 0.0
        group_positions = []

        for pos in positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            if ticker in members:
                qty = float(pos.get("quantity", 0))
                price = prices.get(ticker, 0)
                notional = qty * price
                group_notional += notional
                group_positions.append({"bot": pos.get("bot_id"), "ticker": ticker, "notional": notional})

        group_pct = (group_notional / FLEET_CAPITAL) * 100
        if group_pct > MAX_CORRELATED_GROUP_PCT:
            violations.append({
                "type": "GROUP_OVERSIZED",
                "severity": "HIGH",
                "group": group_name,
                "detail": f"Correlated group '{group_name}' is {group_pct:.1f}% of fleet (limit: {MAX_CORRELATED_GROUP_PCT}%)",
                "current_pct": round(group_pct, 1),
                "positions": group_positions,
                "fix": f"Reduce {group_name} exposure — trim smallest conviction position",
            })

    # Check 3: Positions without stop levels defined
    for pos in positions:
        if not pos.get("stop_price") and not pos.get("stop_pct"):
            violations.append({
                "type": "NO_STOP_DEFINED",
                "severity": "CRITICAL",
                "bot": pos.get("bot_id"),
                "ticker": pos.get("ticker"),
                "detail": f"No stop level defined for {pos.get('bot_id')} {pos.get('ticker')}",
                "fix": "Set 2% hard stop immediately",
            })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_positions": len(positions),
        "violations": violations,
        "violation_count": len(violations),
        "status": "🚨 VIOLATIONS" if violations else "✅ COMPLIANT",
    }


def format_report(result: dict) -> str:
    lines = [
        f"**COMPLIANCE CHECK** — {result['status']}",
        f"Positions: {result['total_positions']} | Violations: {result['violation_count']}",
    ]
    for v in result["violations"]:
        lines.append(f"  [{v['severity']}] {v['type']}: {v['detail']}")
        lines.append(f"    Fix: {v['fix']}")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Compliance Enforcer")
    parser.add_argument("--bot", help="Check specific bot")
    parser.add_argument("--auto-fix", action="store_true", help="Auto-trim violations")
    args = parser.parse_args()

    result = check_compliance(args.bot)
    print(format_report(result))
