#!/usr/bin/env python3
"""sync_market_state.py — Pull market-state from Supabase and write local file. 
Run on bots that don't run market_watcher themselves."""

import os, json, sys
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

import requests
import urllib.request

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STATE_FILE = WORKSPACE / "market-state.json"

def main():
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/market_state?id=eq.latest&select=state_json",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=10
    )
    if resp.status_code != 200 or not resp.json():
        print(f"Error: {resp.status_code}")
        return
    
    state = json.loads(resp.json()[0]["state_json"])
    
    # Flatten technicals and normalize field names for factor engine
    tickers = state.get("tickers", state)
    enriched = 0
    for ticker, data in (tickers.items() if isinstance(tickers, dict) else []):
        # Flatten nested technicals to top-level fields
        technicals = data.get("technicals", {})
        if technicals:
            # RSI: technicals.rsi → rsi_14 (factor engine field name)
            if "rsi" in technicals and technicals["rsi"] is not None:
                data["rsi_14"] = technicals["rsi"]
            # EMA: technicals.ema9/ema21 → ema_short/ema_long
            if "ema9" in technicals:
                data["ema_short"] = technicals["ema9"]
            if "ema21" in technicals:
                data["ema_long"] = technicals["ema21"]
            # MACD
            if "macd" in technicals:
                data["macd"] = technicals["macd"]
                data["macd_signal"] = technicals.get("macd_signal")
                data["macd_histogram"] = technicals.get("macd_histogram")
            # EMA cross signal
            if "ema_cross" in technicals:
                data["ema_cross"] = technicals["ema_cross"]
        
        # Normalize field names: change_24h_pct → change_pct
        if "change_24h_pct" in data and "change_pct" not in data:
            data["change_pct"] = data["change_24h_pct"]
        
        # Normalize volume: volume_24h → volume
        if "volume_24h" in data and "volume" not in data:
            data["volume"] = data["volume_24h"]
        
        # RSI validation
        rsi = data.get("rsi_14", data.get("rsi"))
        if rsi is None or rsi == 0 or rsi == 100:
            data["rsi_stale"] = True
            data["rsi_note"] = "Stale RSI from Supabase — use price action only"
            enriched += 1
        else:
            data["rsi_stale"] = False
        
        # Add data freshness timestamp
        data["vex_sync_time"] = datetime.now(timezone.utc).isoformat()
    
    if enriched > 0:
        print(f"WARNING: {enriched} tickers have stale RSI — flagged for price-only mode")
    
    # Fetch funding rates from Bitget (free, no key needed)
    funding = {}
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT", "NEARUSDT", "AVAXUSDT", "LINKUSDT"]:
        try:
            furl = f"https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol={sym}&productType=USDT-FUTURES"
            freq = urllib.request.Request(furl, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(freq, timeout=5) as fresp:
                fd = json.loads(fresp.read().decode())
                if fd.get("data"):
                    funding[sym] = float(fd["data"][0].get("fundingRate", 0))
        except:
            pass
    state["funding_rates"] = funding
    if funding:
        neg = [s for s, r in funding.items() if r < -0.0001]
        if neg:
            print(f"SIGNAL: Negative funding (shorts paying) on: {', '.join(neg)}")

    state["vex_last_sync"] = datetime.now(timezone.utc).isoformat()
    
    # Atomic write
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)
    print(f"Synced {len(tickers) if isinstance(tickers, dict) else 0} tickers")

if __name__ == "__main__":
    main()
