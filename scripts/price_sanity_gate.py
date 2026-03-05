#!/usr/bin/env python3
"""
Price Sanity Gate — reject prices that deviate >50% from last known good price.
Maintains a cache of last known prices. Any trade/stop evaluation must pass through this.

Usage:
  python3 price_sanity_gate.py --validate BTC-USD 68000    # Validate a price
  python3 price_sanity_gate.py --update BTC-USD 68000      # Update cache with known good price
  python3 price_sanity_gate.py --show                       # Show all cached prices

Import: from price_sanity_gate import validate_price, update_price
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_FILE = Path(__file__).parent.parent / "price_cache.json"
MAX_DEVIATION = 0.50  # 50% max deviation from last known price
MIN_PRICES = {
    # Absolute minimum sane prices (emergency floor)
    "BTC-USD": 10000, "ETH-USD": 500, "SOL-USD": 10, "NEAR-USD": 0.10,
    "ADA-USD": 0.05, "AVAX-USD": 1.0, "LINK-USD": 1.0, "DOGE-USD": 0.01,
    "SUI-USD": 0.10, "FIL-USD": 0.50, "APT-USD": 0.50,
    "SQQQ": 5.0, "GLD": 100, "GDX": 10, "SLV": 10, "XLE": 20,
    "NVDA": 50, "AMD": 30, "INTC": 10, "BIL": 80,
}


def load_cache():
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def update_price(ticker: str, price: float):
    """Update cache with a known good price."""
    cache = load_cache()
    ticker = ticker.upper()
    cache[ticker] = {
        "price": price,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    save_cache(cache)
    return True


def validate_price(ticker: str, price: float) -> tuple:
    """
    Validate a price against cache.
    Returns (is_valid: bool, reason: str)
    """
    ticker = ticker.upper()

    # Check absolute minimum
    min_price = MIN_PRICES.get(ticker)
    if min_price and price < min_price:
        return False, f"REJECTED: {ticker} ${price} below absolute minimum ${min_price}"

    # Check against cache
    cache = load_cache()
    cached = cache.get(ticker)

    if not cached:
        # No cache — accept but warn
        return True, f"WARNING: No cached price for {ticker}. Accepting ${price} (update cache)."

    last_price = cached["price"]
    if last_price == 0:
        return True, f"WARNING: Cached price is $0 for {ticker}. Accepting ${price}."

    deviation = abs(price - last_price) / last_price

    if deviation > MAX_DEVIATION:
        return False, f"REJECTED: {ticker} ${price} deviates {deviation:.0%} from cached ${last_price} (max {MAX_DEVIATION:.0%})"

    return True, f"OK: {ticker} ${price} within {deviation:.1%} of cached ${last_price}"


def show_cache():
    cache = load_cache()
    if not cache:
        print("Price cache empty.")
        return
    print(f"{'Ticker':12s} {'Price':>12s} {'Updated':>25s}")
    print("-" * 52)
    for ticker in sorted(cache):
        entry = cache[ticker]
        print(f"  {ticker:10s} ${entry['price']:>10,.2f}  {entry['updated_at'][:19]}")


def main():
    parser = argparse.ArgumentParser(description="Price Sanity Gate")
    parser.add_argument("--validate", nargs=2, metavar=("TICKER", "PRICE"),
                        help="Validate a price")
    parser.add_argument("--update", nargs=2, metavar=("TICKER", "PRICE"),
                        help="Update cache with known good price")
    parser.add_argument("--show", action="store_true", help="Show cached prices")
    parser.add_argument("--seed", action="store_true",
                        help="Seed cache with current approximate prices")

    args = parser.parse_args()

    if args.validate:
        ticker, price = args.validate
        valid, reason = validate_price(ticker, float(price))
        print(reason)
        sys.exit(0 if valid else 1)

    elif args.update:
        ticker, price = args.update
        update_price(ticker, float(price))
        print(f"✅ {ticker.upper()} cached at ${float(price):,.2f}")

    elif args.seed:
        # Seed with approximate current prices (Mar 3, 2026 EOD)
        seed = {
            "BTC-USD": 67900, "ETH-USD": 1962, "SOL-USD": 84.40,
            "NEAR-USD": 1.36, "ADA-USD": 0.25, "AVAX-USD": 8.70,
            "LINK-USD": 8.50, "DOGE-USD": 0.12, "SUI-USD": 1.50,
            "SQQQ": 72.87, "GLD": 468.14, "GDX": 105.24,
            "SLV": 74.70, "XLE": 56.52, "NVDA": 180.0,
            "BIL": 91.50,
        }
        for ticker, price in seed.items():
            update_price(ticker, price)
        print(f"✅ Seeded {len(seed)} prices into cache.")

    elif args.show:
        show_cache()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
