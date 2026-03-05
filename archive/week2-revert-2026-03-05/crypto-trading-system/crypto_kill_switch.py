#!/usr/bin/env python3
"""
Crypto Kill Switch — Daily circuit breaker.
If any bot's portfolio drops 5% from daily open, freeze ALL new entries for that bot.

Runs alongside stop_enforcer. Checks portfolio value vs daily start.

Usage:
  python3 crypto_kill_switch.py              # Check all bots
  python3 crypto_kill_switch.py --bot alfred  # Check one bot
  python3 crypto_kill_switch.py --reset       # Reset daily baselines (run at midnight)
"""

import argparse
import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta

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

CIRCUIT_BREAKER_PCT = 5.0  # -5% daily drawdown = freeze
BOTS = ["alfred", "tars", "vex", "eddie_v"]
STATE_FILE = os.path.join(os.path.dirname(__file__), "kill_switch_state.json")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"daily_baselines": {}, "frozen_bots": {}, "last_reset": ""}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_portfolio_value(bot_id: str) -> float:
    """Get current portfolio value (cash + positions) from Supabase."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_portfolio_snapshots",
            params={
                "bot_id": f"eq.{bot_id}",
                "select": "total_value",
                "order": "timestamp.desc",
                "limit": "1",
            },
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            return float(r.json()[0].get("total_value", 0))
    except Exception:
        pass
    return 0.0


def check_kill_switch(bot_id: str = None) -> dict:
    """Check if any bot has hit the daily circuit breaker."""
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Auto-reset at midnight
    if state.get("last_reset") != today:
        state["daily_baselines"] = {}
        state["frozen_bots"] = {}
        state["last_reset"] = today

    bots_to_check = [bot_id] if bot_id else BOTS
    results = {}

    for bot in bots_to_check:
        current_value = get_portfolio_value(bot)
        if current_value <= 0:
            results[bot] = {"status": "NO_DATA", "value": 0}
            continue

        # Set baseline if not exists
        if bot not in state["daily_baselines"]:
            state["daily_baselines"][bot] = current_value
            print(f"📊 {bot} daily baseline set: ${current_value:,.2f}")

        baseline = state["daily_baselines"][bot]
        drawdown_pct = ((baseline - current_value) / baseline) * 100

        if drawdown_pct >= CIRCUIT_BREAKER_PCT:
            state["frozen_bots"][bot] = {
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "drawdown_pct": round(drawdown_pct, 2),
                "baseline": baseline,
                "current": current_value,
            }
            results[bot] = {"status": "FROZEN", "drawdown_pct": drawdown_pct}
            print(f"🚨 KILL SWITCH: {bot} frozen! DD: {drawdown_pct:.1f}% "
                  f"(${baseline:,.2f} → ${current_value:,.2f})")
        else:
            results[bot] = {"status": "OK", "drawdown_pct": drawdown_pct}
            print(f"✅ {bot}: ${current_value:,.2f} | DD: {drawdown_pct:.1f}% — OK")

    save_state(state)
    return results


def is_frozen(bot_id: str) -> bool:
    """Check if a bot is currently frozen. Call this before any new entry."""
    state = load_state()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("last_reset") != today:
        return False
    return bot_id in state.get("frozen_bots", {})


def check_round_breaker(bot_id: str = None, round_start_values: dict = None) -> dict:
    """
    Per-round circuit breaker. If a bot drops >3% within a 3-hour round, freeze entries.
    Pass round_start_values = {bot: value} captured at round open.
    """
    ROUND_BREAKER_PCT = 3.0
    bots_to_check = [bot_id] if bot_id else BOTS
    results = {}

    if not round_start_values:
        return {"error": "No round start values provided"}

    for bot in bots_to_check:
        start_val = round_start_values.get(bot, 0)
        if start_val <= 0:
            continue

        current_val = get_portfolio_value(bot)
        if current_val <= 0:
            continue

        dd_pct = ((start_val - current_val) / start_val) * 100
        if dd_pct >= ROUND_BREAKER_PCT:
            state = load_state()
            state["frozen_bots"][bot] = {
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "drawdown_pct": round(dd_pct, 2),
                "baseline": start_val,
                "current": current_val,
                "reason": "ROUND_BREAKER",
            }
            save_state(state)
            results[bot] = {"status": "FROZEN", "drawdown_pct": dd_pct, "reason": "ROUND_BREAKER"}
            print(f"🚨 ROUND BREAKER: {bot} frozen! DD: {dd_pct:.1f}% this round")
        else:
            results[bot] = {"status": "OK", "drawdown_pct": dd_pct}

    return results


def reset_baselines():
    """Force reset all baselines and unfreeze all bots."""
    state = {
        "daily_baselines": {},
        "frozen_bots": {},
        "last_reset": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    save_state(state)
    print("🔓 All bots unfrozen. Daily baselines cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Kill Switch")
    parser.add_argument("--bot", help="Check specific bot only")
    parser.add_argument("--reset", action="store_true", help="Reset baselines")
    parser.add_argument("--check-frozen", help="Check if a bot is frozen")
    args = parser.parse_args()

    if args.reset:
        reset_baselines()
    elif args.check_frozen:
        frozen = is_frozen(args.check_frozen)
        print(f"{args.check_frozen}: {'FROZEN 🚨' if frozen else 'OK ✅'}")
    else:
        check_kill_switch(args.bot)
