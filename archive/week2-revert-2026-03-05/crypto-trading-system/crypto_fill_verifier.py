#!/usr/bin/env python3
"""
Crypto Fill Verifier — Cross-references logged trades against portfolio state.

Catches ghost positions (logged but not real) and orphan positions (real but not logged).
Run after every trade cycle or on a 5-min schedule.

Usage:
  python3 crypto_fill_verifier.py              # Check all bots
  python3 crypto_fill_verifier.py --bot alfred  # Check one bot
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


def get_db_positions(bot_id: str) -> dict:
    """Get open positions from Supabase."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={"bot_id": f"eq.{bot_id}", "status": "eq.OPEN", "select": "ticker,quantity,side,avg_entry"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            positions = {}
            for p in r.json():
                ticker = p["ticker"].upper()
                positions[ticker] = {
                    "quantity": float(p["quantity"]),
                    "side": p["side"],
                    "avg_entry": float(p["avg_entry"]),
                }
            return positions
    except Exception:
        pass
    return {}


def get_portfolio_file(bot_id: str) -> dict:
    """Get portfolio from local JSON file."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    filepath = os.path.join(data_dir, f"{bot_id}_crypto.json")
    if os.path.exists(filepath):
        try:
            with open(filepath) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def verify_bot(bot_id: str) -> dict:
    """Verify a bot's positions match between DB and portfolio file."""
    db_positions = get_db_positions(bot_id)
    portfolio = get_portfolio_file(bot_id)

    issues = []

    # Check DB positions exist in portfolio
    for ticker, db_pos in db_positions.items():
        ticker_lower = ticker.lower()
        portfolio_qty = portfolio.get(ticker_lower, 0)

        if isinstance(portfolio_qty, dict):
            portfolio_qty = portfolio_qty.get("quantity", 0)

        if portfolio_qty == 0 and db_pos["quantity"] > 0:
            issues.append({
                "type": "GHOST_POSITION",
                "severity": "HIGH",
                "bot": bot_id,
                "ticker": ticker,
                "detail": f"DB shows {db_pos['quantity']} {ticker} but portfolio file shows 0. Ghost position?",
            })
        elif abs(float(portfolio_qty) - db_pos["quantity"]) > 0.001:
            issues.append({
                "type": "QUANTITY_MISMATCH",
                "severity": "MEDIUM",
                "bot": bot_id,
                "ticker": ticker,
                "detail": f"DB: {db_pos['quantity']} vs Portfolio: {portfolio_qty}",
            })

    # Check portfolio has positions not in DB
    for key, val in portfolio.items():
        if key in ("usd", "updated_at"):
            continue
        ticker = key.upper()
        qty = float(val) if not isinstance(val, dict) else float(val.get("quantity", 0))
        if qty > 0 and ticker not in db_positions:
            issues.append({
                "type": "ORPHAN_POSITION",
                "severity": "HIGH",
                "bot": bot_id,
                "ticker": ticker,
                "detail": f"Portfolio shows {qty} {ticker} but not in DB. Unlogged trade?",
            })

    return {
        "bot": bot_id,
        "db_positions": len(db_positions),
        "portfolio_positions": len([k for k, v in portfolio.items() if k not in ("usd", "updated_at") and (float(v) if not isinstance(v, dict) else float(v.get("quantity", 0))) > 0]),
        "issues": issues,
        "status": "🚨 ISSUES" if issues else "✅ VERIFIED",
    }


def verify_all(bot_id: str = None) -> list:
    bots = [bot_id] if bot_id else BOTS
    results = []
    for bot in bots:
        result = verify_bot(bot)
        results.append(result)
        print(f"{result['status']} {bot}: {len(result['issues'])} issues")
        for issue in result["issues"]:
            print(f"  [{issue['severity']}] {issue['type']}: {issue['detail']}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Fill Verifier")
    parser.add_argument("--bot", help="Check specific bot")
    args = parser.parse_args()
    verify_all(args.bot)
