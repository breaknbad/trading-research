#!/usr/bin/env python3
"""DA Rotation Tracker — permanent fix for speaking order bugs.

State file: da_state.json in same directory.
Speaking order (permanent): Vex → TARS → Alfred → Eddie (Eddie closes each round).

Usage:
  python3 da_rotation.py status          # Show current state
  python3 da_rotation.py start <rounds>  # Start new DA session with N rounds, topic
  python3 da_rotation.py done            # Mark current speaker done, return next speaker
  python3 da_rotation.py next            # Who speaks next? (read-only)
  python3 da_rotation.py reset           # Clear state
"""

import json, sys, os
from datetime import datetime

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "da_state.json")

SPEAKING_ORDER = ["vex", "tars", "alfred", "eddie"]
BOT_DISCORD_IDS = {
    "vex": "1474965154293612626",
    "tars": "1474972952368775308",
    "alfred": "1474950973997973575",
    "eddie": "1475265797180882984",
}
BOT_NAMES = {v: k for k, v in BOT_DISCORD_IDS.items()}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def start_session(total_rounds, topic=""):
    state = {
        "total_rounds": total_rounds,
        "current_round": 1,
        "current_speaker_idx": 0,  # vex starts
        "current_speaker": SPEAKING_ORDER[0],
        "topic": topic,
        "started_at": datetime.now().isoformat(),
        "history": [],
    }
    save_state(state)
    speaker = SPEAKING_ORDER[0]
    print(f"DA session started: {total_rounds} rounds")
    print(f"Round 1 — {speaker.upper()} speaks first")
    print(f"Ping: <@{BOT_DISCORD_IDS[speaker]}>")
    return state


def mark_done(bot_name=None):
    state = load_state()
    if not state:
        print("ERROR: No active DA session. Use 'start' first.")
        sys.exit(1)

    current = state["current_speaker"]
    if bot_name and bot_name.lower() != current:
        print(f"WARNING: Expected {current.upper()} but {bot_name.upper()} called done.")

    # Log completion
    state["history"].append({
        "round": state["current_round"],
        "speaker": current,
        "completed_at": datetime.now().isoformat(),
    })

    idx = state["current_speaker_idx"]
    
    if idx == len(SPEAKING_ORDER) - 1:
        # Eddie just closed the round
        if state["current_round"] >= state["total_rounds"]:
            print(f"DA SESSION COMPLETE — all {state['total_rounds']} rounds done.")
            state["completed"] = True
            save_state(state)
            return state
        # Advance to next round
        state["current_round"] += 1
        state["current_speaker_idx"] = 0
        state["current_speaker"] = SPEAKING_ORDER[0]
        nxt = SPEAKING_ORDER[0]
        print(f"Round {state['current_round'] - 1} closed by Eddie.")
        print(f"Round {state['current_round']} — {nxt.upper()} opens.")
        print(f"Ping: <@{BOT_DISCORD_IDS[nxt]}>")
    else:
        # Advance to next speaker in same round
        state["current_speaker_idx"] = idx + 1
        state["current_speaker"] = SPEAKING_ORDER[idx + 1]
        nxt = SPEAKING_ORDER[idx + 1]
        print(f"{current.upper()} done. Next: {nxt.upper()}")
        print(f"Ping: <@{BOT_DISCORD_IDS[nxt]}>")

    save_state(state)
    return state


def show_status():
    state = load_state()
    if not state:
        print("No active DA session.")
        return
    print(f"Round {state['current_round']}/{state['total_rounds']}")
    print(f"Current speaker: {state['current_speaker'].upper()}")
    idx = state["current_speaker_idx"]
    remaining = [s.upper() for s in SPEAKING_ORDER[idx:]]
    print(f"Remaining this round: {' → '.join(remaining)}")
    if state.get("completed"):
        print("SESSION COMPLETE")


def show_next():
    state = load_state()
    if not state:
        print("No active DA session.")
        return
    nxt = state["current_speaker"]
    print(f"Next up: {nxt.upper()} — <@{BOT_DISCORD_IDS[nxt]}>")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "start":
        rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        topic = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""
        start_session(rounds, topic)
    elif cmd == "done":
        bot = sys.argv[2] if len(sys.argv) > 2 else None
        mark_done(bot)
    elif cmd == "status":
        show_status()
    elif cmd == "next":
        show_next()
    elif cmd == "reset":
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print("State cleared.")
    else:
        print(__doc__)
