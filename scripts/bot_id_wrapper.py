#!/usr/bin/env python3
"""
Bot ID Wrapper — queries both bot_id variants (alfred + alfred_crypto) in one call.
Solves the recurring issue of split bot IDs causing incomplete queries.

Usage:
  python3 bot_id_wrapper.py --positions alfred          # Get all OPEN positions for alfred + alfred_crypto
  python3 bot_id_wrapper.py --trades alfred --limit 20  # Get recent trades across both IDs
  python3 bot_id_wrapper.py --summary                   # Summary for all bots
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed", file=sys.stderr)
    sys.exit(1)

WORKSPACE = Path(__file__).parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

# All bot ID variants
BOT_VARIANTS = {
    "alfred": ["alfred", "alfred_crypto"],
    "tars": ["tars", "tars_crypto"],
    "eddie": ["eddie_v", "eddie_v_crypto"],
    "vex": ["vex", "vex_crypto"],
}


def get_variants(bot_name: str) -> list:
    """Get all Supabase bot_id variants for a bot name."""
    bot_name = bot_name.lower().replace("_crypto", "").replace("_v", "")
    if bot_name == "eddie":
        return BOT_VARIANTS["eddie"]
    return BOT_VARIANTS.get(bot_name, [bot_name])


def fetch_positions(bot_name: str):
    """Fetch all OPEN positions across both bot ID variants."""
    variants = get_variants(bot_name)
    all_positions = []

    for bot_id in variants:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/trades",
                params={
                    "bot_id": f"eq.{bot_id}",
                    "status": "eq.OPEN",
                    "select": "id,bot_id,trade_id,ticker,action,quantity,price_usd,total_usd,created_at"
                },
                headers=HEADERS,
                timeout=10
            )
            r.raise_for_status()
            all_positions.extend(r.json())
        except Exception as e:
            print(f"⚠️  Failed to fetch {bot_id}: {e}", file=sys.stderr)

    return all_positions


def fetch_trades(bot_name: str, limit: int = 20):
    """Fetch recent trades across both bot ID variants."""
    variants = get_variants(bot_name)
    all_trades = []

    for bot_id in variants:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/trades",
                params={
                    "bot_id": f"eq.{bot_id}",
                    "select": "id,bot_id,trade_id,ticker,action,quantity,price_usd,total_usd,status,created_at",
                    "order": "created_at.desc",
                    "limit": limit
                },
                headers=HEADERS,
                timeout=10
            )
            r.raise_for_status()
            all_trades.extend(r.json())
        except Exception as e:
            print(f"⚠️  Failed to fetch {bot_id}: {e}", file=sys.stderr)

    # Sort by created_at descending
    all_trades.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return all_trades[:limit]


def show_positions(bot_name: str):
    positions = fetch_positions(bot_name)
    if not positions:
        print(f"No open positions for {bot_name}.")
        return

    total_invested = 0
    print(f"📊 {bot_name.upper()} — {len(positions)} open positions")
    print(f"{'Ticker':12s} {'Action':8s} {'Qty':>12s} {'Price':>12s} {'Total':>12s} {'Bot ID':>15s}")
    print("-" * 75)
    for p in sorted(positions, key=lambda x: x.get("total_usd", 0) or 0, reverse=True):
        total = p.get("total_usd") or (p.get("quantity", 0) * p.get("price_usd", 0))
        total_invested += total
        print(f"  {p['ticker']:10s} {p['action']:8s} {p['quantity']:>10,.4f}  ${p['price_usd']:>10,.2f}  ${total:>10,.2f}  {p['bot_id']:>15s}")

    print(f"\nTotal invested: ${total_invested:,.2f}")


def show_summary():
    """Summary across all bots."""
    print(f"{'Bot':10s} {'Positions':>10s} {'Invested':>14s}")
    print("-" * 38)
    for bot_name in ["alfred", "tars", "eddie", "vex"]:
        positions = fetch_positions(bot_name)
        total = sum(p.get("total_usd") or 0 for p in positions)
        print(f"  {bot_name:8s} {len(positions):>10d}  ${total:>12,.2f}")


def main():
    parser = argparse.ArgumentParser(description="Bot ID Wrapper")
    parser.add_argument("--positions", help="Get all OPEN positions for a bot")
    parser.add_argument("--trades", help="Get recent trades for a bot")
    parser.add_argument("--limit", type=int, default=20, help="Trade limit")
    parser.add_argument("--summary", action="store_true", help="Summary for all bots")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    if args.positions:
        if args.json:
            print(json.dumps(fetch_positions(args.positions), indent=2, default=str))
        else:
            show_positions(args.positions)
    elif args.trades:
        trades = fetch_trades(args.trades, args.limit)
        if args.json:
            print(json.dumps(trades, indent=2, default=str))
        else:
            for t in trades:
                total = t.get("total_usd") or 0
                print(f"  {t.get('created_at','')[:19]}  {t['action']:5s} {t['ticker']:10s} {t['quantity']:>10,.4f} @ ${t['price_usd']:>10,.2f}  [{t['status']}]  {t['bot_id']}")
    elif args.summary:
        show_summary()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
