#!/usr/bin/env python3
"""
Sector Momentum Cascade — Sympathy Play Scanner
=================================================
Upgrade #4: When one stock in a sector moves >3%, auto-scan the rest of
that sector within 2 seconds. Alert-based (not auto-execute) initially.

Reads from WebSocket price cache for speed. Falls back to HTTP.

Usage:
  python3 sector_cascade.py              # Run continuously (30s check interval)
  python3 sector_cascade.py --once       # Single pass
  python3 sector_cascade.py --threshold 4.0  # Custom move threshold
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"
LOG_PATH = WORKSPACE / "logs" / "sector_cascade.log"
CASCADE_STATE_PATH = WORKSPACE / "logs" / "cascade_state.json"
CASCADE_COOLDOWN = 600  # 10 min cooldown per sector after cascade

FINNHUB_KEY = ""
try:
    FINNHUB_KEY = open(os.path.expanduser("~/.finnhub_key")).read().strip()
except Exception:
    pass

os.makedirs(WORKSPACE / "logs", exist_ok=True)

# --- Sector Mapping ---
SECTORS = {
    "SEMICONDUCTORS": ["NVDA", "AMD", "AVGO", "TSM", "INTC", "QCOM", "MU", "MRVL", "KLAC", "LRCX"],
    "MEGA_TECH": ["AAPL", "MSFT", "GOOGL", "META", "AMZN"],
    "FINTECH": ["COIN", "HOOD", "SQ", "PYPL", "SOFI"],
    "AI_SOFTWARE": ["PLTR", "CRM", "NOW", "SNOW", "AI"],
    "ENERGY": ["XOM", "CVX", "OXY", "DVN", "SLB", "HAL"],
    "CRYPTO_MAJORS": ["BTC-USD", "ETH-USD", "SOL-USD"],
    "CRYPTO_ALTS": ["LINK-USD", "AVAX-USD", "DOT-USD", "NEAR-USD", "SUI-USD"],
    "BIOTECH": ["MRNA", "PFE", "ABBV", "LLY", "AMGN"],
    "DEFENSE": ["LMT", "RTX", "NOC", "GD", "BA"],
    "EV_CLEAN": ["TSLA", "RIVN", "LCID", "ENPH", "FSLR"],
}

MOVE_THRESHOLD_PCT = 3.0  # Default: 3% move triggers cascade


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def read_price_cache():
    try:
        if PRICE_CACHE_PATH.exists():
            data = json.load(open(PRICE_CACHE_PATH))
            updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            if age < 60:
                return data.get("prices", {})
    except Exception:
        pass
    return None


def fetch_quote(symbol, cache):
    if cache and symbol in cache:
        entry = cache[symbol]
        return {"price": entry.get("price", 0), "change_pct": entry.get("change_pct", 0)}
    if FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            req = urllib.request.Request(url, headers={"User-Agent": "SectorCascade/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("c", 0) > 0:
                pct = round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0
                return {"price": data["c"], "change_pct": pct}
        except Exception:
            pass
    return None


def load_cascade_state():
    try:
        if CASCADE_STATE_PATH.exists():
            return json.load(open(CASCADE_STATE_PATH))
    except Exception:
        pass
    return {}


def save_cascade_state(state):
    with open(CASCADE_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def scan_once(threshold=MOVE_THRESHOLD_PCT):
    cache = read_price_cache()
    state = load_cascade_state()

    for sector_name, tickers in SECTORS.items():
        # Cooldown check
        last_cascade = state.get(sector_name, 0)
        if time.time() - last_cascade < CASCADE_COOLDOWN:
            continue

        # Check each ticker in sector for big moves
        leader = None
        leader_pct = 0

        for ticker in tickers:
            quote = fetch_quote(ticker, cache)
            if not quote:
                continue
            pct = abs(quote.get("change_pct", 0))
            if pct >= threshold and pct > abs(leader_pct):
                leader = ticker
                leader_pct = quote["change_pct"]

        if leader:
            log(f"🔥 SECTOR CASCADE: {sector_name} — {leader} moved {leader_pct:+.1f}%")
            log(f"   Scanning peers: {[t for t in tickers if t != leader]}")

            # Scan remaining tickers quickly
            opportunities = []
            for ticker in tickers:
                if ticker == leader:
                    continue
                quote = fetch_quote(ticker, cache)
                if not quote:
                    continue
                pct = quote.get("change_pct", 0)
                # Look for laggards that haven't moved yet (sympathy potential)
                if abs(pct) < threshold * 0.5:
                    opportunities.append({"ticker": ticker, "price": quote["price"],
                                         "change_pct": pct, "status": "LAGGARD"})
                # Also flag peers already moving in same direction
                elif (leader_pct > 0 and pct > 0) or (leader_pct < 0 and pct < 0):
                    opportunities.append({"ticker": ticker, "price": quote["price"],
                                         "change_pct": pct, "status": "CONFIRMING"})

            if opportunities:
                for opp in opportunities:
                    log(f"   📊 {opp['ticker']}: {opp['change_pct']:+.1f}% ({opp['status']}) @ ${opp['price']:.2f}")

            # Set cooldown
            state[sector_name] = time.time()
            save_cascade_state(state)


def run(threshold=MOVE_THRESHOLD_PCT):
    log(f"🏁 Sector Cascade starting — threshold={threshold}%, bot={BOT_ID}")
    while True:
        try:
            scan_once(threshold)
        except Exception as e:
            log(f"Scan error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--threshold", type=float, default=MOVE_THRESHOLD_PCT)
    args = parser.parse_args()

    if args.once:
        scan_once(args.threshold)
    else:
        run(args.threshold)
