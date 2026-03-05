#!/usr/bin/env python3
"""
Position Limits + Win-Streak Capital Deployment for Crypto.

Two functions:
1. Max 5 concurrent positions per bot. Hard cap, no exceptions.
2. Win-streak detection: 3+ consecutive wins → sizing boost of 25% (up to Kelly ceiling).

Usage:
  from crypto_position_limits import PositionLimits
  pl = PositionLimits(bot_id="alfred")
  pl.can_open_new()          # False if at 5 positions
  pl.streak_multiplier()     # 1.25 if on 3+ win streak, else 1.0
"""

import json
import os
import requests

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

MAX_POSITIONS = 5
WIN_STREAK_THRESHOLD = 3
WIN_STREAK_BOOST = 1.25
MAX_BOOST = 1.50  # Absolute ceiling on streak multiplier


class PositionLimits:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id.lower()

    def _get_open_count(self) -> int:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/crypto_positions",
                params={
                    "bot_id": f"eq.{self.bot_id}",
                    "status": "eq.OPEN",
                    "select": "id",
                },
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                return len(r.json())
        except Exception:
            pass
        return 0

    def _get_recent_pnls(self, limit: int = 10) -> list:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/crypto_trades",
                params={
                    "bot_id": f"eq.{self.bot_id}",
                    "pnl": "not.is.null",
                    "select": "pnl",
                    "order": "timestamp.desc",
                    "limit": str(limit),
                },
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                return [float(t["pnl"]) for t in r.json() if t.get("pnl") is not None]
        except Exception:
            pass
        return []

    def can_open_new(self) -> dict:
        count = self._get_open_count()
        allowed = count < MAX_POSITIONS
        return {
            "allowed": allowed,
            "current_positions": count,
            "max_positions": MAX_POSITIONS,
            "reason": f"{'OK' if allowed else f'AT LIMIT — {count}/{MAX_POSITIONS} positions open. Close one before opening new.'}",
        }

    def streak_multiplier(self) -> dict:
        pnls = self._get_recent_pnls()
        if not pnls:
            return {"multiplier": 1.0, "streak": 0, "type": "none"}

        # Count consecutive wins from most recent
        win_streak = 0
        for pnl in pnls:
            if pnl > 0:
                win_streak += 1
            else:
                break

        # Count consecutive losses
        loss_streak = 0
        for pnl in pnls:
            if pnl < 0:
                loss_streak += 1
            else:
                break

        if win_streak >= WIN_STREAK_THRESHOLD:
            # Progressive boost: 3 wins = 1.25x, 4 = 1.35x, 5+ = 1.50x
            boost = WIN_STREAK_BOOST + (win_streak - WIN_STREAK_THRESHOLD) * 0.10
            multiplier = min(boost, MAX_BOOST)
            return {
                "multiplier": round(multiplier, 2),
                "streak": win_streak,
                "type": "WIN_STREAK",
                "message": f"🔥 {win_streak} consecutive wins. Sizing boosted to {multiplier}x.",
            }
        else:
            return {
                "multiplier": 1.0,
                "streak": max(win_streak, -loss_streak),
                "type": "NORMAL",
            }

    def full_check(self) -> dict:
        """Combined check: position limit + streak multiplier."""
        pos = self.can_open_new()
        streak = self.streak_multiplier()
        return {
            **pos,
            "streak_multiplier": streak["multiplier"],
            "streak_info": streak,
        }


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    pl = PositionLimits(bot)
    print(json.dumps(pl.full_check(), indent=2))
