#!/usr/bin/env python3
"""
CLI entry point for the 5-minute multi-crypto scalper.

Usage:
    python run_scalper.py                          # paper trade, $1,000
    python run_scalper.py --live                   # real trades
    python run_scalper.py --balance 5000           # custom balance
    python run_scalper.py --interval 5             # check every N minutes
    python run_scalper.py --pairs BTC-USD,ETH-USD  # custom pairs
    python run_scalper.py --once                   # single round then exit
"""

import argparse
import logging
import sys

from scalper import Scalper, DEFAULT_PAIRS


def main():
    parser = argparse.ArgumentParser(description="5-Minute Multi-Crypto Scalper")
    parser.add_argument("--live", action="store_true", help="Enable live trading (default: paper)")
    parser.add_argument("--balance", type=float, default=1000.0, help="Starting balance in USD")
    parser.add_argument("--interval", type=int, default=5, help="Polling interval in minutes")
    parser.add_argument("--pairs", type=str, default=None,
                        help="Comma-separated trading pairs (e.g. BTC-USD,ETH-USD)")
    parser.add_argument("--max-positions", type=int, default=3, help="Max simultaneous positions")
    parser.add_argument("--once", action="store_true", help="Run a single round then exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pairs = args.pairs.split(",") if args.pairs else DEFAULT_PAIRS

    if args.live:
        confirm = input("⚠️  LIVE TRADING MODE — real money at risk. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)

    scalper = Scalper(
        pairs=pairs,
        balance=args.balance,
        live=args.live,
        max_positions=args.max_positions,
    )

    if args.once:
        scalper.run_round()
    else:
        scalper.run(interval_minutes=args.interval)


if __name__ == "__main__":
    main()
