#!/usr/bin/env python3
"""
Drawdown-Adaptive Risk Budget for Crypto.

Continuous throttle that adjusts risk sizing based on equity curve position:
  At equity high:      risk_mult = 1.25 (aggressive, riding momentum)
  0 to -2% drawdown:   risk_mult = 1.0  (standard)
  -2% to -3% drawdown: risk_mult = 0.75 (tightening)
  -3% to -5% drawdown: risk_mult = 0.5  (defensive)
  Beyond -5%:          risk_mult = 0.25 (survival mode, kill switch territory)

Applied as a multiplier to position sizes and stop distances.

Usage:
  from crypto_drawdown_throttle import DrawdownThrottle
  dt = DrawdownThrottle(bot_id="alfred", starting_capital=25000)
  mult = dt.get_risk_multiplier()  # 0.25 to 1.25
"""

import json
import os
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

STATE_FILE = os.path.join(os.path.dirname(__file__), "drawdown_throttle_state.json")

THROTTLE_TIERS = [
    (-5.0, 0.25),   # Beyond -5%: survival mode
    (-3.0, 0.50),   # -3% to -5%: defensive
    (-2.0, 0.75),   # -2% to -3%: tightening
    (0.0,  1.00),   # 0% to -2%: standard
]
AT_HIGH_MULTIPLIER = 1.25


class DrawdownThrottle:
    def __init__(self, bot_id: str, starting_capital: float = 25000.0):
        self.bot_id = bot_id.lower()
        self.starting_capital = starting_capital
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    return data.get(self.bot_id, {})
            except Exception:
                pass
        return {}

    def _save_state(self):
        all_state = {}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    all_state = json.load(f)
            except Exception:
                pass
        all_state[self.bot_id] = self.state
        with open(STATE_FILE, "w") as f:
            json.dump(all_state, f, indent=2)

    def _get_current_value(self) -> float:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/crypto_portfolio_snapshots",
                params={
                    "bot_id": f"eq.{self.bot_id}",
                    "select": "total_value",
                    "order": "timestamp.desc",
                    "limit": "1",
                },
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200 and r.json():
                return float(r.json()[0]["total_value"])
        except Exception:
            pass
        return self.starting_capital

    def update_high_water(self, current_value: float):
        hwm = self.state.get("high_water_mark", self.starting_capital)
        if current_value > hwm:
            self.state["high_water_mark"] = current_value
            self._save_state()

    def get_risk_multiplier(self) -> dict:
        current = self._get_current_value()
        hwm = self.state.get("high_water_mark", self.starting_capital)
        self.update_high_water(current)

        # Recalc after possible HWM update
        hwm = self.state.get("high_water_mark", self.starting_capital)

        if hwm <= 0:
            return {"multiplier": 0.25, "drawdown_pct": 0, "tier": "ERROR"}

        drawdown_pct = ((current - hwm) / hwm) * 100  # Negative when in drawdown

        # At equity high
        if drawdown_pct >= 0:
            return {
                "multiplier": AT_HIGH_MULTIPLIER,
                "drawdown_pct": 0.0,
                "tier": "AT_HIGH",
                "current": round(current, 2),
                "high_water": round(hwm, 2),
            }

        # Find tier
        multiplier = 0.25  # Default to worst
        tier_name = "SURVIVAL"
        for threshold, mult in THROTTLE_TIERS:
            if drawdown_pct >= threshold:
                multiplier = mult
                tier_name = f"DD_{abs(threshold):.0f}pct"
                break

        return {
            "multiplier": multiplier,
            "drawdown_pct": round(drawdown_pct, 2),
            "tier": tier_name,
            "current": round(current, 2),
            "high_water": round(hwm, 2),
        }


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    dt = DrawdownThrottle(bot)
    result = dt.get_risk_multiplier()
    print(json.dumps(result, indent=2))
