#!/usr/bin/env python3
"""seed_history.py — Backfill 14+ periods of price history into rolling_closes.json for technicals bootstrap."""

import json, os, sys, time
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPTS = WORKSPACE / "scripts"
DATA_DIR = SCRIPTS / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ROLLING_FILE = DATA_DIR / "rolling_closes.json"

sys.path.insert(0, str(WORKSPACE / ".venv" / "lib" / "python3.13" / "site-packages"))

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

import requests

CRYPTO_MAP = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}
STOCK_TICKERS = ["SPY", "QQQ", "GLD", "TLT", "NVDA", "XLV", "BBAI", "SLV",
                 "SQQQ", "SH", "XLP", "EFA", "EWC"]

def fetch_crypto_history(coin_id, days=30):
    """Fetch daily closes from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    resp = requests.get(url, params={"vs_currency": "usd", "days": days}, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        prices = [p[1] for p in data.get("prices", [])]
        return prices
    print(f"  CoinGecko error for {coin_id}: {resp.status_code}")
    return []

def fetch_stock_history(ticker, days=30):
    """Fetch daily closes from Yahoo Finance."""
    import math
    end = int(time.time())
    start = end - (days * 86400)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, params={"period1": start, "period2": end, "interval": "1d"}, headers=headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            return [c for c in closes if c is not None]
    print(f"  Yahoo error for {ticker}: {resp.status_code}")
    return []

def main():
    rolling = {}
    if ROLLING_FILE.exists():
        try:
            rolling = json.loads(ROLLING_FILE.read_text())
        except:
            pass

    print("Seeding crypto history...")
    for symbol, coin_id in CRYPTO_MAP.items():
        prices = fetch_crypto_history(coin_id, days=30)
        if prices:
            rolling[symbol] = prices[-30:]
            print(f"  {symbol}: {len(prices)} data points")
        time.sleep(1)  # Rate limit

    print("Seeding stock history...")
    for ticker in STOCK_TICKERS:
        prices = fetch_stock_history(ticker, days=30)
        if prices:
            rolling[ticker] = prices[-30:]
            print(f"  {ticker}: {len(prices)} data points")
        time.sleep(0.5)

    # Atomic write
    tmp = ROLLING_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(rolling, indent=2))
    tmp.rename(ROLLING_FILE)

    total = sum(len(v) for v in rolling.values())
    print(f"\nDone. {len(rolling)} tickers, {total} total data points → {ROLLING_FILE}")

if __name__ == "__main__":
    main()
