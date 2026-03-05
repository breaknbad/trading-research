#!/usr/bin/env python3
"""
shared_signals.py — Fleet-wide signal sharing for Mi AI trading bots.

When a bot identifies a 5%+ mover with >1.5x RVOL, it posts to the shared_signals
table in Supabase. All bots read from this table every 5 minutes.

Existing Supabase schema (shared_signals):
  id, ticker, price, change_pct, volume, signal_type, source_bot, reason,
  created_at, claimed_by, status

Functions:
  post_signal(bot_id, ticker, data) — Write a signal (with 30-min dedup)
  get_signals(since_minutes=30) — Read recent signals

Usage:
  python3 shared_signals.py post --bot tars --ticker NVDA --pct 7.2 --volume 5000000 --price 130.50 --reason "Earnings beat"
  python3 shared_signals.py get --since 30
"""

import argparse
import json
import sys
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
    "Prefer": "return=representation",
}

HEADERS_READ = {k: v for k, v in HEADERS.items() if k != "Prefer"}
TABLE = "shared_signals"


def post_signal(bot_id: str, ticker: str, data: dict) -> bool:
    """
    Post a signal to shared_signals with 30-minute dedup.

    Args:
        bot_id: Source bot identifier (tars, alfred, vex, eddie_v)
        ticker: Stock ticker symbol
        data: Dict with keys: change_pct (required), price, volume, reason,
              signal_type (default VELOCITY), rvol, conviction_score

    Returns:
        True if posted, False if duplicate or error.
    """
    ticker = ticker.upper()

    # Dedup check: same ticker within 30 min
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?ticker=eq.{ticker}&created_at=gte.{cutoff}&limit=1",
        headers=HEADERS_READ,
    )
    if r.status_code == 200 and r.json():
        existing = r.json()[0]
        print(f"⏭️  Dedup: {ticker} already posted by {existing.get('source_bot')} at {existing.get('created_at')}")
        return False

    # Build reason string with extra data (rvol, conviction) embedded
    reason_parts = []
    if data.get("reason"):
        reason_parts.append(str(data["reason"]))
    if data.get("rvol"):
        reason_parts.append(f"RVOL={data['rvol']:.1f}x")
    if data.get("conviction_score"):
        reason_parts.append(f"Conv={data['conviction_score']}/10")
    if data.get("market_cap"):
        reason_parts.append(f"MCap={data['market_cap']}")
    if data.get("catalyst"):
        reason_parts.append(f"Catalyst: {data['catalyst']}")

    signal = {
        "ticker": ticker,
        "change_pct": float(data.get("change_pct", data.get("pct_change", 0))),
        "price": float(data["price"]) if data.get("price") else None,
        "volume": int(data["volume"]) if data.get("volume") else None,
        "signal_type": data.get("signal_type", "VELOCITY"),
        "source_bot": bot_id,
        "reason": " | ".join(reason_parts) if reason_parts else None,
        "status": "OPEN",
    }

    r = requests.post(f"{SUPABASE_URL}/rest/v1/{TABLE}", headers=HEADERS, json=signal)
    if r.status_code in (200, 201):
        print(f"✅ Signal posted: {bot_id} → {ticker} +{signal['change_pct']:.1f}%")
        return True
    else:
        print(f"ERROR posting signal: {r.status_code} {r.text}")
        return False


def get_signals(since_minutes: int = 30) -> list:
    """
    Fetch recent signals from the shared_signals table.

    Args:
        since_minutes: How far back to look (default 30 min)

    Returns:
        List of signal dicts, newest first.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?created_at=gte.{cutoff}&order=created_at.desc",
        headers=HEADERS_READ,
    )
    if r.status_code == 200:
        return r.json()
    else:
        print(f"ERROR fetching signals: {r.status_code} {r.text}")
        return []


def claim_signal(signal_id: int, bot_id: str) -> bool:
    """Mark a signal as claimed by a bot."""
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?id=eq.{signal_id}",
        headers=HEADERS,
        json={"claimed_by": bot_id, "status": "CLAIMED"},
    )
    return r.status_code in (200, 204)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fleet-wide signal sharing")
    sub = parser.add_subparsers(dest="command")

    # post
    post_p = sub.add_parser("post", help="Post a signal")
    post_p.add_argument("--bot", required=True)
    post_p.add_argument("--ticker", required=True)
    post_p.add_argument("--pct", required=True, type=float, help="Intraday pct change")
    post_p.add_argument("--price", type=float, help="Current price")
    post_p.add_argument("--volume", type=int, help="Total volume")
    post_p.add_argument("--rvol", type=float, help="Relative volume")
    post_p.add_argument("--conviction", type=int, help="Conviction score 1-10")
    post_p.add_argument("--reason", type=str)
    post_p.add_argument("--catalyst", type=str)
    post_p.add_argument("--market-cap", type=float)
    post_p.add_argument("--signal-type", type=str, default="VELOCITY")

    # get
    get_p = sub.add_parser("get", help="Get recent signals")
    get_p.add_argument("--since", type=int, default=30, help="Minutes to look back")

    args = parser.parse_args()

    if args.command == "post":
        data = {
            "change_pct": args.pct,
            "price": args.price,
            "volume": args.volume,
            "rvol": args.rvol,
            "conviction_score": args.conviction,
            "reason": args.reason,
            "catalyst": args.catalyst,
            "market_cap": args.market_cap,
            "signal_type": args.signal_type,
        }
        post_signal(args.bot, args.ticker, data)
    elif args.command == "get":
        signals = get_signals(args.since)
        if signals:
            print(f"\n📡 {len(signals)} signal(s) in last {args.since} min:")
            for s in signals:
                print(f"  {s['ticker']:6s} +{s.get('change_pct',0) or 0:5.1f}%  "
                      f"Vol={s.get('volume','?')}  by {s['source_bot']}  "
                      f"{s.get('status','?')}  {s['created_at'][:19]}")
                if s.get("reason"):
                    print(f"         {s['reason']}")
        else:
            print(f"No signals in last {args.since} minutes.")
    else:
        parser.print_help()
