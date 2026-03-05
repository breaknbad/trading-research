"""Main loop — ties everything together for live paper trading."""
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

import config
from data_feed import DataFeed
from signal_engine import SignalEngine
from risk_manager import RiskManager
from portfolio import Portfolio
from executor import PaperExecutor

# ── Logging setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE),
    ],
)
log = logging.getLogger("main")


class TradingBot:
    def __init__(self):
        self.data_feed = DataFeed()
        self.portfolio = Portfolio()
        self.signal_engine = SignalEngine()
        self.risk_manager = RiskManager()
        self.executor = PaperExecutor(self.portfolio, self.data_feed)
        self._running = False
        self._last_day = None
        self._eval_interval = 30  # seconds between signal evaluations

    async def start(self):
        log.info("=" * 60)
        log.info("Crypto Trading System — Paper Trading Mode")
        log.info("Capital: $%.2f | Assets: %s", config.execution.initial_capital, config.ASSETS)
        log.info("=" * 60)

        # Load historical data
        log.info("Loading historical candles...")
        await self.data_feed.load_history(config.ASSETS, config.TIMEFRAMES, config.data_feed.history_limit)

        # Register candle callback
        self.data_feed.on_candle(self._on_candle_close)

        # Start WebSocket streams
        log.info("Starting live data streams...")
        await self.data_feed.start_streams(config.ASSETS, config.TIMEFRAMES)

        # Initial daily reset
        self.risk_manager.reset_daily(self.portfolio.cash)
        self._last_day = datetime.now(timezone.utc).date()

        # Main loop
        self._running = True
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(self._eval_interval)
        except KeyboardInterrupt:
            log.info("Shutting down...")
        finally:
            await self.shutdown()

    def _on_candle_close(self, symbol: str, timeframe: str):
        """Called when a candle closes on the WebSocket."""
        pass  # Main evaluation happens in _tick; this could trigger immediate eval

    async def _tick(self):
        """Main evaluation cycle."""
        now = datetime.now(timezone.utc)

        # Daily reset
        if now.date() != self._last_day:
            prices = self.executor.get_current_prices()
            eq = self.portfolio.equity_with_prices(prices)
            self.risk_manager.reset_daily(eq)
            self._last_day = now.date()
            log.info("New day — equity: $%.2f", eq)
            m = self.portfolio.metrics()
            log.info("Performance: %s", m)

        # Get current prices
        prices = self.executor.get_current_prices()
        if not prices:
            return

        # Check exits first
        self.executor.check_exits(prices)

        # Update equity
        self.portfolio.update_equity(prices)

        # Check circuit breaker
        eq = self.portfolio.equity_with_prices(prices)
        if self.risk_manager.check_circuit_breaker(eq):
            return

        # Evaluate signals for each asset
        for symbol in config.ASSETS:
            candles_by_tf = {}
            for tf in config.TIMEFRAMES:
                df = self.data_feed.get_candles(symbol, tf)
                if not df.empty:
                    candles_by_tf[tf] = df

            if not candles_by_tf:
                continue

            # Get supplementary data
            funding = await self.data_feed.fetch_funding_rate(symbol)
            order_book = await self.data_feed.fetch_order_book(symbol, limit=20)

            # Generate signal
            signal = self.signal_engine.evaluate(
                symbol=symbol,
                candles_by_tf=candles_by_tf,
                funding=funding,
                order_book=order_book,
            )

            if signal is None:
                continue

            # Risk check
            size = self.risk_manager.validate_trade(
                signal, eq,
                {s: {"notional": t.notional, "direction": t.direction}
                 for s, t in self.portfolio.positions.items()},
                self.data_feed.candles,
            )

            if size is None:
                continue

            # Execute
            self.executor.execute_entry(signal, size)

        # Periodic status
        if int(time.time()) % 300 < self._eval_interval:
            self._log_status(prices)

    def _log_status(self, prices: dict):
        eq = self.portfolio.equity_with_prices(prices)
        positions = len(self.portfolio.positions)
        closed = len(self.portfolio.closed_trades)
        log.info("STATUS | equity=$%.2f | open=%d | closed=%d | return=%.2f%%",
                 eq, positions, closed,
                 (eq / config.execution.initial_capital - 1) * 100)

    async def shutdown(self):
        self._running = False
        # Close all positions at current price
        prices = self.executor.get_current_prices()
        for sym in list(self.portfolio.positions.keys()):
            if sym in prices:
                self.portfolio.close_position(sym, prices[sym], "shutdown")
        await self.data_feed.stop()
        log.info("Final metrics: %s", self.portfolio.metrics())


async def main():
    bot = TradingBot()
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
