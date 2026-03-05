#!/usr/bin/env python3
"""
Dead Bot Detection — Fleet health monitoring via Supabase heartbeat timestamps.

Each bot writes a heartbeat to Supabase every 5 min. If any bot's timestamp
is >10 min stale, other bots are alerted to take over critical functions.

Usage:
  from crypto_bot_health import BotHealth
  bh = BotHealth()
  bh.heartbeat("alfred")       # Write heartbeat
  status = bh.check_fleet()    # Check all bots
  dead = bh.get_dead_bots()    # List of unresponsive bots
"""

import json
import os
import time
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
    "Prefer": "return=representation",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
DEAD_THRESHOLD_SEC = 600  # 10 minutes
LOCAL_STATE = os.path.join(os.path.dirname(__file__), "data", "bot_health.json")


class BotHealth:
    def __init__(self):
        self.use_supabase = bool(SUPABASE_KEY)

    def heartbeat(self, bot_id: str):
        """Write heartbeat timestamp."""
        now = time.time()
        data = {
            "bot_id": bot_id.lower(),
            "last_heartbeat": now,
            "last_heartbeat_iso": datetime.now(timezone.utc).isoformat(),
            "status": "ALIVE",
        }

        if self.use_supabase:
            try:
                # Upsert
                requests.post(
                    f"{SUPABASE_URL}/rest/v1/bot_health",
                    json=data,
                    headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
                    timeout=5,
                )
            except Exception:
                pass

        # Always write local too
        self._write_local(bot_id, data)

    def _write_local(self, bot_id: str, data: dict):
        os.makedirs(os.path.dirname(LOCAL_STATE), exist_ok=True)
        state = {}
        if os.path.exists(LOCAL_STATE):
            try:
                with open(LOCAL_STATE) as f:
                    state = json.load(f)
            except Exception:
                pass
        state[bot_id.lower()] = data
        with open(LOCAL_STATE, "w") as f:
            json.dump(state, f, indent=2)

    def check_fleet(self) -> dict:
        """Check health of all bots."""
        now = time.time()
        results = {}

        for bot in BOTS:
            last_hb = self._get_last_heartbeat(bot)
            if last_hb is None:
                results[bot] = {"status": "UNKNOWN", "message": "No heartbeat recorded"}
            elif now - last_hb > DEAD_THRESHOLD_SEC:
                age_min = int((now - last_hb) / 60)
                results[bot] = {
                    "status": "DEAD",
                    "last_seen_min_ago": age_min,
                    "message": f"🚨 {bot} last heartbeat {age_min} min ago — UNRESPONSIVE",
                }
            else:
                age_sec = int(now - last_hb)
                results[bot] = {
                    "status": "ALIVE",
                    "last_seen_sec_ago": age_sec,
                    "message": f"✅ {bot} alive ({age_sec}s ago)",
                }

        return results

    def _get_last_heartbeat(self, bot_id: str) -> float:
        """Get last heartbeat timestamp for a bot."""
        if self.use_supabase:
            try:
                r = requests.get(
                    f"{SUPABASE_URL}/rest/v1/bot_health",
                    params={"bot_id": f"eq.{bot_id}", "select": "last_heartbeat"},
                    headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
                    timeout=5,
                )
                if r.status_code == 200 and r.json():
                    return float(r.json()[0]["last_heartbeat"])
            except Exception:
                pass

        # Local fallback
        if os.path.exists(LOCAL_STATE):
            try:
                with open(LOCAL_STATE) as f:
                    state = json.load(f)
                if bot_id in state:
                    return float(state[bot_id]["last_heartbeat"])
            except Exception:
                pass
        return None

    def get_dead_bots(self) -> list:
        """Return list of unresponsive bots."""
        fleet = self.check_fleet()
        return [bot for bot, info in fleet.items() if info["status"] == "DEAD"]

    def should_takeover_stops(self, my_bot_id: str) -> list:
        """Check if I need to take over stop enforcement for dead bots."""
        dead = self.get_dead_bots()
        # Don't take over your own stops
        return [bot for bot in dead if bot != my_bot_id.lower()]


if __name__ == "__main__":
    import sys
    bh = BotHealth()
    if len(sys.argv) > 1 and sys.argv[1] == "--heartbeat":
        bot = sys.argv[2] if len(sys.argv) > 2 else "alfred"
        bh.heartbeat(bot)
        print(f"Heartbeat recorded for {bot}")
    else:
        fleet = bh.check_fleet()
        for bot, info in fleet.items():
            print(info["message"])
