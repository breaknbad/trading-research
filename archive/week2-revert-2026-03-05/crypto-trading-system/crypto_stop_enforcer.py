#!/usr/bin/env python3
"""
Crypto Stop-Loss Enforcer — runs every 60 seconds via cron/launchd.
Checks all open crypto positions against 2% stop threshold.
Auto-executes exit if stop is breached. No asking, no delay.

Adapted from Capital Growth's stop_check.py for 24/7 crypto markets.

Usage:
  python3 crypto_stop_enforcer.py              # Check all bots
  python3 crypto_stop_enforcer.py --bot alfred  # Check one bot
  python3 crypto_stop_enforcer.py --dry-run     # Check without executing
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────
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

STOP_PCT = 2.0          # 2% hard stop — no exceptions
PROFIT_TARGET_PCT = 10.0  # 10% auto-take (crypto is more volatile than stocks)
BOTS = ["alfred", "tars", "vex", "eddie_v"]

# Crypto price sources
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "XRP": "ripple",
}

LOG_FILE = os.path.join(os.path.dirname(__file__), "stop_enforcer.log")


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_crypto_prices() -> dict:
    """Fetch current prices for all tracked crypto from CoinGecko."""
    ids = ",".join(COINGECKO_IDS.values())
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            prices = {}
            for ticker, cg_id in COINGECKO_IDS.items():
                if cg_id in data and "usd" in data[cg_id]:
                    prices[ticker] = float(data[cg_id]["usd"])
            return prices
    except Exception as e:
        log(f"ERROR: Price fetch failed: {e}")
    return {}


def get_positions(bot_id: str) -> list:
    """Fetch open crypto positions from Supabase."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={
                "bot_id": f"eq.{bot_id}",
                "status": "eq.OPEN",
                "select": "*",
            },
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log(f"ERROR: Position fetch for {bot_id} failed: {e}")
    return []


def execute_stop(bot_id: str, position: dict, current_price: float, reason: str, dry_run: bool = False):
    """Execute a stop-loss exit."""
    ticker = position.get("ticker", "???")
    entry = float(position.get("avg_entry", 0))
    qty = float(position.get("quantity", 0))
    side = position.get("side", "LONG")
    pos_id = position.get("id", "")

    if side == "LONG":
        pnl = (current_price - entry) * qty
    else:
        pnl = (entry - current_price) * qty

    log(f"{'[DRY RUN] ' if dry_run else ''}🔴 STOP HIT: {bot_id} | {ticker} {side} | "
        f"Entry: ${entry:.2f} → Current: ${current_price:.2f} | "
        f"P&L: ${pnl:.2f} | Reason: {reason}")

    if dry_run:
        return

    # Log the exit trade
    trade_data = {
        "bot_id": bot_id,
        "ticker": ticker,
        "side": "SELL" if side == "LONG" else "BUY",
        "quantity": qty,
        "price": current_price,
        "trade_type": "STOP_EXIT",
        "reason": reason,
        "pnl": round(pnl, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/crypto_trades",
            headers=HEADERS,
            json=trade_data,
            timeout=10,
        )
        if r.status_code in (200, 201):
            log(f"  ✅ Exit trade logged for {bot_id} {ticker}")
        else:
            log(f"  ⚠️ Trade log failed: {r.status_code} {r.text}")
    except Exception as e:
        log(f"  ⚠️ Trade log error: {e}")

    # Update position status
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={"id": f"eq.{pos_id}"},
            headers=HEADERS,
            json={"status": "CLOSED", "exit_price": current_price, "exit_reason": reason},
            timeout=10,
        )
    except Exception:
        pass


def check_all_stops(bot_id: str = None, dry_run: bool = False):
    """Main check loop."""
    prices = get_crypto_prices()
    if not prices:
        log("WARNING: No prices available. Skipping check.")
        return []

    log(f"Prices: {json.dumps({k: f'${v:,.2f}' for k, v in prices.items()})}")

    bots_to_check = [bot_id] if bot_id else BOTS
    stops_hit = []

    for bot in bots_to_check:
        positions = get_positions(bot)
        if not positions:
            continue

        for pos in positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            entry = float(pos.get("avg_entry", 0))
            qty = float(pos.get("quantity", 0))
            side = pos.get("side", "LONG")

            if entry <= 0 or qty <= 0:
                continue

            current = prices.get(ticker)
            if current is None:
                log(f"  ⚠️ No price for {ticker} — CANNOT ENFORCE STOP for {bot}")
                continue

            # Calculate drawdown
            if side == "LONG":
                drawdown_pct = ((entry - current) / entry) * 100
            else:
                drawdown_pct = ((current - entry) / entry) * 100

            # Check stop
            if drawdown_pct >= STOP_PCT:
                execute_stop(bot, pos, current, f"HARD_STOP_{STOP_PCT}%", dry_run)
                stops_hit.append({"bot": bot, "ticker": ticker, "drawdown": drawdown_pct})

            # Check profit target
            elif side == "LONG" and current > entry:
                gain_pct = ((current - entry) / entry) * 100
                if gain_pct >= PROFIT_TARGET_PCT:
                    execute_stop(bot, pos, current, f"PROFIT_TARGET_{PROFIT_TARGET_PCT}%", dry_run)
                    stops_hit.append({"bot": bot, "ticker": ticker, "gain": gain_pct})
            elif side == "SHORT" and current < entry:
                gain_pct = ((entry - current) / entry) * 100
                if gain_pct >= PROFIT_TARGET_PCT:
                    execute_stop(bot, pos, current, f"PROFIT_TARGET_{PROFIT_TARGET_PCT}%", dry_run)
                    stops_hit.append({"bot": bot, "ticker": ticker, "gain": gain_pct})

            else:
                log(f"  ✅ {bot} {ticker} {side} | Entry: ${entry:.2f} → ${current:.2f} | DD: {drawdown_pct:.1f}% — OK")

    return stops_hit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Stop-Loss Enforcer")
    parser.add_argument("--bot", help="Check specific bot only")
    parser.add_argument("--dry-run", action="store_true", help="Check without executing")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 60s")
    args = parser.parse_args()

    if args.loop:
        log("Starting continuous stop enforcement (60-sec interval)...")
        while True:
            check_all_stops(args.bot, args.dry_run)
            time.sleep(60)
    else:
        stops = check_all_stops(args.bot, args.dry_run)
        if stops:
            log(f"⚠️ {len(stops)} stops triggered.")
        else:
            log("All positions within limits.")
