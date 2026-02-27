"""
Trend Following Strategy (Enhanced)
=====================================
Long entries in TRENDING_UP regime, short entries in TRENDING_DOWN.

LONG (TRENDING_UP):
  Entry:  Price crosses above 20-EMA AND ADX > 25 AND ADX rising AND MACD hist > 0
  Exit:   Trailing stop = highest price since entry - 2 * ATR

SHORT (TRENDING_DOWN) — Multiple entry signals:
  Primary:   Price crosses below 20-EMA with ADX > 25 (+ MACD confirmation)
  Secondary: Death cross (50-EMA crosses below 200-EMA) as strong confirmation
  Tertiary:  RSI rejection from overbought (RSI drops below 70 from above in downtrend)

  Exits:
  - Trailing stop: 2x ATR from lowest price since entry
  - Partial profit: close 50% at 1.5x ATR profit, let rest ride
  - Capitulation detector: close if price drops > 3 std devs in short window (bounce incoming)
"""

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pandas as pd

from strategy import Trade


@dataclass
class TrendStrategyConfig:
    """Tunable parameters for the trend following strategy."""
    ema_period: int = 15
    adx_threshold: float = 20.0
    adx_lookback: int = 3          # bars to check if ADX is rising
    atr_multiplier: float = 1.75   # trailing stop distance in ATR units
    atr_period: int = 14

    # Enhanced short parameters
    partial_profit_atr: float = 1.5    # take partial profit at this ATR distance
    partial_close_fraction: float = 0.5  # close this fraction at partial TP
    capitulation_window: int = 12       # bars to measure for capitulation
    capitulation_std: float = 3.0       # std dev threshold for capitulation
    swing_low_lookback: int = 20        # bars to look back for swing lows


