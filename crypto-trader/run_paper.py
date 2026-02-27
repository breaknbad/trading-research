#!/usr/bin/env python3
"""CLI entry point for paper trading."""

import argparse
import logging

from paper_trader import PaperTrader


def main():
    parser = argparse.ArgumentParser(description="Paper trade crypto with mean reversion strategy")
    parser.add_argument("--product", default="BTC-USD", help="Trading pair (default: BTC-USD)")
    parser.add_argument("--balance", type=float, default=10000, help="Starting balance in USD (default: 10000)")
    parser.add_argument("--interval", type=int, default=5, help="Check interval in minutes (default: 5)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    trader = PaperTrader(
        product_id=args.product,
        initial_balance=args.balance,
    )
    trader.run(interval_minutes=args.interval)


if __name__ == "__main__":
    main()
