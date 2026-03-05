# CALLED BY: cron pnl-alerts (every 5 min during market hours, every 15 min overnight)
#!/usr/bin/env python3
"""
P&L Alert System — "Offense screams too" (DA Round 2, Mar 3)

Checks all OPEN positions across all bots. Alerts at:
  +3% → "Trail or add?"
  +5% → "Scale out 25% or tighten trail"
  +8% → "Take 50% off, trail remainder"
  -1.5% → "Approaching stop — review thesis"

Writes alerts to stdout (cron posts to Discord).
Tracks already-alerted positions to avoid spam.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

SUPABASE_URL = None
SUPABASE_KEY = None
ALERT_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pnl_alert_state.json")

THRESHOLDS = [
    {"pct": 8.0,  "emoji": "🚀", "action": "TAKE 50% OFF — trail remainder at +5%"},
    {"pct": 5.0,  "emoji": "🟢", "action": "Scale out 25% or tighten trail to +2%"},
    {"pct": 3.0,  "emoji": "📈", "action": "TRAIL or ADD? — winner running, don't let it reverse"},
    {"pct": -1.5, "emoji": "⚠️", "action": "Approaching stop — review thesis NOW"},
]

YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def load_env():
    global SUPABASE_URL, SUPABASE_KEY
    env_paths = [
        os.path.expanduser("~/.openclaw/workspace/.env"),
        os.path.expanduser("~/workspace/.env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    ]
    for p in env_paths:
        if os.path.exists(p):
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SUPABASE_URL="):
                        SUPABASE_URL = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("SUPABASE_KEY="):
                        SUPABASE_KEY = line.split("=", 1)[1].strip().strip('"')
            break


def supabase_get(path):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        **HEADERS,
    })
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def get_yahoo_price(ticker):
    try:
        url = f"{YAHOO_BASE}/{ticker}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers=HEADERS)
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None


def load_alert_state():
    try:
        with open(ALERT_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_alert_state(state):
    with open(ALERT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def already_alerted(state, bot_id, ticker, threshold_pct):
    """Don't spam the same alert. Re-alert if position has moved to a NEW threshold."""
    key = f"{bot_id}:{ticker}"
    if key not in state:
        return False
    last = state[key]
    # Re-alert if we've crossed a new threshold level
    return last.get("last_threshold") == threshold_pct


def run_pnl_alerts():
    load_env()
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: No Supabase credentials")
        return []

    # Get all OPEN trades
    trades = supabase_get("trades?status=eq.OPEN&select=bot_id,ticker,action,price_usd,quantity,id")
    if not trades:
        return []

    state = load_alert_state()
    alerts = []
    now = datetime.now(timezone.utc).isoformat()

    for trade in trades:
        bot = trade["bot_id"]
        ticker = trade["ticker"]
        entry = float(trade["price_usd"])
        qty = float(trade["quantity"])
        action = trade["action"]

        current = get_yahoo_price(ticker)
        if current is None:
            continue

        # Calculate P&L %
        if action in ("BUY",):
            pct_change = (current - entry) / entry * 100
        elif action in ("SHORT",):
            pct_change = (entry - current) / entry * 100
        else:
            continue

        unrealized = (current - entry) * qty if action == "BUY" else (entry - current) * qty

        # Check thresholds (check highest first)
        for t in THRESHOLDS:
            threshold = t["pct"]
            if threshold > 0 and pct_change >= threshold:
                if not already_alerted(state, bot, ticker, threshold):
                    alert = (
                        f"{t['emoji']} **{bot.upper()} — {ticker} +{pct_change:.1f}%** "
                        f"(${unrealized:+,.2f})\n"
                        f"   Entry: ${entry:.2f} → Now: ${current:.2f} | Qty: {qty}\n"
                        f"   → {t['action']}"
                    )
                    alerts.append(alert)
                    state[f"{bot}:{ticker}"] = {
                        "last_threshold": threshold,
                        "last_alert": now,
                        "pct": round(pct_change, 2),
                    }
                break  # Only alert on highest threshold crossed
            elif threshold < 0 and pct_change <= threshold:
                if not already_alerted(state, bot, ticker, threshold):
                    alert = (
                        f"{t['emoji']} **{bot.upper()} — {ticker} {pct_change:.1f}%** "
                        f"(${unrealized:+,.2f})\n"
                        f"   Entry: ${entry:.2f} → Now: ${current:.2f} | Qty: {qty}\n"
                        f"   → {t['action']}"
                    )
                    alerts.append(alert)
                    state[f"{bot}:{ticker}"] = {
                        "last_threshold": threshold,
                        "last_alert": now,
                        "pct": round(pct_change, 2),
                    }
                break

    save_alert_state(state)
    return alerts


def execute_scale_out(bot, ticker, qty, price, pct_gain, trim_pct):
    """Auto-execute a scale-out sell."""
    import subprocess
    trim_qty = round(qty * trim_pct, 6)
    reason = f"[SCALE_OUT] Auto-trim {int(trim_pct*100)}% at +{pct_gain:.1f}%"
    cmd = [
        "python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_trade.py"),
        "--bot", bot, "--action", "SELL", "--ticker", ticker,
        "--qty", str(trim_qty), "--price", str(price),
        "--reason", reason, "--skip-validation"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✅ SCALE-OUT: SELL {ticker} {trim_qty}x @ ${price:.2f} (+{pct_gain:.1f}%)")
            return True
        else:
            print(f"  ❌ SCALE-OUT FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-scale", action="store_true", help="Auto-execute scale-outs at +8% (50%) and +5% (25%)")
    args = parser.parse_args()
    
    alerts = run_pnl_alerts()
    if alerts:
        print(f"\n{'='*60}")
        print(f"📊 P&L ALERTS — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
        print(f"{'='*60}")
        for a in alerts:
            print(f"\n{a}")
        print(f"\n{'='*60}")
        
        # Auto-scale if enabled — re-scan for positions hitting thresholds
        if args.auto_scale:
            load_env()
            trades = supabase_get("trades?status=eq.OPEN&select=bot_id,ticker,action,price_usd,quantity,id")
            for trade in (trades or []):
                if trade["action"] != "BUY":
                    continue
                entry = float(trade["price_usd"])
                current = get_yahoo_price(trade["ticker"])
                if current is None:
                    continue
                pct = (current - entry) / entry * 100
                if pct >= 8.0:
                    execute_scale_out(trade["bot_id"], trade["ticker"], float(trade["quantity"]), current, pct, 0.50)
                elif pct >= 5.0:
                    execute_scale_out(trade["bot_id"], trade["ticker"], float(trade["quantity"]), current, pct, 0.25)
    else:
        print("No P&L alerts — all positions within normal range.")
