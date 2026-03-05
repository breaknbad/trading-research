#!/usr/bin/env python3
"""
crypto_turn_checker.py — 60-second round turn monitor
Owner: Alfred | Created: 2026-03-01

Polls Supabase round_state every 60s. If it's Alfred's turn and he hasn't
posted, fires a system event to wake the main session.

This is the fix for the core issue: bots are periodic checkers, not
always-on listeners. This makes Alfred an always-on listener for rounds.
"""

import os
import json
import time
from datetime import datetime, timezone

SPEAKING_ORDER = ["vex", "alfred", "tars", "eddie"]
MY_BOT = "alfred"
ROUND_STATE_FILE = os.path.join(os.path.dirname(__file__), "round_state_cache.json")


def check_my_turn() -> dict:
    """Check if it's Alfred's turn in the current round."""
    # Try Supabase
    try:
        from crypto_supabase_guard import _get_client
        client = _get_client()
        if client:
            result = client.table("round_state").select("*").eq(
                "active", True
            ).order("created_at", desc=True).limit(1).execute()

            if result.data:
                state = result.data[0]
                current_speaker = state.get("current_speaker", "")
                speakers_done = state.get("speakers_completed", [])
                
                # Is it my turn?
                my_turn = current_speaker == MY_BOT
                # Have I already posted?
                already_posted = MY_BOT in speakers_done

                return {
                    "my_turn": my_turn and not already_posted,
                    "current_speaker": current_speaker,
                    "speakers_done": speakers_done,
                    "round_id": state.get("round_id"),
                    "round_number": state.get("round_number"),
                    "topic": state.get("topic", ""),
                    "already_posted": already_posted,
                    "source": "supabase"
                }
    except Exception:
        pass

    # Fallback: check local cache
    try:
        with open(ROUND_STATE_FILE) as f:
            state = json.load(f)
        return {
            "my_turn": state.get("current_speaker") == MY_BOT,
            "source": "cache",
            **state
        }
    except Exception:
        return {"my_turn": False, "source": "none", "error": "No round state available"}


def update_local_cache(state: dict):
    """Cache round state locally."""
    with open(ROUND_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


if __name__ == "__main__":
    result = check_my_turn()
    print(f"Turn checker: {'MY TURN' if result['my_turn'] else 'Not my turn'}")
    print(json.dumps(result, indent=2))
