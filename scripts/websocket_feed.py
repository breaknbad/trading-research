#!/usr/bin/env python3
"""
WebSocket Price Feed — Finnhub Real-Time Streaming
===================================================
Upgrade #2: Replace 10s HTTP polling with real-time WebSocket price updates.
Writes prices to a shared JSON cache that rapid_scanner_v2.py reads.

Uses atomic writes (tmp + rename) to prevent corruption.
Includes staleness detection — cache entries have timestamps.

Usage:
  python3 websocket_feed.py              # Run continuously
  python3 websocket_feed.py --once       # Connect, get prices, disconnect
  python3 websocket_feed.py --symbols AAPL,NVDA,TSLA  # Custom symbols
"""

import json, os, sys, time, threading, tempfile, signal
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
CACHE_PATH = WORKSPACE / "price_cache.json"
LOG_PATH = WORKSPACE / "logs" / "websocket_feed.log"
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
STALE_SECONDS = 30  # Price older than this = stale

# Finnhub API key
FINNHUB_KEY = ""
try:
    key_path = os.path.expanduser("~/.finnhub_key")
    if os.path.exists(key_path):
        FINNHUB_KEY = open(key_path).read().strip()
except Exception:
    pass

os.makedirs(WORKSPACE / "logs", exist_ok=True)

# In-memory price store
_prices = {}
_lock = threading.Lock()
_running = True


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def atomic_write_cache():
    """Write price cache atomically (tmp file + rename)."""
    with _lock:
        data = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "bot_id": BOT_ID,
            "prices": dict(_prices),
        }
    try:
        fd, tmp = tempfile.mkstemp(dir=str(WORKSPACE), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(CACHE_PATH))
    except Exception as e:
        log(f"Cache write error: {e}")


def get_symbols():
    """Get symbols from watchlist + defaults."""
    symbols = set()
    # Defaults — always monitor these
    defaults = ["AAPL", "NVDA", "TSLA", "AMD", "AVGO", "META", "GOOGL", "AMZN", "MSFT"]
    symbols.update(defaults)
    # From watchlist
    try:
        if WATCHLIST_PATH.exists():
            wl = json.load(open(WATCHLIST_PATH))
            for ticker in wl.get("tickers", {}):
                if not ticker.startswith("_"):
                    # Finnhub uses plain symbols for stocks, BINANCE:BTCUSDT for crypto
                    symbols.add(ticker)
    except Exception:
        pass
    return list(symbols)


def run_websocket(symbols, once=False):
    """Connect to Finnhub WebSocket and stream prices."""
    try:
        import websocket
    except ImportError:
        log("ERROR: websocket-client not installed. Run: pip3 install websocket-client")
        # Fallback: poll mode
        run_poll_fallback(symbols, once)
        return

    if not FINNHUB_KEY:
        log("ERROR: No Finnhub API key found at ~/.finnhub_key")
        run_poll_fallback(symbols, once)
        return

    url = f"wss://ws.finnhub.io?token={FINNHUB_KEY}"

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get("type") == "trade":
                for trade in data.get("data", []):
                    symbol = trade.get("s", "")
                    price = trade.get("p", 0)
                    volume = trade.get("v", 0)
                    ts = trade.get("t", 0)  # Unix ms
                    if symbol and price > 0:
                        with _lock:
                            _prices[symbol] = {
                                "price": price,
                                "volume": volume,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "source": "finnhub_ws",
                            }
                atomic_write_cache()
        except Exception as e:
            log(f"Message parse error: {e}")

    def on_error(ws, error):
        log(f"WebSocket error: {error}")

    def on_close(ws, close_status, close_msg):
        log(f"WebSocket closed: {close_status} {close_msg}")

    def on_open(ws):
        log(f"WebSocket connected. Subscribing to {len(symbols)} symbols...")
        for sym in symbols:
            ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
        log("Subscriptions sent.")
        if once:
            # Wait a few seconds for data, then close
            threading.Timer(5.0, ws.close).start()

    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )

    while _running:
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            log(f"WebSocket run error: {e}")
        if once or not _running:
            break
        log("Reconnecting in 5s...")
        time.sleep(5)


def run_poll_fallback(symbols, once=False):
    """Fallback: HTTP polling if WebSocket unavailable."""
    import urllib.request
    log("Running in HTTP poll fallback mode (no WebSocket)")

    while _running:
        for sym in symbols:
            try:
                url = f"https://finnhub.io/api/v1/quote?symbol={sym}&token={FINNHUB_KEY}"
                req = urllib.request.Request(url, headers={"User-Agent": "WSFeed/1.0"})
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                if data.get("c", 0) > 0:
                    with _lock:
                        _prices[sym] = {
                            "price": data["c"],
                            "open": data["o"],
                            "high": data["h"],
                            "low": data["l"],
                            "prev_close": data["pc"],
                            "change_pct": round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "source": "finnhub_http",
                        }
                time.sleep(0.5)  # Rate limit
            except Exception as e:
                log(f"Poll error {sym}: {e}")
        atomic_write_cache()
        if once:
            break
        time.sleep(5)


def signal_handler(sig, frame):
    global _running
    log("Shutting down...")
    _running = False
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    once = "--once" in sys.argv

    # Custom symbols from CLI
    symbols = get_symbols()
    for arg in sys.argv[1:]:
        if arg.startswith("--symbols="):
            symbols = arg.split("=", 1)[1].split(",")
        elif arg == "--symbols" and sys.argv.index(arg) + 1 < len(sys.argv):
            symbols = sys.argv[sys.argv.index(arg) + 1].split(",")

    log(f"Starting WebSocket feed for {len(symbols)} symbols: {symbols[:10]}...")
    run_websocket(symbols, once=once)
