#!/usr/bin/env python3
"""
ABORT Signal — Emergency fleet-wide halt.

Any bot can fire ABORT. All bots halt new entries and flag positions for review.
Used for: fat-finger trades, bad fills, flash crashes, system errors.

Usage:
  from crypto_abort import fire_abort, check_abort, clear_abort
  fire_abort("alfred", "BTC", "Fat finger — entered 10x intended size")
  if check_abort()["active"]: # don't trade
  clear_abort("alfred")  # Only the bot that fired it or Mark can clear
"""

import json
import os
import time
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    key_path = os.path.expanduser("~/.supabase_service_key")
    if os.path.exists(key_path):
        SUPABASE_KEY = open(key_path).read().strip()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

ABORT_FILE = os.path.join(os.path.dirname(__file__), "data", "abort_state.json")


def fire_abort(bot_id: str, ticker: str = None, reason: str = "EMERGENCY") -> dict:
    """Fire fleet-wide ABORT signal."""
    abort = {
        "fired_by": bot_id.lower(),
        "ticker": ticker,
        "reason": reason,
        "fired_at": time.time(),
        "fired_at_iso": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }

    # Write to local
    os.makedirs(os.path.dirname(ABORT_FILE), exist_ok=True)
    with open(ABORT_FILE, "w") as f:
        json.dump(abort, f, indent=2)

    # Write to Supabase
    if SUPABASE_KEY:
        try:
            requests.post(
                f"{SUPABASE_URL}/rest/v1/fleet_alerts",
                json={
                    "alert_type": "ABORT",
                    "fired_by": bot_id.lower(),
                    "ticker": ticker,
                    "reason": reason,
                    "active": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                headers={**HEADERS, "Prefer": "return=representation"},
                timeout=5,
            )
        except Exception:
            pass

    return abort


def check_abort() -> dict:
    """Check if ABORT is active. ALL bots must check this before any entry."""
    # Check local first (fastest)
    if os.path.exists(ABORT_FILE):
        try:
            with open(ABORT_FILE) as f:
                state = json.load(f)
            if state.get("active", False):
                return state
        except Exception:
            pass

    # Check Supabase
    if SUPABASE_KEY:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/fleet_alerts",
                params={
                    "alert_type": "eq.ABORT",
                    "active": "eq.true",
                    "order": "timestamp.desc",
                    "limit": "1",
                },
                headers=HEADERS,
                timeout=5,
            )
            if r.status_code == 200 and r.json():
                return {"active": True, **r.json()[0]}
        except Exception:
            pass

    return {"active": False}


def clear_abort(bot_id: str) -> dict:
    """Clear ABORT signal. Only the bot that fired it should clear it."""
    # Clear local
    if os.path.exists(ABORT_FILE):
        try:
            with open(ABORT_FILE) as f:
                state = json.load(f)
            state["active"] = False
            state["cleared_by"] = bot_id.lower()
            state["cleared_at"] = datetime.now(timezone.utc).isoformat()
            with open(ABORT_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    # Clear Supabase
    if SUPABASE_KEY:
        try:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/fleet_alerts",
                params={"alert_type": "eq.ABORT", "active": "eq.true"},
                json={"active": False},
                headers=HEADERS,
                timeout=5,
            )
        except Exception:
            pass

    return {"cleared": True, "cleared_by": bot_id}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "fire":
            bot = sys.argv[2] if len(sys.argv) > 2 else "alfred"
            reason = sys.argv[3] if len(sys.argv) > 3 else "MANUAL ABORT"
            result = fire_abort(bot, reason=reason)
            print(f"🔴 ABORT FIRED by {bot}: {reason}")
        elif sys.argv[1] == "clear":
            bot = sys.argv[2] if len(sys.argv) > 2 else "alfred"
            clear_abort(bot)
            print(f"✅ ABORT cleared by {bot}")
        elif sys.argv[1] == "check":
            state = check_abort()
            print(f"ABORT active: {state.get('active', False)}")
    else:
        state = check_abort()
        print(json.dumps(state, indent=2))
