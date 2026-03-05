#!/usr/bin/env python3
"""Fleet-wide concentration check.
Queries all 4 bot snapshots, checks if any single ticker > 30% of total fund.
If so, alerts to Discord. Run by reconcile_snapshot.py every 30 min.

Usage: python3 fleet_concentration_check.py
"""
import json, os, sys, requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
KEY = None
for path in [os.path.expanduser("~/.supabase_trading_creds"), ".env"]:
    try:
        for line in open(path):
            if "SUPABASE_ANON_KEY" in line or ("SUPABASE_KEY" in line and "ANON" not in line.upper()):
                KEY = line.split("=", 1)[1].strip().strip('"')
                break
    except FileNotFoundError:
        continue
    if KEY:
        break

if not KEY:
    print("ERROR: No Supabase key", file=sys.stderr)
    sys.exit(1)

HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
BOTS = ["alfred", "tars", "vex", "eddie_v"]
MAX_FUND_PCT = 30.0  # 30% max per ticker across entire fund

def check():
    """Check fleet concentration. Returns list of violations."""
    # Gather all positions across all bots
    ticker_totals = {}  # ticker -> total value across fund
    fund_total = 0
    
    for bot in BOTS:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot}&select=total_value_usd,open_positions",
                headers=HEADERS, timeout=10)
            if not r.ok or not r.json():
                continue
            snap = r.json()[0]
            bot_total = snap.get("total_value_usd", 0) or 0
            fund_total += bot_total
            
            positions = snap.get("open_positions", [])
            if not positions:
                continue
            for pos in positions:
                ticker = pos.get("ticker", "")
                qty = pos.get("quantity", 0)
                price = pos.get("current_price", pos.get("avg_entry", 0))
                value = qty * price
                ticker_totals[ticker] = ticker_totals.get(ticker, 0) + value
        except Exception as e:
            print(f"  ⚠️ Failed to read {bot}: {e}")
    
    if fund_total <= 0:
        print("Fund total is $0 — no positions to check")
        return []
    
    violations = []
    print(f"Fleet Fund: ${fund_total:,.0f}")
    print(f"{'Ticker':<12} {'Value':>12} {'Fund %':>8}")
    print("-" * 34)
    
    for ticker, value in sorted(ticker_totals.items(), key=lambda x: -x[1]):
        pct = (value / fund_total) * 100
        flag = " ⚠️ OVER 30%" if pct > MAX_FUND_PCT else ""
        print(f"{ticker:<12} ${value:>10,.0f} {pct:>7.1f}%{flag}")
        if pct > MAX_FUND_PCT:
            violations.append({"ticker": ticker, "value": value, "pct": pct})
    
    return violations

if __name__ == "__main__":
    violations = check()
    if violations:
        print(f"\n🚨 {len(violations)} CONCENTRATION VIOLATIONS:")
        for v in violations:
            print(f"  {v['ticker']}: {v['pct']:.1f}% of fund (${v['value']:,.0f}) — MAX is {MAX_FUND_PCT}%")
        print("ACTION: Smallest holder should trim to bring below 30%")
    else:
        print("\n✅ All tickers within 30% fund-wide limit")
