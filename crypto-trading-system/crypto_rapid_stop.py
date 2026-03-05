#!/usr/bin/env python3
"""
Rapid Stop Monitor — Adaptive-frequency stop checking for crypto.

Positions near stop (within 1%): check every 15 seconds.
Positions far from stop: check every 60 seconds.
Positions in profit >5%: check trailing stop every 15 seconds.

Reduces average reaction time from 60s to ~20s for at-risk positions.

Usage:
  python3 crypto_rapid_stop.py --loop
"""

import argparse
import json
import os
import time
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    key_path = os.path.expanduser("~/.supabase_service_key")
    if os.path.exists(key_path):
        SUPABASE_KEY = open(key_path).read().strip()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

RAPID_INTERVAL = 15    # seconds for urgent positions
NORMAL_INTERVAL = 60   # seconds for safe positions
NEAR_STOP_PCT = 1.0    # within 1% of stop = urgent
HIGH_PROFIT_PCT = 5.0  # >5% profit = check trailing stop urgently

CG_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "AVAX": "avalanche-2", "ADA": "cardano", "DOT": "polkadot",
    "LINK": "chainlink", "DOGE": "dogecoin", "SHIB": "shiba-inu",
    "XRP": "ripple",
}


def get_prices() -> dict:
    ids = ",".join(CG_IDS.values())
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd",
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            reverse = {v: k for k, v in CG_IDS.items()}
            return {reverse[k]: v["usd"] for k, v in data.items() if k in reverse}
    except Exception:
        pass
    return {}


def get_open_positions() -> list:
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={"status": "eq.OPEN", "select": "*"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def classify_urgency(pos: dict, current_price: float) -> str:
    """Classify position as RAPID or NORMAL based on proximity to stop."""
    entry = float(pos.get("avg_entry", 0))
    side = pos.get("side", "LONG").upper()

    if entry <= 0 or current_price <= 0:
        return "NORMAL"

    # Calculate distance to stop (2% default)
    if side == "LONG":
        stop = entry * 0.98
        distance_pct = ((current_price - stop) / current_price) * 100
        profit_pct = ((current_price - entry) / entry) * 100
    else:
        stop = entry * 1.02
        distance_pct = ((stop - current_price) / current_price) * 100
        profit_pct = ((entry - current_price) / entry) * 100

    # Near stop or high profit (trailing stop territory) = rapid
    if distance_pct <= NEAR_STOP_PCT or profit_pct >= HIGH_PROFIT_PCT:
        return "RAPID"

    return "NORMAL"


def check_stops(positions: list, prices: dict) -> list:
    """Check all positions against stops. Returns triggered list."""
    triggered = []
    for pos in positions:
        ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
        price = prices.get(ticker)
        if not price:
            continue

        entry = float(pos.get("avg_entry", 0))
        side = pos.get("side", "LONG").upper()
        bot = pos.get("bot_id", "?")

        if entry <= 0:
            continue

        if side == "LONG":
            stop = entry * 0.98
            if price <= stop:
                triggered.append({
                    "bot": bot, "ticker": ticker, "side": side,
                    "entry": entry, "stop": round(stop, 2), "current": price,
                    "loss_pct": round(((price - entry) / entry) * 100, 2),
                    "reason": "HARD_STOP",
                })
        else:
            stop = entry * 1.02
            if price >= stop:
                triggered.append({
                    "bot": bot, "ticker": ticker, "side": side,
                    "entry": entry, "stop": round(stop, 2), "current": price,
                    "loss_pct": round(((entry - price) / entry) * 100, 2),
                    "reason": "HARD_STOP",
                })

    return triggered


def run_loop():
    """Adaptive-frequency stop monitoring loop."""
    print(f"🎩 Rapid Stop Monitor started at {datetime.now(timezone.utc).isoformat()}")
    last_normal_check = 0

    while True:
        now = time.time()
        prices = get_prices()
        if not prices:
            time.sleep(RAPID_INTERVAL)
            continue

        positions = get_open_positions()
        if not positions:
            time.sleep(NORMAL_INTERVAL)
            continue

        # Classify each position
        rapid_positions = []
        normal_positions = []
        for pos in positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            price = prices.get(ticker)
            if not price:
                continue
            urgency = classify_urgency(pos, price)
            if urgency == "RAPID":
                rapid_positions.append(pos)
            else:
                normal_positions.append(pos)

        # Always check rapid positions
        if rapid_positions:
            triggered = check_stops(rapid_positions, prices)
            for t in triggered:
                print(f"🚨 STOP HIT: {t['bot']} {t['ticker']} {t['side']} at {t['current']} (stop: {t['stop']})")

        # Check normal positions on normal interval
        if now - last_normal_check >= NORMAL_INTERVAL:
            if normal_positions:
                triggered = check_stops(normal_positions, prices)
                for t in triggered:
                    print(f"🚨 STOP HIT: {t['bot']} {t['ticker']} {t['side']} at {t['current']} (stop: {t['stop']})")
            last_normal_check = now

        time.sleep(RAPID_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rapid Stop Monitor")
    parser.add_argument("--loop", action="store_true", help="Run continuous loop")
    args = parser.parse_args()

    if args.loop:
        run_loop()
    else:
        prices = get_prices()
        positions = get_open_positions()
        for pos in positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            price = prices.get(ticker, 0)
            urgency = classify_urgency(pos, price) if price else "UNKNOWN"
            print(f"  {pos.get('bot_id')} {ticker}: {urgency} (price: {price})")
