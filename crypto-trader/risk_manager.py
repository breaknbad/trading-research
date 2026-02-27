"""
Risk Management Layer
=====================
Portfolio-level risk controls:
  - Circuit breaker: stop all trading if drawdown exceeds 15%
  - Daily loss limit: stop trading for the day if down > 5%
  - Volatility scaling: reduce position sizes when realized vol is high
  - Consecutive loss pause: pause after 5 consecutive losses
  - Exposure limits: max 80% of capital deployed (20% cash reserve)
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class RiskConfig:
    """Risk management parameters."""
    max_drawdown_pct: float = 0.15       # 15% portfolio circuit breaker
    daily_loss_limit_pct: float = 0.07   # 7% daily loss limit
    max_consecutive_losses: int = 4      # pause after this many consecutive losses
    pause_candles: int = 12              # how long to pause after consecutive losses
    max_exposure_pct: float = 0.90       # max 90% of capital deployed
    vol_lookback: int = 24               # hours for realized vol calculation
    vol_scale_threshold: float = 2.0     # if vol > threshold * median vol, scale down
    vol_min_scale: float = 0.25          # minimum position scale during high vol


@dataclass
class RiskState:
    """Mutable risk state tracked during a backtest."""
    peak_equity: float = 0.0
    day_start_equity: float = 0.0
    current_day: Optional[str] = None  # YYYY-MM-DD
    consecutive_losses: int = 0
    pause_remaining: int = 0  # candles remaining in pause
    circuit_breaker_active: bool = False
    daily_stop_active: bool = False
    median_vol: float = 0.0  # baseline volatility


class RiskManager:
    """
    Evaluates risk conditions and gates trading decisions.
    Call check() before each trade to get permission and sizing scale.
    Call record_trade() after each trade closes.
    Call update_bar() every candle.
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self.state = RiskState()
        self._recent_returns: list = []  # for vol calculation

    def initialize(self, equity: float) -> None:
        """Set initial state at backtest start."""
        self.state.peak_equity = equity
        self.state.day_start_equity = equity
        self.state.current_day = None
        self.state.consecutive_losses = 0
        self.state.pause_remaining = 0
        self.state.circuit_breaker_active = False
        self.state.daily_stop_active = False
        self._recent_returns = []

    def update_bar(self, equity: float, time: pd.Timestamp, close_return: float = 0.0) -> None:
        """
        Call every candle to update risk state.
        
        Args:
            equity: Current portfolio equity.
            time: Current timestamp.
            close_return: Single-bar return (close/prev_close - 1).
        """
        cfg = self.config
        state = self.state

        # Track peak equity
        state.peak_equity = max(state.peak_equity, equity)

        # Track daily boundary
        day_str = str(time.date()) if hasattr(time, 'date') else str(time)[:10]
        if state.current_day != day_str:
            state.current_day = day_str
            state.day_start_equity = equity
            state.daily_stop_active = False  # reset daily stop

        # Circuit breaker check
        if state.peak_equity > 0:
            drawdown = (state.peak_equity - equity) / state.peak_equity
            if drawdown >= cfg.max_drawdown_pct:
                state.circuit_breaker_active = True

        # Daily loss check
        if state.day_start_equity > 0:
            daily_loss = (state.day_start_equity - equity) / state.day_start_equity
            if daily_loss >= cfg.daily_loss_limit_pct:
                state.daily_stop_active = True

        # Pause countdown
        if state.pause_remaining > 0:
            state.pause_remaining -= 1

        # Track returns for vol calculation
        self._recent_returns.append(close_return)
        if len(self._recent_returns) > cfg.vol_lookback * 10:
            self._recent_returns = self._recent_returns[-cfg.vol_lookback * 10:]

        # Update median vol baseline (use rolling window)
        if len(self._recent_returns) >= cfg.vol_lookback:
            recent = self._recent_returns[-cfg.vol_lookback:]
            current_vol = np.std(recent) if len(recent) > 1 else 0
            # Slowly update median baseline
            if state.median_vol == 0:
                state.median_vol = current_vol if current_vol > 0 else 1e-6
            else:
                state.median_vol = 0.99 * state.median_vol + 0.01 * current_vol

    def record_trade(self, is_win: bool) -> None:
        """Record trade outcome for consecutive loss tracking."""
        if is_win:
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1
            if self.state.consecutive_losses >= self.config.max_consecutive_losses:
                self.state.pause_remaining = self.config.pause_candles
                self.state.consecutive_losses = 0  # reset after pause triggered

    def can_trade(self) -> bool:
        """Check if trading is currently allowed."""
        state = self.state
        if state.circuit_breaker_active:
            return False
        if state.daily_stop_active:
            return False
        if state.pause_remaining > 0:
            return False
        return True

    def max_new_exposure_usd(self, equity: float, current_exposure: float) -> float:
        """Maximum additional USD that can be deployed."""
        max_total = equity * self.config.max_exposure_pct
        available = max_total - current_exposure
        return max(0.0, available)

    def volatility_scale(self) -> float:
        """
        Position size multiplier based on current volatility.
        Returns 1.0 in normal conditions, scales down to vol_min_scale in high vol.
        """
        cfg = self.config
        state = self.state
        if state.median_vol <= 0 or len(self._recent_returns) < cfg.vol_lookback:
            return 1.0

        recent = self._recent_returns[-cfg.vol_lookback:]
        current_vol = np.std(recent) if len(recent) > 1 else 0

        if current_vol <= 0 or state.median_vol <= 0:
            return 1.0

        vol_ratio = current_vol / state.median_vol
        if vol_ratio <= cfg.vol_scale_threshold:
            return 1.0

        # Linear scale down: at 2x threshold → min_scale
        scale = 1.0 - (vol_ratio - cfg.vol_scale_threshold) / cfg.vol_scale_threshold
        return max(cfg.vol_min_scale, min(1.0, scale))

    def get_status(self) -> dict:
        """Return current risk state as a dict for reporting."""
        return {
            "circuit_breaker": self.state.circuit_breaker_active,
            "daily_stop": self.state.daily_stop_active,
            "consecutive_losses": self.state.consecutive_losses,
            "pause_remaining": self.state.pause_remaining,
            "vol_scale": self.volatility_scale(),
            "drawdown_pct": (
                (self.state.peak_equity - self.state.day_start_equity) / self.state.peak_equity * 100
                if self.state.peak_equity > 0 else 0
            ),
        }
