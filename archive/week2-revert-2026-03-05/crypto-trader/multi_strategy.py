"""
Multi-Strategy Engine
=====================
Routes candles to the appropriate strategy based on market regime:
  - RANGING       → Mean Reversion (Bollinger Bands + RSI)
  - TRENDING_UP   → Trend Following Long
  - TRENDING_DOWN → Trend Following Short

Handles regime transitions by closing open positions.
Risk management: ATR-based position sizing, 2% max risk, 15% circuit breaker.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict

import pandas as pd
import numpy as np

from indicators import add_all_multi_indicators
from regime import detect_regime, Regime
from strategy import Trade, StrategyConfig
from trend_strategy import TrendFollower, TrendStrategyConfig


@dataclass
class MultiStrategyConfig:
    """Configuration for the multi-strategy engine."""
    mean_reversion: StrategyConfig = field(default_factory=StrategyConfig)
    trend: TrendStrategyConfig = field(default_factory=TrendStrategyConfig)
    max_risk_per_trade: float = 0.02   # 2% of capital risked per trade
    circuit_breaker_pct: float = 0.15  # stop trading at 15% total drawdown
    initial_capital: float = 10_000.0


@dataclass
class MultiBacktestResult:
    """Results from the multi-strategy backtest."""
    trades: List[Trade] = field(default_factory=list)
    equity_curve: Optional[pd.Series] = None
    regime_series: Optional[pd.Series] = None
    # Per-strategy trade lists
    mean_reversion_trades: List[Trade] = field(default_factory=list)
    trend_long_trades: List[Trade] = field(default_factory=list)
    trend_short_trades: List[Trade] = field(default_factory=list)


def _position_size(equity: float, atr: float, price: float, max_risk_pct: float) -> float:
    """
    Calculate position size based on ATR risk.
    Risk per trade = max_risk_pct * equity.
    Stop distance = 2 * ATR.
    Position size (in units) = risk_amount / stop_distance.
    Returns fraction of equity to allocate (0-1).
    """
    if atr <= 0 or price <= 0:
        return 1.0  # fallback to full allocation
    risk_amount = max_risk_pct * equity
    stop_distance = 2 * atr
    units = risk_amount / stop_distance
    allocation = (units * price) / equity
    return min(allocation, 1.0)  # cap at 100%


def run_multi_backtest(
    df: pd.DataFrame,
    config: Optional[MultiStrategyConfig] = None,
) -> MultiBacktestResult:
    """
    Run the multi-strategy backtest.

    Args:
        df: OHLCV DataFrame with datetime, open, high, low, close, volume.
        config: Strategy parameters.

    Returns:
        MultiBacktestResult with trades, equity curve, and regime breakdown.
    """
    if config is None:
        config = MultiStrategyConfig()

    # Add all indicators
    df = add_all_multi_indicators(df)
    df = detect_regime(df)

    # Add helper columns for trend strategy
    df["prev_close"] = df["close"].shift(1)
    df["adx_rising"] = df["adx"] > df["adx"].shift(config.trend.adx_lookback)
    # Enhanced short: death cross detection columns
    if "ema_50" in df.columns:
        df["prev_ema_50"] = df["ema_50"].shift(1)
    if "ema_200" in df.columns:
        df["prev_ema_200"] = df["ema_200"].shift(1)

    # Drop rows where indicators aren't ready
    required_cols = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_15", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required_cols).reset_index(drop=True)

    if len(df) == 0:
        return MultiBacktestResult()

    # State
    equity = config.initial_capital
    peak_equity = equity
    equity_values = []
    equity_times = []
    circuit_breaker_active = False

    # Mean reversion state
    mr_in_position = False
    mr_entry_price = 0.0
    mr_entry_time = None
    mr_stop_price = 0.0
    mr_alloc = 1.0  # position size fraction

    # Trend follower
    trend = TrendFollower(config.trend)

    # Track trades by strategy
    all_trades: List[Trade] = []
    mr_trades: List[Trade] = []
    trend_long_trades: List[Trade] = []
    trend_short_trades: List[Trade] = []

    prev_regime = None

    for i, row in df.iterrows():
        price = row["close"]
        regime = row["regime"]
        atr = row["atr"]

        # --- Circuit breaker check ---
        if not circuit_breaker_active:
            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
            if drawdown >= config.circuit_breaker_pct:
                circuit_breaker_active = True
                # Close everything
                if mr_in_position:
                    pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "circuit_breaker")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False

                t = trend.force_close(price, row["datetime"], "circuit_breaker")
                if t:
                    all_trades.append(t)
                    if trend.direction == "long":
                        trend_long_trades.append(t)
                    else:
                        trend_short_trades.append(t)

        if circuit_breaker_active:
            equity_values.append(equity)
            equity_times.append(row["datetime"])
            continue

        # --- Handle regime transition ---
        if prev_regime is not None and regime != prev_regime:
            # Close mean reversion position
            if mr_in_position:
                pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                equity *= (1 + pnl)
                t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "regime_change")
                all_trades.append(t)
                mr_trades.append(t)
                mr_in_position = False

            # Close trend position
            t = trend.force_close(price, row["datetime"], "regime_change")
            if t:
                # Apply P&L
                pnl = t.return_pct * _position_size(equity, atr, price, config.max_risk_per_trade)
                equity *= (1 + pnl)
                all_trades.append(t)
                if "long" in (trend.direction or ""):
                    trend_long_trades.append(t)
                else:
                    trend_short_trades.append(t)

        prev_regime = regime

        # --- Route to strategy ---
        if regime == Regime.RANGING.value:
            # Mean reversion logic (inline, mirrors strategy.py)
            mc = config.mean_reversion
            if mr_in_position:
                # Stop loss
                if row["low"] <= mr_stop_price:
                    pnl = (mr_stop_price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], mr_stop_price, "stop_loss")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False

                elif price >= row["bb_upper"] and row["rsi"] > mc.rsi_sell_threshold:
                    pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "signal")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False

                # Mid-band exit: take profit if price crosses back above SMA (middle band)
                elif price > mr_entry_price and price >= row["bb_mid"]:
                    pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "mid_band_exit")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False
            else:
                if price <= row["bb_lower"] and row["rsi"] < mc.rsi_buy_threshold:
                    mr_alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                    mr_entry_price = price
                    mr_entry_time = row["datetime"]
                    mr_stop_price = mr_entry_price * (1 - mc.stop_loss_pct)
                    mr_in_position = True

        elif regime in (Regime.WEAK_TREND_UP.value, Regime.WEAK_TREND_DOWN.value):
            # Hybrid zone: run BOTH mean reversion and trend following
            # Mean reversion logic
            mc = config.mean_reversion
            if mr_in_position:
                if row["low"] <= mr_stop_price:
                    pnl = (mr_stop_price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], mr_stop_price, "stop_loss")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False
                elif price >= row["bb_upper"] and row["rsi"] > mc.rsi_sell_threshold:
                    pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "signal")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False
                elif price > mr_entry_price and price >= row["bb_mid"]:
                    pnl = (price - mr_entry_price) / mr_entry_price * mr_alloc
                    equity *= (1 + pnl)
                    t = Trade(mr_entry_time, mr_entry_price, row["datetime"], price, "mid_band_exit")
                    all_trades.append(t)
                    mr_trades.append(t)
                    mr_in_position = False
            else:
                if price <= row["bb_lower"] and row["rsi"] < mc.rsi_buy_threshold:
                    mr_alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                    mr_entry_price = price
                    mr_entry_time = row["datetime"]
                    mr_stop_price = mr_entry_price * (1 - mc.stop_loss_pct)
                    mr_in_position = True

            # Also run trend following in weak trend zone
            trend_regime = Regime.TRENDING_UP.value if regime == Regime.WEAK_TREND_UP.value else Regime.TRENDING_DOWN.value
            trade = trend.process_bar(row, trend_regime)
            if trade:
                alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                pnl = trade.return_pct * alloc
                equity *= (1 + pnl)
                all_trades.append(trade)
                if trend_regime == Regime.TRENDING_UP.value:
                    trend_long_trades.append(trade)
                else:
                    trend_short_trades.append(trade)

        elif regime in (Regime.TRENDING_UP.value, Regime.TRENDING_DOWN.value):
            trade = trend.process_bar(row, regime)
            if trade:
                alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                pnl = trade.return_pct * alloc
                equity *= (1 + pnl)
                all_trades.append(trade)
                if regime == Regime.TRENDING_UP.value:
                    trend_long_trades.append(trade)
                else:
                    trend_short_trades.append(trade)

        # Update equity tracking
        peak_equity = max(peak_equity, equity)
        equity_values.append(equity)
        equity_times.append(row["datetime"])

    return MultiBacktestResult(
        trades=all_trades,
        equity_curve=pd.Series(equity_values, index=equity_times, name="equity"),
        regime_series=df.set_index("datetime")["regime"] if "datetime" in df.columns else None,
        mean_reversion_trades=mr_trades,
        trend_long_trades=trend_long_trades,
        trend_short_trades=trend_short_trades,
    )
