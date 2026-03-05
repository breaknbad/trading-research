"""Portfolio state, P&L tracking, performance metrics."""
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np

import config

log = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float
    entry_time: float  # unix timestamp
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: float = 0.0
    fees: float = 0.0
    reason: str = ""
    exit_reason: str = ""

    @property
    def notional(self) -> float:
        return self.size * self.entry_price

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    def unrealized_pnl(self, current_price: float) -> float:
        if self.direction == "long":
            return (current_price - self.entry_price) * self.size - self.fees
        else:
            return (self.entry_price - current_price) * self.size - self.fees

    def close(self, exit_price: float, exit_reason: str = ""):
        self.exit_price = exit_price
        self.exit_time = time.time()
        self.exit_reason = exit_reason
        if self.direction == "long":
            self.pnl = (exit_price - self.entry_price) * self.size - self.fees
        else:
            self.pnl = (self.entry_price - exit_price) * self.size - self.fees


class Portfolio:
    """Tracks all positions, equity, and performance metrics."""

    def __init__(self, initial_capital: float = config.execution.initial_capital):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Trade] = {}  # symbol -> open Trade
        self.closed_trades: List[Trade] = []
        self.equity_curve: List[float] = [initial_capital]
        self.equity_timestamps: List[float] = [time.time()]
        self._trade_log_file = config.TRADE_LOG_FILE

    @property
    def equity(self) -> float:
        return self.cash + sum(
            t.unrealized_pnl(t.entry_price) + t.notional
            for t in self.positions.values()
        )

    def equity_with_prices(self, prices: Dict[str, float]) -> float:
        total = self.cash
        for sym, trade in self.positions.items():
            price = prices.get(sym, trade.entry_price)
            total += trade.unrealized_pnl(price) + trade.notional
        return total

    def open_position(self, trade: Trade):
        self.positions[trade.symbol] = trade
        # Deduct capital
        fee = trade.notional * config.execution.taker_fee_pct
        trade.fees += fee
        self.cash -= trade.notional + fee
        self._log_trade(trade, "OPEN")
        log.info("OPEN %s %s @ %.4f size=%.6f notional=%.2f",
                 trade.direction.upper(), trade.symbol, trade.entry_price, trade.size, trade.notional)

    def close_position(self, symbol: str, exit_price: float, exit_reason: str = ""):
        if symbol not in self.positions:
            return
        trade = self.positions.pop(symbol)
        # Exit fee
        exit_notional = trade.size * exit_price
        fee = exit_notional * config.execution.taker_fee_pct
        trade.fees += fee
        trade.close(exit_price, exit_reason)
        self.cash += exit_notional - fee
        self.closed_trades.append(trade)
        self._log_trade(trade, "CLOSE")
        log.info("CLOSE %s %s @ %.4f pnl=%.2f reason=%s",
                 trade.direction.upper(), trade.symbol, exit_price, trade.pnl, exit_reason)

    def update_equity(self, prices: Dict[str, float]):
        eq = self.equity_with_prices(prices)
        self.equity_curve.append(eq)
        self.equity_timestamps.append(time.time())

    # ── Performance Metrics ─────────────────────────────────────────────
    def metrics(self) -> dict:
        if not self.closed_trades:
            return {"trades": 0, "equity": self.equity}

        pnls = [t.pnl for t in self.closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1e-10

        returns = np.diff(self.equity_curve) / np.array(self.equity_curve[:-1])
        returns = returns[np.isfinite(returns)]

        # Max drawdown
        curve = np.array(self.equity_curve)
        peak = np.maximum.accumulate(curve)
        dd = (peak - curve) / peak
        max_dd = float(dd.max()) if len(dd) else 0

        # Sharpe (annualized, assume 5-min bars, 288 per day)
        if len(returns) > 1 and returns.std() > 0:
            sharpe = float(returns.mean() / returns.std() * np.sqrt(288 * 365))
        else:
            sharpe = 0.0

        # Time-based trades per day
        if self.closed_trades:
            first_time = self.closed_trades[0].entry_time
            last_time = self.closed_trades[-1].exit_time or time.time()
            days = max((last_time - first_time) / 86400, 1)
            trades_per_day = len(self.closed_trades) / days
        else:
            trades_per_day = 0

        return {
            "trades": len(self.closed_trades),
            "win_rate": len(wins) / len(pnls) * 100 if pnls else 0,
            "profit_factor": gross_profit / gross_loss if gross_loss else float("inf"),
            "total_pnl": sum(pnls),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "trades_per_day": round(trades_per_day, 1),
            "equity": round(self.equity_curve[-1], 2),
            "return_pct": round((self.equity_curve[-1] / self.initial_capital - 1) * 100, 2),
        }

    def _log_trade(self, trade: Trade, action: str):
        entry = {
            "action": action,
            "time": time.time(),
            "symbol": trade.symbol,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "size": trade.size,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "reason": trade.reason,
        }
        if action == "CLOSE":
            entry["exit_price"] = trade.exit_price
            entry["pnl"] = trade.pnl
            entry["fees"] = trade.fees
            entry["exit_reason"] = trade.exit_reason
        try:
            with open(self._trade_log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log.error("Failed to write trade log: %s", e)
