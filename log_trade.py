#!/usr/bin/env python3
"""
Universal trade logger for the Mi AI trading competition.
Any bot can use this to log trades directly to Supabase.

Usage:
  python3 log_trade.py --bot tars --action BUY --ticker SPY --qty 10 --price 685.56 --reason "Macro momentum play"
  python3 log_trade.py --bot vex --action SELL --ticker EFA --qty 25 --price 87.50 --reason "Taking profits"

Actions: BUY, SELL, SHORT, COVER
Markets: US, CRYPTO, FOREX, COMMODITY, INTL (auto-detected from ticker)
"""

import argparse
import json
import uuid
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BOT_PREFIXES = {"tars": "TARS", "alfred": "ALF", "vex": "VEX", "eddie_v": "EDV"}

CRYPTO_TICKERS = {"BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "ADA-USD"}
INTL_TICKERS = {"EFA", "EWC", "EWZ", "EWJ", "FXI", "VGK", "INDA"}
COMMODITY_TICKERS = {"GLD", "SLV", "USO", "UNG", "DBA", "WEAT"}


def detect_market(ticker):
    t = ticker.upper()
    if t in CRYPTO_TICKERS or "-USD" in t:
        return "CRYPTO"
    if t in INTL_TICKERS:
        return "INTL"
    if t in COMMODITY_TICKERS:
        return "COMMODITY"
    return "US"


def log_trade(bot_id, action, ticker, qty, price, reason, market=None):
    prefix = BOT_PREFIXES.get(bot_id, bot_id.upper()[:3])
    trade_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    if market is None:
        market = detect_market(ticker)

    trade = {
        "bot_id": bot_id,
        "trade_id": trade_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action.upper(),
        "ticker": ticker.upper(),
        "market": market,
        "quantity": float(qty),
        "price_usd": float(price),
        "total_usd": float(qty) * float(price),
        "reason": reason,
        "status": "OPEN" if action.upper() in ("BUY", "SHORT") else "CLOSED",
    }

    # Insert trade
    r = requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=trade)
    if r.status_code not in (200, 201):
        print(f"ERROR logging trade: {r.status_code} {r.text}")
        return False

    # Update portfolio
    update_portfolio(bot_id, action.upper(), ticker, float(qty), float(price), market)

    print(f"✅ Logged: {bot_id} {action} {qty}x {ticker} @ ${price} (${float(qty)*float(price):.2f})")
    print(f"   Trade ID: {trade_id}")
    return True


def update_portfolio(bot_id, action, ticker, qty, price, market):
    # Fetch current portfolio
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=*",
        headers=HEADERS,
    )
    if not r.json():
        print("WARNING: No portfolio found for", bot_id)
        return

    portfolio = r.json()[0]
    positions = portfolio.get("open_positions", []) or []
    cash = float(portfolio.get("cash_usd", 0))
    trade_count = int(portfolio.get("trade_count", 0))

    if action in ("BUY",):
        cost = qty * price
        cash -= cost
        # Check if position exists
        found = False
        for pos in positions:
            if pos.get("ticker") == ticker:
                old_qty = float(pos.get("quantity", 0))
                old_avg = float(pos.get("avg_entry", 0))
                new_qty = old_qty + qty
                new_avg = ((old_avg * old_qty) + (price * qty)) / new_qty
                pos["quantity"] = new_qty
                pos["avg_entry"] = round(new_avg, 4)
                pos["current_price"] = price
                found = True
                break
        if not found:
            positions.append({
                "ticker": ticker,
                "market": market,
                "quantity": qty,
                "avg_entry": price,
                "current_price": price,
                "unrealized_pl": 0,
                "side": "LONG",
            })

    elif action in ("SELL",):
        proceeds = qty * price
        cash += proceeds
        for pos in positions:
            if pos.get("ticker") == ticker:
                old_qty = float(pos.get("quantity", 0))
                new_qty = old_qty - qty
                if new_qty <= 0:
                    positions.remove(pos)
                else:
                    pos["quantity"] = new_qty
                break

    # Recalculate total value
    position_value = sum(
        float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
        for p in positions
    )
    total_value = cash + position_value

    patch = {
        "cash_usd": round(cash, 2),
        "open_positions": positions,
        "total_value_usd": round(total_value, 2),
        "trade_count": trade_count + 1,
        "total_return_pct": round(((total_value - 25000) / 25000) * 100, 2),
    }

    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}",
        headers=HEADERS,
        json=patch,
    )
    if r.status_code not in (200, 204):
        print(f"WARNING: Portfolio update failed: {r.status_code} {r.text}")
    else:
        print(f"   Portfolio: ${round(cash,2)} cash, ${round(total_value,2)} total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log a trade to the Mi AI dashboard")
    parser.add_argument("--bot", required=True, choices=["tars", "alfred", "vex", "eddie_v"])
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "SHORT", "COVER"])
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--qty", required=True, type=float)
    parser.add_argument("--price", required=True, type=float)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--market", choices=["US", "CRYPTO", "FOREX", "COMMODITY", "INTL"])

    args = parser.parse_args()
    log_trade(args.bot, args.action, args.ticker, args.qty, args.price, args.reason, args.market)
