#!/usr/bin/env python3
"""
Cross-Bot Correlation Guard — prevents fleet concentration risk.
Queries Supabase for all bots' OPEN positions and flags:
1. Same ticker held by 3+ bots (concentration risk)
2. Same sector held by all 4 bots (sector risk)
3. Any single ticker >30% of fund (position risk)

Usage:
  python3 correlation_guard.py --check              # Full fleet correlation check
  python3 correlation_guard.py --check-ticker BTC   # Check specific ticker across fleet
  python3 correlation_guard.py --pre-trade BTC alfred 5000  # Pre-trade check: would this create concentration?
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed", file=sys.stderr)
    sys.exit(1)

WORKSPACE = Path(__file__).parent.parent

# Load creds
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# All bot IDs (equities + crypto)
BOT_IDS = [
    "tars", "tars_crypto",
    "alfred", "alfred_crypto",
    "eddie_v", "eddie_v_crypto",
    "vex", "vex_crypto",
]

# Normalize bot names
BOT_PARENT = {
    "tars": "TARS", "tars_crypto": "TARS",
    "alfred": "Alfred", "alfred_crypto": "Alfred",
    "eddie_v": "Eddie", "eddie_v_crypto": "Eddie",
    "vex": "Vex", "vex_crypto": "Vex",
}

# Sector mappings (extend as needed)
SECTOR_MAP = {
    "BTC-USD": "crypto", "ETH-USD": "crypto", "SOL-USD": "crypto",
    "NEAR-USD": "crypto", "ADA-USD": "crypto", "AVAX-USD": "crypto",
    "LINK-USD": "crypto", "DOGE-USD": "crypto", "SUI-USD": "crypto",
    "FIL-USD": "crypto", "APT-USD": "crypto",
    "SQQQ": "inverse-equity", "TQQQ": "leveraged-equity",
    "SH": "inverse-equity", "SOXS": "inverse-semi",
    "GLD": "gold", "GDX": "gold-miners", "GDXJ": "gold-miners",
    "SLV": "silver", "XLE": "energy", "XLV": "healthcare",
    "BIL": "cash-equiv", "SHV": "cash-equiv",
    "NVDA": "semis", "AMD": "semis", "INTC": "semis",
}

# Thresholds
MAX_BOTS_SAME_TICKER = 3    # Flag if 3+ bots hold same ticker
MAX_FUND_SINGLE_TICKER = 0.30  # Flag if single ticker > 30% of fund
FUND_SIZE = 200000  # Approximate fund size


def fetch_all_positions():
    """Fetch all OPEN positions across all bots."""
    positions = []
    for bot_id in BOT_IDS:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/trades",
                params={
                    "bot_id": f"eq.{bot_id}",
                    "status": "eq.OPEN",
                    "select": "bot_id,ticker,action,quantity,price_usd,total_usd"
                },
                headers=HEADERS,
                timeout=10
            )
            r.raise_for_status()
            for pos in r.json():
                pos["parent_bot"] = BOT_PARENT.get(bot_id, bot_id)
                positions.append(pos)
        except Exception as e:
            print(f"⚠️  Failed to fetch {bot_id}: {e}", file=sys.stderr)
    return positions


def analyze_concentration(positions):
    """Analyze fleet concentration risk."""
    # Group by normalized ticker
    ticker_bots = defaultdict(set)
    ticker_total_usd = defaultdict(float)
    sector_bots = defaultdict(set)
    bot_exposure = defaultdict(float)

    for pos in positions:
        ticker = pos["ticker"].upper()
        bot = pos["parent_bot"]
        total = pos.get("total_usd") or (pos.get("quantity", 0) * pos.get("price_usd", 0))

        ticker_bots[ticker].add(bot)
        ticker_total_usd[ticker] += total
        bot_exposure[bot] += total

        sector = SECTOR_MAP.get(ticker, "unknown")
        sector_bots[sector].add(bot)

    alerts = []

    # Check 1: Same ticker held by 3+ bots
    for ticker, bots in ticker_bots.items():
        if len(bots) >= MAX_BOTS_SAME_TICKER:
            alerts.append({
                "type": "CONCENTRATION",
                "severity": "🔴 HIGH" if len(bots) == 4 else "🟡 MEDIUM",
                "ticker": ticker,
                "bots": sorted(bots),
                "total_usd": ticker_total_usd[ticker],
                "fund_pct": ticker_total_usd[ticker] / FUND_SIZE * 100,
                "msg": f"{ticker} held by {len(bots)} bots ({', '.join(sorted(bots))}): ${ticker_total_usd[ticker]:,.0f} ({ticker_total_usd[ticker]/FUND_SIZE*100:.1f}% of fund)"
            })

    # Check 2: Same sector held by all 4 bots
    for sector, bots in sector_bots.items():
        if len(bots) >= 4 and sector != "cash-equiv":
            alerts.append({
                "type": "SECTOR_CONCENTRATION",
                "severity": "🟡 MEDIUM",
                "sector": sector,
                "bots": sorted(bots),
                "msg": f"All 4 bots exposed to {sector} sector"
            })

    # Check 3: Single ticker > 30% of fund
    for ticker, total in ticker_total_usd.items():
        pct = total / FUND_SIZE
        if pct > MAX_FUND_SINGLE_TICKER:
            alerts.append({
                "type": "OVERSIZED",
                "severity": "🔴 HIGH",
                "ticker": ticker,
                "total_usd": total,
                "fund_pct": pct * 100,
                "msg": f"{ticker} is {pct*100:.1f}% of fund (${total:,.0f}) — exceeds {MAX_FUND_SINGLE_TICKER*100:.0f}% limit"
            })

    return alerts, ticker_bots, ticker_total_usd


def check_pre_trade(ticker: str, bot: str, amount: float, positions: list):
    """Check if a new trade would create concentration risk."""
    ticker = ticker.upper()
    bot_name = BOT_PARENT.get(bot, bot)

    # Count current holders
    current_bots = set()
    current_total = 0
    for pos in positions:
        if pos["ticker"].upper() == ticker:
            current_bots.add(pos["parent_bot"])
            current_total += pos.get("total_usd") or 0

    new_bots = current_bots | {bot_name}
    new_total = current_total + amount

    issues = []

    if len(new_bots) >= MAX_BOTS_SAME_TICKER:
        issues.append(f"🔴 {ticker} would be held by {len(new_bots)} bots ({', '.join(sorted(new_bots))})")

    if new_total / FUND_SIZE > MAX_FUND_SINGLE_TICKER:
        issues.append(f"🔴 {ticker} would be {new_total/FUND_SIZE*100:.1f}% of fund (${new_total:,.0f})")

    if issues:
        print(f"⚠️  PRE-TRADE ALERT for {bot_name} buying {ticker}:")
        for i in issues:
            print(f"  {i}")
        return False
    else:
        print(f"✅ {bot_name} buying {ticker} (${amount:,.0f}) — no concentration risk.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Cross-Bot Correlation Guard")
    parser.add_argument("--check", action="store_true", help="Full fleet correlation check")
    parser.add_argument("--check-ticker", help="Check specific ticker across fleet")
    parser.add_argument("--pre-trade", nargs=3, metavar=("TICKER", "BOT", "AMOUNT"),
                        help="Pre-trade concentration check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    positions = fetch_all_positions()

    if args.check:
        alerts, ticker_bots, ticker_totals = analyze_concentration(positions)
        if args.json:
            print(json.dumps(alerts, indent=2, default=str))
        else:
            print(f"📊 Fleet Correlation Check — {len(positions)} positions across {len(set(p['parent_bot'] for p in positions))} bots")
            print("=" * 60)
            if alerts:
                for a in alerts:
                    print(f"  {a['severity']} [{a['type']}] {a['msg']}")
                print(f"\n⚠️  {len(alerts)} alert(s) found.")
            else:
                print("  ✅ No concentration risk detected.")

            # Summary table
            print(f"\n{'Ticker':12s} {'Bots':20s} {'Total $':>12s} {'Fund %':>8s}")
            print("-" * 55)
            for ticker in sorted(ticker_totals, key=lambda t: ticker_totals[t], reverse=True):
                bots = ", ".join(sorted(ticker_bots[ticker]))
                total = ticker_totals[ticker]
                pct = total / FUND_SIZE * 100
                flag = " ⚠️" if len(ticker_bots[ticker]) >= 3 or pct > 20 else ""
                print(f"  {ticker:10s} {bots:20s} ${total:>10,.0f} {pct:>6.1f}%{flag}")

    elif args.check_ticker:
        ticker = args.check_ticker.upper()
        holders = []
        total = 0
        for pos in positions:
            if pos["ticker"].upper() == ticker:
                holders.append(pos)
                total += pos.get("total_usd") or 0
        if holders:
            bots = set(p["parent_bot"] for p in holders)
            print(f"📊 {ticker} — held by {len(bots)} bot(s): {', '.join(sorted(bots))}")
            print(f"   Total: ${total:,.0f} ({total/FUND_SIZE*100:.1f}% of fund)")
            for h in holders:
                print(f"   {h['parent_bot']:10s} {h['quantity']}x @ ${h['price_usd']:,.2f}")
        else:
            print(f"✅ {ticker} — not held by any bot.")

    elif args.pre_trade:
        ticker, bot, amount = args.pre_trade
        ok = check_pre_trade(ticker, bot, float(amount), positions)
        sys.exit(0 if ok else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
