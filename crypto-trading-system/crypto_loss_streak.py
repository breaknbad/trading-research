#!/usr/bin/env python3
"""
Loss Cluster Circuit Breaker for Crypto.

Detects losing streaks and enforces cool-off periods:
  3 consecutive losses (single bot) → 1-hour cool-off for that bot
  5 consecutive losses (fleet-wide) → Full fleet pause + mandatory autopsy

Prevents tilt-driven over-trading on bad signals.

Usage:
  from crypto_loss_streak import LossStreakMonitor
  lsm = LossStreakMonitor()
  lsm.record_result("alfred", "BTC", -150.0)
  can_trade = lsm.can_trade("alfred")  # False if in cool-off
"""

import json
import os
import time
from datetime import datetime, timezone

STATE_FILE = os.path.join(os.path.dirname(__file__), "loss_streak_state.json")

BOT_STREAK_LIMIT = 3
FLEET_STREAK_LIMIT = 5
COOLOFF_SECONDS = 3600  # 1 hour


class LossStreakMonitor:
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"bots": {}, "fleet": {"streak": 0, "cooloff_until": 0}}

    def _save(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _ensure_bot(self, bot_id: str):
        if bot_id not in self.state["bots"]:
            self.state["bots"][bot_id] = {"streak": 0, "cooloff_until": 0, "results": []}

    def record_result(self, bot_id: str, ticker: str, pnl: float) -> dict:
        """Record a trade result and check for streak breakers."""
        bot_id = bot_id.lower()
        self._ensure_bot(bot_id)
        bot = self.state["bots"][bot_id]
        fleet = self.state["fleet"]
        now = time.time()

        result = {"ticker": ticker, "pnl": pnl, "timestamp": now}
        bot["results"].append(result)
        bot["results"] = bot["results"][-20:]  # Keep last 20

        alerts = []

        if pnl < 0:
            bot["streak"] += 1
            fleet["streak"] += 1

            # Bot-level breaker
            if bot["streak"] >= BOT_STREAK_LIMIT:
                bot["cooloff_until"] = now + COOLOFF_SECONDS
                alerts.append({
                    "type": "BOT_COOLOFF",
                    "bot": bot_id,
                    "streak": bot["streak"],
                    "until": datetime.fromtimestamp(bot["cooloff_until"], tz=timezone.utc).isoformat(),
                    "message": f"🚨 {bot_id} has {bot['streak']} consecutive losses. 1-hour cool-off enforced.",
                })

            # Fleet-level breaker
            if fleet["streak"] >= FLEET_STREAK_LIMIT:
                fleet["cooloff_until"] = now + COOLOFF_SECONDS
                alerts.append({
                    "type": "FLEET_PAUSE",
                    "streak": fleet["streak"],
                    "until": datetime.fromtimestamp(fleet["cooloff_until"], tz=timezone.utc).isoformat(),
                    "message": f"🚨🚨 FLEET has {fleet['streak']} consecutive losses. FULL FLEET PAUSE + autopsy required.",
                })
        else:
            # Win resets streak
            bot["streak"] = 0
            fleet["streak"] = 0

        self._save()
        return {"bot_streak": bot["streak"], "fleet_streak": fleet["streak"], "alerts": alerts}

    def can_trade(self, bot_id: str) -> dict:
        """Check if a bot is allowed to trade (not in cool-off)."""
        bot_id = bot_id.lower()
        self._ensure_bot(bot_id)
        now = time.time()

        bot = self.state["bots"][bot_id]
        fleet = self.state["fleet"]

        bot_blocked = now < bot.get("cooloff_until", 0)
        fleet_blocked = now < fleet.get("cooloff_until", 0)

        if fleet_blocked:
            remaining = int(fleet["cooloff_until"] - now)
            return {"allowed": False, "reason": f"FLEET_PAUSE — {remaining}s remaining", "streak": fleet["streak"]}
        elif bot_blocked:
            remaining = int(bot["cooloff_until"] - now)
            return {"allowed": False, "reason": f"BOT_COOLOFF — {remaining}s remaining", "streak": bot["streak"]}
        else:
            return {"allowed": True, "bot_streak": bot["streak"], "fleet_streak": fleet["streak"]}

    def status(self) -> dict:
        return self.state


if __name__ == "__main__":
    lsm = LossStreakMonitor()
    print(json.dumps(lsm.status(), indent=2))
