#!/usr/bin/env python3
"""
eod_sweep.py — Pre-close auto-sell for leveraged/inverse ETFs.

At 3:45 PM ET, scans all bot portfolios for leveraged/inverse ETFs and
auto-generates SELL orders via log_trade.py. No exceptions.

Leveraged/Inverse ETF list:
  SQQQ, TQQQ, SOXL, SOXS, UVXY, SVXY, SPXU, UPRO, QLD, QID,
  TNA, TZA, LABU, LABD, and any 2x/3x ETF.

Designed to run as a cron job at 3:45 PM ET Mon-Fri:
  45 15 * * 1-5 cd /path/to/trading-research && python3 eod_sweep.py

Usage:
  python3 eod_sweep.py              # Sweep all bots
  python3 eod_sweep.py --bot tars   # Sweep specific bot
  python3 eod_sweep.py --dry-run    # Show what would be sold
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

from log_trade import log_trade

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]

# Known leveraged/inverse ETFs — NO OVERNIGHT HOLDS
LEVERAGED_ETFS = {
    # 3x Bull
    "TQQQ", "SOXL", "UPRO", "TNA", "LABU", "FNGU", "TECL", "FAS",
    "NAIL", "DPST", "MIDU", "DFEN", "DUSL", "WANT", "CURE",
    # 3x Bear
    "SQQQ", "SOXS", "SPXU", "TZA", "LABD", "FNGD", "TECS", "FAZ",
    "DRV", "DPST", "SMDD", "WEBS", "YANG",
    # 2x Bull
    "QLD", "SSO", "UWM", "ROM", "UYG", "UGE",
    # 2x Bear
    "QID", "SDS", "TWM", "REK", "SKF", "SRS",
    # Volatility
    "UVXY", "SVXY", "VXX", "VIXY", "SVOL",
}


def is_leveraged_etf(ticker: str) -> bool:
    """Check if a ticker is a known leveraged/inverse ETF."""
    return ticker.upper() in LEVERAGED_ETFS


def get_portfolios(bot_filter=None):
    url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?select=*"
    if bot_filter:
        url += f"&bot_id=eq.{bot_filter}"
    r = requests.get(url, headers=HEADERS)
    return r.json() if r.status_code == 200 else []


def eod_sweep(bot_filter=None, dry_run=False) -> list:
    """
    Scan all portfolios and sell any leveraged/inverse ETF positions.

    Returns list of sells executed.
    """
    sells = []
    portfolios = get_portfolios(bot_filter)

    for portfolio in portfolios:
        bot_id = portfolio.get("bot_id")
        positions = portfolio.get("open_positions", []) or []

        for pos in positions:
            ticker = pos.get("ticker", "").upper()
            qty = float(pos.get("quantity", 0))
            current_price = float(pos.get("current_price", pos.get("avg_entry", 0)))
            side = pos.get("side", "LONG")

            if not is_leveraged_etf(ticker):
                continue

            if qty <= 0:
                continue

            action = "SELL" if side == "LONG" else "COVER"
            reason = f"EOD sweep: {ticker} is leveraged/inverse ETF — no overnight holds"

            print(f"🔴 {bot_id}: {action} {qty}x {ticker} @ ${current_price:.2f} — {reason}")

            if not dry_run:
                log_trade(bot_id, action, ticker, qty, current_price, reason)

            sells.append({
                "bot_id": bot_id,
                "ticker": ticker,
                "action": action,
                "quantity": qty,
                "price": current_price,
            })

    return sells


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EOD sweep — sell leveraged/inverse ETFs before close")
    parser.add_argument("--bot", choices=BOTS, help="Sweep specific bot")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sold")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")

    args = parser.parse_args()

    # Time check (unless forced)
    if not args.force:
        now_utc = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-5)
        now_et = now_utc + et_offset
        if now_et.weekday() >= 5:
            print("Weekend — no sweep needed.")
            sys.exit(0)

    print(f"\n🧹 EOD Sweep — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    sells = eod_sweep(args.bot, args.dry_run)
    if sells:
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Swept {len(sells)} leveraged/inverse position(s).")
    else:
        print("No leveraged/inverse ETFs found in any portfolio. Clean.")
    print("=" * 60)
