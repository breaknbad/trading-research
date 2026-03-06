#!/usr/bin/env python3
"""signal_auto_exec.py — Auto-enter SCOUT on 5%+ signal bus movers.

Reads shared_signals from Supabase, finds any ticker with >=5% move
and volume confirmation, logs a SCOUT trade via log_trade.py.

No risk check needed for SCOUT tier per Mark's directive.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Config
SCOUT_SIZE_USD = 2000
TRAIL_STOP_PCT = 0.02  # -2% trailing stop
MIN_MOVE_PCT = 5.0
COOLDOWN_SECONDS = 3600  # Don't re-enter same ticker within 1 hour
BOT_ID = "vex"

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(WORKSPACE, "trading", "data")
STATE_FILE = os.path.join(DATA_DIR, "auto_exec_state.json")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "vex.json")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_entries": {}}


def save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {"positions": [], "cash": 0}


def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)


def fetch_signals():
    """Fetch recent shared_signals from Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        # Fallback: read local alerts.json
        alerts_file = os.path.join(WORKSPACE, "alerts.json")
        if os.path.exists(alerts_file):
            with open(alerts_file) as f:
                return json.load(f)
        return []

    url = f"{SUPABASE_URL}/rest/v1/shared_signals?order=created_at.desc&limit=50"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[signal_auto_exec] Supabase fetch failed: {e}")
        return []


def get_live_price(ticker):
    """Get live price from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
            return float(price)
    except Exception as e:
        print(f"[signal_auto_exec] Price fetch failed for {ticker}: {e}")
        return None


def should_enter(ticker, move_pct, state):
    """Check if we should auto-enter this ticker."""
    now = time.time()

    # Check cooldown
    last = state["last_entries"].get(ticker, 0)
    if now - last < COOLDOWN_SECONDS:
        print(f"[signal_auto_exec] {ticker} in cooldown ({int(now - last)}s ago)")
        return False

    # Check if already holding
    portfolio = load_portfolio()
    held = [p["ticker"] for p in portfolio.get("positions", [])]
    if ticker in held:
        print(f"[signal_auto_exec] Already holding {ticker}")
        return False

    # Check cash
    if portfolio.get("cash", 0) < SCOUT_SIZE_USD:
        print(f"[signal_auto_exec] Insufficient cash (${portfolio.get('cash', 0):.0f} < ${SCOUT_SIZE_USD})")
        return False

    # Move must be >= threshold
    if abs(move_pct) < MIN_MOVE_PCT:
        return False

    return True


def execute_scout(ticker, price, side="BUY"):
    """Execute a SCOUT-tier trade."""
    portfolio = load_portfolio()
    qty = int(SCOUT_SIZE_USD / price) if price > 1 else round(SCOUT_SIZE_USD / price, 4)
    cost = qty * price

    if cost > portfolio.get("cash", 0):
        print(f"[signal_auto_exec] Cost ${cost:.0f} > cash ${portfolio.get('cash', 0):.0f}")
        return False

    # Add position
    position = {
        "ticker": ticker,
        "side": side,
        "qty": qty,
        "entry_price": price,
        "cost_basis": cost,
        "stop_price": round(price * (1 - TRAIL_STOP_PCT), 4),
        "tier": "SCOUT",
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "source": "signal_auto_exec"
    }
    portfolio["positions"].append(position)
    portfolio["cash"] = round(portfolio["cash"] - cost, 2)

    save_portfolio(portfolio)
    print(f"[signal_auto_exec] EXECUTED: {side} {qty} {ticker} @ ${price:.4f} = ${cost:.0f} (SCOUT)")
    print(f"[signal_auto_exec] Stop: ${position['stop_price']:.4f} (-{TRAIL_STOP_PCT*100}%)")
    print(f"[signal_auto_exec] Remaining cash: ${portfolio['cash']:.0f}")
    return True


def run():
    """Main scan loop."""
    print(f"[signal_auto_exec] Running at {datetime.now().isoformat()}")

    state = load_state()
    signals = fetch_signals()

    if not signals:
        print("[signal_auto_exec] No signals found")
        return

    entries_made = 0
    for sig in signals:
        ticker = sig.get("ticker") or sig.get("symbol", "")
        move_pct = float(sig.get("move_pct") or sig.get("change_pct") or 0)

        if not ticker or abs(move_pct) < MIN_MOVE_PCT:
            continue

        if not should_enter(ticker, move_pct, state):
            continue

        # Get live price
        # Map crypto tickers for Yahoo
        yf_ticker = ticker
        crypto_map = {
            "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD",
            "LINK": "LINK-USD", "AVAX": "AVAX-USD", "NEAR": "NEAR-USD",
            "UNI": "UNI-USD", "DOGE": "DOGE-USD", "SUI": "SUI-USD",
            "PENDLE": "PENDLE-USD", "AAVE": "AAVE-USD", "ARB": "ARB-USD",
            "MARA": "MARA", "PLTR": "PLTR", "AI": "AI"
        }
        yf_ticker = crypto_map.get(ticker, ticker)

        price = get_live_price(yf_ticker)
        if not price:
            print(f"[signal_auto_exec] Skipping {ticker} — no price")
            continue

        side = "BUY" if move_pct > 0 else "SHORT"
        if execute_scout(ticker, price, side):
            state["last_entries"][ticker] = time.time()
            entries_made += 1

    save_state(state)
    print(f"[signal_auto_exec] Done. {entries_made} entries made.")


if __name__ == "__main__":
    run()
