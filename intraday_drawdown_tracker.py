#!/usr/bin/env python3
"""Intraday drawdown tracker — tracks high-water marks and max adverse excursion per position."""

import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CACHE_DIR

MAE_STATE_FILE = os.path.join(CACHE_DIR, "mae_state.json")


def _load_state():
    if os.path.exists(MAE_STATE_FILE):
        with open(MAE_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state):
    os.makedirs(os.path.dirname(MAE_STATE_FILE), exist_ok=True)
    with open(MAE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_position_hwm(ticker: str, current_price: float, entry_price: float, side: str = "long") -> dict:
    """Update high-water mark for a position, return MAE and current drawdown stats.

    Args:
        ticker: Stock symbol
        current_price: Current market price
        entry_price: Original entry price
        side: 'long' or 'short'

    Returns:
        {mae_pct, current_drawdown_pct, hwm_price}
    """
    state = _load_state()
    key = ticker.upper()

    if key not in state:
        state[key] = {
            "entry_price": entry_price,
            "side": side,
            "hwm_price": current_price if side == "long" else current_price,
            "mae_pct": 0.0,
            "last_update": time.time(),
        }

    pos = state[key]
    pos["entry_price"] = entry_price
    pos["side"] = side

    if side == "long":
        # HWM is the highest price seen
        if current_price > pos["hwm_price"]:
            pos["hwm_price"] = current_price
        # Current drawdown from HWM
        current_drawdown_pct = ((pos["hwm_price"] - current_price) / pos["hwm_price"]) * 100 if pos["hwm_price"] > 0 else 0.0
        # MAE: deepest drawdown from entry
        adverse = ((entry_price - current_price) / entry_price) * 100 if entry_price > 0 else 0.0
        adverse = max(adverse, 0.0)  # only negative moves count
    else:
        # Short: HWM is the lowest price seen
        if current_price < pos["hwm_price"] or pos["hwm_price"] == 0:
            pos["hwm_price"] = current_price
        current_drawdown_pct = ((current_price - pos["hwm_price"]) / pos["hwm_price"]) * 100 if pos["hwm_price"] > 0 else 0.0
        adverse = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
        adverse = max(adverse, 0.0)

    if adverse > pos["mae_pct"]:
        pos["mae_pct"] = adverse

    pos["last_update"] = time.time()
    _save_state(state)

    return {
        "mae_pct": round(pos["mae_pct"], 4),
        "current_drawdown_pct": round(current_drawdown_pct, 4),
        "hwm_price": round(pos["hwm_price"], 4),
    }


def get_mae_report() -> list:
    """Return MAE stats for all tracked positions."""
    state = _load_state()
    report = []
    for ticker, pos in state.items():
        report.append({
            "ticker": ticker,
            "side": pos["side"],
            "entry_price": pos["entry_price"],
            "hwm_price": pos["hwm_price"],
            "mae_pct": round(pos["mae_pct"], 4),
            "last_update": pos["last_update"],
        })
    return sorted(report, key=lambda x: x["mae_pct"], reverse=True)


def clear_position(ticker: str):
    """Remove a closed position from tracking."""
    state = _load_state()
    state.pop(ticker.upper(), None)
    _save_state(state)


if __name__ == "__main__":
    # Demo
    print(update_position_hwm("NVDA", 130.0, 125.0, "long"))
    print(update_position_hwm("NVDA", 128.0, 125.0, "long"))
    print(update_position_hwm("NVDA", 132.0, 125.0, "long"))
    print(get_mae_report())
