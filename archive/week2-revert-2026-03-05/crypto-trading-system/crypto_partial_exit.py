#!/usr/bin/env python3
"""
Crypto Partial Exit Manager — Scaled profit-taking.

Instead of binary hold/sell, take profits in stages:
  +5%  → sell 25% of position
  +8%  → sell another 25%
  +12% → sell another 25%
  Remaining 25% rides with trailing stop

Usage:
  from crypto_partial_exit import PartialExitManager
  pem = PartialExitManager()
  actions = pem.check_position("alfred", "BTC", entry=64000, current=67500, qty=0.15)
  # Returns: [{"action": "PARTIAL_EXIT", "pct": 25, "qty": 0.0375, "reason": "+5% tier hit"}]
"""

import json
import os
import time

STATE_FILE = os.path.join(os.path.dirname(__file__), "partial_exit_state.json")

# Profit tiers → cumulative % to have exited
EXIT_TIERS = [
    {"gain_pct": 5.0,  "exit_cumulative_pct": 25, "label": "Tier 1 (+5%)"},
    {"gain_pct": 8.0,  "exit_cumulative_pct": 50, "label": "Tier 2 (+8%)"},
    {"gain_pct": 12.0, "exit_cumulative_pct": 75, "label": "Tier 3 (+12%)"},
    # Remaining 25% rides with trailing stop until stopped out
]


class PartialExitManager:
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

    def register_position(self, bot_id: str, ticker: str, entry_price: float, quantity: float, side: str = "LONG"):
        """Register a position for partial exit tracking."""
        key = self._key(bot_id, ticker)
        self.state[key] = {
            "entry_price": entry_price,
            "original_qty": quantity,
            "remaining_qty": quantity,
            "side": side.upper(),
            "exited_pct": 0,
            "exits": [],
        }
        self._save()

    def check_position(self, bot_id: str, ticker: str, current_price: float) -> list:
        """Check if any partial exit tiers are triggered. Returns list of actions."""
        key = self._key(bot_id, ticker)
        pos = self.state.get(key)
        if not pos:
            return []

        entry = pos["entry_price"]
        side = pos["side"]
        original_qty = pos["original_qty"]

        if side == "LONG":
            gain_pct = ((current_price - entry) / entry) * 100
        else:
            gain_pct = ((entry - current_price) / entry) * 100

        if gain_pct <= 0:
            return []

        actions = []
        for tier in EXIT_TIERS:
            if gain_pct >= tier["gain_pct"] and pos["exited_pct"] < tier["exit_cumulative_pct"]:
                # How much more to exit
                additional_pct = tier["exit_cumulative_pct"] - pos["exited_pct"]
                exit_qty = original_qty * (additional_pct / 100)

                if exit_qty > pos["remaining_qty"]:
                    exit_qty = pos["remaining_qty"]

                if exit_qty <= 0:
                    continue

                actions.append({
                    "action": "PARTIAL_EXIT",
                    "tier": tier["label"],
                    "gain_pct": round(gain_pct, 2),
                    "exit_pct": additional_pct,
                    "exit_qty": round(exit_qty, 8),
                    "price": current_price,
                    "reason": f"{tier['label']} hit at {gain_pct:.1f}% gain",
                })

                pos["exited_pct"] = tier["exit_cumulative_pct"]
                pos["remaining_qty"] -= exit_qty
                pos["exits"].append({
                    "tier": tier["label"],
                    "qty": exit_qty,
                    "price": current_price,
                    "timestamp": time.time(),
                })

        if actions:
            self._save()

        return actions

    def remove_position(self, bot_id: str, ticker: str):
        key = self._key(bot_id, ticker)
        self.state.pop(key, None)
        self._save()

    def status(self) -> dict:
        return dict(self.state)


if __name__ == "__main__":
    pem = PartialExitManager()
    print(json.dumps(pem.status(), indent=2))
