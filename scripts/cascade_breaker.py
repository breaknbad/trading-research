#!/usr/bin/env python3
"""
Cascade Circuit Breaker — halts all new entries when stops are firing too fast.

Rule: 3+ stops across any bot(s) in a 30-minute window = CASCADE regime = HALT all entries.

Usage:
    from cascade_breaker import is_cascade
    halted, info = is_cascade()  # Returns (True/False, dict with details)

    python3 cascade_breaker.py          # CLI check
    python3 cascade_breaker.py --reset  # Manual reset (clears cascade state)
"""

import json
import os
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

CASCADE_THRESHOLD = 3       # stops in window = halt
CASCADE_WINDOW_MIN = 30     # window size in minutes
CASCADE_COOLDOWN_MIN = 15   # after cascade, wait this long before allowing new entries

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "cascade_state.json")


def _load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"cascade_triggered_at": None, "last_check": None, "stop_count": 0}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def count_recent_stops(window_min=CASCADE_WINDOW_MIN):
    """Count stop-loss exits across ALL bots in the last N minutes."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=window_min)).strftime("%Y-%m-%dT%H:%M:%S")

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades",
            params={
                "created_at": f"gte.{cutoff}",
                "reason": "like.*STOP*",
                "action": "in.(SELL,COVER)",
                "select": "bot_id,ticker,created_at,reason",
                "order": "created_at.desc",
            },
            headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
            timeout=10,
        )
        if r.status_code == 200:
            stops = r.json()
            return len(stops), stops
    except Exception as e:
        print(f"⚠️ Cascade check failed: {e}")

    return 0, []


def is_cascade():
    """
    Check if we're in CASCADE mode.
    Returns (is_halted: bool, info: dict)
    """
    state = _load_state()

    # If cascade was previously triggered, check cooldown
    if state.get("cascade_triggered_at"):
        triggered = datetime.fromisoformat(state["cascade_triggered_at"])
        elapsed = (datetime.now(timezone.utc) - triggered).total_seconds() / 60
        if elapsed < CASCADE_COOLDOWN_MIN:
            return True, {
                "regime": "CASCADE",
                "stops": state.get("stop_count", CASCADE_THRESHOLD),
                "cooldown_remaining_min": round(CASCADE_COOLDOWN_MIN - elapsed, 1),
                "message": f"CASCADE active — {CASCADE_COOLDOWN_MIN - elapsed:.0f}min cooldown remaining"
            }
        else:
            # Cooldown expired — clear cascade
            state["cascade_triggered_at"] = None
            _save_state(state)

    # Count recent stops
    stop_count, stop_details = count_recent_stops()
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    state["stop_count"] = stop_count

    if stop_count >= CASCADE_THRESHOLD:
        state["cascade_triggered_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)

        tickers = [s.get("ticker", "?") for s in stop_details[:5]]
        bots = list(set(s.get("bot_id", "?") for s in stop_details))
        return True, {
            "regime": "CASCADE",
            "stops": stop_count,
            "window_min": CASCADE_WINDOW_MIN,
            "tickers": tickers,
            "bots": bots,
            "cooldown_min": CASCADE_COOLDOWN_MIN,
            "message": f"🔴 CASCADE: {stop_count} stops in {CASCADE_WINDOW_MIN}min across {bots}. ALL ENTRIES HALTED for {CASCADE_COOLDOWN_MIN}min."
        }

    _save_state(state)
    return False, {
        "regime": "CLEAR",
        "stops": stop_count,
        "window_min": CASCADE_WINDOW_MIN,
        "message": f"✅ No cascade — {stop_count} stops in last {CASCADE_WINDOW_MIN}min (threshold: {CASCADE_THRESHOLD})"
    }


def reset_cascade():
    state = _load_state()
    state["cascade_triggered_at"] = None
    state["stop_count"] = 0
    _save_state(state)
    print("✅ Cascade state reset.")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_cascade()
    else:
        halted, info = is_cascade()
        print(json.dumps(info, indent=2))
        sys.exit(1 if halted else 0)
