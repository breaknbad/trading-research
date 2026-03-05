#!/usr/bin/env python3
"""
Crypto Cooldown Enforcer — 10-min same-ticker re-entry block.
Prevents revenge trading in 24/7 crypto markets.

Call can_trade() before ANY new entry. If the bot traded the same ticker
within the last 10 minutes, it's blocked.

Usage:
  from crypto_cooldown import CooldownEnforcer
  cd = CooldownEnforcer()
  if cd.can_trade("alfred", "BTC"):
      # proceed with trade
      cd.record_trade("alfred", "BTC")
  else:
      print(cd.time_remaining("alfred", "BTC"))
"""

import json
import os
import time
from datetime import datetime, timezone

COOLDOWN_SECONDS = 600  # 10 minutes
STATE_FILE = os.path.join(os.path.dirname(__file__), "cooldown_state.json")


class CooldownEnforcer:
    def __init__(self, state_file: str = STATE_FILE, cooldown_sec: int = COOLDOWN_SECONDS):
        self.state_file = state_file
        self.cooldown_sec = cooldown_sec
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

    def can_trade(self, bot_id: str, ticker: str) -> bool:
        """Check if this bot can trade this ticker (cooldown expired)."""
        key = self._key(bot_id, ticker)
        last_trade = self.state.get(key, 0)
        elapsed = time.time() - last_trade
        return elapsed >= self.cooldown_sec

    def record_trade(self, bot_id: str, ticker: str):
        """Record a trade — starts the cooldown timer."""
        key = self._key(bot_id, ticker)
        self.state[key] = time.time()
        self._save()

    def time_remaining(self, bot_id: str, ticker: str) -> int:
        """Seconds remaining on cooldown. 0 = can trade."""
        key = self._key(bot_id, ticker)
        last_trade = self.state.get(key, 0)
        elapsed = time.time() - last_trade
        remaining = max(0, self.cooldown_sec - elapsed)
        return int(remaining)

    def block_message(self, bot_id: str, ticker: str) -> str:
        """Human-readable block message."""
        remaining = self.time_remaining(bot_id, ticker)
        if remaining <= 0:
            return f"✅ {bot_id} can trade {ticker}."
        minutes = remaining // 60
        seconds = remaining % 60
        return (f"🚫 COOLDOWN: {bot_id} cannot trade {ticker} for "
                f"{minutes}m {seconds}s. 10-min same-ticker rule.")

    def cleanup(self, max_age_hours: int = 24):
        """Remove entries older than max_age_hours."""
        cutoff = time.time() - (max_age_hours * 3600)
        self.state = {k: v for k, v in self.state.items() if v > cutoff}
        self._save()


if __name__ == "__main__":
    import sys
    cd = CooldownEnforcer()

    if len(sys.argv) >= 4 and sys.argv[1] == "check":
        bot, ticker = sys.argv[2], sys.argv[3]
        print(cd.block_message(bot, ticker))
    elif len(sys.argv) >= 4 and sys.argv[1] == "record":
        bot, ticker = sys.argv[2], sys.argv[3]
        cd.record_trade(bot, ticker)
        print(f"Recorded trade: {bot} {ticker}. Cooldown started.")
    else:
        print("Usage:")
        print("  python3 crypto_cooldown.py check alfred BTC")
        print("  python3 crypto_cooldown.py record alfred BTC")
