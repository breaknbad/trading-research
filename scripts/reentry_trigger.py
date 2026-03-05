#!/usr/bin/env python3
"""
Re-Entry Trigger — Smart re-entry after stop-outs.

Replaces "2 stops = dead for session" with:
  - 2 stops on same ticker in 30 min = 60-min cooldown (not dead forever)
  - After cooldown: if price reclaims (entry + 0.5x ATR) on rising RVOL → re-enter at half original size
  - Max 1 re-entry per ticker per session

Usage:
  python3 reentry_trigger.py                     # Check all pending re-entries
  python3 reentry_trigger.py --bot alfred_crypto  # Check one bot
  python3 reentry_trigger.py --status             # Show cooldown/re-entry state

Designed to run every 60s via launchd.
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

COOLDOWN_MIN = 60       # minutes after 2nd stop before re-entry allowed
MAX_REENTRIES = 1       # max re-entries per ticker per session
REENTRY_ATR_MULT = 0.5  # price must reclaim entry + this * ATR
REENTRY_SIZE_MULT = 0.5 # re-enter at half original size

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "reentry_state.json")

# ATR defaults (same as trailing stop)
DEFAULT_ATR_PCT = {
    "BTC": 3.0, "ETH": 4.0, "SOL": 6.0, "NEAR": 8.0, "AVAX": 7.0,
    "LINK": 6.0, "SQQQ": 4.0, "SPY": 1.2, "QQQ": 1.5,
    "GLD": 1.5, "GDX": 3.5, "_DEFAULT": 2.5,
}


def get_price(ticker):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            meta = r.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = float(meta.get("regularMarketPrice", 0))
            return price if price > 0 else None
    except Exception:
        pass
    return None


def estimate_atr(ticker, price):
    base = ticker.replace("-USD", "").upper()
    pct = DEFAULT_ATR_PCT.get(base, DEFAULT_ATR_PCT["_DEFAULT"])
    return price * (pct / 100) if price > 0 else None


def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"stopped_out": {}, "reentries_done": {}, "session_start": datetime.now(timezone.utc).isoformat()}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def record_stop(bot_id, ticker, side, entry_price, qty):
    """Call this when a stop is hit to register for potential re-entry."""
    state = load_state()
    key = f"{bot_id}:{ticker}:{side}"

    if key not in state["stopped_out"]:
        state["stopped_out"][key] = []

    state["stopped_out"][key].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry_price": entry_price,
        "quantity": qty,
        "side": side,
    })

    save_state(state)
    count = len(state["stopped_out"][key])
    print(f"📝 Stop recorded: {bot_id} {side} {ticker} (stop #{count})")

    if count >= 2:
        print(f"⏸️ COOLDOWN ACTIVE: {ticker} blocked for {COOLDOWN_MIN} min. Re-entry will trigger if price reclaims entry + 0.5x ATR.")


def check_reentries(bot_id=None):
    """Check if any stopped-out positions qualify for re-entry."""
    state = load_state()
    stopped = state.get("stopped_out", {})
    reentries_done = state.get("reentries_done", {})
    actions = []
    now = datetime.now(timezone.utc)

    for key, stops in list(stopped.items()):
        parts = key.split(":")
        if len(parts) != 3:
            continue
        bot, ticker, side = parts

        if bot_id and bot != bot_id:
            continue

        # Need at least 1 stop to consider re-entry
        if not stops:
            continue

        # Check if already re-entered this ticker this session
        if reentries_done.get(key, 0) >= MAX_REENTRIES:
            continue

        last_stop = stops[-1]
        stop_time = datetime.fromisoformat(last_stop["timestamp"])
        elapsed_min = (now - stop_time).total_seconds() / 60

        # If 2+ stops: enforce cooldown
        if len(stops) >= 2 and elapsed_min < COOLDOWN_MIN:
            remaining = COOLDOWN_MIN - elapsed_min
            # Only print periodically
            if int(elapsed_min) % 10 == 0:
                print(f"⏸️ {bot} {ticker}: {remaining:.0f}min cooldown remaining")
            continue

        # Cooldown expired (or only 1 stop). Check re-entry conditions.
        entry_price = float(last_stop["entry_price"])
        original_qty = float(last_stop["quantity"])
        current = get_price(ticker)
        if current is None:
            continue

        atr = estimate_atr(ticker, current)
        if atr is None:
            continue

        # Re-entry trigger: price must reclaim entry + 0.5x ATR (for longs)
        # For shorts: price must drop below entry - 0.5x ATR
        if side == "LONG":
            trigger = entry_price + (REENTRY_ATR_MULT * atr)
            triggered = current >= trigger
        else:
            trigger = entry_price - (REENTRY_ATR_MULT * atr)
            triggered = current <= trigger

        if triggered:
            reentry_qty = round(original_qty * REENTRY_SIZE_MULT, 6)
            reentry_price = current

            print(f"🔄 RE-ENTRY TRIGGER: {bot} {side} {ticker} @ ${current:.2f} (trigger was ${trigger:.2f})")
            print(f"   Original: {original_qty} @ ${entry_price:.2f} → Re-entry: {reentry_qty} @ ${current:.2f} (half size)")

            # Execute re-entry
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trading-research"))
                from log_trade import log_trade
                action = "BUY" if side == "LONG" else "SHORT"
                # Calculate a reasonable stop for the re-entry
                if side == "LONG":
                    stop = current - (1.5 * atr)
                else:
                    stop = current + (1.5 * atr)

                success = log_trade(
                    bot, action, ticker, reentry_qty, current,
                    f"RE-ENTRY: stopped at ${entry_price:.2f}, reclaimed +0.5xATR at ${current:.2f}. Half size.",
                    stop_price=stop
                )
                if success:
                    reentries_done[key] = reentries_done.get(key, 0) + 1
                    # Clear stops for this ticker
                    del stopped[key]
                    actions.append({"bot": bot, "ticker": ticker, "side": side, "qty": reentry_qty, "price": current})
                    print(f"   ✅ Re-entry executed")
                else:
                    print(f"   ❌ Re-entry blocked by pipeline gates (regime/cascade/factor)")
            except Exception as e:
                print(f"   ❌ Re-entry failed: {e}")

    state["stopped_out"] = stopped
    state["reentries_done"] = reentries_done
    save_state(state)

    if not actions:
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        pending = len([k for k, v in stopped.items() if v])
        print(f"✅ {now_str} UTC — No re-entries triggered. {pending} tickers in cooldown/monitoring.")

    return actions


def show_status():
    state = load_state()
    print("=== RE-ENTRY STATE ===")
    print(f"Session start: {state.get('session_start', 'unknown')}")

    stopped = state.get("stopped_out", {})
    if not stopped:
        print("No stopped-out positions tracked.")
    else:
        now = datetime.now(timezone.utc)
        for key, stops in stopped.items():
            bot, ticker, side = key.split(":")
            last = stops[-1]
            stop_time = datetime.fromisoformat(last["timestamp"])
            elapsed = (now - stop_time).total_seconds() / 60
            cooldown_active = len(stops) >= 2 and elapsed < COOLDOWN_MIN
            status = f"COOLDOWN ({COOLDOWN_MIN - elapsed:.0f}min left)" if cooldown_active else "MONITORING for re-entry"
            print(f"  {bot} {side} {ticker}: {len(stops)} stops, last @ ${last['entry_price']}, {status}")

    done = state.get("reentries_done", {})
    if done:
        print(f"Re-entries completed: {done}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-Entry Trigger")
    parser.add_argument("--bot", help="Check specific bot only")
    parser.add_argument("--status", action="store_true", help="Show current state")
    args = parser.parse_args()

    if args.status:
        show_status()
    else:
        check_reentries(args.bot)
