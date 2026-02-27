#!/usr/bin/env python3
"""
Signal Router — Routes CONFIRM+ signals to the bot with the most cash.

When any bot posts a CONFIRM or CONVICTION signal but can't act (low cash),
this script finds the bot with the most dry powder and executes the trade
through the full pipeline (log_trade.py with all guards).

Also: if ANY bot has >40% cash and a CONFIRM+ signal exists on the bus,
auto-sizes and executes. No freezing. No asking.

Usage:
  python3 signal_router.py                    # Check bus + deploy
  python3 signal_router.py --signal "SLV CONFIRM 85.00"  # Manual signal inject
  python3 signal_router.py --check-cash       # Just show who has cash

Runs as a cron every 5 min during market hours.
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone, timedelta

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
MAX_POSITION_PCT = 0.10  # 10% max per position
CASH_THRESHOLD_PCT = 0.40  # Flag if >40% cash
PORTFOLIO_BASE = 25000


def get_portfolios():
    """Fetch all bot portfolios."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
        params={"select": "bot_id,cash_usd,total_value_usd,open_positions"},
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )
    if r.status_code != 200:
        print(f"ERROR fetching portfolios: {r.status_code}")
        return {}
    
    portfolios = {}
    for p in r.json():
        bot = p.get("bot_id")
        cash = float(p.get("cash_usd", 0))
        total = float(p.get("total_value_usd", PORTFOLIO_BASE))
        positions = p.get("open_positions", []) or []
        
        # Calculate cash percentage (for shorts, use total_value as base)
        cash_pct = (cash / total * 100) if total > 0 else 0
        
        # Get list of tickers already held
        held_tickers = set()
        for pos in positions:
            held_tickers.add(pos.get("ticker", "").upper())
        
        portfolios[bot] = {
            "cash": cash,
            "total": total,
            "cash_pct": cash_pct,
            "positions": positions,
            "held_tickers": held_tickers,
            "position_count": len(positions),
        }
    
    return portfolios


def get_price(ticker):
    """Get current price from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            return float(meta.get("regularMarketPrice", 0))
    except Exception:
        pass
    return None


def find_best_deployer(portfolios, ticker):
    """Find the bot with the most cash that doesn't already hold this ticker."""
    candidates = []
    for bot, info in portfolios.items():
        if ticker.upper() not in info["held_tickers"] and info["cash"] > 500:
            candidates.append((bot, info["cash"], info["cash_pct"]))
    
    # Sort by cash descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def size_position(cash, total, price, conviction="CONFIRM"):
    """Size a position based on conviction tier and available capital."""
    if conviction == "CONVICTION":
        target_pct = 0.08  # 8% of portfolio
    elif conviction == "CONFIRM":
        target_pct = 0.05  # 5% of portfolio
    else:  # SCOUT
        target_pct = 0.03  # 3% of portfolio
    
    # Don't exceed 10% max position rule
    target_pct = min(target_pct, MAX_POSITION_PCT)
    
    # Target dollar amount
    target_dollars = total * target_pct
    
    # Don't use more than 25% of remaining cash on one trade
    max_from_cash = cash * 0.25
    target_dollars = min(target_dollars, max_from_cash)
    
    # Calculate shares (round down)
    if price <= 0:
        return 0
    shares = int(target_dollars / price)
    
    return max(shares, 0)


def route_signal(ticker, conviction="CONFIRM", side="BUY", reason="Signal bus routing"):
    """Route a signal to the best available bot and execute."""
    price = get_price(ticker)
    if not price:
        print(f"❌ Could not get price for {ticker}")
        return False
    
    portfolios = get_portfolios()
    if not portfolios:
        print("❌ Could not fetch portfolios")
        return False
    
    candidates = find_best_deployer(portfolios, ticker)
    if not candidates:
        print(f"⚠️  No bot available to trade {ticker} (all holding or no cash)")
        return False
    
    # Pick the bot with the most cash
    best_bot, best_cash, best_cash_pct = candidates[0]
    best_info = portfolios[best_bot]
    
    # Size the position
    qty = size_position(best_cash, best_info["total"], price, conviction)
    if qty <= 0:
        print(f"⚠️  Position too small for {best_bot} on {ticker} @ ${price:.2f}")
        return False
    
    print(f"🎯 ROUTING: {ticker} {conviction} → {best_bot} (${best_cash:.0f} cash, {best_cash_pct:.0f}%)")
    print(f"   {side} {qty}x {ticker} @ ${price:.2f} = ${qty * price:.2f}")
    
    # Execute through log_trade (which has dedup + rate limit guards)
    try:
        from log_trade import log_trade
        success = log_trade(
            best_bot, side, ticker, qty, price,
            f"SIGNAL ROUTER: {conviction} signal, routed from bus. {reason}"
        )
        if success:
            print(f"   ✅ Executed: {best_bot} {side} {qty}x {ticker} @ ${price:.2f}")
            return True
        else:
            print(f"   ❌ Trade rejected by guards (dedup/rate limit/validation)")
            return False
    except Exception as e:
        print(f"   ❌ Execution error: {e}")
        return False


def check_cash_deployment(portfolios=None):
    """Check if any bot has too much cash and should be deploying."""
    if portfolios is None:
        portfolios = get_portfolios()
    
    idle_bots = []
    for bot, info in portfolios.items():
        if info["cash_pct"] > CASH_THRESHOLD_PCT * 100:
            idle_bots.append((bot, info["cash"], info["cash_pct"]))
            print(f"💰 {bot}: ${info['cash']:.0f} cash ({info['cash_pct']:.0f}%) — needs deployment")
    
    return idle_bots


def is_market_hours():
    """Check if within US market hours."""
    now_utc = datetime.now(timezone.utc)
    et_offset = timezone(timedelta(hours=-5))
    now_et = now_utc.astimezone(et_offset)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return now_et.weekday() < 5 and market_open <= now_et <= market_close


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Signal Router — routes signals to capital")
    parser.add_argument("--signal", help="Manual signal: 'TICKER TIER PRICE' e.g. 'SLV CONFIRM 85.00'")
    parser.add_argument("--check-cash", action="store_true", help="Show cash deployment status")
    parser.add_argument("--force", action="store_true", help="Run outside market hours")
    args = parser.parse_args()

    if not args.force and not is_market_hours():
        print("Market closed. Use --force to run anyway.")
        sys.exit(0)

    if args.check_cash:
        check_cash_deployment()
    elif args.signal:
        parts = args.signal.split()
        if len(parts) >= 2:
            ticker = parts[0]
            conviction = parts[1] if len(parts) > 1 else "CONFIRM"
            route_signal(ticker, conviction)
        else:
            print("Usage: --signal 'TICKER TIER' e.g. 'SLV CONFIRM'")
    else:
        # Default: check cash deployment status
        portfolios = get_portfolios()
        idle = check_cash_deployment(portfolios)
        if idle:
            print(f"\n{len(idle)} bot(s) with excess cash. Route CONFIRM+ signals to them.")
