#!/usr/bin/env python3
"""
Scout Gate — prevents duplicate scout entries within a session.
Tracks which tickers have already been entered per bot per day.
Call before any automated scan-to-trade logic.

Usage:
  from scout_gate import can_enter, record_entry
  if can_enter("alfred", "NVDA", "SHORT"):
      # proceed with trade
      record_entry("alfred", "NVDA", "SHORT")
  else:
      print("Already entered NVDA SHORT today")
"""

import json
import os
from datetime import datetime, timezone

GATE_FILE = os.path.join(os.path.dirname(__file__), "data", "scout_entries.json")


def _load():
    if os.path.exists(GATE_FILE):
        try:
            with open(GATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save(data):
    os.makedirs(os.path.dirname(GATE_FILE), exist_ok=True)
    with open(GATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def can_enter(bot_id, ticker, action):
    """Check if this bot can open a new position in this ticker today."""
    data = _load()
    today = _today()
    key = f"{bot_id}|{ticker.upper()}|{action.upper()}|{today}"
    return key not in data


def record_entry(bot_id, ticker, action):
    """Record that this bot entered this ticker today."""
    data = _load()
    today = _today()
    key = f"{bot_id}|{ticker.upper()}|{action.upper()}|{today}"
    data[key] = datetime.now(timezone.utc).isoformat()

    # Prune entries older than today
    data = {k: v for k, v in data.items() if k.endswith(today)}
    _save(data)


def clear_day(bot_id=None):
    """Clear all entries for today (or all bots if bot_id is None)."""
    data = _load()
    today = _today()
    if bot_id:
        data = {k: v for k, v in data.items() if not (k.startswith(f"{bot_id}|") and k.endswith(today))}
    else:
        data = {k: v for k, v in data.items() if not k.endswith(today)}
    _save(data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        bot, ticker, action = sys.argv[1], sys.argv[2], sys.argv[3]
        if can_enter(bot, ticker, action):
            print(f"✅ {bot} can enter {action} {ticker}")
        else:
            print(f"❌ {bot} already entered {action} {ticker} today")
    else:
        print("Usage: python3 scout_gate.py <bot> <ticker> <action>")
        print("Entries today:")
        data = _load()
        for k, v in data.items():
            print(f"  {k}: {v}")
