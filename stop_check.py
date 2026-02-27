#!/usr/bin/env python3
"""
Fast Stop-Loss Checker — runs every 1 minute during market hours.
Checks all open positions against their 2% stop threshold.
Auto-executes SELL/COVER if stop is breached. No asking, no delay.

Usage:
  python3 stop_check.py          # Check all bots
  python3 stop_check.py --bot alfred  # Check one bot
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

STOP_PCT = 2.0  # 2% stop-loss threshold
TARGET_PCT = 5.0  # 5% profit target — auto-take profits
BOTS = ["alfred", "tars", "vex", "eddie_v"]

# Yahoo Finance price fetch (lightweight)
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


def check_stops(bot_id=None):
    """Check all positions for stop-loss breaches."""
    bots_to_check = [bot_id] if bot_id else BOTS
    stops_hit = []

    for bot in bots_to_check:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
            params={"bot_id": f"eq.{bot}", "select": "open_positions,cash_usd"},
            headers=HEADERS,
        )
        if r.status_code != 200 or not r.json():
            continue

        positions = r.json()[0].get("open_positions", []) or []

        for pos in positions:
            ticker = pos.get("ticker", "")
            entry = float(pos.get("avg_entry", 0))
            qty = float(pos.get("quantity", 0))
            side = pos.get("side", "LONG")

            if entry <= 0 or qty <= 0:
                continue

            current = get_price(ticker)
            if current is None:
                continue

            # Calculate drawdown based on side
            if side == "LONG":
                drawdown_pct = ((entry - current) / entry) * 100
            else:  # SHORT
                drawdown_pct = ((current - entry) / entry) * 100

            # TARGET CHECK: 5%+ gain = take profits (20-sec rule)
            if side == "LONG":
                gain_pct = ((current - entry) / entry) * 100
            else:
                gain_pct = ((entry - current) / entry) * 100

            if gain_pct >= TARGET_PCT:
                action = "SELL" if side == "LONG" else "COVER"
                print(f"🎯 TARGET HIT: {bot} {side} {ticker} — entry ${entry:.2f}, now ${current:.2f}, gain {gain_pct:.1f}%")
                try:
                    from log_trade import log_trade
                    success = log_trade(
                        bot, action, ticker, qty, current,
                        f"TARGET AUTO-EXIT: {gain_pct:.1f}% gain (threshold {TARGET_PCT}%)"
                    )
                    if success:
                        print(f"   ✅ Auto-executed: {action} {qty}x {ticker} @ ${current:.2f}")
                        stops_hit.append({"bot": bot, "ticker": ticker, "action": action, "price": current, "gain": gain_pct})
                    else:
                        print(f"   ❌ Auto-execute failed for {ticker}")
                except Exception as e:
                    print(f"   ❌ Error executing target exit: {e}")
                continue  # Don't also check stop on same position

            if drawdown_pct >= STOP_PCT:
                action = "SELL" if side == "LONG" else "COVER"
                print(f"🚨 STOP HIT: {bot} {side} {ticker} — entry ${entry:.2f}, now ${current:.2f}, drawdown {drawdown_pct:.1f}%")

                # Auto-execute via log_trade
                try:
                    from log_trade import log_trade
                    success = log_trade(
                        bot, action, ticker, qty, current,
                        f"STOP-LOSS AUTO-EXIT: {drawdown_pct:.1f}% drawdown (threshold {STOP_PCT}%)"
                    )
                    if success:
                        print(f"   ✅ Auto-executed: {action} {qty}x {ticker} @ ${current:.2f}")
                        stops_hit.append({"bot": bot, "ticker": ticker, "action": action, "price": current, "drawdown": drawdown_pct})
                    else:
                        print(f"   ❌ Auto-execute failed for {ticker}")
                except Exception as e:
                    print(f"   ❌ Error executing stop: {e}")
            elif drawdown_pct >= STOP_PCT * 0.75:
                print(f"⚠️  NEAR STOP: {bot} {side} {ticker} — {drawdown_pct:.1f}% drawdown (stop at {STOP_PCT}%)")

    if not stops_hit:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"✅ {now} UTC — No stops breached across {len(bots_to_check)} bot(s)")

    return stops_hit


def is_market_hours():
    """Check if within US market hours (9:30 AM - 4:00 PM ET)."""
    from datetime import timedelta
    # ET = UTC-5 (EST) or UTC-4 (EDT). Approximate with UTC-5 for now.
    now_utc = datetime.now(timezone.utc)
    et_offset = timezone(timedelta(hours=-5))
    now_et = now_utc.astimezone(et_offset)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now_et.weekday()
    return weekday < 5 and market_open <= now_et <= market_close


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast stop-loss checker")
    parser.add_argument("--bot", choices=BOTS, help="Check specific bot only")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()

    if not args.force and not is_market_hours():
        print("Market closed. Use --force to run anyway.")
        sys.exit(0)

    check_stops(args.bot)
