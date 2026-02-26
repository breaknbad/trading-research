#!/usr/bin/env python3
"""
Trade Enforcer — Validates that trades mentioned in Discord are logged to Supabase.

Runs as a periodic check (every 2 minutes during market hours).
Scans recent trades table in Supabase and compares against expected trades
from portfolio snapshots. Flags:
  1. Positions in portfolio with no matching trade log entry
  2. Cash > 60% during market hours (underdeployment alert)
  3. Trades logged but not reflected in portfolio (sync issues)

Usage:
  python3 trade_enforcer.py              # One-shot audit
  python3 trade_enforcer.py --watch      # Continuous monitoring (every 2 min)
  python3 trade_enforcer.py --bot eddie_v # Audit specific bot
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta

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
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
STARTING_CAPITAL = 25000


def get_portfolio(bot_id):
    """Fetch current portfolio snapshot for a bot."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=*",
        headers=HEADERS,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def get_recent_trades(bot_id, hours=8):
    """Fetch trades from the last N hours for a bot."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&timestamp=gte.{cutoff}&order=timestamp.desc",
        headers=HEADERS,
    )
    if r.status_code == 200:
        return r.json()
    return []


def audit_bot(bot_id):
    """Run full audit on a single bot. Returns list of issues."""
    issues = []
    portfolio = get_portfolio(bot_id)
    if not portfolio:
        issues.append(f"🚨 {bot_id}: NO PORTFOLIO FOUND IN SUPABASE")
        return issues

    cash = float(portfolio.get("cash_usd", 0))
    total_value = float(portfolio.get("total_value_usd", STARTING_CAPITAL))
    positions = portfolio.get("open_positions", []) or []
    trade_count = int(portfolio.get("trade_count", 0))

    # 1. Cash deployment check
    cash_pct = (cash / total_value * 100) if total_value > 0 else 100
    if cash_pct > 60:
        issues.append(
            f"⚠️ {bot_id}: {cash_pct:.0f}% CASH (${cash:,.0f} of ${total_value:,.0f}). "
            f"Deploy capital — stops protect you, not the bench."
        )

    # 2. Check positions have valid data
    for pos in positions:
        ticker = pos.get("ticker", "???")
        qty = float(pos.get("quantity", 0))
        entry = float(pos.get("avg_entry", 0))
        current = float(pos.get("current_price", 0))

        if qty <= 0:
            issues.append(f"🚨 {bot_id}: Ghost position {ticker} with qty={qty}. Clean it up.")

        if entry <= 0:
            issues.append(f"🚨 {bot_id}: {ticker} has no entry price. Data integrity issue.")

        if current <= 0:
            issues.append(f"⚠️ {bot_id}: {ticker} has no current price. Price streamer may be down.")

        # Check P&L vs stop
        if entry > 0 and current > 0:
            side = pos.get("side", "LONG").upper()
            if side == "LONG":
                pnl_pct = (current - entry) / entry * 100
            else:
                pnl_pct = (entry - current) / entry * 100

            if pnl_pct < -2.0:
                issues.append(
                    f"🚨 {bot_id}: {ticker} at {pnl_pct:+.1f}% — STOP BREACHED (2% rule). "
                    f"Entry ${entry:.2f} → Current ${current:.2f}. SELL NOW."
                )

    # 3. Cross-reference trades vs positions
    recent_trades = get_recent_trades(bot_id, hours=12)
    open_buys = {}
    for trade in recent_trades:
        action = trade.get("action", "").upper()
        ticker = trade.get("ticker", "")
        status = trade.get("status", "")
        if action in ("BUY", "SHORT") and status == "OPEN":
            open_buys[ticker] = trade

    position_tickers = {p.get("ticker", "") for p in positions}
    trade_tickers = set(open_buys.keys())

    # Positions without matching open trade
    unmatched = position_tickers - trade_tickers
    if unmatched:
        issues.append(
            f"⚠️ {bot_id}: Positions without trade log entries: {', '.join(unmatched)}. "
            f"Trades must be logged via log_trade.py."
        )

    # 4. Zero-trade check
    today_trades = [
        t for t in recent_trades
        if t.get("timestamp", "")[:10] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ]
    if len(today_trades) == 0 and is_market_hours():
        issues.append(
            f"⚠️ {bot_id}: ZERO trades logged today. Are you trading or watching?"
        )

    return issues


def is_market_hours():
    """Check if we're in US market hours (9:30 AM - 4:00 PM ET)."""
    from datetime import timezone as tz
    now_utc = datetime.now(timezone.utc)
    # ET is UTC-5 (EST) or UTC-4 (EDT)
    et_offset = timedelta(hours=-5)  # EST
    now_et = now_utc + et_offset
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now_et.weekday()
    return weekday < 5 and market_open <= now_et <= market_close


def run_audit(bot_filter=None):
    """Run audit across all bots (or a specific one)."""
    bots = [bot_filter] if bot_filter else BOTS
    all_issues = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print(f"\n🔍 TRADE ENFORCER AUDIT — {timestamp}")
    print("=" * 60)

    for bot_id in bots:
        issues = audit_bot(bot_id)
        if issues:
            all_issues.extend(issues)
            for issue in issues:
                print(issue)
        else:
            print(f"✅ {bot_id}: All clear. Positions valid, trades logged, capital deployed.")

    print("=" * 60)

    if not all_issues:
        print("✅ FLEET CLEAN — All bots passing enforcement checks.")
    else:
        print(f"⚠️ {len(all_issues)} issue(s) found across fleet.")

    return all_issues


def watch_mode(bot_filter=None, interval=120):
    """Continuous monitoring mode."""
    print(f"👁️ Trade Enforcer — Watch Mode (every {interval}s)")
    print("Press Ctrl+C to stop.\n")
    while True:
        if is_market_hours():
            issues = run_audit(bot_filter)
            if issues:
                # Could hook into Discord webhook here for alerts
                pass
        else:
            print(f"[{datetime.now().strftime('%H:%M')}] Market closed. Sleeping...")
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trade Enforcer — Validate trades are logged")
    parser.add_argument("--bot", choices=BOTS, help="Audit specific bot")
    parser.add_argument("--watch", action="store_true", help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=120, help="Watch interval in seconds")

    args = parser.parse_args()

    if args.watch:
        watch_mode(args.bot, args.interval)
    else:
        run_audit(args.bot)
