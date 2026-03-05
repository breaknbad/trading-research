"""
Asset Selection / Rotation Scorer
==================================
Scores each asset based on:
  - Regime clarity (ADX strength)
  - Recent strategy performance (win rate, P&L)
  - Volatility profile (moderate vol preferred)
  - Trend alignment (how cleanly the asset is trending)

Re-evaluates every N candles (default 24 = daily for hourly candles).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class AssetScore:
    """Scoring result for a single asset."""
    asset: str
    total_score: float = 0.0
    regime_clarity: float = 0.0    # 0-25 points
    recent_performance: float = 0.0  # 0-25 points
    volatility_score: float = 0.0   # 0-25 points
    trend_alignment: float = 0.0    # 0-25 points
    regime: str = "RANGING"
    adx: float = 0.0


@dataclass
class ScorerConfig:
    """Configuration for the asset scorer."""
    re_evaluate_every: int = 12     # candles between re-evaluations
    lookback_candles: int = 48      # candles to look back for performance
    min_score_threshold: float = 20.0  # minimum score to be considered tradeable


class AssetScorer:
    """
    Ranks assets and determines which ones deserve capital allocation.
    """

    def __init__(self, config: Optional[ScorerConfig] = None):
        self.config = config or ScorerConfig()
        self._last_scores: Dict[str, AssetScore] = {}
        self._candles_since_eval: int = 0
        self._trade_history: Dict[str, list] = {}  # asset -> list of (pnl_pct, is_win)

    def record_trade(self, asset: str, pnl_pct: float, is_win: bool) -> None:
        """Record a completed trade for performance tracking."""
        if asset not in self._trade_history:
            self._trade_history[asset] = []
        self._trade_history[asset].append((pnl_pct, is_win))
        # Keep only recent trades
        if len(self._trade_history[asset]) > 50:
            self._trade_history[asset] = self._trade_history[asset][-50:]

    def should_re_evaluate(self) -> bool:
        """Check if it's time to re-evaluate asset scores."""
        self._candles_since_eval += 1
        if self._candles_since_eval >= self.config.re_evaluate_every:
            self._candles_since_eval = 0
            return True
        return False

    def score_assets(self, asset_data: Dict[str, pd.DataFrame]) -> List[AssetScore]:
        """
        Score all assets and return sorted list (best first).
        
        Args:
            asset_data: Dict mapping asset name to its DataFrame with indicators.
                        Each DF should have: adx, atr, close, ema_20, regime, rsi, etc.
        
        Returns:
            Sorted list of AssetScore (highest score first).
        """
        scores = []

        for asset, df in asset_data.items():
            if len(df) < self.config.lookback_candles:
                continue

            recent = df.tail(self.config.lookback_candles)
            score = self._score_single(asset, recent)
            scores.append(score)
            self._last_scores[asset] = score

        scores.sort(key=lambda s: s.total_score, reverse=True)
        return scores

    def _score_single(self, asset: str, df: pd.DataFrame) -> AssetScore:
        """Score a single asset based on recent data."""
        score = AssetScore(asset=asset)
        latest = df.iloc[-1]

        # 1. Regime clarity (0-25): higher ADX = clearer regime
        adx = latest.get("adx", 0)
        if pd.isna(adx):
            adx = 0
        score.adx = adx
        score.regime = latest.get("regime", "RANGING")
        # ADX 0-50+ mapped to 0-25 points
        score.regime_clarity = min(25.0, adx / 2.0)

        # 2. Recent performance (0-25): based on trade history
        history = self._trade_history.get(asset, [])
        if len(history) >= 3:
            recent_trades = history[-5:]  # last 5 trades (weight recent more heavily)
            win_rate = sum(1 for _, w in recent_trades if w) / len(recent_trades)
            avg_pnl = np.mean([p for p, _ in recent_trades])
            # Win rate contributes 0-15, avg P&L contributes 0-10
            score.recent_performance = min(15.0, win_rate * 15.0) + min(10.0, max(0, avg_pnl * 300))
        else:
            # No history — neutral score
            score.recent_performance = 12.5

        # 3. Volatility profile (0-25): moderate vol is preferred
        closes = df["close"].values
        returns = np.diff(closes) / closes[:-1]
        vol = np.std(returns) if len(returns) > 1 else 0
        # Sweet spot: 1-3% hourly vol. Too low = no opportunity, too high = too risky
        if vol > 0:
            # Normalized vol score — peak at ~2% vol
            vol_pct = vol * 100
            if vol_pct < 0.5:
                score.volatility_score = vol_pct / 0.5 * 15  # low vol = less opportunity
            elif vol_pct <= 3.0:
                score.volatility_score = 25.0  # sweet spot
            else:
                score.volatility_score = max(5.0, 25.0 - (vol_pct - 3.0) * 5)  # too volatile
        else:
            score.volatility_score = 5.0

        # 4. Trend alignment (0-25): how well price aligns with its trend
        ema_20 = latest.get("ema_20", None)
        sma_50 = latest.get("sma_50", None)
        close = latest["close"]

        if ema_20 is not None and sma_50 is not None and not pd.isna(ema_20) and not pd.isna(sma_50):
            # Check if EMAs are aligned
            if close > ema_20 > sma_50:  # clean uptrend
                score.trend_alignment = 25.0
            elif close < ema_20 < sma_50:  # clean downtrend
                score.trend_alignment = 22.0  # slightly less (shorts are harder)
            elif close > ema_20:  # somewhat bullish
                score.trend_alignment = 15.0
            elif close < ema_20:  # somewhat bearish
                score.trend_alignment = 12.0
            else:
                score.trend_alignment = 10.0
        else:
            score.trend_alignment = 10.0

        score.total_score = (
            score.regime_clarity
            + score.recent_performance
            + score.volatility_score
            + score.trend_alignment
        )
        return score

    def get_tradeable_assets(self, asset_data: Dict[str, pd.DataFrame], max_assets: int = 3) -> List[str]:
        """
        Return the top N tradeable assets (above minimum score threshold).
        """
        scores = self.score_assets(asset_data)
        tradeable = [
            s.asset for s in scores
            if s.total_score >= self.config.min_score_threshold
        ]
        return tradeable[:max_assets]

    @property
    def last_scores(self) -> Dict[str, AssetScore]:
        return self._last_scores
