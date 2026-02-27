"""
partial_exit_manager.py - Configurable partial profit-taking manager.
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
STATE_FILE = os.path.join(CACHE_DIR, "partial_state.json")

# Profiles: list of (gain_pct_threshold, sell_fraction_of_original)
PROFILES = {
    "default": [
        {"gain_pct": 3.0, "sell_frac": 0.33, "label": "+3% sell 33%"},
        {"gain_pct": 5.0, "sell_frac": 0.33, "label": "+5% sell 33%"},
        # Remaining rides with trailing stop
    ],
    "momentum": [
        {"gain_pct": 5.0,  "sell_frac": 0.25, "label": "+5% sell 25%"},
        {"gain_pct": 8.0,  "sell_frac": 0.25, "label": "+8% sell 25%"},
        {"gain_pct": 12.0, "sell_frac": 0.25, "label": "+12% sell 25%"},
    ],
    "rotation": [
        {"gain_pct": 2.0, "sell_frac": 0.33, "label": "+2% sell 33%"},
        {"gain_pct": 4.0, "sell_frac": 0.33, "label": "+4% sell 33%"},
    ],
}


def _load_state():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_state(state):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_partials(ticker, entry_price, current_price, shares_held, profile="default"):
    """
    Check if any partial exit rules are triggered.

    Returns: {action: str, shares_to_sell: int, reason: str, remaining: int, gain_pct: float}
    """
    if entry_price <= 0 or current_price <= 0 or shares_held <= 0:
        return {"action": "HOLD", "shares_to_sell": 0, "reason": "Invalid inputs", "remaining": shares_held, "gain_pct": 0.0}

    gain_pct = round(((current_price - entry_price) / entry_price) * 100, 2)
    rules = PROFILES.get(profile, PROFILES["default"])
    state = _load_state()
    ticker_state = state.get(ticker, {"partials_taken": []})
    taken_thresholds = set(ticker_state.get("partials_taken", []))

    # Find highest untaken threshold that's been hit
    triggered = None
    for rule in rules:
        t = rule["gain_pct"]
        if gain_pct >= t and t not in taken_thresholds:
            triggered = rule

    if triggered is None:
        return {
            "action": "HOLD",
            "shares_to_sell": 0,
            "reason": f"No partial triggered at {gain_pct:+.1f}%",
            "remaining": shares_held,
            "gain_pct": gain_pct,
        }

    # Calculate shares to sell based on fraction of ORIGINAL position
    # We approximate original from current shares + previously sold
    shares_to_sell = max(1, math.floor(shares_held * triggered["sell_frac"]))
    remaining = shares_held - shares_to_sell

    # Record the partial
    ticker_state.setdefault("partials_taken", []).append(triggered["gain_pct"])
    ticker_state.setdefault("history", []).append({
        "threshold": triggered["gain_pct"],
        "shares_sold": shares_to_sell,
        "price": current_price,
        "gain_pct": gain_pct,
    })
    state[ticker] = ticker_state
    _save_state(state)

    return {
        "action": "SELL_PARTIAL",
        "shares_to_sell": shares_to_sell,
        "reason": triggered["label"],
        "remaining": remaining,
        "gain_pct": gain_pct,
    }


def get_partial_history(ticker):
    """Return list of partial sells taken for a ticker."""
    state = _load_state()
    return state.get(ticker, {}).get("history", [])


def reset_partials(ticker):
    """Reset partial state for a ticker (e.g., after full exit)."""
    state = _load_state()
    if ticker in state:
        del state[ticker]
        _save_state(state)
    return {"ticker": ticker, "reset": True}


if __name__ == "__main__":
    # Simulate
    print("--- Default profile ---")
    print(json.dumps(check_partials("AAPL", 150.0, 155.0, 100, "default"), indent=2))
    print(json.dumps(check_partials("AAPL", 150.0, 158.0, 67, "default"), indent=2))
    print(json.dumps(get_partial_history("AAPL"), indent=2))
    reset_partials("AAPL")
