#!/usr/bin/env python3
"""
Dynamic Kelly Criterion Position Sizer for Crypto.

Calculates optimal position size using Kelly formula:
  f = (bp - q) / b
  where b = avg_win/avg_loss, p = win_rate, q = 1-win_rate

Uses actual trade history to feed the formula. As edge improves,
size automatically increases. As edge degrades, size shrinks.

Half-Kelly used by default (more conservative, smoother equity curve).

Usage:
  from crypto_kelly_sizer import KellySizer
  ks = KellySizer(bot_id="alfred")
  size = ks.optimal_size(portfolio_value=25000, conviction=7)
"""

import json
import os
import requests
from typing import Optional

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

# Kelly fraction — 0.5 = half-Kelly (industry standard for smoothing)
KELLY_FRACTION = 0.5
MIN_TRADES_FOR_KELLY = 20  # Need enough data before trusting Kelly
MIN_SIZE_PCT = 0.01        # 1% floor
MAX_SIZE_PCT = 0.15        # 15% ceiling (even if Kelly says more)
FALLBACK_SIZE_PCT = 0.03   # 3% if insufficient trade history


class KellySizer:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id.lower()
        self._stats_cache = None

    def _get_trade_stats(self) -> dict:
        """Fetch win rate and avg win/loss from trade history."""
        if self._stats_cache:
            return self._stats_cache

        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/crypto_trades",
                params={
                    "bot_id": f"eq.{self.bot_id}",
                    "select": "pnl",
                    "pnl": "not.is.null",
                    "order": "timestamp.desc",
                    "limit": "100",
                },
                headers=HEADERS,
                timeout=10,
            )
            if r.status_code != 200:
                return {}

            trades = r.json()
            if len(trades) < MIN_TRADES_FOR_KELLY:
                return {"insufficient": True, "count": len(trades)}

            pnls = [float(t["pnl"]) for t in trades if t.get("pnl") is not None]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            if not wins or not losses:
                return {"insufficient": True, "count": len(pnls)}

            stats = {
                "win_rate": len(wins) / len(pnls),
                "avg_win": sum(wins) / len(wins),
                "avg_loss": abs(sum(losses) / len(losses)),
                "total_trades": len(pnls),
                "insufficient": False,
            }
            self._stats_cache = stats
            return stats

        except Exception:
            return {"insufficient": True}

    def kelly_fraction_calc(self) -> float:
        """Calculate Kelly fraction from trade history."""
        stats = self._get_trade_stats()
        if stats.get("insufficient", True):
            return FALLBACK_SIZE_PCT

        p = stats["win_rate"]
        q = 1 - p
        b = stats["avg_win"] / stats["avg_loss"] if stats["avg_loss"] > 0 else 1

        kelly = (b * p - q) / b

        # Negative Kelly = no edge, use minimum
        if kelly <= 0:
            return MIN_SIZE_PCT

        # Apply half-Kelly
        adjusted = kelly * KELLY_FRACTION

        # Clamp to bounds
        return max(MIN_SIZE_PCT, min(MAX_SIZE_PCT, adjusted))

    def optimal_size(self, portfolio_value: float, conviction: int = 5) -> dict:
        """
        Calculate optimal position size in dollars.
        Conviction (1-10) scales the Kelly output.
        """
        base_kelly = self.kelly_fraction_calc()
        stats = self._get_trade_stats()

        # Conviction multiplier: 1=0.5x, 5=1.0x, 10=1.5x
        conviction_mult = 0.5 + (conviction - 1) * (1.0 / 9)
        adjusted_pct = base_kelly * conviction_mult
        adjusted_pct = max(MIN_SIZE_PCT, min(MAX_SIZE_PCT, adjusted_pct))

        size_dollars = portfolio_value * adjusted_pct

        return {
            "size_dollars": round(size_dollars, 2),
            "size_pct": round(adjusted_pct * 100, 2),
            "kelly_raw": round(base_kelly * 100, 2),
            "conviction": conviction,
            "conviction_multiplier": round(conviction_mult, 2),
            "trade_count": stats.get("total_trades", 0),
            "win_rate": round(stats.get("win_rate", 0) * 100, 1) if not stats.get("insufficient") else None,
            "method": "kelly" if not stats.get("insufficient") else "fallback",
        }


if __name__ == "__main__":
    import sys
    bot = sys.argv[1] if len(sys.argv) > 1 else "alfred"
    ks = KellySizer(bot)
    result = ks.optimal_size(25000, conviction=7)
    print(json.dumps(result, indent=2))
