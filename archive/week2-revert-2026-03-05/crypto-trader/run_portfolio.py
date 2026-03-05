#!/usr/bin/env python3
"""
Full Portfolio Backtest CLI
============================
Multi-asset, multi-strategy portfolio backtest with risk management
and asset rotation.

Usage:
    python run_portfolio.py
    python run_portfolio.py --products "BTC-USD,ETH-USD,SOL-USD" --days 90 --balance 10000
    python run_portfolio.py --products "BTC-USD,POL-USD,SOL-USD,NEAR-USD,ETH-USD" --days 90
"""

import argparse
import logging
import time as time_module
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from coinbase_client import fetch_candles, GRANULARITY_MAP
from indicators import add_all_multi_indicators
from regime import detect_regime, Regime
from strategy import Trade, StrategyConfig
from trend_strategy import TrendFollower, TrendStrategyConfig
from position import Position, PositionSide, PositionTracker
from portfolio import PortfolioManager, PortfolioConfig
from risk_manager import RiskManager, RiskConfig
from asset_scorer import AssetScorer, ScorerConfig
from metrics import compute_metrics
from strategy import BacktestResult

logger = logging.getLogger(__name__)

GRAN_ALIASES = {v: k for k, v in GRANULARITY_MAP.items()}


def fetch_all_assets(products: List[str], days: int, granularity: str) -> Dict[str, pd.DataFrame]:
    """Fetch candle data for all products."""
    data = {}
    for product in products:
        print(f"   📡 Fetching {product}...")
        try:
            df = fetch_candles(product_id=product, granularity=granularity, days=days)
            print(f"      ✅ {len(df)} candles")
            data[product] = df
        except Exception as e:
            print(f"      ❌ Failed: {e}")
        time_module.sleep(0.5)  # rate limit
    return data


