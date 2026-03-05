"""Individual strategy implementations. Each returns a Signal with direction and score."""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd

import config
import indicators

log = logging.getLogger(__name__)


class Direction(Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    strategy: str
    direction: Direction
    score: float  # 0-100
    reason: str
    symbol: str = ""
    timeframe: str = ""


class MomentumStrategy:
    """Volume spike + price acceleration breakout detection."""

    def evaluate(self, df: pd.DataFrame, symbol: str = "", tf: str = "") -> Signal:
        if len(df) < 30:
            return Signal("momentum", Direction.NEUTRAL, 0, "insufficient data", symbol, tf)

        ind = indicators.compute_all(df)
        last = ind.iloc[-1]
        prev = ind.iloc[-2]

        score = 0.0
        reasons = []

        # Volume spike
        vol_ratio = last.get("vol_ratio", 0)
        if vol_ratio > config.indicators.volume_spike_mult:
            score += 30
            reasons.append(f"vol_spike={vol_ratio:.1f}x")

        # Price acceleration (momentum)
        mom = last.get("momentum", 0)
        if abs(mom) > 2.0:
            score += 20
            reasons.append(f"momentum={mom:.2f}%")

        # MACD histogram increasing
        if last.get("macd_hist", 0) > prev.get("macd_hist", 0) and last["macd_hist"] > 0:
            score += 15
            reasons.append("macd_accel_up")
        elif last.get("macd_hist", 0) < prev.get("macd_hist", 0) and last["macd_hist"] < 0:
            score += 15
            reasons.append("macd_accel_down")

        # EMA crossover
        if last.get("ema_9", 0) > last.get("ema_21", 0) and prev.get("ema_9", 0) <= prev.get("ema_21", 0):
            score += 20
            reasons.append("ema_cross_up")
        elif last.get("ema_9", 0) < last.get("ema_21", 0) and prev.get("ema_9", 0) >= prev.get("ema_21", 0):
            score += 20
            reasons.append("ema_cross_down")

        # Breakout above recent high
        recent_high = df["high"].iloc[-20:].max()
        recent_low = df["low"].iloc[-20:].min()
        if last["close"] > recent_high * 0.998:
            score += 15
            reasons.append("breakout_high")
            direction = Direction.LONG
        elif last["close"] < recent_low * 1.002:
            score += 15
            reasons.append("breakout_low")
            direction = Direction.SHORT
        else:
            direction = Direction.LONG if mom > 0 else Direction.SHORT if mom < 0 else Direction.NEUTRAL

        score = min(score, 100)
        return Signal("momentum", direction, score, "; ".join(reasons) or "no signal", symbol, tf)


class MeanReversionStrategy:
    """Bollinger Band bounces + RSI extremes."""

    def evaluate(self, df: pd.DataFrame, symbol: str = "", tf: str = "") -> Signal:
        if len(df) < 30:
            return Signal("mean_reversion", Direction.NEUTRAL, 0, "insufficient data", symbol, tf)

        ind = indicators.compute_all(df)
        last = ind.iloc[-1]

        score = 0.0
        reasons = []
        direction = Direction.NEUTRAL

        rsi_val = last.get("rsi", 50)
        bb_pct_b = last.get("bb_pct_b", 0.5)

        # RSI extremes
        if rsi_val < config.indicators.rsi_oversold:
            score += 35
            direction = Direction.LONG
            reasons.append(f"rsi_oversold={rsi_val:.1f}")
        elif rsi_val > config.indicators.rsi_overbought:
            score += 35
            direction = Direction.SHORT
            reasons.append(f"rsi_overbought={rsi_val:.1f}")

        # Bollinger Band touch/pierce
        if bb_pct_b < 0.0:
            score += 30
            direction = Direction.LONG
            reasons.append(f"below_lower_bb={bb_pct_b:.3f}")
        elif bb_pct_b > 1.0:
            score += 30
            direction = Direction.SHORT
            reasons.append(f"above_upper_bb={bb_pct_b:.3f}")
        elif bb_pct_b < 0.1:
            score += 15
            direction = Direction.LONG
            reasons.append(f"near_lower_bb={bb_pct_b:.3f}")
        elif bb_pct_b > 0.9:
            score += 15
            direction = Direction.SHORT
            reasons.append(f"near_upper_bb={bb_pct_b:.3f}")

        # Bandwidth squeeze (low volatility = potential reversion)
        bw = last.get("bb_bandwidth", 0)
        if bw < 0.02:
            score += 15
            reasons.append(f"squeeze={bw:.4f}")

        # Price far from middle band
        mid = last.get("bb_middle", last["close"])
        dev = abs(last["close"] - mid) / mid if mid else 0
        if dev > 0.02:
            score += 20
            reasons.append(f"deviation={dev:.3f}")

        score = min(score, 100)
        return Signal("mean_reversion", direction, score, "; ".join(reasons) or "no signal", symbol, tf)


class FundingRateStrategy:
    """Funding rate arbitrage signals — extreme funding = contrarian opportunity."""

    def evaluate(self, funding_rate: Optional[float], symbol: str = "") -> Signal:
        if funding_rate is None:
            return Signal("funding_rate", Direction.NEUTRAL, 0, "no data", symbol)

        score = 0.0
        reasons = []
        direction = Direction.NEUTRAL

        # Extreme positive funding → shorts might squeeze or longs overextended
        if funding_rate > 0.001:  # 0.1%+
            score += 40
            direction = Direction.SHORT
            reasons.append(f"high_funding={funding_rate:.5f}")
        elif funding_rate > 0.0005:
            score += 20
            direction = Direction.SHORT
            reasons.append(f"elevated_funding={funding_rate:.5f}")
        elif funding_rate < -0.001:
            score += 40
            direction = Direction.LONG
            reasons.append(f"neg_funding={funding_rate:.5f}")
        elif funding_rate < -0.0005:
            score += 20
            direction = Direction.LONG
            reasons.append(f"slightly_neg_funding={funding_rate:.5f}")

        return Signal("funding_rate", direction, min(score, 100), "; ".join(reasons) or "neutral funding", symbol)


class CrossTimeframeStrategy:
    """Confirms signals across multiple timeframes."""

    def evaluate(self, candles_by_tf: dict, symbol: str = "") -> Signal:
        bullish = 0
        bearish = 0
        total = 0
        reasons = []

        for tf, df in candles_by_tf.items():
            if df.empty or len(df) < 30:
                continue
            ind = indicators.compute_all(df)
            last = ind.iloc[-1]
            total += 1

            is_bull = (
                last.get("close", 0) > last.get("ema_21", 0)
                and last.get("rsi", 50) > 45
                and last.get("macd_hist", 0) > 0
            )
            is_bear = (
                last.get("close", 0) < last.get("ema_21", 0)
                and last.get("rsi", 50) < 55
                and last.get("macd_hist", 0) < 0
            )

            if is_bull:
                bullish += 1
                reasons.append(f"{tf}:bull")
            elif is_bear:
                bearish += 1
                reasons.append(f"{tf}:bear")
            else:
                reasons.append(f"{tf}:neutral")

        if total == 0:
            return Signal("cross_timeframe", Direction.NEUTRAL, 0, "no data", symbol)

        alignment = max(bullish, bearish) / total
        score = alignment * 100
        direction = Direction.LONG if bullish > bearish else Direction.SHORT if bearish > bullish else Direction.NEUTRAL

        return Signal("cross_timeframe", direction, score, "; ".join(reasons), symbol)


class VWAPDeviationStrategy:
    """VWAP deviation plays — price far from VWAP signals reversion or trend."""

    def evaluate(self, df: pd.DataFrame, symbol: str = "", tf: str = "") -> Signal:
        if len(df) < 30:
            return Signal("vwap_deviation", Direction.NEUTRAL, 0, "insufficient data", symbol, tf)

        ind = indicators.compute_all(df)
        last = ind.iloc[-1]
        vwap_val = last.get("vwap", None)
        if vwap_val is None or np.isnan(vwap_val):
            return Signal("vwap_deviation", Direction.NEUTRAL, 0, "no vwap", symbol, tf)

        price = last["close"]
        deviation_pct = (price - vwap_val) / vwap_val * 100

        score = 0.0
        reasons = [f"vwap_dev={deviation_pct:.2f}%"]

        # Mean reversion from VWAP
        abs_dev = abs(deviation_pct)
        if abs_dev > 2.0:
            score += 40
        elif abs_dev > 1.0:
            score += 25
        elif abs_dev > 0.5:
            score += 10

        # Direction: revert toward VWAP
        if deviation_pct > 0.5:
            direction = Direction.SHORT
            reasons.append("above_vwap_revert")
        elif deviation_pct < -0.5:
            direction = Direction.LONG
            reasons.append("below_vwap_revert")
        else:
            direction = Direction.NEUTRAL

        # Trend confirmation: price trending away from VWAP with volume
        vol_ratio = last.get("vol_ratio", 1)
        if vol_ratio > 1.5 and abs_dev > 1.0:
            # Trend, not reversion
            score += 20
            if deviation_pct > 0:
                direction = Direction.LONG
                reasons.append("vwap_trend_long")
            else:
                direction = Direction.SHORT
                reasons.append("vwap_trend_short")

        return Signal("vwap_deviation", direction, min(score, 100), "; ".join(reasons), symbol, tf)


class OrderFlowStrategy:
    """Order flow imbalance from taker buy/sell volume and order book."""

    def evaluate(self, df: pd.DataFrame, order_book: Optional[dict] = None, symbol: str = "", tf: str = "") -> Signal:
        if len(df) < 10:
            return Signal("order_flow", Direction.NEUTRAL, 0, "insufficient data", symbol, tf)

        score = 0.0
        reasons = []

        # Taker buy/sell imbalance from candle data
        recent = df.tail(10)
        if "taker_buy_base" in recent.columns:
            total_vol = recent["volume"].sum()
            taker_buy = recent["taker_buy_base"].sum()
            if total_vol > 0:
                buy_pct = taker_buy / total_vol
                imbalance = buy_pct - 0.5  # 0 = balanced
                reasons.append(f"taker_buy={buy_pct:.2%}")

                if abs(imbalance) > 0.1:
                    score += 35
                elif abs(imbalance) > 0.05:
                    score += 20

        # Order book imbalance
        if order_book:
            bids = sum(float(b[1]) for b in order_book.get("bids", [])[:10])
            asks = sum(float(a[1]) for a in order_book.get("asks", [])[:10])
            total = bids + asks
            if total > 0:
                bid_pct = bids / total
                ob_imbalance = bid_pct - 0.5
                reasons.append(f"book_bid={bid_pct:.2%}")
                if abs(ob_imbalance) > 0.15:
                    score += 30
                elif abs(ob_imbalance) > 0.08:
                    score += 15

        # Determine direction from combined signals
        # Net buy pressure
        buy_signal = 0
        if "taker_buy_base" in df.columns:
            recent_buy_pct = recent["taker_buy_base"].sum() / max(recent["volume"].sum(), 1e-10)
            buy_signal += (recent_buy_pct - 0.5)
        if order_book:
            buy_signal += ob_imbalance if 'ob_imbalance' in dir() else 0

        if buy_signal > 0.05:
            direction = Direction.LONG
        elif buy_signal < -0.05:
            direction = Direction.SHORT
        else:
            direction = Direction.NEUTRAL

        return Signal("order_flow", direction, min(score, 100), "; ".join(reasons) or "balanced flow", symbol, tf)
