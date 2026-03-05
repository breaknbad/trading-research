"""
Mean-reversion trading strategy using Bollinger Bands + RSI.

Rules:
  BUY  — price <= lower Bollinger Band AND RSI < 30
  SELL — price >= upper Bollinger Band AND RSI > 70
  STOP — price drops 3% below entry (stop-loss)
"""

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from indicators import add_all_indicators


@dataclass
class Trade:
    """Record of a single completed trade."""
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str  # "signal" or "stop_loss"

    @property
    def return_pct(self) -> float:
        return (self.exit_price - self.entry_price) / self.entry_price

    @property
    def is_win(self) -> bool:
        return self.exit_price > self.entry_price


@dataclass
class StrategyConfig:
    """Tunable parameters for the mean-reversion strategy."""
    bb_window: int = 20
    bb_std: float = 1.75
    rsi_window: int = 14
    rsi_buy_threshold: float = 35.0
    rsi_sell_threshold: float = 65.0
    stop_loss_pct: float = 0.025  # 2.5%


@dataclass
class BacktestResult:
    """Container for backtest output."""
    trades: List[Trade] = field(default_factory=list)
    equity_curve: Optional[pd.Series] = None


def run_backtest(
    df: pd.DataFrame,
    config: Optional[StrategyConfig] = None,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    """
    Run the mean-reversion backtest on OHLCV data.

    Assumes fully invested on each trade (no position sizing / leverage).
    Only one position open at a time (long only).

    Args:
        df: OHLCV DataFrame (must have datetime, open, high, low, close, volume).
        config: Strategy parameters. Uses defaults if None.
        initial_capital: Starting capital in USD.

    Returns:
        BacktestResult with trade list and equity curve.
    """
    if config is None:
        config = StrategyConfig()

    # Compute indicators
    df = add_all_indicators(df)

    # Drop rows where indicators aren't ready yet
    df = df.dropna(subset=["bb_lower", "bb_upper", "rsi"]).reset_index(drop=True)

    trades: List[Trade] = []
    equity = initial_capital
    equity_values = []
    equity_times = []

    in_position = False
    entry_price = 0.0
    entry_time = None
    stop_price = 0.0

    for i, row in df.iterrows():
        price = row["close"]

        if in_position:
            # --- Check stop-loss (use the low of the candle) ---
            if row["low"] <= stop_price:
                exit_price = stop_price  # assume filled at stop
                pnl = (exit_price - entry_price) / entry_price
                equity *= (1 + pnl)

                trades.append(Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=row["datetime"],
                    exit_price=exit_price,
                    exit_reason="stop_loss",
                ))

                in_position = False

            # --- Check sell signal ---
            elif price >= row["bb_upper"] and row["rsi"] > config.rsi_sell_threshold:
                pnl = (price - entry_price) / entry_price
                equity *= (1 + pnl)

                trades.append(Trade(
                    entry_time=entry_time,
                    entry_price=entry_price,
                    exit_time=row["datetime"],
                    exit_price=price,
                    exit_reason="signal",
                ))

                in_position = False

        else:
            # --- Check buy signal ---
            if price <= row["bb_lower"] and row["rsi"] < config.rsi_buy_threshold:
                entry_price = price
                entry_time = row["datetime"]
                stop_price = entry_price * (1 - config.stop_loss_pct)
                in_position = True

        equity_values.append(equity)
        equity_times.append(row["datetime"])

    result = BacktestResult(
        trades=trades,
        equity_curve=pd.Series(equity_values, index=equity_times, name="equity"),
    )

    return result
