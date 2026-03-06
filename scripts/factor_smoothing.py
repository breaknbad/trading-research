"""
Factor Engine Smoothing Module
- Reads market-state.json for ticker data
- Uses 15-min EMA period for trend scoring
- 30-min cooldown per ticker (cached in factor_cooldown.json)
- Import and call get_smoothed_factor(ticker)
"""

import json
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKET_STATE_PATH = os.path.join(SCRIPT_DIR, "market-state.json")
COOLDOWN_PATH = os.path.join(SCRIPT_DIR, "factor_cooldown.json")
COOLDOWN_SECONDS = 30 * 60  # 30 minutes
EMA_PERIOD = 15  # 15-min EMA


def _load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _calc_ema_trend_score(prices):
    """Calculate trend score using EMA with 15-min period. Returns -1 to 1."""
    if not prices or len(prices) < 2:
        return 0.0
    k = 2 / (EMA_PERIOD + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    current = prices[-1]
    if ema == 0:
        return 0.0
    score = (current - ema) / ema
    return max(-1.0, min(1.0, score * 10))  # normalize


def get_smoothed_factor(ticker):
    """
    Get smoothed factor score for a ticker.
    Returns cached score if evaluated <30 min ago.
    Otherwise recalculates from market-state.json.
    Returns float between -1.0 and 1.0.
    """
    cooldown = _load_json(COOLDOWN_PATH)
    now = time.time()

    entry = cooldown.get(ticker, {})
    last_time = entry.get("timestamp", 0)
    cached_score = entry.get("score", 0.0)

    if now - last_time < COOLDOWN_SECONDS:
        return cached_score

    market = _load_json(MARKET_STATE_PATH)
    ticker_data = market.get(ticker, market.get("tickers", {}).get(ticker, {}))
    prices = ticker_data.get("prices", ticker_data.get("recent_prices", []))

    score = _calc_ema_trend_score(prices)

    cooldown[ticker] = {"timestamp": now, "score": score}
    _save_json(COOLDOWN_PATH, cooldown)

    return score


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    print(f"{t} smoothed factor: {get_smoothed_factor(t):.4f}")
