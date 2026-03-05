"""Combines strategy signals into scored trade decisions."""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

import config
from strategies import (
    CrossTimeframeStrategy, Direction, FundingRateStrategy,
    MeanReversionStrategy, MomentumStrategy, OrderFlowStrategy,
    Signal, VWAPDeviationStrategy,
)

log = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    symbol: str
    direction: Direction
    combined_score: float  # 0-100
    signals: List[Signal]
    entry_price: float
    stop_loss: float
    take_profit: float

    @property
    def reasons(self) -> str:
        parts = []
        for s in self.signals:
            if s.score > 0 and s.direction != Direction.NEUTRAL:
                parts.append(f"{s.strategy}({s.score:.0f}): {s.reason}")
        return " | ".join(parts)


class SignalEngine:
    """Evaluates all strategies and produces combined trade signals."""

    def __init__(self, cfg: config.SignalConfig = config.signal):
        self.cfg = cfg
        self.momentum = MomentumStrategy()
        self.mean_reversion = MeanReversionStrategy()
        self.funding_rate = FundingRateStrategy()
        self.cross_timeframe = CrossTimeframeStrategy()
        self.vwap_deviation = VWAPDeviationStrategy()
        self.order_flow = OrderFlowStrategy()

    def evaluate(
        self,
        symbol: str,
        candles_by_tf: Dict[str, pd.DataFrame],
        funding: Optional[float] = None,
        order_book: Optional[dict] = None,
    ) -> Optional[TradeSignal]:
        """Run all strategies and combine into a single scored signal."""
        # Pick primary timeframe (5m) for single-tf strategies
        primary_tf = "5m"
        df = candles_by_tf.get(primary_tf, pd.DataFrame())
        if df.empty or len(df) < 30:
            return None

        # Collect signals
        signals: List[Signal] = []
        signals.append(self.momentum.evaluate(df, symbol, primary_tf))
        signals.append(self.mean_reversion.evaluate(df, symbol, primary_tf))
        signals.append(self.funding_rate.evaluate(funding, symbol))
        signals.append(self.cross_timeframe.evaluate(candles_by_tf, symbol))
        signals.append(self.vwap_deviation.evaluate(df, symbol, primary_tf))
        signals.append(self.order_flow.evaluate(df, order_book, symbol, primary_tf))

        # Weighted score + direction voting
        weights = self.cfg.strategy_weights
        long_score = 0.0
        short_score = 0.0
        total_weight = 0.0

        for sig in signals:
            w = weights.get(sig.strategy, 0)
            total_weight += w
            if sig.direction == Direction.LONG:
                long_score += sig.score * w
            elif sig.direction == Direction.SHORT:
                short_score += sig.score * w

        if total_weight == 0:
            return None

        long_score /= total_weight
        short_score /= total_weight

        # Pick dominant direction
        if long_score >= short_score and long_score >= self.cfg.min_score:
            direction = Direction.LONG
            combined_score = long_score
        elif short_score > long_score and short_score >= self.cfg.min_score:
            direction = Direction.SHORT
            combined_score = short_score
        else:
            return None

        # Calculate entry, stop, take-profit
        price = float(df["close"].iloc[-1])
        atr_val = float(df["close"].rolling(14).std().iloc[-1]) if len(df) > 14 else price * 0.01
        # Use ATR for dynamic stop if available
        from indicators import atr as calc_atr
        atr_series = calc_atr(df)
        if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
            atr_val = float(atr_series.iloc[-1])

        stop_dist = max(atr_val * 1.5, price * config.risk.stop_loss_pct)

        if direction == Direction.LONG:
            entry = price
            stop_loss = entry - stop_dist
            take_profit = entry + stop_dist * config.risk.min_reward_risk
        else:
            entry = price
            stop_loss = entry + stop_dist
            take_profit = entry - stop_dist * config.risk.min_reward_risk

        trade_signal = TradeSignal(
            symbol=symbol,
            direction=direction,
            combined_score=combined_score,
            signals=signals,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        log.info(
            "Signal: %s %s score=%.1f entry=%.4f sl=%.4f tp=%.4f | %s",
            symbol, direction.value, combined_score,
            entry, stop_loss, take_profit, trade_signal.reasons,
        )
        return trade_signal
