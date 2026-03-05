#!/usr/bin/env python3
"""Fetch BTC, ETH, SOL perpetual funding rates from OKX and Bitget."""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

TICKERS = {
    "BTC": {"okx": "BTC-USDT-SWAP", "bitget": "BTCUSDT"},
    "ETH": {"okx": "ETH-USDT-SWAP", "bitget": "ETHUSDT"},
    "SOL": {"okx": "SOL-USDT-SWAP", "bitget": "SOLUSDT"},
}

def fetch_json(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def fetch_okx(ticker, inst_id):
    url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
    data = fetch_json(url)
    if data.get("code") == "0" and data.get("data"):
        d = data["data"][0]
        return {
            "ticker": ticker,
            "rate": float(d["fundingRate"]),
            "timestamp": datetime.fromtimestamp(int(d["fundingTime"]) / 1000, tz=timezone.utc).isoformat(),
            "source": "OKX",
        }
    return None

def fetch_bitget(ticker, symbol):
    url = f"https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol={symbol}&productType=USDT-FUTURES"
    data = fetch_json(url)
    if data.get("code") == "00000" and data.get("data"):
        d = data["data"][0] if isinstance(data["data"], list) else data["data"]
        return {
            "ticker": ticker,
            "rate": float(d["fundingRate"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "Bitget",
        }
    return None

def main():
    results = []
    for ticker, ids in TICKERS.items():
        result = None
        for fetcher, key in [(fetch_okx, "okx"), (fetch_bitget, "bitget")]:
            try:
                result = fetcher(ticker, ids[key])
                if result:
                    break
            except Exception as e:
                print(f"  {key} failed for {ticker}: {e}", file=sys.stderr)
        if result:
            results.append(result)
        else:
            results.append({"ticker": ticker, "rate": None, "error": "all sources failed"})

    # JSON output
    print(json.dumps(results, indent=2))

    # Human-readable
    print("\n--- Funding Rate Summary ---")
    for r in results:
        if r.get("rate") is not None:
            pct = r["rate"] * 100
            direction = "longs pay shorts" if r["rate"] > 0 else "shorts pay longs"
            print(f"  {r['ticker']}: {pct:+.4f}% ({direction}) via {r['source']}")
        else:
            print(f"  {r['ticker']}: unavailable")

if __name__ == "__main__":
    main()