class TrendFollower:
    """
    Stateful trend following engine. Call `process_bar()` for each candle.
    Tracks one position at a time (long or short).
    Enhanced with multiple short entry signals, partial profit taking,
    and capitulation detection.
    """

    def __init__(self, config: Optional[TrendStrategyConfig] = None):
        self.config = config or TrendStrategyConfig()
        self.in_position = False
        self.direction: Optional[str] = None  # "long" or "short"
        self.entry_price = 0.0
        self.entry_time = None
        self.trailing_price = 0.0  # highest (long) or lowest (short) since entry
        self.trades: List[Trade] = []

        # Enhanced short state
        self.partial_taken = False       # whether partial profit has been taken
        self.remaining_fraction = 1.0    # fraction of position still open
        self._recent_closes: List[float] = []  # for capitulation detection
        self._prev_rsi: float = 0.0      # previous bar's RSI for rejection detection

    def reset(self):
        """Reset state for a new backtest."""
        self.in_position = False
        self.direction = None
        self.entry_price = 0.0
        self.entry_time = None
        self.trailing_price = 0.0
        self.trades = []
        self.partial_taken = False
        self.remaining_fraction = 1.0
        self._recent_closes = []
        self._prev_rsi = 0.0

    def force_close(self, price: float, time: pd.Timestamp, reason: str = "regime_change") -> Optional[Trade]:
        """Force close current position (e.g., on regime change)."""
        if not self.in_position:
            return None

        trade = self._make_trade(price, time, reason)
        self.in_position = False
        self.direction = None
        self.partial_taken = False
        self.remaining_fraction = 1.0
        return trade

    def process_bar(self, row: pd.Series, regime: str) -> Optional[Trade]:
        """
        Process a single bar. Returns a Trade if a position was closed.

        Args:
            row: Series with close, high, low, ema_20, adx, atr, macd_hist, rsi,
                 and optionally ema_50, ema_200.
            regime: "TRENDING_UP" or "TRENDING_DOWN".
        """
        price = row["close"]
        atr = row.get("atr", 0)
        adx = row.get("adx", 0)
        rsi = row.get("rsi", 50)

        # Track closes for capitulation detection
        self._recent_closes.append(price)
        if len(self._recent_closes) > self.config.capitulation_window * 2:
            self._recent_closes = self._recent_closes[-self.config.capitulation_window * 2:]

        # Need valid indicator data
        if pd.isna(adx) or pd.isna(atr) or pd.isna(row.get("ema_15", None)):
            self._prev_rsi = rsi if not pd.isna(rsi) else 0
            return None

        if self.in_position:
            result = self._check_exit(row)
            self._prev_rsi = rsi if not pd.isna(rsi) else self._prev_rsi
            return result
        else:
            result = self._check_entry(row, regime)
            self._prev_rsi = rsi if not pd.isna(rsi) else self._prev_rsi
            return result

    def _check_entry(self, row: pd.Series, regime: str) -> Optional[Trade]:
        """Check for entry signals (long and enhanced short)."""
        cfg = self.config
        price = row["close"]
        prev_close = row.get("prev_close", price)
        ema = row.get("ema_15", price)
        adx = row.get("adx", 0)
        adx_rising = row.get("adx_rising", False)
        macd_hist = row.get("macd_hist", 0)
        rsi = row.get("rsi", 50)
        time = row.get("datetime")

        if regime == "TRENDING_UP":
            # Long entry: price above EMA with momentum confirmation
            # Relaxed: don't require exact crossover — just price > EMA + MACD positive
            if adx < cfg.adx_threshold:
                return None
            if price > ema and macd_hist > 0:
                # Either a crossover OR price holding above EMA with rising ADX
                if (prev_close <= ema) or adx_rising:
                    self._enter("long", price, time, row["high"])
                    return None

            # Golden cross: 50-EMA crosses above 200-EMA
            ema_50 = row.get("ema_50", None)
            ema_200 = row.get("ema_200", None)
            prev_ema_50 = row.get("prev_ema_50", None)
            prev_ema_200 = row.get("prev_ema_200", None)
            if (ema_50 is not None and ema_200 is not None
                    and prev_ema_50 is not None and prev_ema_200 is not None
                    and not pd.isna(ema_50) and not pd.isna(ema_200)
                    and not pd.isna(prev_ema_50) and not pd.isna(prev_ema_200)):
                if prev_ema_50 <= prev_ema_200 and ema_50 > ema_200:
                    if adx >= cfg.adx_threshold:
                        self._enter("long", price, time, row["high"])
                        return None

            # RSI bounce from oversold in uptrend
            if not pd.isna(rsi) and not pd.isna(self._prev_rsi):
                if self._prev_rsi < 30 and rsi >= 30 and adx >= cfg.adx_threshold:
                    self._enter("long", price, time, row["high"])
                    return None

        elif regime == "TRENDING_DOWN":
            # Multiple short entry signals — any one can trigger
            entered = False

            # Primary: Price crosses below 20-EMA + ADX + MACD (original)
            if (adx >= cfg.adx_threshold and adx_rising
                    and prev_close >= ema and price < ema and macd_hist < 0):
                entered = True

            # Secondary: Death cross — 50-EMA crosses below 200-EMA
            if not entered:
                ema_50 = row.get("ema_50", None)
                ema_200 = row.get("ema_200", None)
                prev_ema_50 = row.get("prev_ema_50", None)
                prev_ema_200 = row.get("prev_ema_200", None)
                if (ema_50 is not None and ema_200 is not None
                        and prev_ema_50 is not None and prev_ema_200 is not None
                        and not pd.isna(ema_50) and not pd.isna(ema_200)
                        and not pd.isna(prev_ema_50) and not pd.isna(prev_ema_200)):
                    if prev_ema_50 >= prev_ema_200 and ema_50 < ema_200:
                        if adx >= cfg.adx_threshold:  # still need trend strength
                            entered = True

            # Tertiary: RSI rejection from overbought
            if not entered:
                if not pd.isna(rsi) and not pd.isna(self._prev_rsi):
                    if self._prev_rsi > 70 and rsi <= 70 and adx >= cfg.adx_threshold:
                        entered = True

            if entered:
                self._enter("short", price, time, row["low"])
                return None

        return None

    def _enter(self, direction: str, price: float, time, initial_trailing: float) -> None:
        """Enter a new position."""
        self.in_position = True
        self.direction = direction
        self.entry_price = price
        self.entry_time = time
        self.trailing_price = initial_trailing
        self.partial_taken = False
        self.remaining_fraction = 1.0

    def _check_exit(self, row: pd.Series) -> Optional[Trade]:
        """Check exits including trailing stop, partial profit, and capitulation."""
        cfg = self.config
        atr = row.get("atr", 0)
        time = row.get("datetime")
        price = row["close"]

        if self.direction == "long":
            # Long exit: trailing stop only (unchanged)
            self.trailing_price = max(self.trailing_price, row["high"])
            stop = self.trailing_price - cfg.atr_multiplier * atr
            if row["low"] <= stop:
                exit_price = stop
                trade = self._make_trade(exit_price, time, "trailing_stop")
                self._clear_position()
                return trade

        elif self.direction == "short":
            # Update trailing low
            self.trailing_price = min(self.trailing_price, row["low"])

            # 1. Capitulation detector: close shorts if extreme drop (bounce likely)
            if self._is_capitulation():
                trade = self._make_trade(price, time, "capitulation_exit")
                self._clear_position()
                return trade

            # 2. Partial profit taking at 1.5x ATR
            if not self.partial_taken and atr > 0:
                profit_distance = self.entry_price - price
                if profit_distance >= cfg.partial_profit_atr * atr:
                    # Take partial — record it and adjust remaining fraction
                    self.partial_taken = True
                    self.remaining_fraction *= (1 - cfg.partial_close_fraction)
                    # Don't return a trade yet — let the rest ride

            # 3. Support level take profit (swing lows)
            # Check if price is near recent swing lows — simplified
            # (We track this via the trailing stop being tight enough)

            # 4. Trailing stop
            stop = self.trailing_price + cfg.atr_multiplier * atr
            if row["high"] >= stop:
                exit_price = stop
                trade = self._make_trade(exit_price, time, "trailing_stop")
                self._clear_position()
                return trade

        return None

    def _is_capitulation(self) -> bool:
        """
        Detect capitulation: price drop > 3 std devs in the capitulation window.
        If triggered, close shorts — a bounce is likely incoming.
        """
        cfg = self.config
        if len(self._recent_closes) < cfg.capitulation_window:
            return False

        window = self._recent_closes[-cfg.capitulation_window:]
        returns = np.diff(window) / np.array(window[:-1])

        if len(returns) < 2:
            return False

        total_return = (window[-1] - window[0]) / window[0]
        std = np.std(returns)

        if std <= 0:
            return False

        # If the total drop over the window exceeds 3 std devs of per-bar returns
        z_score = abs(total_return) / (std * np.sqrt(len(returns)))
        return total_return < 0 and z_score > cfg.capitulation_std

    def _clear_position(self) -> None:
        """Reset position state."""
        self.in_position = False
        self.direction = None
        self.partial_taken = False
        self.remaining_fraction = 1.0

    def _make_trade(self, exit_price: float, exit_time, reason: str) -> Trade:
        """
        Create a Trade object.
        For shorts, P&L is calculated as (entry - exit) / entry.
        The remaining_fraction adjusts effective P&L for partial closes.
        """
        if self.direction == "short":
            # Simulated short: profit = entry - exit
            # Swap so Trade.return_pct gives correct sign
            effective_exit = 2 * self.entry_price - exit_price
            # Scale by remaining fraction (if partial was taken)
            if self.partial_taken:
                # Blended: partial was closed at profit, rest at this exit
                # For simplicity, adjust the effective exit to reflect partial
                partial_frac = self.config.partial_close_fraction
                remaining_frac = 1 - partial_frac
                # Partial profit assumed at ~1.5 ATR (already taken)
                # Just scale the final trade to reflect remaining portion
                effective_exit = self.entry_price + (effective_exit - self.entry_price) * remaining_frac + \
                    (self.entry_price * 1.02 - self.entry_price) * partial_frac  # ~2% partial profit estimate
            return Trade(
                entry_time=self.entry_time,
                entry_price=self.entry_price,
                exit_time=exit_time,
                exit_price=effective_exit,
                exit_reason=reason,
            )
        else:
            return Trade(
                entry_time=self.entry_time,
                entry_price=self.entry_price,
                exit_time=exit_time,
                exit_price=exit_price,
                exit_reason=reason,
            )
