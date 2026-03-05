"""Position sizing, exposure limits, correlation checks, circuit breakers."""
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import config
from strategies import Direction
from signal_engine import TradeSignal

log = logging.getLogger(__name__)


class RiskManager:
    """Enforces all risk rules before allowing trade execution."""

    def __init__(self, cfg: config.RiskConfig = config.risk):
        self.cfg = cfg
        self._daily_start_equity: Optional[float] = None
        self._circuit_breaker_active = False

    def reset_daily(self, equity: float):
        self._daily_start_equity = equity
        self._circuit_breaker_active = False
        log.info("Daily risk reset — start equity: %.2f", equity)

    def check_circuit_breaker(self, current_equity: float) -> bool:
        """Returns True if trading should be halted."""
        if self._daily_start_equity is None:
            return False
        drawdown = (self._daily_start_equity - current_equity) / self._daily_start_equity
        if drawdown >= self.cfg.daily_drawdown_limit_pct:
            if not self._circuit_breaker_active:
                log.warning("CIRCUIT BREAKER: daily drawdown %.2f%% >= %.2f%% limit",
                            drawdown * 100, self.cfg.daily_drawdown_limit_pct * 100)
                self._circuit_breaker_active = True
            return True
        return False

    def calculate_position_size(
        self, equity: float, entry_price: float, stop_loss: float
    ) -> float:
        """Position size in base asset units, respecting max portfolio % and stop loss."""
        # Max notional by portfolio %
        max_notional = equity * self.cfg.max_position_pct
        # Size based on stop loss distance
        stop_dist = abs(entry_price - stop_loss)
        if stop_dist == 0:
            return 0
        risk_amount = equity * self.cfg.stop_loss_pct
        size_from_risk = risk_amount / stop_dist
        # Notional from risk-based size
        notional_from_risk = size_from_risk * entry_price
        # Take the smaller
        notional = min(max_notional, notional_from_risk)
        size = notional / entry_price
        return size

    def check_exposure(
        self, current_positions: Dict[str, dict], equity: float, new_notional: float
    ) -> bool:
        """Check if adding a new position would exceed max total exposure."""
        current_exposure = sum(
            abs(p.get("notional", 0)) for p in current_positions.values()
        )
        total = current_exposure + new_notional
        max_exposure = equity * self.cfg.max_total_exposure_pct
        if total > max_exposure:
            log.warning("Exposure check failed: current=%.2f + new=%.2f = %.2f > max=%.2f",
                        current_exposure, new_notional, total, max_exposure)
            return False
        return True

    def check_correlation(
        self,
        symbol: str,
        current_positions: Dict[str, dict],
        candles: Dict[str, Dict[str, pd.DataFrame]],
        direction: Direction,
    ) -> bool:
        """Don't stack correlated positions in the same direction."""
        if not current_positions:
            return True

        # Get close prices for correlation
        sym_df = candles.get(symbol, {}).get("5m", pd.DataFrame())
        if sym_df.empty:
            return True

        same_dir_correlated = 0
        for pos_sym, pos_info in current_positions.items():
            if pos_info.get("direction") != direction.value:
                continue
            pos_df = candles.get(pos_sym, {}).get("5m", pd.DataFrame())
            if pos_df.empty:
                continue
            # Align and compute correlation
            merged = pd.DataFrame({
                "a": sym_df["close"].tail(self.cfg.correlation_lookback),
                "b": pos_df["close"].tail(self.cfg.correlation_lookback),
            }).dropna()
            if len(merged) < 20:
                continue
            corr = merged["a"].pct_change().corr(merged["b"].pct_change())
            if abs(corr) >= self.cfg.correlation_threshold:
                same_dir_correlated += 1
                log.debug("Correlated: %s <-> %s = %.3f", symbol, pos_sym, corr)

        if same_dir_correlated >= self.cfg.max_correlated_positions:
            log.warning("Correlation check failed: %s already has %d correlated positions",
                        symbol, same_dir_correlated)
            return False
        return True

    def validate_trade(
        self,
        signal: TradeSignal,
        equity: float,
        positions: Dict[str, dict],
        candles: Dict[str, Dict[str, pd.DataFrame]],
    ) -> Optional[float]:
        """Full risk check. Returns position size if approved, None if rejected."""
        # Circuit breaker
        if self.check_circuit_breaker(equity):
            log.warning("Trade rejected: circuit breaker active")
            return None

        # Already in this symbol?
        if signal.symbol in positions:
            log.info("Trade skipped: already in %s", signal.symbol)
            return None

        # R:R check
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit - signal.entry_price)
        if risk == 0 or reward / risk < self.cfg.min_reward_risk:
            log.info("Trade rejected: R:R %.2f < %.2f", reward / risk if risk else 0, self.cfg.min_reward_risk)
            return None

        # Position size
        size = self.calculate_position_size(equity, signal.entry_price, signal.stop_loss)
        if size <= 0:
            return None
        notional = size * signal.entry_price

        # Exposure
        if not self.check_exposure(positions, equity, notional):
            return None

        # Correlation
        if not self.check_correlation(signal.symbol, positions, candles, signal.direction):
            return None

        log.info("Trade approved: %s %s size=%.6f notional=%.2f",
                 signal.symbol, signal.direction.value, size, notional)
        return size
