"""
Portfolio Manager
=================
Manages capital allocation across multiple assets simultaneously.
  - Maximum 3 concurrent positions
  - Per-asset allocation: no more than 40% of portfolio in one asset
  - Kelly Criterion position sizing
  - Correlation check: avoid correlated positions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from position import Position, PositionSide, PositionTracker


@dataclass
class PortfolioConfig:
    """Portfolio management parameters."""
    max_concurrent_positions: int = 4
    max_per_asset_pct: float = 0.50      # 50% max in one asset
    max_risk_per_trade: float = 0.02     # 2% risk per trade
    min_position_usd: float = 100.0      # minimum position size
    correlation_threshold: float = 0.70  # reject if correlation > this
    correlation_lookback: int = 48       # candles for correlation calc
    kelly_fraction: float = 0.25         # use quarter-Kelly for safety


# Known high-correlation pairs (used as fallback when insufficient data)
HIGH_CORR_PAIRS = {
    frozenset({"BTC-USD", "ETH-USD"}),
    frozenset({"SOL-USD", "ETH-USD"}),
}


class PortfolioManager:
    """
    Manages capital allocation and position sizing across multiple assets.
    """

    def __init__(self, initial_capital: float, config: Optional[PortfolioConfig] = None):
        self.initial_capital = initial_capital
        self.equity = initial_capital
        self.config = config or PortfolioConfig()
        self.tracker = PositionTracker()
        self._trade_stats: Dict[str, dict] = {}  # asset -> {wins, losses, avg_win, avg_loss}
        self._price_history: Dict[str, list] = {}  # asset -> recent closes for correlation

    def update_equity(self, prices: Dict[str, float]) -> float:
        """
        Recalculate equity: cash + unrealized P&L on open positions.
        Returns updated equity.
        """
        cash = self.equity
        # Subtract allocated capital and add current value
        for pos in self.tracker.open_positions:
            if pos.is_open and pos.asset in prices:
                cash += pos.unrealized_pnl_usd(prices[pos.asset])
        return cash

    def record_prices(self, prices: Dict[str, float]) -> None:
        """Record current prices for correlation calculation."""
        for asset, price in prices.items():
            if asset not in self._price_history:
                self._price_history[asset] = []
            self._price_history[asset].append(price)
            # Keep manageable size
            if len(self._price_history[asset]) > 200:
                self._price_history[asset] = self._price_history[asset][-200:]

    def can_open_position(self, asset: str) -> Tuple[bool, str]:
        """
        Check if we can open a new position for this asset.
        Returns (allowed, reason).
        """
        cfg = self.config
        open_positions = [p for p in self.tracker.open_positions if p.is_open]

        # Already have a position in this asset?
        if any(p.asset == asset for p in open_positions):
            return False, "already_positioned"

        # Max concurrent positions?
        if len(open_positions) >= cfg.max_concurrent_positions:
            return False, "max_positions"

        # Correlation check
        for pos in open_positions:
            if self._is_correlated(asset, pos.asset):
                return False, f"correlated_with_{pos.asset}"

        return True, "ok"

    def _is_correlated(self, asset1: str, asset2: str) -> bool:
        """Check if two assets are too highly correlated."""
        # Known pairs shortcut
        if frozenset({asset1, asset2}) in HIGH_CORR_PAIRS:
            return True

        # Calculate from price history
        cfg = self.config
        h1 = self._price_history.get(asset1, [])
        h2 = self._price_history.get(asset2, [])

        min_len = min(len(h1), len(h2))
        if min_len < cfg.correlation_lookback:
            # Not enough data — use known pairs only
            return False

        r1 = np.diff(h1[-cfg.correlation_lookback:]) / np.array(h1[-cfg.correlation_lookback:])[:-1]
        r2 = np.diff(h2[-cfg.correlation_lookback:]) / np.array(h2[-cfg.correlation_lookback:])[:-1]

        if len(r1) < 2 or np.std(r1) == 0 or np.std(r2) == 0:
            return False

        corr = np.corrcoef(r1, r2)[0, 1]
        return abs(corr) > cfg.correlation_threshold

    def calculate_position_size(
        self,
        asset: str,
        atr: float,
        price: float,
        side: PositionSide,
    ) -> float:
        """
        Calculate position size in USD using Kelly Criterion + constraints.
        
        Returns USD amount to allocate.
        """
        cfg = self.config

        # Base: ATR-based risk sizing
        if atr <= 0 or price <= 0:
            base_size = self.equity * 0.1  # fallback
        else:
            risk_amount = cfg.max_risk_per_trade * self.equity
            stop_distance = 2 * atr
            units = risk_amount / stop_distance
            base_size = units * price

        # Kelly adjustment
        kelly = self._kelly_fraction(asset)
        size = base_size * kelly

        # Cap at max per-asset allocation
        max_alloc = self.equity * cfg.max_per_asset_pct
        size = min(size, max_alloc)

        # Check exposure limit (handled by risk manager, but double-check)
        current_exposure = self.tracker.total_exposure_usd
        remaining = self.equity * 0.9 - current_exposure  # 90% exposure limit
        size = min(size, max(0, remaining))

        # Minimum size check
        if size < cfg.min_position_usd:
            return 0.0

        return size

    def _kelly_fraction(self, asset: str) -> float:
        """
        Calculate Kelly Criterion fraction for position sizing.
        Kelly = (W * avg_win - (1-W) * avg_loss) / avg_win
        We use quarter-Kelly for safety.
        """
        stats = self._trade_stats.get(asset, None)
        if stats is None or stats.get("total", 0) < 5:
            return self.config.kelly_fraction  # default quarter-Kelly

        wins = stats["wins"]
        total = stats["total"]
        w = wins / total  # win rate
        avg_win = abs(stats["avg_win"]) if stats["avg_win"] != 0 else 0.01
        avg_loss = abs(stats["avg_loss"]) if stats["avg_loss"] != 0 else 0.01

        if avg_win <= 0:
            return self.config.kelly_fraction

        kelly = (w * avg_win - (1 - w) * avg_loss) / avg_win
        kelly = max(0.05, min(1.0, kelly))  # clamp
        return kelly * self.config.kelly_fraction  # quarter-Kelly

    def record_trade(self, asset: str, pnl_pct: float, is_win: bool) -> None:
        """Record trade result for Kelly calculation."""
        if asset not in self._trade_stats:
            self._trade_stats[asset] = {"wins": 0, "losses": 0, "total": 0, "sum_wins": 0.0, "sum_losses": 0.0, "avg_win": 0.0, "avg_loss": 0.0}

        stats = self._trade_stats[asset]
        stats["total"] += 1
        if is_win:
            stats["wins"] += 1
            stats["sum_wins"] += pnl_pct
            stats["avg_win"] = stats["sum_wins"] / stats["wins"]
        else:
            stats["losses"] += 1
            stats["sum_losses"] += abs(pnl_pct)
            stats["avg_loss"] = stats["sum_losses"] / stats["losses"] if stats["losses"] > 0 else 0

    def realize_pnl(self, pnl_usd: float) -> None:
        """Add realized P&L to equity."""
        self.equity += pnl_usd

    def get_allocation_summary(self) -> Dict[str, float]:
        """Return current allocation percentages by asset."""
        result = {}
        for pos in self.tracker.open_positions:
            if pos.is_open:
                result[pos.asset] = pos.remaining_usd / self.equity * 100 if self.equity > 0 else 0
        result["cash"] = max(0, (self.equity - self.tracker.total_exposure_usd) / self.equity * 100) if self.equity > 0 else 100
        return result
