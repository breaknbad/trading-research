#!/usr/bin/env python3
"""
Regime Transition Hedging for Crypto.

When regime shifts from AGGRESSIVE → CAUTIOUS or CAUTIOUS → DEFENSIVE,
proactively hedge existing positions rather than waiting for stops.

Actions on regime downshift:
  AGGRESSIVE → CAUTIOUS: Trim all positions to 75%. Tighten stops to 1.5%.
  CAUTIOUS → DEFENSIVE: Trim to 50%. Tighten stops to 1%. No new entries.
  DEFENSIVE → EXTREME_FEAR: Close all except highest conviction. Max 1 position.

Usage:
  from crypto_regime_hedge import RegimeHedger
  rh = RegimeHedger()
  actions = rh.check_transition(previous_regime, current_regime, positions)
"""

import json
import os
from datetime import datetime, timezone

STATE_FILE = os.path.join(os.path.dirname(__file__), "regime_hedge_state.json")

REGIME_ORDER = ["EXTREME_FEAR", "DEFENSIVE", "CAUTIOUS", "NEUTRAL", "AGGRESSIVE", "EXTREME_GREED"]

TRANSITION_RULES = {
    "AGGRESSIVE→CAUTIOUS": {
        "trim_pct": 25,
        "new_stop_pct": 1.5,
        "new_entries": True,
        "max_positions": 5,
        "message": "Regime cooling. Trimming 25%, tightening stops to 1.5%.",
    },
    "CAUTIOUS→DEFENSIVE": {
        "trim_pct": 50,
        "new_stop_pct": 1.0,
        "new_entries": False,
        "max_positions": 3,
        "message": "Regime shifting defensive. Trimming 50%, no new entries.",
    },
    "DEFENSIVE→EXTREME_FEAR": {
        "trim_pct": 75,
        "new_stop_pct": 0.75,
        "new_entries": False,
        "max_positions": 1,
        "message": "🚨 EXTREME FEAR. Closing most positions. Keep only highest conviction.",
    },
    "NEUTRAL→DEFENSIVE": {
        "trim_pct": 30,
        "new_stop_pct": 1.5,
        "new_entries": True,
        "max_positions": 4,
        "message": "Skipped cautious, going straight to defensive. Trimming 30%.",
    },
    "AGGRESSIVE→DEFENSIVE": {
        "trim_pct": 50,
        "new_stop_pct": 1.0,
        "new_entries": False,
        "max_positions": 3,
        "message": "⚠️ Sharp regime drop. Aggressive trimming.",
    },
}


class RegimeHedger:
    def __init__(self):
        self.state = self._load()

    def _load(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"last_regime": None, "transitions": []}

    def _save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _regime_rank(self, regime: str) -> int:
        try:
            return REGIME_ORDER.index(regime.upper())
        except ValueError:
            return 3  # Default to NEUTRAL

    def check_transition(self, previous_regime: str, current_regime: str, positions: list = None) -> dict:
        """Check if regime transition requires hedging action."""
        prev_rank = self._regime_rank(previous_regime)
        curr_rank = self._regime_rank(current_regime)

        # Upshift = no hedge needed (expanding)
        if curr_rank >= prev_rank:
            return {"action": "NONE", "reason": "Regime stable or improving"}

        # Downshift — find matching rule
        key = f"{previous_regime.upper()}→{current_regime.upper()}"
        rule = TRANSITION_RULES.get(key)

        if not rule:
            # Generic downshift
            severity = prev_rank - curr_rank
            rule = {
                "trim_pct": min(25 * severity, 75),
                "new_stop_pct": max(2.0 - severity * 0.5, 0.75),
                "new_entries": severity < 2,
                "max_positions": max(5 - severity, 1),
                "message": f"Regime downshift ({severity} levels). Adjusting.",
            }

        # Generate specific actions for each position
        actions = []
        if positions:
            # Sort by conviction (highest first) to keep best positions
            sorted_pos = sorted(positions, key=lambda p: float(p.get("conviction", 5)), reverse=True)

            for i, pos in enumerate(sorted_pos):
                if i >= rule["max_positions"]:
                    actions.append({
                        "ticker": pos.get("ticker"),
                        "bot": pos.get("bot_id"),
                        "action": "CLOSE",
                        "reason": f"Exceeds max positions ({rule['max_positions']}) for {current_regime} regime",
                    })
                else:
                    actions.append({
                        "ticker": pos.get("ticker"),
                        "bot": pos.get("bot_id"),
                        "action": "TRIM",
                        "trim_pct": rule["trim_pct"],
                        "new_stop_pct": rule["new_stop_pct"],
                        "reason": rule["message"],
                    })

        # Log transition
        self.state["transitions"].append({
            "from": previous_regime,
            "to": current_regime,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions_count": len(actions),
        })
        self.state["transitions"] = self.state["transitions"][-50:]
        self.state["last_regime"] = current_regime
        self._save()

        return {
            "action": "HEDGE",
            "transition": key,
            "rule": rule,
            "position_actions": actions,
            "message": rule["message"],
        }


if __name__ == "__main__":
    rh = RegimeHedger()
    # Example: AGGRESSIVE → DEFENSIVE
    result = rh.check_transition("AGGRESSIVE", "DEFENSIVE", [
        {"ticker": "BTC", "bot_id": "alfred", "conviction": 8},
        {"ticker": "ETH", "bot_id": "alfred", "conviction": 6},
        {"ticker": "SOL", "bot_id": "alfred", "conviction": 4},
        {"ticker": "DOGE", "bot_id": "alfred", "conviction": 3},
    ])
    print(json.dumps(result, indent=2))
