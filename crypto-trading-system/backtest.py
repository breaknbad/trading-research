"""Backtesting harness — replay historical data through the signal engine."""
import asyncio
import logging
import time
from typing import Dict, List

import pandas as pd

import config
import indicators
from data_feed import DataFeed
from signal_engine import SignalEngine, TradeSignal
from risk_manager import RiskManager
from portfolio import Portfolio, Trade
from strategies import Direction

log = logging.getLogger(__name__)


class Backtester:
    """Replay historical candles through the full trading pipeline."""

    def __init__(
        self,
        symbols: List[str] = None,
        timeframe: str = "5m",
        initial_capital: float = config.execution.initial_capital,
    ):
        self.symbols = symbols or config.ASSETS
        self.timeframe = timeframe
        self.portfolio = Portfolio(initial_capital)
        self.signal_engine = SignalEngine()
        self.risk_manager = RiskManager()
        self.slippage = config.execution.slippage_pct
        self.fee = config.execution.taker_fee_pct

    async def load_data(self, limit: int = 1000) -> Dict[str, pd.DataFrame]:
        """Fetch historical data for backtesting."""
        feed = DataFeed()
        data = {}
        for sym in self.symbols:
            df = await feed.fetch_klines(sym, self.timeframe, limit=limit)
            if not df.empty:
                data[sym] = df
                log.info("Loaded %d candles for %s", len(df), sym)
        await feed.stop()
        return data

    def run(self, data: Dict[str, pd.DataFrame], window: int = 100):
        """Walk-forward backtest across all symbols."""
        # Find common time range
        all_times = set()
        for df in data.values():
            all_times.update(df.index.tolist())
        sorted_times = sorted(all_times)

        if len(sorted_times) < window:
            log.error("Not enough data for backtest (need %d, got %d)", window, len(sorted_times))
            return

        self.risk_manager.reset_daily(self.portfolio.cash)
        last_day = None
        processed = 0

        for i in range(window, len(sorted_times)):
            current_time = sorted_times[i]
            current_day = current_time.date() if hasattr(current_time, 'date') else None

            # Daily reset
            if current_day and current_day != last_day:
                eq = self.portfolio.equity_curve[-1] if self.portfolio.equity_curve else self.portfolio.cash
                self.risk_manager.reset_daily(eq)
                last_day = current_day

            # Get current prices for exit checks
            prices = {}
            for sym, df in data.items():
                mask = df.index <= current_time
                if mask.any():
                    prices[sym] = float(df.loc[mask, "close"].iloc[-1])

            # Check exits
            self._check_exits(prices)

            # Update equity
            self.portfolio.update_equity(prices)

            # Generate signals for each symbol
            for sym in self.symbols:
                if sym not in data:
                    continue
                df = data[sym]
                window_df = df[df.index <= current_time].tail(window)
                if len(window_df) < 30:
                    continue

                # Build candles_by_tf (in backtest we only have one tf)
                candles_by_tf = {self.timeframe: window_df}

                signal = self.signal_engine.evaluate(
                    symbol=sym,
                    candles_by_tf=candles_by_tf,
                    funding=None,
                    order_book=None,
                )

                if signal is None:
                    continue

                # Risk check
                eq = self.portfolio.equity_curve[-1]
                size = self.risk_manager.validate_trade(
                    signal, eq, self.portfolio.positions, {sym: {self.timeframe: window_df}}
                )
                if size is None:
                    continue

                # Execute
                fill_price = signal.entry_price * (
                    1 + self.slippage if signal.direction == Direction.LONG else 1 - self.slippage
                )
                trade = Trade(
                    symbol=sym,
                    direction=signal.direction.value,
                    entry_price=fill_price,
                    size=size,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    entry_time=current_time.timestamp() if hasattr(current_time, 'timestamp') else time.time(),
                    reason=signal.reasons,
                )
                self.portfolio.open_position(trade)

            processed += 1
            if processed % 500 == 0:
                log.info("Processed %d/%d bars, trades=%d, equity=%.2f",
                         processed, len(sorted_times) - window,
                         len(self.portfolio.closed_trades),
                         self.portfolio.equity_curve[-1])

        # Close remaining positions at last price
        for sym in list(self.portfolio.positions.keys()):
            if sym in prices:
                self.portfolio.close_position(sym, prices[sym], "backtest_end")

        return self.portfolio.metrics()

    def _check_exits(self, prices: Dict[str, float]):
        to_close = []
        for sym, trade in self.portfolio.positions.items():
            price = prices.get(sym)
            if price is None:
                continue
            if trade.direction == "long":
                if price <= trade.stop_loss:
                    ep = trade.stop_loss * (1 - self.slippage)
                    to_close.append((sym, ep, "stop_loss"))
                elif price >= trade.take_profit:
                    ep = trade.take_profit * (1 - self.slippage)
                    to_close.append((sym, ep, "take_profit"))
            else:
                if price >= trade.stop_loss:
                    ep = trade.stop_loss * (1 + self.slippage)
                    to_close.append((sym, ep, "stop_loss"))
                elif price <= trade.take_profit:
                    ep = trade.take_profit * (1 + self.slippage)
                    to_close.append((sym, ep, "take_profit"))
        for sym, ep, reason in to_close:
            self.portfolio.close_position(sym, ep, reason)


async def run_backtest():
    """CLI entry point for backtesting."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bt = Backtester()
    log.info("Loading historical data...")
    data = await bt.load_data(limit=1000)
    if not data:
        log.error("No data loaded")
        return
    log.info("Running backtest...")
    metrics = bt.run(data)
    log.info("=" * 60)
    log.info("BACKTEST RESULTS")
    log.info("=" * 60)
    if metrics:
        for k, v in metrics.items():
            log.info("  %-20s: %s", k, v)


if __name__ == "__main__":
    asyncio.run(run_backtest())
