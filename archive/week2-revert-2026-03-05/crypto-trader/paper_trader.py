"""
Paper trading engine — simulates trades using live Coinbase market data
and the mean reversion strategy, without placing real orders.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from coinbase_client import fetch_candles
from indicators import add_all_indicators
from strategy import StrategyConfig

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "paper_trades.json"


class PaperTrader:
    """Simulated trading engine using live market data."""

    def __init__(
        self,
        product_id: str = "BTC-USD",
        initial_balance: float = 10_000.0,
        config: Optional[StrategyConfig] = None,
        state_file: Optional[Path] = None,
    ):
        self.product_id = product_id
        self.initial_balance = initial_balance
        self.config = config or StrategyConfig()
        self.state_file = state_file or STATE_FILE

        # Portfolio state
        self.cash = initial_balance
        self.position_size = 0.0  # base currency held
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.in_position = False
        self.trades = []

        # Try to resume from saved state
        self._load_state()

    # ── State persistence ──

    def _save_state(self):
        state = {
            "product_id": self.product_id,
            "initial_balance": self.initial_balance,
            "cash": self.cash,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "in_position": self.in_position,
            "trades": self.trades,
        }
        self.state_file.write_text(json.dumps(state, indent=2))

    def _load_state(self):
        if not self.state_file.exists():
            return
        try:
            state = json.loads(self.state_file.read_text())
            if state.get("product_id") != self.product_id:
                logger.info("State file is for %s, ignoring (trading %s)",
                            state.get("product_id"), self.product_id)
                return
            self.cash = state["cash"]
            self.position_size = state["position_size"]
            self.entry_price = state["entry_price"]
            self.stop_price = state["stop_price"]
            self.in_position = state["in_position"]
            self.trades = state["trades"]
            logger.info("Resumed state: $%.2f cash, %s position",
                        self.cash, "IN" if self.in_position else "NO")
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Could not load state file: %s", exc)

    # ── Market data ──

    def _get_latest_data(self) -> pd.DataFrame:
        """Fetch recent candles for indicator calculation."""
        # Need ~50 candles for indicators (BB20 + RSI14 warmup)
        df = fetch_candles(self.product_id, granularity="5m", days=1)
        df = add_all_indicators(df)
        df = df.dropna(subset=["bb_lower", "bb_upper", "rsi"]).reset_index(drop=True)
        return df

    # ── Trading logic ──

    def check_and_trade(self):
        """Run one iteration of the strategy against live data."""
        try:
            df = self._get_latest_data()
        except Exception as exc:
            logger.error("Failed to fetch market data: %s", exc)
            return

        if df.empty:
            logger.warning("No indicator data available yet")
            return

        latest = df.iloc[-1]
        price = float(latest["close"])
        now = datetime.now(timezone.utc).isoformat()

        if self.in_position:
            # Check stop-loss
            if price <= self.stop_price:
                self._close_position(price, now, "stop_loss")
            # Check sell signal
            elif price >= float(latest["bb_upper"]) and float(latest["rsi"]) > self.config.rsi_sell_threshold:
                self._close_position(price, now, "signal")
            else:
                holding_pnl = (price - self.entry_price) / self.entry_price * 100
                print(f"  📊 Holding | Entry: ${self.entry_price:,.2f} | "
                      f"Now: ${price:,.2f} | P&L: {holding_pnl:+.2f}% | "
                      f"RSI: {latest['rsi']:.1f}")
        else:
            # Check buy signal
            if price <= float(latest["bb_lower"]) and float(latest["rsi"]) < self.config.rsi_buy_threshold:
                self._open_position(price, now)
            else:
                print(f"  👀 Watching | Price: ${price:,.2f} | "
                      f"BB: [{latest['bb_lower']:.2f}, {latest['bb_upper']:.2f}] | "
                      f"RSI: {latest['rsi']:.1f}")

        self._save_state()

    def _open_position(self, price: float, timestamp: str):
        """Simulate buying."""
        self.position_size = self.cash / price
        self.entry_price = price
        self.stop_price = price * (1 - self.config.stop_loss_pct)
        self.in_position = True
        self.cash = 0.0

        print(f"  🟢 BUY  | Price: ${price:,.2f} | "
              f"Size: {self.position_size:.6f} {self.product_id.split('-')[0]} | "
              f"Stop: ${self.stop_price:,.2f}")

        self.trades.append({
            "type": "BUY",
            "price": price,
            "size": self.position_size,
            "timestamp": timestamp,
        })

    def _close_position(self, price: float, timestamp: str, reason: str):
        """Simulate selling."""
        proceeds = self.position_size * price
        pnl = proceeds - (self.position_size * self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price * 100

        emoji = "🔴" if reason == "stop_loss" else "🟡"
        print(f"  {emoji} SELL ({reason}) | Price: ${price:,.2f} | "
              f"P&L: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")

        self.trades.append({
            "type": "SELL",
            "price": price,
            "size": self.position_size,
            "reason": reason,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "timestamp": timestamp,
        })

        self.cash = proceeds
        self.position_size = 0.0
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.in_position = False

    # ── Status ──

    def print_status(self):
        """Print current portfolio status."""
        total_pnl = sum(t.get("pnl", 0) for t in self.trades if t["type"] == "SELL")
        n_trades = sum(1 for t in self.trades if t["type"] == "SELL")
        wins = sum(1 for t in self.trades if t["type"] == "SELL" and t.get("pnl", 0) > 0)

        portfolio_value = self.cash
        if self.in_position:
            # Approximate with entry price (actual shown during check)
            portfolio_value = self.position_size * self.entry_price

        print(f"\n{'='*50}")
        print(f"  📈 Paper Trader — {self.product_id}")
        print(f"  💰 Portfolio: ${portfolio_value:,.2f} (started ${self.initial_balance:,.2f})")
        print(f"  📊 Trades: {n_trades} closed | Win rate: {wins}/{n_trades}")
        print(f"  💵 Realized P&L: ${total_pnl:+,.2f}")
        print(f"  {'IN position' if self.in_position else 'No position'}")
        print(f"{'='*50}\n")

    # ── Main loop ──

    def run(self, interval_minutes: int = 5):
        """Run the paper trader in a loop."""
        print(f"🚀 Starting paper trader for {self.product_id}")
        print(f"   Check interval: {interval_minutes} min")
        self.print_status()

        try:
            while True:
                now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                print(f"\n⏰ [{now}] Checking {self.product_id}...")
                self.check_and_trade()
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n⛔ Stopped by user")
            self._save_state()
            self.print_status()
