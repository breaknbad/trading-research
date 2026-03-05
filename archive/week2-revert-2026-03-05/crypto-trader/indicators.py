"""
Technical indicator calculations for the backtester.

Uses the `ta` library for standard implementations.
"""

import pandas as pd
import numpy as np
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator, EMAIndicator, SMAIndicator, MACD


def add_bollinger_bands(
    df: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
    price_col: str = "close",
) -> pd.DataFrame:
    """Add Bollinger Band columns: bb_mid, bb_upper, bb_lower, bb_width, bb_pband."""
    bb = BollingerBands(close=df[price_col], window=window, window_dev=num_std)
    df = df.copy()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    df["bb_pband"] = bb.bollinger_pband()
    return df


def add_rsi(
    df: pd.DataFrame,
    window: int = 14,
    price_col: str = "close",
) -> pd.DataFrame:
    """Add RSI column."""
    rsi = RSIIndicator(close=df[price_col], window=window)
    df = df.copy()
    df["rsi"] = rsi.rsi()
    return df


def add_adx(
    df: pd.DataFrame,
    window: int = 14,
) -> pd.DataFrame:
    """Add ADX, +DI, -DI columns."""
    adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=window)
    df = df.copy()
    df["adx"] = adx.adx()
    df["adx_pos"] = adx.adx_pos()  # +DI
    df["adx_neg"] = adx.adx_neg()  # -DI
    return df


def add_atr(
    df: pd.DataFrame,
    window: int = 14,
) -> pd.DataFrame:
    """Add ATR (Average True Range) column."""
    atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=window)
    df = df.copy()
    df["atr"] = atr.average_true_range()
    return df


def add_ema(
    df: pd.DataFrame,
    window: int = 20,
    price_col: str = "close",
    col_name: str = None,
) -> pd.DataFrame:
    """Add EMA column. Column name defaults to 'ema_{window}'."""
    ema = EMAIndicator(close=df[price_col], window=window)
    df = df.copy()
    df[col_name or f"ema_{window}"] = ema.ema_indicator()
    return df


def add_macd(
    df: pd.DataFrame,
    window_slow: int = 26,
    window_fast: int = 12,
    window_sign: int = 9,
    price_col: str = "close",
) -> pd.DataFrame:
    """Add MACD line, signal line, and histogram columns."""
    macd = MACD(
        close=df[price_col],
        window_slow=window_slow,
        window_fast=window_fast,
        window_sign=window_sign,
    )
    df = df.copy()
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()
    return df


def add_sma_slope(
    df: pd.DataFrame,
    window: int = 50,
    slope_periods: int = 5,
    price_col: str = "close",
) -> pd.DataFrame:
    """
    Add SMA and its slope (change over N periods).
    
    Slope is the difference between current SMA and SMA `slope_periods` bars ago,
    normalized by the SMA value to get a percentage change.
    """
    sma = SMAIndicator(close=df[price_col], window=window)
    df = df.copy()
    df[f"sma_{window}"] = sma.sma_indicator()
    df[f"sma_{window}_slope"] = df[f"sma_{window}"].diff(slope_periods) / df[f"sma_{window}"].shift(slope_periods)
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators used by the mean-reversion strategy."""
    df = add_bollinger_bands(df, num_std=1.75)
    df = add_rsi(df)
    return df


def add_trend_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators needed for regime detection and trend following."""
    df = add_adx(df, window=14)
    df = add_atr(df, window=14)
    df = add_ema(df, window=20)
    df = add_macd(df)
    df = add_sma_slope(df, window=50, slope_periods=5)
    return df


def add_all_multi_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicators for multi-strategy engine (mean reversion + trend)."""
    df = add_all_indicators(df)    # BB, RSI
    df = add_trend_indicators(df)  # ADX, ATR, EMA-20, MACD, SMA slope
    df = add_ema(df, window=15)    # EMA-15 for faster trend signals
    # Additional EMAs for enhanced short strategy (death cross detection)
    df = add_ema(df, window=50, col_name="ema_50")
    df = add_ema(df, window=200, col_name="ema_200")
    return df
