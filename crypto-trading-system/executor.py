"""Paper trading execution engine with simulated fills."""
import logging
import time
from typing import Dict, Optional

import config
from data_feed import DataFeed
from portfolio import Portfolio, Trade
from signal_engine import TradeSignal
from strategies import Direction

log = logging.getLogger(__name__)


class PaperExecutor:
    """Simulates order execution with slippage and fees."""

    def __init__(self, portfolio: Portfolio, data_feed: DataFeed,
                 cfg: config.ExecutionConfig = config.execution):
        self.portfolio = portfolio
        self.data_feed = data_feed
        self.cfg = cfg

    def execute_entry(self, signal: TradeSignal, size: float) -> bool:
        """Simulate a market entry order with slippage."""
        price = signal.entry_price
        # Apply slippage
        if signal.direction == Direction.LONG:
            fill_price = price * (1 + self.cfg.slippage_pct)
        else:
            fill_price = price * (1 - self.cfg.slippage_pct)

        trade = Trade(
            symbol=signal.symbol,
            direction=signal.direction.value,
            entry_price=fill_price,
            size=size,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_time=time.time(),
            reason=signal.reasons,
        )
        self.portfolio.open_position(trade)
        return True

    def check_exits(self, prices: Dict[str, float]):
        """Check stop loss and take profit for all open positions."""
        to_close = []
        for sym, trade in self.portfolio.positions.items():
            price = prices.get(sym)
            if price is None:
                continue

            if trade.direction == "long":
                if price <= trade.stop_loss:
                    exit_price = trade.stop_loss * (1 - self.cfg.slippage_pct)
                    to_close.append((sym, exit_price, "stop_loss"))
                elif price >= trade.take_profit:
                    exit_price = trade.take_profit * (1 - self.cfg.slippage_pct)
                    to_close.append((sym, exit_price, "take_profit"))
            else:  # short
                if price >= trade.stop_loss:
                    exit_price = trade.stop_loss * (1 + self.cfg.slippage_pct)
                    to_close.append((sym, exit_price, "stop_loss"))
                elif price <= trade.take_profit:
                    exit_price = trade.take_profit * (1 + self.cfg.slippage_pct)
                    to_close.append((sym, exit_price, "take_profit"))

        for sym, exit_price, reason in to_close:
            self.portfolio.close_position(sym, exit_price, reason)

    def get_current_prices(self) -> Dict[str, float]:
        prices = {}
        for sym in config.ASSETS:
            p = self.data_feed.get_price(sym)
            if p is not None:
                prices[sym] = p
        return prices
