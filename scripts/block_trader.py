#!/usr/bin/env python3
"""block_trader.py — Anti-fizzle engine for Vex.

Runs every 30 minutes. Checks:
1. Cash idle > 5 min? → Deploy into highest-conviction available setup
2. Any position stale (flat for 2+ hours)? → Rotate into better mover
3. Block velocity on track? → If behind 5% floor, force action
4. No ceiling on gains — keep pushing when momentum is there

Per Mark's directive: $0 cash idle >5 min = failure.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

BOT_ID = "vex"
WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(WORKSPACE, "trading", "data")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "vex.json")
MARKET_STATE = os.path.join(WORKSPACE, "market-state.json")
STATE_FILE = os.path.join(DATA_DIR, "block_trader_state.json")

# Thresholds
MAX_CASH_IDLE_MIN = 5
STALE_POSITION_HOURS = 2
STALE_MOVE_PCT = 0.5  # <0.5% move in 2 hours = stale
BLOCK_TARGET_PCT = 5.0  # 5% per 2-hour block FLOOR
ROTATION_MIN_EDGE_PCT = 2.0  # New position must have 2%+ more potential


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_crypto_price(ticker):
    """Quick price check via Yahoo Finance."""
    crypto_map = {
        "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
        "LINK": "LINK-USD", "AVAX": "AVAX-USD", "NEAR": "NEAR-USD",
        "UNI": "UNI-USD", "DOGE": "DOGE-USD", "SUI": "SUI-USD",
        "PENDLE": "PENDLE-USD", "AAVE": "AAVE-USD", "ARB": "ARB-USD",
    }
    yf = crypto_map.get(ticker, ticker)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        return None


def check_cash_idle(portfolio, state):
    """If cash > $500, flag it and find deployment target."""
    cash = portfolio.get("cash", 0)
    if cash < 500:
        state["last_deployed"] = time.time()
        return []

    idle_since = state.get("last_deployed", time.time())
    idle_min = (time.time() - idle_since) / 60

    actions = []
    if idle_min > MAX_CASH_IDLE_MIN:
        actions.append({
            "action": "DEPLOY_CASH",
            "cash": cash,
            "idle_minutes": round(idle_min, 1),
            "urgency": "HIGH",
            "message": f"${cash:.0f} idle for {idle_min:.0f} min. DEPLOY NOW."
        })
    return actions


def check_stale_positions(portfolio):
    """Find positions that haven't moved in 2+ hours."""
    actions = []
    now = datetime.now(timezone.utc)

    for pos in portfolio.get("positions", []):
        entry_time = pos.get("entry_time", "")
        if not entry_time:
            continue

        try:
            entered = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        except:
            continue

        hours_held = (now - entered).total_seconds() / 3600
        if hours_held < STALE_POSITION_HOURS:
            continue

        # Check current price vs entry
        price = get_crypto_price(pos["ticker"])
        if not price:
            continue

        entry = pos.get("entry_price", price)
        move_pct = ((price - entry) / entry) * 100

        if abs(move_pct) < STALE_MOVE_PCT:
            actions.append({
                "action": "ROTATE_STALE",
                "ticker": pos["ticker"],
                "hours_held": round(hours_held, 1),
                "move_pct": round(move_pct, 2),
                "message": f"{pos['ticker']} stale: {move_pct:+.1f}% in {hours_held:.0f}h. Rotation candidate."
            })

    return actions


def check_block_velocity(portfolio):
    """Are we on track for 5% this block?"""
    actions = []
    total_value = portfolio.get("cash", 0)

    for pos in portfolio.get("positions", []):
        price = get_crypto_price(pos["ticker"])
        if price:
            total_value += pos.get("qty", 0) * price
        else:
            total_value += pos.get("cost_basis", 0)

    start_value = 50000  # Week 2 starting capital
    total_return_pct = ((total_value - start_value) / start_value) * 100

    # Calculate block progress (2-hour blocks starting from market open)
    now = datetime.now(timezone.utc)
    hour = now.hour
    block_progress = (now.minute + (hour % 2) * 60) / 120  # 0-1 within 2hr block

    expected_gain = BLOCK_TARGET_PCT * block_progress
    gap = expected_gain - max(0, total_return_pct)

    if gap > 1.0:  # Behind by more than 1%
        actions.append({
            "action": "VELOCITY_BEHIND",
            "current_pct": round(total_return_pct, 2),
            "expected_pct": round(expected_gain, 2),
            "gap_pct": round(gap, 2),
            "portfolio_value": round(total_value, 2),
            "message": f"Behind block target: {total_return_pct:.1f}% vs {expected_gain:.1f}% expected. Gap: {gap:.1f}%"
        })

    return actions


def run():
    """Main block_trader cycle."""
    print(f"[block_trader] Running at {datetime.now().isoformat()}")

    portfolio = load_json(PORTFOLIO_FILE)
    if not portfolio:
        print("[block_trader] No portfolio found")
        return

    state = load_json(STATE_FILE)
    if not state:
        state = {"last_deployed": time.time(), "last_run": ""}

    all_actions = []

    # 1. Cash idle check
    all_actions.extend(check_cash_idle(portfolio, state))

    # 2. Stale position check
    all_actions.extend(check_stale_positions(portfolio))

    # 3. Block velocity check
    all_actions.extend(check_block_velocity(portfolio))

    # Report
    if all_actions:
        print(f"\n[block_trader] {len(all_actions)} action(s) needed:")
        for a in all_actions:
            print(f"  [{a['action']}] {a['message']}")
    else:
        print("[block_trader] All clear — positions active, cash deployed, velocity on track.")

    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_json(STATE_FILE, state)

    # Write actions for heartbeat to pick up
    actions_file = os.path.join(DATA_DIR, "block_actions.json")
    save_json(actions_file, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actions": all_actions
    })

    return all_actions


if __name__ == "__main__":
    run()
