#!/usr/bin/env python3
"""run_factor_engine.py — Wrapper that extracts ticker data from market-state.json
into the flat format factor_engine.py expects, then runs it.

Usage: python3 run_factor_engine.py --ticker BTC --side long
"""
import argparse, json, sys, subprocess, tempfile, os
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
MARKET_STATE = WORKSPACE / "market-state.json"
FACTOR_ENGINE = Path(__file__).resolve().parent / "factor_engine.py"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--side", required=True, choices=["long", "short"])
    args = parser.parse_args()

    ticker = args.ticker.upper().replace("-USD", "")

    with open(MARKET_STATE) as f:
        state = json.load(f)

    tdata = state.get("tickers", {}).get(ticker)
    if not tdata:
        print(json.dumps({"error": f"Ticker {ticker} not in market-state.json", "exit_code": 3}))
        sys.exit(3)

    techs = tdata.get("technicals", {})
    flat = {
        "price": tdata.get("price", 0),
        "rsi": techs.get("rsi", 50),
        "ema9": techs.get("ema9", tdata.get("price", 0)),
        "ema21": techs.get("ema21", tdata.get("price", 0)),
        "macd": techs.get("macd", 0),
        "volume": tdata.get("volume_24h", 0),
        "atr": tdata.get("price", 0) * 0.02,  # estimate ATR as 2% of price if missing
        "change_24h_pct": tdata.get("change_24h_pct", 0),
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(flat, tmp)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, str(FACTOR_ENGINE), "--ticker", args.ticker, "--side", args.side, "--market-state", tmp_path],
            capture_output=True, text=True
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        sys.exit(result.returncode)
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    main()
