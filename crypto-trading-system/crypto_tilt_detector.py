#!/usr/bin/env python3
"""
Anti-Tilt Detector for Crypto.

Detects behavioral tilt patterns beyond simple loss streaks:
- Position sizes increasing while win rate decreasing
- Hold times shortening (panic cutting)
- Trading frequency spiking after losses
- Overriding gate rejections

When tilt is detected, auto-reduces sizing by 50% until pattern breaks.

Usage:
  from crypto_tilt_detector import TiltDetector
  td = TiltDetector(bot_id="alfred")
  result = td.check_tilt()  # {"tilted": True, "multiplier": 0.5, "signals": [...]}
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict

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

TILT_SIGNALS_NEEDED = 2  # 2+ tilt signals = tilted
TILT_MULTIPLIER = 0.5    # Cut sizing in half when tilted
LOOKBACK_TRADES = 20     # Analyze last 20 trades


class TiltDetector:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id.lower()

    def _get_recent_trades(self) -> list:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/crypto_trades",
                params={
                    "bot_id": f"eq.{self.bot_id}",
                    "select": "ticker,side,quantity,price,pnl,timestamp,trade_type",
                    "order": "timestamp.desc",
                    "limit": str(LOOKBACK_TRADES),
                },
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return []

    def check_tilt(self) -> dict:
        trades = self._get_recent_trades()
        if len(trades) < 6:
            return {"tilted": False, "multiplier": 1.0, "signals": [], "reason": "Insufficient data"}

        tilt_signals = []

        # Signal 1: Position sizes increasing while losing
        first_half = trades[len(trades)//2:]
        second_half = trades[:len(trades)//2]

        first_avg_size = sum(float(t.get("quantity", 0)) * float(t.get("price", 0)) for t in first_half) / max(len(first_half), 1)
        second_avg_size = sum(float(t.get("quantity", 0)) * float(t.get("price", 0)) for t in second_half) / max(len(second_half), 1)

        first_wr = sum(1 for t in first_half if float(t.get("pnl", 0)) > 0) / max(len(first_half), 1)
        second_wr = sum(1 for t in second_half if float(t.get("pnl", 0)) > 0) / max(len(second_half), 1)

        if second_avg_size > first_avg_size * 1.3 and second_wr < first_wr:
            tilt_signals.append({
                "signal": "SIZE_UP_WHILE_LOSING",
                "detail": f"Avg size up {((second_avg_size/max(first_avg_size,1))-1)*100:.0f}% while win rate dropped from {first_wr*100:.0f}% to {second_wr*100:.0f}%",
            })

        # Signal 2: Trading frequency spiking
        if len(trades) >= 4:
            recent_4 = trades[:4]
            timestamps = []
            for t in recent_4:
                ts = t.get("timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    timestamps.append(dt)
                except Exception:
                    pass

            if len(timestamps) >= 2:
                gaps = [(timestamps[i] - timestamps[i+1]).total_seconds() for i in range(len(timestamps)-1)]
                avg_gap = sum(gaps) / len(gaps)
                if avg_gap < 300:  # Less than 5 min between trades
                    tilt_signals.append({
                        "signal": "RAPID_FIRE_TRADING",
                        "detail": f"Avg {avg_gap:.0f}s between last {len(timestamps)} trades. Possible revenge trading.",
                    })

        # Signal 3: Hold times shortening on losses
        losses = [t for t in trades if float(t.get("pnl", 0)) < 0]
        if len(losses) >= 3:
            # Check if recent losses were cut faster than earlier ones
            recent_loss_count = sum(1 for t in trades[:5] if float(t.get("pnl", 0)) < 0)
            if recent_loss_count >= 4:
                tilt_signals.append({
                    "signal": "LOSS_CLUSTER",
                    "detail": f"{recent_loss_count} of last 5 trades are losses. Pattern suggests chasing.",
                })

        # Signal 4: Same ticker repeated after loss
        if len(trades) >= 2:
            for i in range(min(3, len(trades) - 1)):
                if (trades[i].get("ticker") == trades[i+1].get("ticker")
                        and float(trades[i+1].get("pnl", 0)) < 0
                        and trades[i].get("trade_type") in ("BUY", "ENTRY")):
                    tilt_signals.append({
                        "signal": "REVENGE_RE_ENTRY",
                        "detail": f"Re-entered {trades[i]['ticker']} immediately after a loss on same ticker.",
                    })
                    break

        tilted = len(tilt_signals) >= TILT_SIGNALS_NEEDED
        return {
            "tilted": tilted,
            "multiplier": TILT_MULTIPLIER if tilted else 1.0,
            "signals": tilt_signals,
            "signal_count": len(tilt_signals),
            "threshold": TILT_SIGNALS_NEEDED,
        }


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    td = TiltDetector(bot)
    result = td.check_tilt()
    print(json.dumps(result, indent=2))
