"""
DA Round Manager — Enforces speaking order in crypto roundtable.

Order: Vex (1) → Alfred (2) → TARS (3) → Eddie (4, closes)

Rules:
- Vex kicks off every round.
- Alfred speaks second.
- TARS speaks third.
- Eddie always closes the round. Round is not complete until Eddie posts.
- No bot may post out of order. If they try, they get a reminder.
- Round advances only when the current speaker has posted.

Usage:
  from round_manager import RoundManager
  rm = RoundManager()
  rm.can_speak("alfred")      # False if it's not Alfred's turn
  rm.record_speech("vex")     # Vex posted, advance to Alfred
  rm.current_speaker()        # "alfred"
  rm.is_round_complete()      # True only after Eddie closes
  rm.next_round()             # Reset for next round
"""

from dataclasses import dataclass, field
from typing import Optional
import time
import json
import os

# Speaking order — fixed by Mark's directive 2026-03-01
SPEAKING_ORDER = [
    {"name": "vex",    "discord_id": "1474965154293612626", "role": "opener"},
    {"name": "alfred", "discord_id": "1474950973997973575", "role": "second"},
    {"name": "tars",   "discord_id": "1474972952368775308", "role": "third"},
    {"name": "eddie",  "discord_id": "1475265797180882984", "role": "closer"},
]

STATE_FILE = os.path.join(os.path.dirname(__file__), "round_state.json")


@dataclass
class RoundState:
    round_number: int = 1
    current_index: int = 0  # index into SPEAKING_ORDER
    speeches: list = field(default_factory=list)  # list of {name, timestamp, summary}
    round_complete: bool = False
    started_at: float = 0.0

    def to_dict(self):
        return {
            "round_number": self.round_number,
            "current_index": self.current_index,
            "speeches": self.speeches,
            "round_complete": self.round_complete,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class RoundManager:
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> RoundState:
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                return RoundState.from_dict(json.load(f))
        return RoundState(started_at=time.time())

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state.to_dict(), f, indent=2)

    def current_speaker(self) -> str:
        """Who should speak next."""
        if self.state.round_complete:
            return "none (round complete)"
        return SPEAKING_ORDER[self.state.current_index]["name"]

    def current_speaker_id(self) -> str:
        """Discord ID of current speaker."""
        if self.state.round_complete:
            return ""
        return SPEAKING_ORDER[self.state.current_index]["discord_id"]

    def can_speak(self, bot_name: str) -> bool:
        """Check if it's this bot's turn."""
        if self.state.round_complete:
            return False
        return bot_name.lower() == self.current_speaker()

    def record_speech(self, bot_name: str, summary: str = "") -> dict:
        """Record that a bot has spoken. Returns status."""
        bot_name = bot_name.lower()

        if self.state.round_complete:
            return {"ok": False, "error": "Round already complete"}

        if not self.can_speak(bot_name):
            expected = self.current_speaker()
            return {
                "ok": False,
                "error": f"Out of order. Waiting for {expected}.",
                "expected": expected,
                "got": bot_name,
            }

        self.state.speeches.append({
            "name": bot_name,
            "timestamp": time.time(),
            "summary": summary,
        })

        # Advance to next speaker
        self.state.current_index += 1

        # If Eddie (index 3) just spoke, round is complete
        if self.state.current_index >= len(SPEAKING_ORDER):
            self.state.round_complete = True

        self._save_state()

        return {
            "ok": True,
            "speaker": bot_name,
            "round": self.state.round_number,
            "next": self.current_speaker() if not self.state.round_complete else "ROUND COMPLETE",
            "round_complete": self.state.round_complete,
        }

    def next_round(self) -> dict:
        """Advance to the next round. Resets speaking order."""
        self.state.round_number += 1
        self.state.current_index = 0
        self.state.speeches = []
        self.state.round_complete = False
        self.state.started_at = time.time()
        self._save_state()
        return {
            "round": self.state.round_number,
            "first_speaker": SPEAKING_ORDER[0]["name"],
            "first_speaker_id": SPEAKING_ORDER[0]["discord_id"],
        }

    def status(self) -> dict:
        """Full round status."""
        return {
            "round": self.state.round_number,
            "current_speaker": self.current_speaker(),
            "current_speaker_id": self.current_speaker_id(),
            "speeches_so_far": [s["name"] for s in self.state.speeches],
            "remaining": [
                SPEAKING_ORDER[i]["name"]
                for i in range(self.state.current_index, len(SPEAKING_ORDER))
            ],
            "round_complete": self.state.round_complete,
        }

    def reminder_message(self) -> str:
        """Generate a ping message for the current speaker."""
        if self.state.round_complete:
            return "Round complete. Call next_round() to continue."
        speaker = SPEAKING_ORDER[self.state.current_index]
        return (
            f"⏳ Round {self.state.round_number} — waiting on "
            f"**{speaker['name'].upper()}** (<@{speaker['discord_id']}>) "
            f"to post. Order: Vex → Alfred → TARS → Eddie (closes)."
        )

    def enforce_message(self, wrong_bot: str) -> str:
        """Message to send when a bot tries to speak out of turn."""
        expected = self.current_speaker()
        return (
            f"🚫 **{wrong_bot.upper()}** — hold. It's **{expected.upper()}'s** turn. "
            f"Order: Vex → Alfred → TARS → Eddie (closes). "
            f"Wait for <@{self.current_speaker_id()}> to post first."
        )


if __name__ == "__main__":
    # Quick test
    rm = RoundManager()
    print(f"Status: {json.dumps(rm.status(), indent=2)}")
    print(f"Reminder: {rm.reminder_message()}")
