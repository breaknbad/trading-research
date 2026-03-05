#!/usr/bin/env python3
"""
Intraday Momentum Scanner v2 — 50+ Ticker Weakest Link Rotation Engine
Scans top crypto by short-term momentum, compares against current holdings,
flags rotation opportunities, and kills losers within 15 min of entry.

Alfred's 10 Rules compliant:
- Rule 3: Kill losers in 15 min
- Rule 6: Scan every 10 min
- Rule 7: Scan 50+ tickers per cycle
- Rule 9: Fewer positions, bigger bets (min $2K)
- Rule 10: Zero idle cash overnight
"""

import json
import os
import sys
import urllib.request
import time
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3Mzk0ODgsImV4cCI6MjA4NzMxNTQ4OH0.UY8CFrYSkvygv0YzHY_N4uSCf0JwqYlKdGwRwpygub4")
BOT_ID = os.environ.get("BOT_ID", "alfred")
ROTATION_THRESHOLD = 2.0  # lowered from 3% — more aggressive rotations
MIN_POSITION_SIZE = 2000  # Rule 9: no $500 scouts
LOSER_KILL_MINUTES = 15   # Rule 3: kill losers in 15 min

# 51 tickers — Rule 7: scan 50+ per cycle
YAHOO_TICKERS = [
    # Major
    'BTC-USD','ETH-USD','SOL-USD','XRP-USD','ADA-USD','DOGE-USD','DOT-USD','AVAX-USD',
    # L1/L2
    'NEAR-USD','MATIC-USD','FTM-USD','ATOM-USD','ALGO-USD','ICP-USD','HBAR-USD','SEI-USD',
    'SUI-USD','APT-USD','INJ-USD','TIA-USD','OP-USD','ARB-USD','STX-USD',
    # DeFi
    'AAVE-USD','UNI-USD','LINK-USD','MKR-USD','CRV-USD','DYDX-USD','COMP-USD','SNX-USD',
    'RUNE-USD','PENDLE-USD','ENA-USD','LDO-USD',
    # AI/Compute
    'RNDR-USD','FET-USD','GRT-USD',
    # Meme/High Vol
    'SHIB-USD','PEPE-USD','FLOKI-USD','BONK-USD','WIF-USD',
    # Store of Value
    'LTC-USD','BCH-USD','XLM-USD','FIL-USD','KAS-USD',
    # Misc movers
    'TON-USD','MNT-USD',
]


def fetch_yahoo_price(ticker):
    """Fetch price + 24h change from Yahoo Finance."""
    try:
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=5m'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        r = data['chart']['result'][0]
        price = r['meta']['regularMarketPrice']
        prev = r['meta'].get('chartPreviousClose', r['meta'].get('previousClose', price))
        chg24 = ((price - prev) / prev * 100) if prev and prev > 0 else 0
        # 30-min momentum from closes
        closes = [c for c in r['indicators']['quote'][0].get('close', []) if c]
        h30 = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 else 0
        return {'ticker': ticker, 'price': price, 'chg24': chg24, 'h30': h30}
    except:
        return None


