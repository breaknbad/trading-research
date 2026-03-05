#!/usr/bin/env python3
"""
SPY 20-day MA Trend Filter — compliance gate for directional trades.
- SPY above 20d MA → bullish regime → short entries get -1 conviction penalty
- SPY below 20d MA → bearish regime → long entries get +0 (no penalty, shorts favored)

Usage:
  from trend_filter import check_trend, get_spy_regime
  regime = get_spy_regime()  # "BULLISH" or "BEARISH"
  ok, warning = check_trend("SHORT", "NVDA")  # Returns (True, "warning msg") or (True, "")
"""

import requests

def get_spy_data():
    """Fetch SPY current price and 20-day SMA from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=30d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200:
            return None, None

        data = r.json()
        result = data.get("chart", {}).get("result", [{}])[0]
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        meta = result.get("meta", {})
        current = float(meta.get("regularMarketPrice", 0))

        # Filter out None values and get last 20
        valid_closes = [c for c in closes if c is not None]
        if len(valid_closes) < 20:
            return current, None

        sma_20 = sum(valid_closes[-20:]) / 20
        return current, sma_20
    except Exception:
        return None, None


def get_spy_regime():
    """Returns 'BULLISH' if SPY > 20d MA, 'BEARISH' otherwise."""
    current, sma_20 = get_spy_data()
    if current is None or sma_20 is None:
        return "UNKNOWN"
    return "BULLISH" if current > sma_20 else "BEARISH"


def check_trend(action, ticker):
    """
    Check if a trade direction aligns with the SPY trend.
    Returns (allowed, warning_message).
    Always allows the trade but warns when fighting the trend.
    """
    regime = get_spy_regime()

    if regime == "UNKNOWN":
        return True, ""

    current, sma_20 = get_spy_data()

    if action.upper() == "SHORT" and regime == "BULLISH":
        return True, (
            f"⚠️ TREND WARNING: Shorting {ticker} in BULLISH regime "
            f"(SPY ${current:.2f} > 20d MA ${sma_20:.2f}). "
            f"Conviction penalty: -1. Consider reducing size."
        )

    if action.upper() == "BUY" and regime == "BEARISH":
        return True, (
            f"📊 TREND NOTE: Buying {ticker} in BEARISH regime "
            f"(SPY ${current:.2f} < 20d MA ${sma_20:.2f}). "
            f"Proceed with normal conviction."
        )

    return True, ""


if __name__ == "__main__":
    regime = get_spy_regime()
    current, sma_20 = get_spy_data()
    print(f"SPY Regime: {regime}")
    if current and sma_20:
        print(f"SPY Current: ${current:.2f} | 20d MA: ${sma_20:.2f} | Delta: {((current-sma_20)/sma_20)*100:.2f}%")
