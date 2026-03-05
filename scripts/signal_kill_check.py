"""
Signal Kill Switch Integration
- Reads/writes scripts/signal_tracker.json
- is_signal_dead(ticker, session_date) → True if 3+ PASS votes
- record_pass(ticker, bot_name, session_date) → adds a PASS vote
- Format: {"2026-03-03": {"GLD": {"passes": ["alfred","tars","vex"], "count": 3}}}
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRACKER_PATH = os.path.join(SCRIPT_DIR, "signal_tracker.json")
KILL_THRESHOLD = 3


def _load_tracker():
    if os.path.exists(TRACKER_PATH):
        with open(TRACKER_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_tracker(data):
    with open(TRACKER_PATH, "w") as f:
        json.dump(data, f, indent=2)


def is_signal_dead(ticker, session_date):
    """Returns True if ticker has 3+ PASS votes for the given session date."""
    data = _load_tracker()
    entry = data.get(session_date, {}).get(ticker, {})
    return entry.get("count", 0) >= KILL_THRESHOLD


def record_pass(ticker, bot_name, session_date):
    """Record a PASS vote. Returns updated count."""
    data = _load_tracker()
    day = data.setdefault(session_date, {})
    entry = day.setdefault(ticker, {"passes": [], "count": 0})
    if bot_name not in entry["passes"]:
        entry["passes"].append(bot_name)
        entry["count"] = len(entry["passes"])
    _save_tracker(data)
    return entry["count"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4 and sys.argv[1] == "pass":
        c = record_pass(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "2026-03-03")
        print(f"Recorded. Count: {c}")
    elif len(sys.argv) >= 3:
        print(f"Dead: {is_signal_dead(sys.argv[1], sys.argv[2])}")
