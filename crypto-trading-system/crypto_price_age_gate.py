#!/usr/bin/env python3
"""
crypto_price_age_gate.py — F9: Hard reject on stale price data
Owner: Alfred | Created: 2026-03-01

No trade executes if price data is older than MAX_PRICE_AGE_SECONDS.
Integrates into pretrade_gate_v2 as an additional hard-block check.
"""

import time
import json
import os
from datetime import datetime, timezone

MAX_PRICE_AGE_SECONDS = 120  # 2 minutes

# TARS price cache location (read-only for Alfred)
PRICE_CACHE_PATHS = [
    os.path.expanduser("~/.crypto_price_cache.json"),
    os.path.join(os.path.dirname(__file__), "price_cache.json"),
]

def get_price_age(ticker: str) -> dict:
    """Check age of price data for a ticker. Returns age in seconds."""
    for path in PRICE_CACHE_PATHS:
        try:
            with open(path) as f:
                cache = json.load(f)
            if ticker in cache:
                entry = cache[ticker]
                ts = entry.get("timestamp", entry.get("updated_at", 0))
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - dt).total_seconds()
                else:
                    age = time.time() - ts
                return {
                    "ticker": ticker,
                    "age_seconds": int(age),
                    "max_age": MAX_PRICE_AGE_SECONDS,
                    "fresh": age <= MAX_PRICE_AGE_SECONDS,
                    "price": entry.get("price", entry.get("usd", None)),
                    "source": path
                }
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue

    return {
        "ticker": ticker,
        "age_seconds": 999999,
        "max_age": MAX_PRICE_AGE_SECONDS,
        "fresh": False,
        "price": None,
        "source": None,
        "error": "No price data found in any cache"
    }

def gate_check(ticker: str) -> dict:
    """Gate check — returns PASS/HARD_BLOCK."""
    result = get_price_age(ticker)
    if result["fresh"]:
        return {
            "check": "price_age",
            "result": "PASS",
            "detail": f"{ticker} price is {result['age_seconds']}s old (limit: {MAX_PRICE_AGE_SECONDS}s)",
            "price": result["price"]
        }
    else:
        return {
            "check": "price_age",
            "result": "HARD_BLOCK",
            "detail": f"{ticker} price is {result['age_seconds']}s old — STALE (limit: {MAX_PRICE_AGE_SECONDS}s)",
            "action": "DO NOT TRADE — wait for fresh price data"
        }


if __name__ == "__main__":
    print("crypto_price_age_gate.py — Stale price hard block")
    print(f"  Max age: {MAX_PRICE_AGE_SECONDS}s")
    for ticker in ["BTC", "ETH", "SOL"]:
        result = gate_check(ticker)
        print(f"  {ticker}: {result['result']} — {result['detail']}")
    print("  Status: READY")