def fetch_open_positions(bot_id):
    """Fetch open positions from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=ticker,quantity,price_usd,total_usd,created_at"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except:
        return []


def run_scan():
    """Run the expanded momentum scan."""
    now = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"INTRADAY MOMENTUM SCAN v2 — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Bot: {BOT_ID} | Threshold: {ROTATION_THRESHOLD}% | Tickers: {len(YAHOO_TICKERS)}")
    print(f"{'='*60}\n")

    # Get current holdings
    positions = fetch_open_positions(BOT_ID)
    held_tickers = {p["ticker"] for p in positions}

    # Scan all tickers via Yahoo
    print(f"Scanning {len(YAHOO_TICKERS)} tickers...")
    universe = []
    for t in YAHOO_TICKERS:
        result = fetch_yahoo_price(t)
        if result and result['price'] > 0.0001:  # filter out broken Yahoo data
            universe.append(result)
    
    print(f"Got valid data for {len(universe)} tickers.\n")

    # Holdings performance
    print("CURRENT HOLDINGS:")
    holdings_perf = []
    for pos in positions:
        ticker = pos["ticker"]
        entry = pos.get("price_usd", 0)
        qty = pos.get("quantity", 0)
        created = pos.get("created_at", "")
        
        # Find current price
        current = None
        for u in universe:
            if u['ticker'] == ticker:
                current = u['price']
                break
        
        if current and entry and entry > 0:
            pct = ((current - entry) / entry) * 100
            value = current * qty
            
            # Check 15-min kill rule
            age_min = None
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    age_min = (now - created_dt).total_seconds() / 60
                except:
                    pass
            
            kill_flag = ""
            if age_min and age_min <= LOSER_KILL_MINUTES and pct < -0.5:
                kill_flag = " ⚠️ KILL (red within 15 min!)"
            
            marker = "🔴" if pct < 0 else "🟢"
            print(f"  {marker} {ticker:12s} {pct:+6.1f}%  ${value:>8,.0f}  (entry ${entry:.4f} → ${current:.4f}){kill_flag}")
            
            holdings_perf.append({
                "ticker": ticker, "entry": entry, "current": current,
                "pct": pct, "value": value, "qty": qty,
                "age_min": age_min, "should_kill": bool(kill_flag),
            })

    holdings_perf.sort(key=lambda x: x["pct"])
    worst = holdings_perf[0] if holdings_perf else None

    # Top movers not held
    print(f"\nTOP 15 MOVERS (not held):")
    not_held = [u for u in universe if u['ticker'] not in held_tickers]
    not_held.sort(key=lambda x: x['chg24'], reverse=True)
    
    for u in not_held[:15]:
        marker = "🔥" if u['chg24'] > 5 else ("🟢" if u['chg24'] > 1 else "🟡" if u['chg24'] > 0 else "🔴")
        h30_str = f"30m:{u['h30']:+.2f}%" if u['h30'] != 0 else ""
        print(f"  {marker} {u['ticker']:12s} ${u['price']:>12.4f}  24h:{u['chg24']:+.1f}%  {h30_str}")

    # Hourly momentum leaders
    print(f"\nHOURLY MOMENTUM LEADERS (30-min change, not held):")
    by_h30 = sorted(not_held, key=lambda x: x['h30'], reverse=True)
    for u in by_h30[:10]:
        if u['h30'] > 0:
            print(f"  🔥 {u['ticker']:12s} ${u['price']:>12.4f}  30m:{u['h30']:+.3f}%  24h:{u['chg24']:+.1f}%")

    # Rotation candidates
    print(f"\nROTATION CANDIDATES (beat worst holding by {ROTATION_THRESHOLD}%):")
    candidates = []
    if worst:
        for u in not_held:
            delta = u['chg24'] - worst['pct']
            if delta >= ROTATION_THRESHOLD:
                candidates.append({**u, "delta": delta, "replace": worst["ticker"], "replace_value": worst["value"]})
                print(f"  🔄 {u['ticker']} ({u['chg24']:+.1f}%) replaces {worst['ticker']} ({worst['pct']:+.1f}%) | spread: {delta:+.1f}%")
    
    if not candidates:
        print("  No rotation candidates found.")

    # Kill list
    kills = [h for h in holdings_perf if h.get("should_kill")]
    if kills:
        print(f"\n⚠️ 15-MIN KILL LIST:")
        for k in kills:
            print(f"  🔴 {k['ticker']} entered {k['age_min']:.0f} min ago, already {k['pct']:+.1f}% — SELL IMMEDIATELY")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(universe)} scanned | {len(candidates)} rotation(s) | {len(kills)} kill(s)")
    if candidates:
        best = max(candidates, key=lambda x: x['delta'])
        print(f"TOP SWAP: Sell {best['replace']} (${best['replace_value']:,.0f}) → Buy {best['ticker']} (spread: {best['delta']:+.1f}%)")
    print(f"{'='*60}\n")

    return candidates, kills


def auto_execute_kills(kills):
    """Execute kill list — sell positions that should have been cut 15 min ago."""
    if not kills:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'trading-research'))
        from log_trade import log_trade
    except ImportError:
        print("❌ log_trade not found — cannot auto-execute kills")
        return
    
    for k in kills:
        ticker = k['ticker']
        qty = k.get('quantity', 0)
        price = k.get('current_price', 0)
        side = k.get('side', 'LONG')
        bot = k.get('bot_id', 'alfred')
        if qty <= 0 or price <= 0:
            print(f"  ⚠️ Skipping {ticker} — missing qty ({qty}) or price ({price})")
            continue
        action = "SELL" if side == "LONG" else "COVER"
        reason = f"15-MIN KILL: {k['pct']:+.1f}% in {k['age_min']:.0f}min. Auto-executed by momentum scanner."
        print(f"  🔪 EXECUTING: {action} {qty}x {ticker} @ ${price:.2f}")
        try:
            success = log_trade(bot, action, ticker, qty, price, reason)
            if success:
                print(f"  ✅ Killed {ticker}")
            else:
                print(f"  ❌ Kill failed for {ticker}")
        except Exception as e:
            print(f"  ❌ Kill error for {ticker}: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-execute", action="store_true", help="Auto-execute kill list")
    args = parser.parse_args()
    candidates, kills = run_scan()
    if args.auto_execute and kills:
        auto_execute_kills(kills)
    sys.exit(0)
