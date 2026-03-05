#!/usr/bin/env python3
"""
Trailing Stop Manager — Dynamic Stop Ratcheting
=================================================
Upgrade #7: After +2% move → stop to breakeven. After +3% → trail by 1.5%.
Replaces static stops for managed positions. stop_check.py reads our state.

State stored in logs/trailing_stop_state.json (stop_check.py already reads this).

Usage:
  python3 trailing_stop.py              # Run every 30s
  python3 trailing_stop.py --once       # Single pass
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
STATE_PATH = WORKSPACE / "logs" / "trailing_stop_state.json"
LOG_PATH = WORKSPACE / "logs" / "trailing_stop.log"
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"

# Trailing stop rules
BREAKEVEN_TRIGGER_PCT = 2.0   # Move stop to breakeven after +2%
TRAIL_TRIGGER_PCT = 3.0       # Start trailing after +3%
TRAIL_DISTANCE_PCT = 1.5      # Trail by 1.5% below high-water mark

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = ""
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
except Exception:
    pass

FINNHUB_KEY = ""
try:
    FINNHUB_KEY = open(os.path.expanduser("~/.finnhub_key")).read().strip()
except Exception:
    pass

os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state():
    try:
        if STATE_PATH.exists():
            return json.load(open(STATE_PATH))
    except Exception:
        pass
    return {}


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_open_positions():
    """Get all open positions from Supabase portfolio snapshots."""
    if not SUPABASE_KEY:
        return []
    positions = []
    for bot in [BOT_ID, f"{BOT_ID}_crypto"]:
        try:
            url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot}&select=open_positions"
            req = urllib.request.Request(url, headers={
                "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data and data[0].get("open_positions"):
                for pos in data[0]["open_positions"]:
                    pos["_bot_id"] = bot
                    positions.append(pos)
        except Exception as e:
            log(f"Position fetch error for {bot}: {e}")
    return positions


def get_price(symbol):
    """Get price from cache or HTTP."""
    # Cache first
    try:
        if PRICE_CACHE_PATH.exists():
            cache = json.load(open(PRICE_CACHE_PATH))
            prices = cache.get("prices", {})
            if symbol in prices:
                return prices[symbol].get("price", 0)
    except Exception:
        pass
    # HTTP fallback
    if FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            req = urllib.request.Request(url, headers={"User-Agent": "TrailingStop/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            return data.get("c", 0)
        except Exception:
            pass
    # Yahoo fallback
    try:
        yahoo_sym = symbol
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return data.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("regularMarketPrice", 0)
    except Exception:
        pass
    return 0


def update_trailing_stops():
    """Check all positions and update trailing stop levels."""
    positions = get_open_positions()
    if not positions:
        return

    state = load_state()
    updated = False

    for pos in positions:
        ticker = pos.get("ticker", "")
        entry = float(pos.get("avg_entry", 0))
        qty = float(pos.get("quantity", 0))
        side = pos.get("side", "LONG")
        bot_id = pos.get("_bot_id", BOT_ID)

        if entry <= 0 or qty <= 0:
            continue

        # Get current price
        price_symbol = ticker
        current = get_price(price_symbol)
        if current <= 0:
            continue

        key = f"{bot_id}:{ticker}:{side}"
        prev = state.get(key, {})

        # Calculate gain
        if side == "LONG":
            gain_pct = ((current - entry) / entry) * 100
        else:
            gain_pct = ((entry - current) / entry) * 100

        # Update high-water mark
        hwm = max(current, prev.get("high_water", current)) if side == "LONG" else min(current, prev.get("high_water", current))

        # Determine trailing stop level
        trailing_stop = prev.get("trailing_stop")
        stop_reason = prev.get("stop_reason", "none")

        if gain_pct >= TRAIL_TRIGGER_PCT:
            # Trail by 1.5% below high-water mark
            if side == "LONG":
                new_stop = round(hwm * (1 - TRAIL_DISTANCE_PCT / 100), 4)
            else:
                new_stop = round(hwm * (1 + TRAIL_DISTANCE_PCT / 100), 4)

            if trailing_stop is None or (side == "LONG" and new_stop > trailing_stop) or (side == "SHORT" and new_stop < trailing_stop):
                if trailing_stop != new_stop:
                    log(f"📈 TRAIL: {bot_id} {ticker} gain={gain_pct:.1f}% hwm=${hwm:.2f} → stop=${new_stop:.2f}")
                trailing_stop = new_stop
                stop_reason = f"trailing_{TRAIL_DISTANCE_PCT}%_from_hwm"
                updated = True

        elif gain_pct >= BREAKEVEN_TRIGGER_PCT:
            # Move stop to breakeven
            if trailing_stop is None or (side == "LONG" and entry > trailing_stop) or (side == "SHORT" and entry < trailing_stop):
                log(f"🔒 BREAKEVEN: {bot_id} {ticker} gain={gain_pct:.1f}% → stop=entry ${entry:.2f}")
                trailing_stop = entry
                stop_reason = "breakeven"
                updated = True

        state[key] = {
            "ticker": ticker,
            "bot_id": bot_id,
            "side": side,
            "entry": entry,
            "current": current,
            "gain_pct": round(gain_pct, 2),
            "high_water": hwm,
            "trailing_stop": trailing_stop,
            "stop_reason": stop_reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    if updated:
        save_state(state)
    else:
        # Still save for freshness tracking
        save_state(state)


def run():
    log(f"🏁 Trailing Stop Manager starting — bot={BOT_ID}")
    log(f"   Rules: +{BREAKEVEN_TRIGGER_PCT}% → breakeven, +{TRAIL_TRIGGER_PCT}% → trail {TRAIL_DISTANCE_PCT}%")
    while True:
        try:
            update_trailing_stops()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    if "--once" in sys.argv:
        update_trailing_stops()
    else:
        run()
