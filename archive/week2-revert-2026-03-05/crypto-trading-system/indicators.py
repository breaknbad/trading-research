"""Technical indicator calculations — real math, not toy implementations."""
import numpy as np
import pandas as pd
from typing import Optional
import config

cfg = config.indicators


def rsi(series: pd.Series, period: int = None) -> pd.Series:
    """Wilder's RSI."""
    period = period or cfg.rsi_period
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = None, slow: int = None, signal: int = None) -> pd.DataFrame:
    """MACD line, signal line, histogram."""
    fast = fast or cfg.macd_fast
    slow = slow or cfg.macd_slow
    signal = signal or cfg.macd_signal
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": hist}, index=series.index)


def bollinger_bands(series: pd.Series, period: int = None, std_mult: float = None) -> pd.DataFrame:
    """Bollinger Bands — middle, upper, lower, %B, bandwidth."""
    period = period or cfg.bb_period
    std_mult = std_mult or cfg.bb_std
    middle = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    pct_b = (series - lower) / (upper - lower)
    bandwidth = (upper - lower) / middle
    return pd.DataFrame({
        "middle": middle, "upper": upper, "lower": lower,
        "pct_b": pct_b, "bandwidth": bandwidth,
    }, index=series.index)


def atr(df: pd.DataFrame, period: int = None) -> pd.Series:
    """Average True Range."""
    period = period or cfg.atr_period
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP (cumulative from start of data / session)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def vwap_bands(df: pd.DataFrame, num_std: float = 2.0) -> pd.DataFrame:
    """VWAP with standard deviation bands."""
    v = vwap(df)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    # Rolling variance weighted by volume
    sq_diff = ((typical - v) ** 2 * df["volume"]).cumsum()
    variance = sq_diff / cum_vol.replace(0, np.nan)
    std = np.sqrt(variance)
    return pd.DataFrame({
        "vwap": v,
        "upper_1": v + std,
        "lower_1": v - std,
        "upper_2": v + num_std * std,
        "lower_2": v - num_std * std,
    }, index=df.index)


def volume_profile(df: pd.DataFrame, bins: int = None) -> pd.DataFrame:
    """Volume at price profile — returns price levels and their volumes."""
    bins = bins or cfg.volume_profile_bins
    price_range = np.linspace(df["low"].min(), df["high"].max(), bins + 1)
    vol_at_price = np.zeros(bins)
    for i in range(bins):
        mask = (df["close"] >= price_range[i]) & (df["close"] < price_range[i + 1])
        vol_at_price[i] = df.loc[mask, "volume"].sum()
    centers = (price_range[:-1] + price_range[1:]) / 2
    return pd.DataFrame({"price": centers, "volume": vol_at_price})


def poc(df: pd.DataFrame, bins: int = None) -> float:
    """Point of Control — price level with highest volume."""
    vp = volume_profile(df, bins)
    if vp.empty:
        return df["close"].iloc[-1]
    return float(vp.loc[vp["volume"].idxmax(), "price"])


def momentum(series: pd.Series, lookback: int = None) -> pd.Series:
    """Rate of change (percentage)."""
    lookback = lookback or cfg.momentum_lookback
    return series.pct_change(lookback) * 100


def volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df["volume"].rolling(period).mean()


def ema(series: pd.Series, period: int = 20) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all indicators and merge onto the candle DataFrame. Returns a copy."""
    if df.empty or len(df) < 30:
        return df.copy()
    out = df.copy()
    out["rsi"] = rsi(out["close"])
    m = macd(out["close"])
    out["macd"] = m["macd"]
    out["macd_signal"] = m["signal"]
    out["macd_hist"] = m["histogram"]
    bb = bollinger_bands(out["close"])
    out["bb_upper"] = bb["upper"]
    out["bb_lower"] = bb["lower"]
    out["bb_middle"] = bb["middle"]
    out["bb_pct_b"] = bb["pct_b"]
    out["bb_bandwidth"] = bb["bandwidth"]
    out["atr"] = atr(out)
    out["vwap"] = vwap(out)
    out["momentum"] = momentum(out["close"])
    out["vol_sma20"] = volume_sma(out, 20)
    out["vol_ratio"] = out["volume"] / out["vol_sma20"]
    out["ema_9"] = ema(out["close"], 9)
    out["ema_21"] = ema(out["close"], 21)
    return out
