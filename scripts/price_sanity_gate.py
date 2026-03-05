#!/usr/bin/env python3
"""price_sanity_gate.py — Reject prices >50% from last known good.
# CALLED BY: execute_trade.py (every trade), heartbeat (stop checks)
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

CACHE_FILE = Path(__file__).parent / "price_cache.json"
MAX_DEVIATION = 0.50  # 50%

# Absolute floors — reject anything below these
FLOORS = {
    "BTC-USD": 1000, "ETH-USD": 50, "SOL-USD": 1, "NEAR-USD": 0.10,
    "ADA-USD": 0.01, "DOGE-USD": 0.001, "SUI-USD": 0.01, "AVAX-USD": 0.50,
    "LINK-USD": 0.50, "GLD": 100, "SLV": 10, "XLE": 20, "XLV": 50,
    "SQQQ": 5, "GDX": 10, "GDXJ": 20, "NVDA": 30, "AMD": 20,
}

def _load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text())
    return {}

def _save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))

def validate_price(ticker, price):
    """Returns (is_valid, reason_string)."""
    if price is None or price <= 0:
        return False, f"Invalid price: {price}"
    floor = FLOORS.get(ticker, 0.001)
    if price < floor:
        return False, f"{ticker} ${price} below absolute floor ${floor}"
    cache = _load_cache()
    last = cache.get(ticker)
    if last and last.get("price"):
        last_price = last["price"]
        deviation = abs(price - last_price) / last_price
        if deviation > MAX_DEVIATION:
            return False, f"{ticker} ${price} deviates {deviation:.0%} from last known ${last_price}"
    return True, "OK"

def update_price(ticker, price):
    """Cache a known-good price."""
    cache = _load_cache()
    cache[ticker] = {"price": price, "ts": datetime.now(timezone.utc).isoformat()}
    _save_cache(cache)

def seed_prices():
    """Seed cache with reasonable EOD prices."""
    seeds = {
        "BTC-USD": 67900, "ETH-USD": 1962, "SOL-USD": 84.40, "NEAR-USD": 1.37,
        "ADA-USD": 0.25, "DOGE-USD": 0.085, "SUI-USD": 0.91, "AVAX-USD": 18.50,
        "LINK-USD": 9.80, "GLD": 468, "SLV": 75, "XLE": 56.20, "XLV": 157,
        "SQQQ": 72.80, "GDX": 105, "GDXJ": 141, "NVDA": 180, "AMD": 95,
    }
    for t, p in seeds.items():
        update_price(t, p)
    print(f"Seeded {len(seeds)} prices")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--seed":
        seed_prices()
    elif len(sys.argv) > 2 and sys.argv[1] == "--validate":
        ticker, price = sys.argv[2], float(sys.argv[3])
        ok, reason = validate_price(ticker, price)
        print(f"{'✅ PASS' if ok else '❌ REJECTED'}: {reason}")
    else:
        print("Usage: price_sanity_gate.py --seed | --validate TICKER PRICE")
