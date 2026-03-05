"""Real-time and historical price data from Binance public API."""
import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional

import aiohttp
import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)


def _kline_to_row(k: list) -> dict:
    return {
        "open_time": int(k[0]),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
        "close_time": int(k[6]),
        "quote_volume": float(k[7]),
        "trades": int(k[8]),
        "taker_buy_base": float(k[9]),
        "taker_buy_quote": float(k[10]),
    }


class DataFeed:
    """Manages historical candle fetching and live WebSocket streams."""

    def __init__(self, cfg: config.DataFeedConfig = config.data_feed):
        self.cfg = cfg
        # symbol -> timeframe -> DataFrame
        self.candles: Dict[str, Dict[str, pd.DataFrame]] = defaultdict(dict)
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_tasks: List[asyncio.Task] = []
        self._callbacks: List[Callable] = []
        self._running = False

    # ── HTTP helpers ────────────────────────────────────────────────────
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_klines(
        self, symbol: str, interval: str, limit: int = 500, end_time: Optional[int] = None
    ) -> pd.DataFrame:
        session = await self._get_session()
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if end_time:
            params["endTime"] = end_time
        url = f"{self.cfg.binance_base}/api/v3/klines"
        for attempt in range(3):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
                    data = await resp.json()
                    rows = [_kline_to_row(k) for k in data]
                    df = pd.DataFrame(rows)
                    if not df.empty:
                        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
                        df.set_index("open_time", inplace=True)
                    return df
            except Exception as e:
                log.warning("kline fetch attempt %d failed: %s", attempt, e)
                await asyncio.sleep(1)
        return pd.DataFrame()

    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Get latest funding rate from Binance futures (public)."""
        session = await self._get_session()
        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        try:
            async with session.get(url, params={"symbol": symbol, "limit": 1}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return float(data[0]["fundingRate"])
        except Exception as e:
            log.debug("Funding rate fetch failed for %s: %s", symbol, e)
        return None

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> Optional[dict]:
        session = await self._get_session()
        url = f"{self.cfg.binance_base}/api/v3/depth"
        try:
            async with session.get(url, params={"symbol": symbol, "limit": limit}) as resp:
                resp.raise_for_status()
                return await resp.json()
        except Exception as e:
            log.debug("Order book fetch failed for %s: %s", symbol, e)
            return None

    # ── Bulk historical load ────────────────────────────────────────────
    async def load_history(self, symbols: List[str], timeframes: List[str], limit: int = 500):
        """Load historical candles for all symbol/timeframe combos."""
        tasks = []
        keys = []
        for sym in symbols:
            for tf in timeframes:
                tasks.append(self.fetch_klines(sym, tf, limit))
                keys.append((sym, tf))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (sym, tf), result in zip(keys, results):
            if isinstance(result, pd.DataFrame) and not result.empty:
                self.candles[sym][tf] = result
                log.info("Loaded %d candles for %s/%s", len(result), sym, tf)
            else:
                log.warning("Failed to load %s/%s: %s", sym, tf, result)

    # ── WebSocket live stream ───────────────────────────────────────────
    def on_candle(self, callback: Callable):
        self._callbacks.append(callback)

    async def _stream_klines(self, symbol: str, interval: str):
        """Connect to Binance kline WebSocket and update candles."""
        import websockets
        stream = f"{symbol.lower()}@kline_{interval}"
        url = f"{self.cfg.binance_ws}/{stream}"
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    log.info("WS connected: %s", stream)
                    async for msg in ws:
                        if not self._running:
                            break
                        data = json.loads(msg)
                        k = data.get("k", {})
                        if not k:
                            continue
                        row = {
                            "open": float(k["o"]),
                            "high": float(k["h"]),
                            "low": float(k["l"]),
                            "close": float(k["c"]),
                            "volume": float(k["v"]),
                            "close_time": int(k["T"]),
                            "quote_volume": float(k["q"]),
                            "trades": int(k["n"]),
                            "taker_buy_base": float(k["V"]),
                            "taker_buy_quote": float(k["Q"]),
                        }
                        ts = pd.Timestamp(int(k["t"]), unit="ms")
                        sym = k["s"]
                        tf = k["i"]
                        # Update in-memory candle DataFrame
                        if tf in self.candles.get(sym, {}):
                            df = self.candles[sym][tf]
                            if ts in df.index:
                                for col, val in row.items():
                                    df.at[ts, col] = val
                            else:
                                new = pd.DataFrame([row], index=pd.DatetimeIndex([ts], name="open_time"))
                                self.candles[sym][tf] = pd.concat([df, new]).tail(config.data_feed.history_limit)
                        is_closed = k["x"]
                        if is_closed:
                            for cb in self._callbacks:
                                try:
                                    cb(sym, tf)
                                except Exception as e:
                                    log.error("Callback error: %s", e)
            except Exception as e:
                log.warning("WS %s error: %s — reconnecting in %.0fs", stream, e, self.cfg.ws_reconnect_delay)
                await asyncio.sleep(self.cfg.ws_reconnect_delay)

    async def start_streams(self, symbols: List[str], timeframes: List[str]):
        self._running = True
        for sym in symbols:
            for tf in timeframes:
                task = asyncio.create_task(self._stream_klines(sym, tf))
                self._ws_tasks.append(task)
        log.info("Started %d WebSocket streams", len(self._ws_tasks))

    async def stop(self):
        self._running = False
        for t in self._ws_tasks:
            t.cancel()
        self._ws_tasks.clear()
        if self._session and not self._session.closed:
            await self._session.close()

    def get_candles(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self.candles.get(symbol, {}).get(timeframe, pd.DataFrame())

    def get_price(self, symbol: str) -> Optional[float]:
        """Latest close price from 1m candles."""
        df = self.get_candles(symbol, "1m")
        if df.empty:
            return None
        return float(df["close"].iloc[-1])
