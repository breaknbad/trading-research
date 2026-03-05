#!/usr/bin/env python3
"""
Signal Kill Switch — 3 PASS votes on a ticker = DEAD for the session.
Tracks PASS votes in signal_tracker.json. Any bot can register a PASS.
Query before posting a signal to check if it's blacklisted.

Usage:
  python3 signal_kill_switch.py --pass GLD --bot alfred      # Register a PASS vote
  python3 signal_kill_switch.py --check GLD                   # Check if ticker is dead
  python3 signal_kill_switch.py --list                        # Show all tracked tickers
  python3 signal_kill_switch.py --reset                       # Reset for new session
  python3 signal_kill_switch.py --reset-ticker GLD            # Reset single ticker
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TRACKER_FILE = Path(__file__).parent.parent / "signal_tracker.json"
KILL_THRESHOLD = 3  # PASS votes needed to kill a signal


def load_tracker():
    if TRACKER_FILE.exists():
        try:
            data = json.loads(TRACKER_FILE.read_text())
            # Reset if from a different date (new session)
            if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                return {"date": datetime.now().strftime("%Y-%m-%d"), "tickers": {}}
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"date": datetime.now().strftime("%Y-%m-%d"), "tickers": {}}


def save_tracker(data):
    TRACKER_FILE.write_text(json.dumps(data, indent=2))


def register_pass(ticker: str, bot: str):
    data = load_tracker()
    ticker = ticker.upper()
    if ticker not in data["tickers"]:
        data["tickers"][ticker] = {"passes": [], "killed": False}

    entry = data["tickers"][ticker]

    # Don't double-count same bot
    bot_names = [p["bot"] for p in entry["passes"]]
    if bot.lower() in bot_names:
        print(f"⚠️  {bot} already voted PASS on {ticker}")
        save_tracker(data)
        return entry

    entry["passes"].append({
        "bot": bot.lower(),
        "time": datetime.now(timezone.utc).isoformat()
    })

    if len(entry["passes"]) >= KILL_THRESHOLD and not entry["killed"]:
        entry["killed"] = True
        entry["killed_at"] = datetime.now(timezone.utc).isoformat()
        print(f"🔴 {ticker} is DEAD — {len(entry['passes'])} PASS votes. Signal blacklisted for session.")
    else:
        remaining = KILL_THRESHOLD - len(entry["passes"])
        print(f"📝 PASS registered: {bot} on {ticker} ({len(entry['passes'])}/{KILL_THRESHOLD}). {remaining} more to kill.")

    save_tracker(data)
    return entry


def check_ticker(ticker: str):
    data = load_tracker()
    ticker = ticker.upper()
    entry = data["tickers"].get(ticker)

    if not entry:
        print(f"✅ {ticker} — no PASS votes. Clear to signal.")
        return False

    if entry.get("killed"):
        print(f"🔴 {ticker} — DEAD. {len(entry['passes'])} PASS votes. DO NOT SIGNAL.")
        return True
    else:
        remaining = KILL_THRESHOLD - len(entry["passes"])
        bots = ", ".join(p["bot"] for p in entry["passes"])
        print(f"🟡 {ticker} — {len(entry['passes'])}/{KILL_THRESHOLD} PASS votes ({bots}). {remaining} more to kill.")
        return False


def list_all():
    data = load_tracker()
    if not data["tickers"]:
        print("No signals tracked today.")
        return

    print(f"Signal Tracker — {data['date']}")
    print("-" * 50)
    for ticker, entry in sorted(data["tickers"].items()):
        status = "🔴 DEAD" if entry.get("killed") else f"🟡 {len(entry['passes'])}/{KILL_THRESHOLD}"
        bots = ", ".join(p["bot"] for p in entry["passes"])
        print(f"  {ticker:10s} {status:15s} votes: {bots}")


def reset_all():
    data = {"date": datetime.now().strftime("%Y-%m-%d"), "tickers": {}}
    save_tracker(data)
    print("✅ Signal tracker reset for new session.")


def reset_ticker(ticker: str):
    data = load_tracker()
    ticker = ticker.upper()
    if ticker in data["tickers"]:
        del data["tickers"][ticker]
        save_tracker(data)
        print(f"✅ {ticker} reset.")
    else:
        print(f"⚠️  {ticker} not in tracker.")


def main():
    parser = argparse.ArgumentParser(description="Signal Kill Switch")
    parser.add_argument("--pass", dest="pass_ticker", help="Register a PASS vote for ticker")
    parser.add_argument("--bot", help="Bot name registering the PASS")
    parser.add_argument("--check", help="Check if a ticker is blacklisted")
    parser.add_argument("--list", action="store_true", help="List all tracked tickers")
    parser.add_argument("--reset", action="store_true", help="Reset tracker for new session")
    parser.add_argument("--reset-ticker", help="Reset a single ticker")

    args = parser.parse_args()

    if args.reset:
        reset_all()
    elif args.reset_ticker:
        reset_ticker(args.reset_ticker)
    elif args.list:
        list_all()
    elif args.check:
        killed = check_ticker(args.check)
        sys.exit(1 if killed else 0)
    elif args.pass_ticker:
        if not args.bot:
            print("ERROR: --bot required with --pass")
            sys.exit(2)
        register_pass(args.pass_ticker, args.bot)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
