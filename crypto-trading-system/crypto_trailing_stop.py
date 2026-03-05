#!/usr/bin/env python3
"""
Crypto Trailing Stop — Dynamic stop that ratchets up as price moves favorably.

For LONG positions: stop follows price up, never moves down.
For SHORT positions: stop follows price down, never moves up.

Trail distance tightens as profit grows:
  0-3% profit  → 2.0% trail (standard)
  3-5% profit  → 1.5% trail (tighten)
  5-10% profit → 1.2% trail (lock gains)
  10%+ profit  → 1.0% trail (tight lock)

Usage:
  from crypto_trailing_stop import TrailingStopManager
  tsm = TrailingStopManager()
  tsm.update_price("alfred", "BTC", 68000.0)  # call on every price tick
  stop = tsm.get_stop("alfred", "BTC")         # current trailing stop level
  triggered = tsm.check_stops(prices)           # check all, return triggered list
"""

import json
import os
import time
from typing import Optional

STATE_FILE = os.path.join(os.path.dirname(__file__), "trailing_stop_state.json")

# Trail distance by profit tier
TRAIL_TIERS = [
    (10.0, 1.0),   # 10%+ profit → 1.0% trail
    (5.0,  1.2),   # 5-10% → 1.2%
    (3.0,  1.5),   # 3-5% → 1.5%
    (0.0,  2.0),   # 0-3% → 2.0% (standard)
]


class TrailingStopManager:
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
        return {}

    def _save(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _key(self, bot_id: str, ticker: str) -> str:
        return f"{bot_id.lower()}:{ticker.upper()}"

    def _trail_pct(self, profit_pct: float) -> float:
        for threshold, trail in TRAIL_TIERS:
            if profit_pct >= threshold:
                return trail
        return 2.0

    def register_position(self, bot_id: str, ticker: str, entry_price: float, side: str = "LONG"):
        """Register a new position for trailing stop tracking."""
        key = self._key(bot_id, ticker)
        self.state[key] = {
            "entry_price": entry_price,
            "side": side.upper(),
            "high_water": entry_price if side.upper() == "LONG" else entry_price,
            "low_water": entry_price if side.upper() == "SHORT" else entry_price,
            "current_stop": entry_price * (1 - 0.02) if side.upper() == "LONG" else entry_price * (1 + 0.02),
            "last_update": time.time(),
        }
        self._save()

    def update_price(self, bot_id: str, ticker: str, current_price: float) -> Optional[float]:
        """Update price and ratchet trailing stop. Returns new stop level."""
        key = self._key(bot_id, ticker)
        pos = self.state.get(key)
        if not pos:
            return None

        entry = pos["entry_price"]
        side = pos["side"]

        if side == "LONG":
            # Update high water mark
            if current_price > pos["high_water"]:
                pos["high_water"] = current_price

            profit_pct = ((pos["high_water"] - entry) / entry) * 100
            trail = self._trail_pct(profit_pct)
            new_stop = pos["high_water"] * (1 - trail / 100)

            # Stop only moves UP, never down
            if new_stop > pos["current_stop"]:
                pos["current_stop"] = new_stop

        else:  # SHORT
            if current_price < pos["low_water"]:
                pos["low_water"] = current_price

            profit_pct = ((entry - pos["low_water"]) / entry) * 100
            trail = self._trail_pct(profit_pct)
            new_stop = pos["low_water"] * (1 + trail / 100)

            # Stop only moves DOWN for shorts
            if new_stop < pos["current_stop"]:
                pos["current_stop"] = new_stop

        pos["last_update"] = time.time()
        self._save()
        return pos["current_stop"]

    def get_stop(self, bot_id: str, ticker: str) -> Optional[float]:
        key = self._key(bot_id, ticker)
        pos = self.state.get(key)
        return pos["current_stop"] if pos else None

    def check_stops(self, prices: dict) -> list:
        """Check all positions against trailing stops. Returns list of triggered."""
        triggered = []
        for key, pos in self.state.items():
            bot_id, ticker = key.split(":", 1)
            current = prices.get(ticker)
            if current is None:
                continue

            self.update_price(bot_id, ticker, current)

            if pos["side"] == "LONG" and current <= pos["current_stop"]:
                triggered.append({
                    "bot": bot_id, "ticker": ticker, "side": "LONG",
                    "entry": pos["entry_price"], "stop": pos["current_stop"],
                    "current": current, "reason": "TRAILING_STOP",
                })
            elif pos["side"] == "SHORT" and current >= pos["current_stop"]:
                triggered.append({
                    "bot": bot_id, "ticker": ticker, "side": "SHORT",
                    "entry": pos["entry_price"], "stop": pos["current_stop"],
                    "current": current, "reason": "TRAILING_STOP",
                })

        return triggered

    def remove_position(self, bot_id: str, ticker: str):
        key = self._key(bot_id, ticker)
        self.state.pop(key, None)
        self._save()

    def status(self) -> dict:
        return {k: {**v, "current_stop": round(v["current_stop"], 2)} for k, v in self.state.items()}


if __name__ == "__main__":
    tsm = TrailingStopManager()
    print(json.dumps(tsm.status(), indent=2))
