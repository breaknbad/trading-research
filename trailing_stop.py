#!/usr/bin/env python3
"""
trailing_stop.py — Auto trailing stop manager for Mi AI trading bots.

When a position is up >3% from entry, converts to a trailing stop at 1.5%
below the intraday high watermark. Checks every run if price has fallen
1.5% from the high — if so, generates a SELL signal via log_trade.py.

Tracks high watermarks in Supabase (trailing_stop_state table).
Designed to run every 5 minutes during market hours.

Usage:
  python3 trailing_stop.py                    # Check all bots
  python3 trailing_stop.py --bot tars         # Check specific bot
  python3 trailing_stop.py --dry-run          # Show what would happen
  python3 trailing_stop.py create-table       # Create state table
"""

import argparse
import json
import os
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
    "Prefer": "return=representation",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
TRAIL_ACTIVATION_PCT = 3.0   # Activate trailing stop when up 3%+
TRAIL_DISTANCE_PCT = 1.5     # Trail 1.5% below high watermark
STATE_TABLE = "trailing_stop_state"
LOCAL_STATE_FILE = os.path.join(os.path.dirname(__file__), "trailing_stop_state.json")

# Try Supabase table, fall back to local JSON
_use_local = None

def _check_table():
    global _use_local
    if _use_local is not None:
        return
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{STATE_TABLE}?limit=0",
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )
    _use_local = r.status_code != 200
    if _use_local:
        print(f"⚠️  {STATE_TABLE} table not in Supabase. Using local JSON. Run setup_tables.sql to fix.")


def _load_local():
    try:
        with open(LOCAL_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_local(data):
    with open(LOCAL_STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_state(bot_id: str, ticker: str) -> dict:
    """Get trailing stop state for a bot/ticker pair."""
    _check_table()
    if _use_local:
        data = _load_local()
        return data.get(f"{bot_id}:{ticker}")

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{STATE_TABLE}?bot_id=eq.{bot_id}&ticker=eq.{ticker}&limit=1",
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def upsert_state(bot_id: str, ticker: str, high_watermark: float, trail_active: bool):
    """Create or update trailing stop state."""
    _check_table()
    if _use_local:
        data = _load_local()
        data[f"{bot_id}:{ticker}"] = {
            "bot_id": bot_id, "ticker": ticker,
            "high_watermark": high_watermark, "trail_active": trail_active,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_local(data)
        return True

    payload = {
        "bot_id": bot_id,
        "ticker": ticker,
        "high_watermark": high_watermark,
        "trail_active": trail_active,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if trail_active:
        payload["activated_at"] = datetime.now(timezone.utc).isoformat()

    headers = dict(HEADERS)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{STATE_TABLE}",
        headers=headers,
        json=payload,
    )
    return r.status_code in (200, 201)


def remove_state(bot_id: str, ticker: str):
    """Remove trailing stop state after selling."""
    _check_table()
    if _use_local:
        data = _load_local()
        data.pop(f"{bot_id}:{ticker}", None)
        _save_local(data)
        return

    requests.delete(
        f"{SUPABASE_URL}/rest/v1/{STATE_TABLE}?bot_id=eq.{bot_id}&ticker=eq.{ticker}",
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )


def get_portfolios(bot_filter=None):
    """Fetch portfolio snapshots for all bots (or one)."""
    url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?select=*"
    if bot_filter:
        url += f"&bot_id=eq.{bot_filter}"
    r = requests.get(url, headers={k: v for k, v in HEADERS.items() if k != "Prefer"})
    if r.status_code == 200:
        return r.json()
    return []


def check_trailing_stops(bot_filter=None, dry_run=False):
    """
    Main loop: check all positions, manage trailing stops, trigger sells.

    Returns list of actions taken.
    """
    actions = []
    portfolios = get_portfolios(bot_filter)

    for portfolio in portfolios:
        bot_id = portfolio.get("bot_id")
        positions = portfolio.get("open_positions", []) or []

        for pos in positions:
            if pos.get("side", "LONG") != "LONG":
                continue  # Only trail long positions

            ticker = pos.get("ticker", "")
            entry = float(pos.get("avg_entry", 0))
            current = float(pos.get("current_price", 0))
            qty = float(pos.get("quantity", 0))

            if entry <= 0 or current <= 0 or qty <= 0:
                continue

            gain_pct = (current - entry) / entry * 100
            state = get_state(bot_id, ticker)

            # Update high watermark
            prev_high = float(state["high_watermark"]) if state else current
            new_high = max(prev_high, current)

            # Check if trailing stop should activate (up >3%)
            if gain_pct >= TRAIL_ACTIVATION_PCT:
                if not state or not state.get("trail_active"):
                    print(f"🔔 {bot_id} {ticker}: +{gain_pct:.1f}% — ACTIVATING trailing stop "
                          f"(high={new_high:.2f}, trail at {new_high * (1 - TRAIL_DISTANCE_PCT/100):.2f})")
                    if not dry_run:
                        upsert_state(bot_id, ticker, new_high, trail_active=True)
                    actions.append({"bot": bot_id, "ticker": ticker, "action": "ACTIVATE", "gain": gain_pct})
                else:
                    # Already active — update high watermark
                    if new_high > prev_high:
                        print(f"📈 {bot_id} {ticker}: new high {new_high:.2f} (was {prev_high:.2f})")
                        if not dry_run:
                            upsert_state(bot_id, ticker, new_high, trail_active=True)

                    # Check if trailing stop triggered
                    trail_price = new_high * (1 - TRAIL_DISTANCE_PCT / 100)
                    if current <= trail_price:
                        print(f"🚨 {bot_id} {ticker}: TRAILING STOP TRIGGERED! "
                              f"Current ${current:.2f} <= trail ${trail_price:.2f} "
                              f"(high was ${new_high:.2f})")
                        if not dry_run:
                            log_trade(
                                bot_id, "SELL", ticker, qty, current,
                                f"Trailing stop triggered: fell {TRAIL_DISTANCE_PCT}% from high ${new_high:.2f}"
                            )
                            remove_state(bot_id, ticker)
                        actions.append({"bot": bot_id, "ticker": ticker, "action": "SELL", "price": current})
                    else:
                        print(f"  {bot_id} {ticker}: +{gain_pct:.1f}% trail active — "
                              f"current ${current:.2f} > trail ${trail_price:.2f}")
            else:
                # Not activated yet — just track the high
                if not dry_run and state:
                    upsert_state(bot_id, ticker, new_high, trail_active=False)

    return actions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto trailing stop manager")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "create-table"])
    parser.add_argument("--bot", choices=BOTS, help="Check specific bot")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without executing")

    args = parser.parse_args()

    if args.command == "create-table":
        create_table()
    else:
        print(f"\n⏱️ Trailing Stop Check — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 60)
        actions = check_trailing_stops(args.bot, args.dry_run)
        if not actions:
            print("No trailing stop actions needed.")
        print("=" * 60)
