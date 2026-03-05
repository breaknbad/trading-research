"""
Coinbase Advanced Trade API client for fetching public market data.

Uses the public REST endpoint for OHLCV candles — no authentication required.
"""

import time
import logging
from typing import Optional

import requests
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"

# Coinbase granularity values
GRANULARITY_MAP = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "2h": "TWO_HOUR",
    "6h": "SIX_HOUR",
    "1d": "ONE_DAY",
}

# Max candles per request (Coinbase limit is 350)
MAX_CANDLES_PER_REQUEST = 300


def fetch_candles(
    product_id: str = "BTC-USD",
    granularity: str = "1h",
    start: Optional[int] = None,
    end: Optional[int] = None,
    days: int = 90,
) -> pd.DataFrame:
    """
    Fetch OHLCV candle data from Coinbase.

    Args:
        product_id: Trading pair (e.g. "BTC-USD", "ETH-USD").
        granularity: Candle interval — one of the keys in GRANULARITY_MAP.
        start: Unix timestamp for range start. If None, computed from `days`.
        end: Unix timestamp for range end. Defaults to now.
        days: How many days of history to fetch (used when start is None).

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
        sorted ascending by timestamp.
    """
    if granularity not in GRANULARITY_MAP:
        raise ValueError(f"Invalid granularity '{granularity}'. Use one of {list(GRANULARITY_MAP)}")

    gran_value = GRANULARITY_MAP[granularity]

    # Determine time range
    if end is None:
        end = int(time.time())
    if start is None:
        start = end - (days * 86400)

    # Calculate seconds per candle for pagination
    seconds_per_candle = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "6h": 21600, "1d": 86400,
    }[granularity]

    all_candles = []
    current_start = start

    while current_start < end:
        # Chunk end: don't exceed MAX_CANDLES_PER_REQUEST candles or the overall end
        chunk_end = min(current_start + MAX_CANDLES_PER_REQUEST * seconds_per_candle, end)

        params = {
            "start": str(current_start),
            "end": str(chunk_end),
            "granularity": gran_value,
        }

        url = f"{BASE_URL}/{product_id}/candles"
        logger.debug("GET %s  params=%s", url, params)

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Request failed for %s: %s", product_id, exc)
            raise

        data = resp.json()
        candles = data.get("candles", [])

        if not candles:
            logger.warning("No candles returned for chunk %s–%s", current_start, chunk_end)
            break

        all_candles.extend(candles)
        current_start = chunk_end

        # Be polite to the API
        time.sleep(0.25)

    if not all_candles:
        raise RuntimeError(f"No candle data returned for {product_id}")

    # Build DataFrame
    df = pd.DataFrame(all_candles)
    df = df.rename(columns={"start": "timestamp"})
    for col in ["timestamp", "open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df[["datetime", "timestamp", "open", "high", "low", "close", "volume"]]
    df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)

    logger.info("Fetched %d candles for %s (%s)", len(df), product_id, granularity)
    return df
