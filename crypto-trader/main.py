#!/usr/bin/env python3
"""
Crypto Mean-Reversion Backtester
================================
Fetches 90 days of hourly BTC-USD candles from Coinbase and runs a
Bollinger Bands + RSI mean-reversion backtest.

Usage:
    python main.py
    python main.py --product ETH-USD --days 60
"""

import argparse
import logging

from coinbase_client import fetch_candles
from strategy import run_backtest, StrategyConfig
from metrics import compute_metrics, print_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Crypto Mean-Reversion Backtester")
    parser.add_argument("--product", default="BTC-USD", help="Trading pair (default: BTC-USD)")
    parser.add_argument("--days", type=int, default=90, help="Days of history (default: 90)")
    parser.add_argument("--granularity", default="1h", help="Candle interval (default: 1h)")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital (default: 10000)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 1. Fetch data
    print(f"\n📡 Fetching {args.days} days of {args.granularity} candles for {args.product}...")
    df = fetch_candles(
        product_id=args.product,
        granularity=args.granularity,
        days=args.days,
    )
    print(f"   ✅ Got {len(df)} candles  ({df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]})")

    # 2. Run backtest
    print(f"\n⚙️  Running mean-reversion backtest...")
    config = StrategyConfig()
    result = run_backtest(df, config=config, initial_capital=args.capital)

    # 3. Compute & display metrics
    metrics = compute_metrics(result, initial_capital=args.capital)
    print_report(metrics, product_id=args.product)

    # 4. Show individual trades if there are any
    if result.trades:
        print(f"📋 Trade Log ({len(result.trades)} trades):")
        print(f"   {'#':>3}  {'Entry Time':<22} {'Entry $':>10}  {'Exit $':>10}  {'P&L':>8}  {'Reason'}")
        print(f"   {'—'*3}  {'—'*22} {'—'*10}  {'—'*10}  {'—'*8}  {'—'*10}")
        for i, t in enumerate(result.trades, 1):
            pnl = t.return_pct * 100
            print(
                f"   {i:>3}  {str(t.entry_time):<22} "
                f"${t.entry_price:>9,.2f}  ${t.exit_price:>9,.2f}  "
                f"{pnl:>+7.2f}%  {t.exit_reason}"
            )
        print()
    else:
        print("⚠️  No trades were triggered with the current strategy parameters.\n")


if __name__ == "__main__":
    main()
