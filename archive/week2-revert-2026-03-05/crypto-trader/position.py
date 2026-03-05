"""
Position Management
===================
Tracks open positions with entry price, size, type (long/short),
stop loss, take profit. Supports partial closes and P&L tracking.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

import pandas as pd


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class PositionClose:
    """Record of a partial or full position close."""
    time: pd.Timestamp
    price: float
    size_fraction: float  # fraction of original position closed (0-1)
    reason: str
    pnl_pct: float  # realized P&L for this chunk


@dataclass
class Position:
    """
    Represents an open or closed trading position.
    
    Supports partial closes — each close reduces remaining_fraction.
    """
    asset: str
    side: PositionSide
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float  # total USD allocated at entry
    stop_loss: float = 0.0
    take_profit: float = 0.0

    # Tracking
    trailing_price: float = 0.0  # best price since entry (high for long, low for short)
    remaining_fraction: float = 1.0  # 1.0 = fully open, 0.0 = fully closed
    closes: List[PositionClose] = field(default_factory=list)

    # Partial profit tracking
    partial_taken: bool = False  # whether first partial TP has fired

    @property
    def is_open(self) -> bool:
        return self.remaining_fraction > 0.001

    @property
    def remaining_usd(self) -> float:
        return self.size_usd * self.remaining_fraction

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L as a percentage."""
        if self.side == PositionSide.LONG:
            return (current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - current_price) / self.entry_price

    def unrealized_pnl_usd(self, current_price: float) -> float:
        """Calculate unrealized P&L in USD for remaining position."""
        return self.remaining_usd * self.unrealized_pnl_pct(current_price)

    def realized_pnl_usd(self) -> float:
        """Total realized P&L from all partial closes."""
        return sum(c.pnl_pct * self.size_usd * c.size_fraction for c in self.closes)

    def close_partial(
        self,
        fraction: float,
        price: float,
        time: pd.Timestamp,
        reason: str,
    ) -> PositionClose:
        """
        Close a fraction of the position.
        
        Args:
            fraction: Fraction of ORIGINAL position to close (e.g., 0.5 for half).
            price: Exit price.
            time: Exit timestamp.
            reason: Why we're closing.
            
        Returns:
            PositionClose record.
        """
        # Clamp to what's remaining
        actual_fraction = min(fraction, self.remaining_fraction)
        pnl_pct = self.unrealized_pnl_pct(price)

        close = PositionClose(
            time=time,
            price=price,
            size_fraction=actual_fraction,
            reason=reason,
            pnl_pct=pnl_pct,
        )
        self.closes.append(close)
        self.remaining_fraction -= actual_fraction
        return close

    def close_full(self, price: float, time: pd.Timestamp, reason: str) -> PositionClose:
        """Close the entire remaining position."""
        return self.close_partial(self.remaining_fraction, price, time, reason)

    def update_trailing(self, high: float, low: float) -> None:
        """Update trailing price with new candle data."""
        if self.side == PositionSide.LONG:
            self.trailing_price = max(self.trailing_price, high)
        else:
            self.trailing_price = min(self.trailing_price, low) if self.trailing_price > 0 else low


@dataclass
class PositionTracker:
    """
    Manages multiple positions across assets.
    Keeps history of all closed positions.
    """
    open_positions: List[Position] = field(default_factory=list)
    closed_positions: List[Position] = field(default_factory=list)

    def open_position(
        self,
        asset: str,
        side: PositionSide,
        entry_price: float,
        entry_time: pd.Timestamp,
        size_usd: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> Position:
        """Open a new position and track it."""
        pos = Position(
            asset=asset,
            side=side,
            entry_price=entry_price,
            entry_time=entry_time,
            size_usd=size_usd,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_price=entry_price,
        )
        self.open_positions.append(pos)
        return pos

    def get_position(self, asset: str) -> Optional[Position]:
        """Get the open position for an asset, if any."""
        for p in self.open_positions:
            if p.asset == asset and p.is_open:
                return p
        return None

    def close_position(self, position: Position, price: float, time: pd.Timestamp, reason: str) -> PositionClose:
        """Fully close a position and move it to history."""
        close = position.close_full(price, time, reason)
        if not position.is_open:
            if position in self.open_positions:
                self.open_positions.remove(position)
            self.closed_positions.append(position)
        return close

    def cleanup_closed(self) -> None:
        """Move any fully closed positions from open to closed list."""
        still_open = []
        for p in self.open_positions:
            if p.is_open:
                still_open.append(p)
            else:
                self.closed_positions.append(p)
        self.open_positions = still_open

    @property
    def total_exposure_usd(self) -> float:
        """Total USD exposure across all open positions."""
        return sum(p.remaining_usd for p in self.open_positions if p.is_open)

    def total_unrealized_pnl(self, prices: dict) -> float:
        """Total unrealized P&L across all open positions. prices = {asset: current_price}."""
        total = 0.0
        for p in self.open_positions:
            if p.is_open and p.asset in prices:
                total += p.unrealized_pnl_usd(prices[p.asset])
        return total