def prepare_data(raw_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Add all indicators and regime detection to each asset's data."""
    prepared = {}
    for asset, df in raw_data.items():
        df = add_all_multi_indicators(df)
        df = detect_regime(df)
        df["prev_close"] = df["close"].shift(1)
        df["adx_rising"] = df["adx"] > df["adx"].shift(3)
        if "ema_50" in df.columns:
            df["prev_ema_50"] = df["ema_50"].shift(1)
        if "ema_200" in df.columns:
            df["prev_ema_200"] = df["ema_200"].shift(1)
        # Drop NaN rows
        required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
        available = [c for c in required if c in df.columns]
        df = df.dropna(subset=available).reset_index(drop=True)
        if len(df) > 0:
            prepared[asset] = df
    return prepared


def run_portfolio_backtest(
    data: Dict[str, pd.DataFrame],
    initial_balance: float = 10_000.0,
) -> dict:
    """
    Run the full multi-asset portfolio backtest.
    
    Returns a results dict with equity curve, trades, regime stats, etc.
    """
    # Initialize components
    portfolio = PortfolioManager(initial_balance, PortfolioConfig())
    risk_mgr = RiskManager(RiskConfig())
    risk_mgr.initialize(initial_balance)
    scorer = AssetScorer(ScorerConfig())

    # Per-asset trend followers and mean-reversion state
    trend_followers: Dict[str, TrendFollower] = {}
    mr_state: Dict[str, dict] = {}  # asset -> {in_position, entry_price, entry_time, stop_price, alloc}
    mr_config = StrategyConfig()

    for asset in data:
        trend_followers[asset] = TrendFollower(TrendStrategyConfig())
        mr_state[asset] = {"in_position": False, "entry_price": 0, "entry_time": None, "stop_price": 0, "alloc": 0}

    # Align all assets to a common timeline
    all_times = set()
    for df in data.values():
        all_times.update(df["datetime"].tolist())
    timeline = sorted(all_times)

    # Create index lookups for each asset
    asset_indices: Dict[str, dict] = {}
    for asset, df in data.items():
        asset_indices[asset] = {row["datetime"]: i for i, row in df.iterrows()}

    # Tracking
    equity_curve = []
    equity_times = []
    all_trades: List[Trade] = []
    mr_trades: List[Trade] = []
    trend_long_trades: List[Trade] = []
    trend_short_trades: List[Trade] = []
    regime_counts: Dict[str, Dict[str, int]] = {a: {} for a in data}
    rotation_decisions: List[dict] = []
    active_assets: List[str] = list(data.keys())  # start with all

    prev_regimes: Dict[str, Optional[str]] = {a: None for a in data}

    for t_idx, current_time in enumerate(timeline):
        # Get current prices for all assets at this time
        current_prices = {}
        current_rows = {}
        for asset, df in data.items():
            idx = asset_indices[asset].get(current_time)
            if idx is not None:
                row = df.iloc[idx]
                current_prices[asset] = row["close"]
                current_rows[asset] = row

        if not current_prices:
            continue

        # Update portfolio prices for correlation tracking
        portfolio.record_prices(current_prices)

        # Calculate current equity (cash + unrealized)
        equity = portfolio.update_equity(current_prices)

        # Update risk manager
        prev_price_return = 0.0
        if len(equity_curve) > 0:
            prev_price_return = (equity - equity_curve[-1]) / equity_curve[-1] if equity_curve[-1] > 0 else 0
        risk_mgr.update_bar(equity, current_time, prev_price_return)

        # Asset rotation check
        if scorer.should_re_evaluate() and current_rows:
            # Build recent data snapshots
            asset_snapshots = {}
            for asset, df in data.items():
                idx = asset_indices[asset].get(current_time)
                if idx is not None and idx >= 48:
                    asset_snapshots[asset] = df.iloc[:idx + 1]
            
            if asset_snapshots:
                active_assets = scorer.get_tradeable_assets(asset_snapshots, max_assets=3)
                scores = scorer.last_scores
                rotation_decisions.append({
                    "time": current_time,
                    "active": list(active_assets),
                    "scores": {a: s.total_score for a, s in scores.items()},
                })

        # Process each asset
        for asset in data:
            if asset not in current_rows:
                continue

            row = current_rows[asset]
            regime = row.get("regime", Regime.RANGING.value)
            price = row["close"]
            atr = row.get("atr", 0)

            # Track regime distribution
            regime_counts[asset][regime] = regime_counts[asset].get(regime, 0) + 1

            # Handle regime transitions — close positions on change
            prev_regime = prev_regimes[asset]
            if prev_regime is not None and regime != prev_regime:
                # Close mean reversion
                ms = mr_state[asset]
                if ms["in_position"]:
                    pnl_pct = (price - ms["entry_price"]) / ms["entry_price"]
                    pnl_usd = pnl_pct * ms["alloc"]
                    portfolio.realize_pnl(pnl_usd)
                    t = Trade(ms["entry_time"], ms["entry_price"], current_time, price, "regime_change")
                    all_trades.append(t)
                    mr_trades.append(t)
                    ms["in_position"] = False
                    is_win = pnl_pct > 0
                    risk_mgr.record_trade(is_win)
                    portfolio.record_trade(asset, pnl_pct, is_win)
                    scorer.record_trade(asset, pnl_pct, is_win)
                    # Close the tracked position
                    pos = portfolio.tracker.get_position(asset)
                    if pos:
                        portfolio.tracker.close_position(pos, price, current_time, "regime_change")

                # Close trend
                tf = trend_followers[asset]
                trade = tf.force_close(price, current_time, "regime_change")
                if trade:
                    pnl_pct = trade.return_pct
                    alloc = _position_size_simple(portfolio.equity, atr, price)
                    pnl_usd = pnl_pct * alloc
                    portfolio.realize_pnl(pnl_usd)
                    all_trades.append(trade)
                    if prev_regime in (Regime.TRENDING_UP.value, Regime.WEAK_TREND_UP.value):
                        trend_long_trades.append(trade)
                    else:
                        trend_short_trades.append(trade)
                    is_win = pnl_pct > 0
                    risk_mgr.record_trade(is_win)
                    portfolio.record_trade(asset, pnl_pct, is_win)
                    scorer.record_trade(asset, pnl_pct, is_win)
                    pos = portfolio.tracker.get_position(asset)
                    if pos:
                        portfolio.tracker.close_position(pos, price, current_time, "regime_change")

            prev_regimes[asset] = regime

            # Skip if risk manager says no
            if not risk_mgr.can_trade():
                continue

            # Skip if asset not in active rotation
            if asset not in active_assets:
                continue

            # Route to strategy
            if regime == Regime.RANGING.value:
                trade = _process_mean_reversion(
                    asset, row, current_time, mr_state[asset], mr_config,
                    portfolio, risk_mgr, scorer
                )
                if trade:
                    all_trades.append(trade)
                    mr_trades.append(trade)

            elif regime in (Regime.WEAK_TREND_UP.value, Regime.WEAK_TREND_DOWN.value):
                # Hybrid zone: both mean reversion and trend following
                # Mean reversion
                trade = _process_mean_reversion(
                    asset, row, current_time, mr_state[asset], mr_config,
                    portfolio, risk_mgr, scorer
                )
                if trade:
                    all_trades.append(trade)
                    mr_trades.append(trade)

                # Trend following
                tf = trend_followers[asset]
                trend_regime = Regime.TRENDING_UP.value if regime == Regime.WEAK_TREND_UP.value else Regime.TRENDING_DOWN.value
                if not tf.in_position:
                    can_open, reason = portfolio.can_open_position(asset)
                    if can_open:
                        max_new = risk_mgr.max_new_exposure_usd(portfolio.equity, portfolio.tracker.total_exposure_usd)
                        if max_new >= portfolio.config.min_position_usd:
                            trade = tf.process_bar(row, trend_regime)
                            if trade:
                                pnl_pct = trade.return_pct
                                vol_scale = risk_mgr.volatility_scale()
                                alloc = _position_size_simple(portfolio.equity, atr, price) * vol_scale
                                pnl_usd = pnl_pct * alloc
                                portfolio.realize_pnl(pnl_usd)
                                all_trades.append(trade)
                                if trend_regime == Regime.TRENDING_UP.value:
                                    trend_long_trades.append(trade)
                                else:
                                    trend_short_trades.append(trade)
                                is_win = pnl_pct > 0
                                risk_mgr.record_trade(is_win)
                                portfolio.record_trade(asset, pnl_pct, is_win)
                                scorer.record_trade(asset, pnl_pct, is_win)
                            elif tf.in_position and not portfolio.tracker.get_position(asset):
                                side = PositionSide.LONG if tf.direction == "long" else PositionSide.SHORT
                                size = portfolio.calculate_position_size(asset, atr, price, side) * risk_mgr.volatility_scale()
                                if size >= portfolio.config.min_position_usd:
                                    portfolio.tracker.open_position(asset, side, price, current_time, size)
                else:
                    trade = tf.process_bar(row, trend_regime)
                    if trade:
                        pnl_pct = trade.return_pct
                        vol_scale = risk_mgr.volatility_scale()
                        alloc = _position_size_simple(portfolio.equity, atr, price) * vol_scale
                        pnl_usd = pnl_pct * alloc
                        portfolio.realize_pnl(pnl_usd)
                        all_trades.append(trade)
                        if trend_regime == Regime.TRENDING_UP.value:
                            trend_long_trades.append(trade)
                        else:
                            trend_short_trades.append(trade)
                        is_win = pnl_pct > 0
                        risk_mgr.record_trade(is_win)
                        portfolio.record_trade(asset, pnl_pct, is_win)
                        scorer.record_trade(asset, pnl_pct, is_win)
                        pos = portfolio.tracker.get_position(asset)
                        if pos:
                            portfolio.tracker.close_position(pos, price, current_time, trade.exit_reason)

            elif regime in (Regime.TRENDING_UP.value, Regime.TRENDING_DOWN.value):
                tf = trend_followers[asset]
                # Check if we need to open a position first
                if not tf.in_position:
                    can_open, reason = portfolio.can_open_position(asset)
                    if not can_open:
                        continue
                    # Check exposure
                    max_new = risk_mgr.max_new_exposure_usd(portfolio.equity, portfolio.tracker.total_exposure_usd)
                    if max_new < portfolio.config.min_position_usd:
                        continue

                trade = tf.process_bar(row, regime)
                if trade:
                    pnl_pct = trade.return_pct
                    vol_scale = risk_mgr.volatility_scale()
                    alloc = _position_size_simple(portfolio.equity, atr, price) * vol_scale
                    pnl_usd = pnl_pct * alloc
                    portfolio.realize_pnl(pnl_usd)
                    all_trades.append(trade)
                    if regime == Regime.TRENDING_UP.value:
                        trend_long_trades.append(trade)
                    else:
                        trend_short_trades.append(trade)
                    is_win = pnl_pct > 0
                    risk_mgr.record_trade(is_win)
                    portfolio.record_trade(asset, pnl_pct, is_win)
                    scorer.record_trade(asset, pnl_pct, is_win)
                    pos = portfolio.tracker.get_position(asset)
                    if pos:
                        portfolio.tracker.close_position(pos, price, current_time, trade.exit_reason)
                elif tf.in_position and not portfolio.tracker.get_position(asset):
                    # Just entered — register position
                    side = PositionSide.LONG if tf.direction == "long" else PositionSide.SHORT
                    size = portfolio.calculate_position_size(asset, atr, price, side) * risk_mgr.volatility_scale()
                    if size >= portfolio.config.min_position_usd:
                        portfolio.tracker.open_position(asset, side, price, current_time, size)

        # Update equity
        equity = portfolio.equity
        for pos in portfolio.tracker.open_positions:
            if pos.is_open and pos.asset in current_prices:
                equity += pos.unrealized_pnl_usd(current_prices[pos.asset])

        equity_curve.append(equity)
        equity_times.append(current_time)

    # Build results
    return {
        "equity_curve": pd.Series(equity_curve, index=equity_times, name="equity"),
        "all_trades": all_trades,
        "mr_trades": mr_trades,
        "trend_long_trades": trend_long_trades,
        "trend_short_trades": trend_short_trades,
        "regime_counts": regime_counts,
        "rotation_decisions": rotation_decisions,
        "final_equity": portfolio.equity,
        "initial_balance": portfolio.initial_capital,
        "risk_status": risk_mgr.get_status(),
        "allocation": portfolio.get_allocation_summary(),
        "scorer_scores": {a: s.total_score for a, s in scorer.last_scores.items()},
    }


def _position_size_simple(equity: float, atr: float, price: float, max_risk: float = 0.02) -> float:
    """Simple ATR-based position size as fraction of equity."""
    if atr <= 0 or price <= 0:
        return equity * 0.1
    risk_amount = max_risk * equity
    stop_distance = 2 * atr
    units = risk_amount / stop_distance
    allocation = units * price
    return min(allocation, equity)


def _process_mean_reversion(
    asset: str, row: pd.Series, time, state: dict,
    config: StrategyConfig, portfolio: PortfolioManager,
    risk_mgr: RiskManager, scorer: AssetScorer,
) -> Optional[Trade]:
    """Process mean reversion strategy for a single asset bar."""
    price = row["close"]
    atr = row.get("atr", 0)

    if state["in_position"]:
        # Stop loss
        if row["low"] <= state["stop_price"]:
            pnl_pct = (state["stop_price"] - state["entry_price"]) / state["entry_price"]
            pnl_usd = pnl_pct * state["alloc"]
            portfolio.realize_pnl(pnl_usd)
            t = Trade(state["entry_time"], state["entry_price"], time, state["stop_price"], "stop_loss")
            state["in_position"] = False
            is_win = pnl_pct > 0
            risk_mgr.record_trade(is_win)
            portfolio.record_trade(asset, pnl_pct, is_win)
            scorer.record_trade(asset, pnl_pct, is_win)
            pos = portfolio.tracker.get_position(asset)
            if pos:
                portfolio.tracker.close_position(pos, state["stop_price"], time, "stop_loss")
            return t

        # Sell signal
        elif price >= row["bb_upper"] and row["rsi"] > config.rsi_sell_threshold:
            pnl_pct = (price - state["entry_price"]) / state["entry_price"]
            pnl_usd = pnl_pct * state["alloc"]
            portfolio.realize_pnl(pnl_usd)
            t = Trade(state["entry_time"], state["entry_price"], time, price, "signal")
            state["in_position"] = False
            is_win = pnl_pct > 0
            risk_mgr.record_trade(is_win)
            portfolio.record_trade(asset, pnl_pct, is_win)
            scorer.record_trade(asset, pnl_pct, is_win)
            pos = portfolio.tracker.get_position(asset)
            if pos:
                portfolio.tracker.close_position(pos, price, time, "signal")
            return t
    else:
        # Buy signal
        if price <= row["bb_lower"] and row["rsi"] < config.rsi_buy_threshold:
            can_open, reason = portfolio.can_open_position(asset)
            if not can_open:
                return None
            max_new = risk_mgr.max_new_exposure_usd(portfolio.equity, portfolio.tracker.total_exposure_usd)
            if max_new < portfolio.config.min_position_usd:
                return None

            vol_scale = risk_mgr.volatility_scale()
            size = portfolio.calculate_position_size(asset, atr, price, PositionSide.LONG) * vol_scale
            if size < portfolio.config.min_position_usd:
                return None

            state["in_position"] = True
            state["entry_price"] = price
            state["entry_time"] = time
            state["stop_price"] = price * (1 - config.stop_loss_pct)
            state["alloc"] = size
            portfolio.tracker.open_position(asset, PositionSide.LONG, price, time, size)

    return None


def print_results(results: dict, products: List[str]) -> None:
    """Print comprehensive portfolio backtest results."""
    initial = results["initial_balance"]
    final = results["final_equity"]
    total_return = (final - initial) / initial * 100

    print("\n" + "=" * 65)
    print("  PORTFOLIO BACKTEST REPORT")
    print("=" * 65)
    print(f"  Initial Balance:    ${initial:>12,.2f}")
    print(f"  Final Equity:       ${final:>12,.2f}")
    print(f"  Total Return:       {total_return:>+12.2f}%")

    # Equity curve metrics
    eq = results["equity_curve"]
    if len(eq) > 0:
        cummax = eq.cummax()
        drawdown = (eq - cummax) / cummax
        max_dd = abs(drawdown.min()) * 100
        returns = eq.pct_change().dropna()
        sharpe = 0
        if len(returns) > 1 and returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(8760)
        print(f"  Max Drawdown:       {max_dd:>12.2f}%")
        print(f"  Sharpe Ratio:       {sharpe:>12.4f}")
    print("-" * 65)

    # Trade summary
    all_trades = results["all_trades"]
    print(f"  Total Trades:       {len(all_trades):>12d}")
    if all_trades:
        wins = sum(1 for t in all_trades if t.is_win)
        print(f"  Win Rate:           {wins / len(all_trades) * 100:>12.1f}%")
    print()

    # Strategy attribution
    strategies = [
        ("Mean Reversion (RANGING)", results["mr_trades"]),
        ("Trend Long (TRENDING_UP)", results["trend_long_trades"]),
        ("Trend Short (TRENDING_DOWN)", results["trend_short_trades"]),
    ]
    print("📈 Strategy Attribution:")
    print(f"   {'Strategy':<32} {'Trades':>7} {'Wins':>5} {'Win%':>7} {'Avg P&L':>9}")
    print(f"   {'—'*32} {'—'*7} {'—'*5} {'—'*7} {'—'*9}")
    for name, trades in strategies:
        n = len(trades)
        if n == 0:
            print(f"   {name:<32} {0:>7d} {0:>5d} {'N/A':>7} {'N/A':>9}")
            continue
        wins = sum(1 for t in trades if t.is_win)
        avg_pnl = sum(t.return_pct for t in trades) / n * 100
        wr = wins / n * 100
        print(f"   {name:<32} {n:>7d} {wins:>5d} {wr:>6.1f}% {avg_pnl:>+8.2f}%")
    print()

    # Per-asset regime breakdown
    print("📊 Regime Distribution by Asset:")
    for asset in sorted(results["regime_counts"].keys()):
        counts = results["regime_counts"][asset]
        total = sum(counts.values())
        if total == 0:
            continue
        print(f"   {asset}:")
        for regime in ["RANGING", "WEAK_TREND_UP", "WEAK_TREND_DOWN", "TRENDING_UP", "TRENDING_DOWN"]:
            c = counts.get(regime, 0)
            print(f"      {regime:<18} {c:>6d} candles ({c/total*100:>5.1f}%)")

    # Asset scores
    print(f"\n📋 Final Asset Scores:")
    for asset, score in sorted(results["scorer_scores"].items(), key=lambda x: -x[1]):
        print(f"   {asset:<12} {score:>6.1f}/100")

    # Rotation decisions (last 5)
    decisions = results["rotation_decisions"]
    if decisions:
        print(f"\n🔄 Asset Rotation Decisions (last 5 of {len(decisions)}):")
        for d in decisions[-5:]:
            time_str = str(d["time"])[:19]
            active = ", ".join(d["active"][:3]) if d["active"] else "none"
            print(f"   {time_str}  →  {active}")

    # Risk status
    risk = results["risk_status"]
    print(f"\n🛡️  Risk Status:")
    print(f"   Circuit breaker:    {'ACTIVE ⚠️' if risk['circuit_breaker'] else 'OK ✅'}")
    print(f"   Daily stop:         {'ACTIVE ⚠️' if risk['daily_stop'] else 'OK ✅'}")
    print(f"   Vol scale:          {risk['vol_scale']:.2f}x")
    print(f"   Consec. losses:     {risk['consecutive_losses']}")

    # Current allocation
    alloc = results["allocation"]
    print(f"\n💰 Final Allocation:")
    for k, v in sorted(alloc.items()):
        print(f"   {k:<12} {v:>6.1f}%")

    print("=" * 65 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Backtest CLI")
    parser.add_argument("--products", default="BTC-USD,ETH-USD,SOL-USD,POL-USD,NEAR-USD",
                        help="Comma-separated trading pairs")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--balance", type=float, default=10_000.0, help="Initial balance")
    parser.add_argument("--granularity", default="ONE_HOUR",
                        help="Candle interval (e.g. ONE_HOUR, 1h)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Normalize granularity
    gran = args.granularity
    if gran in GRAN_ALIASES:
        gran = GRAN_ALIASES[gran]
    if gran not in GRANULARITY_MAP:
        print(f"❌ Unknown granularity: {args.granularity}")
        return

    products = [p.strip() for p in args.products.split(",")]

    print(f"\n🚀 Portfolio Backtest")
    print(f"   Assets:      {', '.join(products)}")
    print(f"   Period:      {args.days} days")
    print(f"   Granularity: {gran}")
    print(f"   Balance:     ${args.balance:,.2f}")
    print()

    # 1. Fetch data
    print("📡 Fetching market data...")
    raw_data = fetch_all_assets(products, args.days, gran)
    if not raw_data:
        print("❌ No data fetched. Exiting.")
        return

    # 2. Prepare data (indicators + regime)
    print("\n⚙️  Computing indicators and regime detection...")
    data = prepare_data(raw_data)
    for asset, df in data.items():
        print(f"   {asset}: {len(df)} prepared candles")

    # 3. Run portfolio backtest
    print(f"\n🏃 Running portfolio backtest...")
    results = run_portfolio_backtest(data, initial_balance=args.balance)

    # 4. Print results
    print_results(results, products)

    # 5. Trade log (compact)
    trades = results["all_trades"]
    if trades:
        print(f"📋 Trade Log ({len(trades)} trades, showing first 20):")
        print(f"   {'#':>3}  {'Entry Time':<22} {'Entry $':>10}  {'Exit $':>10}  {'P&L':>8}  {'Reason'}")
        print(f"   {'—'*3}  {'—'*22} {'—'*10}  {'—'*10}  {'—'*8}  {'—'*12}")
        for i, t in enumerate(trades[:20], 1):
            pnl = t.return_pct * 100
            print(
                f"   {i:>3}  {str(t.entry_time):<22} "
                f"${t.entry_price:>9,.2f}  ${t.exit_price:>9,.2f}  "
                f"{pnl:>+7.2f}%  {t.exit_reason}"
            )
        if len(trades) > 20:
            print(f"   ... and {len(trades) - 20} more trades")
        print()
    else:
        print("⚠️  No trades were triggered.\n")


if __name__ == "__main__":
    main()
