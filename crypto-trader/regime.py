"""
Market Regime Detector
======================
Classifies each candle into one of three market regimes:
  - RANGING:        ADX < 25 (weak trend)
  - TRENDING_UP:    ADX >= 25 AND 50-SMA slope positive
  - TRENDING_DOWN:  ADX >= 25 AND 50-SMA slope negative

Also provides a regime strength score (0-100) based on ADX value.
"""

from enum import Enum
import pandas as pd
import numpy as np

from indicators import add_adx, add_sma_slope


class Regime(str, Enum):
    RANGING = "RANGING"
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    WEAK_TREND_UP = "WEAK_TREND_UP"
    WEAK_TREND_DOWN = "WEAK_TREND_DOWN"


def detect_regime(
    df: pd.DataFrame,
    adx_threshold: float = 20.0,
    adx_window: int = 14,
    sma_window: int = 50,
    slope_periods: int = 5,
) -> pd.DataFrame:
    """
    Add 'regime' and 'regime_strength' columns to the dataframe.

    Args:
        df: OHLCV dataframe (must have high, low, close).
        adx_threshold: ADX level that separates ranging from trending.
        adx_window: Period for ADX calculation.
        sma_window: Period for SMA used in slope calculation.
        slope_periods: Number of bars to measure SMA slope over.

    Returns:
        DataFrame with 'regime' (Regime enum) and 'regime_strength' (0-100) columns.
    """
    df = df.copy()

    # Add ADX if not present
    if "adx" not in df.columns:
        df = add_adx(df, window=adx_window)

    # Add SMA slope if not present
    slope_col = f"sma_{sma_window}_slope"
    if slope_col not in df.columns:
        df = add_sma_slope(df, window=sma_window, slope_periods=slope_periods)

    # Classify regime with weak trend hybrid zone (ADX 20-30)
    weak_trend_upper = 30.0
    conditions = [
        df["adx"] < adx_threshold,                                                    # RANGING
        (df["adx"] >= adx_threshold) & (df["adx"] < weak_trend_upper) & (df[slope_col] > 0),   # WEAK_TREND_UP
        (df["adx"] >= adx_threshold) & (df["adx"] < weak_trend_upper) & (df[slope_col] <= 0),  # WEAK_TREND_DOWN
        (df["adx"] >= weak_trend_upper) & (df[slope_col] > 0),                        # TRENDING_UP
        (df["adx"] >= weak_trend_upper) & (df[slope_col] <= 0),                       # TRENDING_DOWN
    ]
    choices = [
        Regime.RANGING.value,
        Regime.WEAK_TREND_UP.value,
        Regime.WEAK_TREND_DOWN.value,
        Regime.TRENDING_UP.value,
        Regime.TRENDING_DOWN.value,
    ]

    df["regime"] = np.select(
        conditions,
        choices,
        default=Regime.RANGING.value,  # fallback for NaN rows
    )

    # Regime strength: clamp ADX to 0-100 range
    df["regime_strength"] = df["adx"].clip(0, 100).fillna(0)

    return df
