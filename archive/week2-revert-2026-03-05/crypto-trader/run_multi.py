#!/usr/bin/env python3
"""
Multi-Strategy Crypto Backtester
=================================
Runs regime detection + strategy routing on historical candle data.

Usage:
    python run_multi.py
    python run_multi.py --product BTC-USD --days 90
    python run_multi.py --product POL-USD --days 90 --granularity ONE_HOUR
"""

import argparse
import logging

from coinbase_client import fetch_candles, GRANULARITY_MAP
from multi_strategy import run_multi_backtest, MultiStrategyConfig
from metrics import compute_metrics, print_report
from strategy import BacktestResult


# Reverse map so users can pass either format
GRAN_ALIASES = {v: k for k, v in GRANULARITY_MAP.items()}


def print_regime_breakdown(result) -> None:
    """Print percentage of time spent in each regime."""
    if result.regime_series is None:
        return
    counts = result.regime_series.value_counts()
    total = len(result.regime_series)
    print("\n📊 Regime Breakdown:")
    print(f"   {'Regime':<18} {'Candles':>8} {'Pct':>8}")
    print(f"   {'—'*18} {'—'*8} {'—'*8}")
    for regime, count in counts.items():
        pct = count / total * 100
        print(f"   {regime:<18} {count:>8d} {pct:>7.1f}%")
    print()


def print_strategy_performance(result, initial_capital: float) -> None:
    """Print per-strategy trade summary."""
    strategies = [
        ("Mean Reversion (RANGING)", result.mean_reversion_trades),
        ("Trend Long (TRENDING_UP)", result.trend_long_trades),
        ("Trend Short (TRENDING_DOWN)", result.trend_short_trades),
    ]
    print("📈 Per-Strategy Breakdown:")
    print(f"   {'Strategy':<30} {'Trades':>7} {'Wins':>5} {'Win%':>7} {'Avg P&L':>9}")
    print(f"   {'—'*30} {'—'*7} {'—'*5} {'—'*7} {'—'*9}")
    for name, trades in strategies:
        n = len(trades)
        if n == 0:
            print(f"   {name:<30} {0:>7d} {0:>5d} {'N/A':>7} {'N/A':>9}")
            continue
        wins = sum(1 for t in trades if t.is_win)
        avg_pnl = sum(t.return_pct for t in trades) / n * 100
        wr = wins / n * 100
        print(f"   {name:<30} {n:>7d} {wins:>5d} {wr:>6.1f}% {avg_pnl:>+8.2f}%")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Strategy Crypto Backtester")
    parser.add_argument("--product", default="BTC-USD", help="Trading pair")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--granularity", default="ONE_HOUR",
                        help="Candle interval (e.g. ONE_HOUR, 1h)")
    parser.add_argument("--capital", type=float, default=10_000.0, help="Initial capital")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Normalize granularity
    gran = args.granularity
    if gran in GRAN_ALIASES:
        gran = GRAN_ALIASES[gran]  # e.g. ONE_HOUR -> 1h
    if gran not in GRANULARITY_MAP:
        print(f"❌ Unknown granularity: {args.granularity}")
        print(f"   Valid: {list(GRANULARITY_MAP.keys())} or {list(GRANULARITY_MAP.values())}")
        return

    # 1. Fetch data
    print(f"\n📡 Fetching {args.days} days of {gran} candles for {args.product}...")
    df = fetch_candles(product_id=args.product, granularity=gran, days=args.days)
    print(f"   ✅ Got {len(df)} candles  ({df['datetime'].iloc[0]} → {df['datetime'].iloc[-1]})")

    # 2. Run multi-strategy backtest
    print(f"\n⚙️  Running multi-strategy backtest...")
    config = MultiStrategyConfig(initial_capital=args.capital)
    result = run_multi_backtest(df, config=config)

    # 3. Regime breakdown
    print_regime_breakdown(result)

    # 4. Per-strategy performance
    print_strategy_performance(result, args.capital)

    # 5. Overall metrics (reuse existing metrics)
    bt_result = BacktestResult(trades=result.trades, equity_curve=result.equity_curve)
    metrics = compute_metrics(bt_result, initial_capital=args.capital)
    print_report(metrics, product_id=f"{args.product} (Multi-Strategy)")

    # 6. Trade log
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
        print("⚠️  No trades were triggered.\n")


if __name__ == "__main__":
    main()
