#!/usr/bin/env python3
"""Timing filter — blocks entries during volatile open/close windows."""

from datetime import datetime, timezone, timedelta

# Eastern Time offset (handles EST only; for DST-aware, use zoneinfo on 3.9+)
try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-5))


def _now_et() -> datetime:
    return datetime.now(ET)


def check_timing(action: str, premarket_score: float = None) -> dict:
    """Check if a trade action is allowed right now.

    Args:
        action: 'BUY' or 'SELL'
        premarket_score: pre-market scanner score (0-100), optional

    Returns:
        dict with allowed, reason, minutes_until_allowed
    """
    action = action.upper()

    # Always allow exits
    if action in ("SELL", "EXIT", "CLOSE"):
        return {"allowed": True, "reason": "Exits always allowed", "minutes_until_allowed": 0}

    now = _now_et()
    t = now.time()
    market_open = datetime.strptime("09:30", "%H:%M").time()
    early_block_end = datetime.strptime("09:35", "%H:%M").time()
    late_block_start = datetime.strptime("15:55", "%H:%M").time()
    market_close = datetime.strptime("16:00", "%H:%M").time()

    # Pre-market (before 9:30)
    if t < market_open:
        mins = int((datetime.combine(now.date(), market_open) - datetime.combine(now.date(), t)).total_seconds() / 60)
        return {"allowed": False, "reason": "Market not open yet", "minutes_until_allowed": mins}

    # Post-market (after 4:00)
    if t >= market_close:
        return {"allowed": False, "reason": "Market closed", "minutes_until_allowed": 0}

    # First 5 minutes block (9:30-9:35)
    if t < early_block_end:
        mins = int((datetime.combine(now.date(), early_block_end) - datetime.combine(now.date(), t)).total_seconds() / 60)

        # Exception: premarket score > 90 allows entry at 9:35 (i.e., from 9:35:00)
        if premarket_score is not None and premarket_score > 90 and t >= datetime.strptime("09:35", "%H:%M").time():
            return {"allowed": True, "reason": f"Pre-market score {premarket_score} override", "minutes_until_allowed": 0}

        return {
            "allowed": False,
            "reason": f"Opening volatility window (9:30-9:35). {f'Score {premarket_score} < 90 threshold' if premarket_score else 'No pre-market score'}",
            "minutes_until_allowed": max(mins, 1),
        }

    # Last 5 minutes block (3:55-4:00)
    if t >= late_block_start:
        return {
            "allowed": False,
            "reason": "Closing volatility window (3:55-4:00)",
            "minutes_until_allowed": 0,
        }

    return {"allowed": True, "reason": "Within trading window", "minutes_until_allowed": 0}


if __name__ == "__main__":
    print(check_timing("BUY"))
    print(check_timing("SELL"))
    print(check_timing("BUY", premarket_score=95))
