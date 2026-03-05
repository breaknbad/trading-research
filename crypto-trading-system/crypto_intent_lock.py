#!/usr/bin/env python3
"""
Trade Intent Lock — Prevents double-entry race conditions across bots.

Before executing any trade, bot writes intent to Supabase. Gate checks
all pending intents. If another bot already intends to enter the same
ticker on the same side, the second bot is blocked.

Intents expire after 2 minutes (trade should be committed or abandoned by then).

Usage:
  from crypto_intent_lock import IntentLock
  il = IntentLock()
  lock = il.acquire("alfred", "BTC", "LONG", 2500)
  if lock["acquired"]:
      # execute trade
      il.release("alfred", "BTC")
  else:
      # another bot already intending this trade
      print(lock["blocked_by"])
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

INTENT_EXPIRY_SEC = 120  # 2 minutes
# Fallback to local file if Supabase is unavailable
LOCAL_LOCK_FILE = os.path.join(os.path.dirname(__file__), "data", "intent_locks.json")


class IntentLock:
    def __init__(self):
        self.use_supabase = bool(SUPABASE_KEY)

    def _get_active_intents(self, ticker: str, side: str) -> list:
        """Get active intents for a ticker+side from Supabase or local."""
        cutoff = time.time() - INTENT_EXPIRY_SEC

        if self.use_supabase:
            try:
                r = requests.get(
                    f"{SUPABASE_URL}/rest/v1/fleet_intents",
                    params={
                        "ticker": f"eq.{ticker.upper()}",
                        "side": f"eq.{side.upper()}",
                        "select": "*",
                    },
                    headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
                    timeout=5,
                )
                if r.status_code == 200:
                    intents = r.json()
                    # Filter to non-expired
                    active = []
                    for i in intents:
                        ts = i.get("created_at_epoch", 0)
                        if ts > cutoff:
                            active.append(i)
                    return active
            except Exception:
                pass

        # Fallback: local file
        return self._get_local_intents(ticker, side, cutoff)

    def _get_local_intents(self, ticker: str, side: str, cutoff: float) -> list:
        if not os.path.exists(LOCAL_LOCK_FILE):
            return []
        try:
            with open(LOCAL_LOCK_FILE) as f:
                all_intents = json.load(f)
            return [i for i in all_intents if
                    i["ticker"] == ticker.upper() and
                    i["side"] == side.upper() and
                    i.get("created_at_epoch", 0) > cutoff]
        except Exception:
            return []

    def _write_local_intent(self, intent: dict):
        os.makedirs(os.path.dirname(LOCAL_LOCK_FILE), exist_ok=True)
        intents = []
        if os.path.exists(LOCAL_LOCK_FILE):
            try:
                with open(LOCAL_LOCK_FILE) as f:
                    intents = json.load(f)
            except Exception:
                pass
        # Clean expired
        cutoff = time.time() - INTENT_EXPIRY_SEC
        intents = [i for i in intents if i.get("created_at_epoch", 0) > cutoff]
        intents.append(intent)
        with open(LOCAL_LOCK_FILE, "w") as f:
            json.dump(intents, f, indent=2)

    def acquire(self, bot_id: str, ticker: str, side: str, notional: float) -> dict:
        """Attempt to acquire an intent lock. Returns {acquired, blocked_by} if conflict."""
        ticker = ticker.upper()
        side = side.upper()
        bot_id = bot_id.lower()

        # Check existing intents
        active = self._get_active_intents(ticker, side)
        conflicts = [i for i in active if i.get("bot_id") != bot_id]

        if conflicts:
            return {
                "acquired": False,
                "blocked_by": [c.get("bot_id") for c in conflicts],
                "message": f"BLOCKED — {conflicts[0].get('bot_id')} already intending {side} {ticker}",
            }

        # Write intent
        intent = {
            "bot_id": bot_id,
            "ticker": ticker,
            "side": side,
            "notional": notional,
            "created_at_epoch": time.time(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.use_supabase:
            try:
                r = requests.post(
                    f"{SUPABASE_URL}/rest/v1/fleet_intents",
                    json=intent,
                    headers=HEADERS,
                    timeout=5,
                )
                if r.status_code in (200, 201):
                    return {"acquired": True, "intent": intent}
            except Exception:
                pass

        # Fallback: local
        self._write_local_intent(intent)
        return {"acquired": True, "intent": intent}

    def release(self, bot_id: str, ticker: str):
        """Release an intent lock after trade commits or abandons."""
        if self.use_supabase:
            try:
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/fleet_intents",
                    params={"bot_id": f"eq.{bot_id.lower()}", "ticker": f"eq.{ticker.upper()}"},
                    headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
                    timeout=5,
                )
            except Exception:
                pass

        # Also clean local
        if os.path.exists(LOCAL_LOCK_FILE):
            try:
                with open(LOCAL_LOCK_FILE) as f:
                    intents = json.load(f)
                intents = [i for i in intents if not (i["bot_id"] == bot_id.lower() and i["ticker"] == ticker.upper())]
                with open(LOCAL_LOCK_FILE, "w") as f:
                    json.dump(intents, f, indent=2)
            except Exception:
                pass


if __name__ == "__main__":
    il = IntentLock()
    # Test
    result = il.acquire("alfred", "BTC", "LONG", 2500)
    print(json.dumps(result, indent=2, default=str))
