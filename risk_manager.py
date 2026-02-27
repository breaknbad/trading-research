#!/usr/bin/env python3
"""Risk manager: monitors positions, stops, limits, circuit breaker."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    sys.exit(1)

import config


def _supabase_get(path):
    try:
        r = requests.get(f"{config.SUPABASE_URL}/rest/v1/{path}", headers=config.SUPABASE_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"  [WARN] Supabase GET {path}: {r.status_code}")
    except Exception as e:
        print(f"  [ERR] Supabase: {e}")
    return None


def _load_trade_timestamps():
    if os.path.exists(config.TRADE_TIMESTAMPS_FILE):
        try:
            with open(config.TRADE_TIMESTAMPS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"trades": []}


def save_trade_timestamp():
    """Record a trade timestamp. Call after each trade."""
    data = _load_trade_timestamps()
    data["trades"].append(datetime.now(timezone.utc).isoformat())
    # Keep only last 24h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    data["trades"] = [t for t in data["trades"] if t > cutoff]
    os.makedirs(os.path.dirname(config.TRADE_TIMESTAMPS_FILE), exist_ok=True)
    with open(config.TRADE_TIMESTAMPS_FILE, "w") as f:
        json.dump(data, f)


def get_portfolio():
    """Fetch current portfolio from Supabase."""
    data = _supabase_get(f"portfolio_snapshots?bot_id=eq.{config.BOT_ID}&select=*")
    if data and len(data) > 0:
        return data[0]
    return None


def check_risk(verbose=True):
    """
    Full risk check. Returns dict:
      positions_to_close: [{ticker, reason, ...}]
      circuit_breaker: bool
      can_trade: bool
      trades_today: int
      trades_this_hour: int
      portfolio: dict
    """
    result = {
        "positions_to_close": [],
        "circuit_breaker": False,
        "can_trade": True,
        "trades_today": 0,
        "trades_this_hour": 0,
        "portfolio": None,
        "reasons": [],
    }

    if verbose:
        print("[RISK] Running risk checks...")

    # 1. Get portfolio
    portfolio = get_portfolio()
    if not portfolio:
        print("  [WARN] No portfolio found")
        result["can_trade"] = False
        result["reasons"].append("No portfolio data")
        return result

    result["portfolio"] = portfolio
    total_value = float(portfolio.get("total_value_usd", config.STARTING_CAPITAL))
    cash = float(portfolio.get("cash_usd", 0))
    positions = portfolio.get("open_positions", []) or []

    # 2. Check daily P&L (circuit breaker)
    daily_return_pct = float(portfolio.get("total_return_pct", 0))
    # More accurate: check if today's losses exceed threshold
    if daily_return_pct <= -config.DAILY_CIRCUIT_BREAKER_PCT:
        result["circuit_breaker"] = True
        result["can_trade"] = False
        result["reasons"].append(f"Circuit breaker: {daily_return_pct:.2f}% return")
        if verbose:
            print(f"  🛑 CIRCUIT BREAKER: {daily_return_pct:.2f}% return")

    # 3. Check each position
    for pos in positions:
        ticker = pos.get("ticker", "???")
        qty = float(pos.get("quantity", 0))
        entry = float(pos.get("avg_entry", 0))
        current = float(pos.get("current_price", entry))
        side = pos.get("side", "LONG")

        if entry <= 0 or qty <= 0:
            continue

        # Stop loss check
        if side == "LONG":
            loss_pct = ((entry - current) / entry) * 100
        else:
            loss_pct = ((current - entry) / entry) * 100

        if loss_pct >= config.STOP_LOSS_PCT:
            result["positions_to_close"].append({
                "ticker": ticker,
                "quantity": qty,
                "entry": entry,
                "current": current,
                "loss_pct": round(loss_pct, 2),
                "side": side,
                "reason": f"Stop loss hit: -{loss_pct:.1f}%",
            })
            if verbose:
                print(f"  🔴 STOP {ticker}: -{loss_pct:.1f}% (entry ${entry} -> ${current})")

        # Position size check
        pos_value = qty * current
        pos_pct = (pos_value / total_value) * 100 if total_value > 0 else 0
        if pos_pct > config.MAX_POSITION_PCT * 1.2:  # 20% overage buffer before forced close
            result["positions_to_close"].append({
                "ticker": ticker,
                "quantity": qty,
                "entry": entry,
                "current": current,
                "pos_pct": round(pos_pct, 2),
                "side": side,
                "reason": f"Oversized: {pos_pct:.1f}% of portfolio",
            })
            if verbose:
                print(f"  ⚠️  OVERSIZED {ticker}: {pos_pct:.1f}% of portfolio")

    # 4. Trade count limits
    ts_data = _load_trade_timestamps()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    hour_ago = (now - timedelta(hours=1)).isoformat()
    last_trade_time = None

    trades_today = sum(1 for t in ts_data["trades"] if t > today_start)
    trades_hour = sum(1 for t in ts_data["trades"] if t > hour_ago)
    result["trades_today"] = trades_today
    result["trades_this_hour"] = trades_hour

    if ts_data["trades"]:
        last_trade_time = max(ts_data["trades"])

    # v1.2: No trade caps. "Cap risk, not activity."

    # Cooldown check
    if last_trade_time:
        try:
            last_dt = datetime.fromisoformat(last_trade_time.replace("Z", "+00:00"))
            mins_since = (now - last_dt).total_seconds() / 60
            if mins_since < config.COOLDOWN_MINUTES:
                result["can_trade"] = False
                result["reasons"].append(f"Cooldown: {mins_since:.0f}/{config.COOLDOWN_MINUTES} min")
                if verbose:
                    print(f"  ⏳ Cooldown: {mins_since:.0f} min since last trade")
        except Exception:
            pass

    if verbose:
        status = "✅ CAN TRADE" if result["can_trade"] else "❌ CANNOT TRADE"
        print(f"  {status} | Trades today: {trades_today} | Positions to close: {len(result['positions_to_close'])}")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check risk status")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    result = check_risk(verbose=not args.quiet)
    print(f"\nCan trade: {result['can_trade']}")
    print(f"Circuit breaker: {result['circuit_breaker']}")
    print(f"Positions to close: {len(result['positions_to_close'])}")
    for p in result["positions_to_close"]:
        print(f"  - {p['ticker']}: {p['reason']}")
