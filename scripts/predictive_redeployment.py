#!/usr/bin/env python3
"""
Hot Cash Predictive Redeployment — Pre-Loaded Trade Queue
==========================================================
Upgrade #10: Maintain a "next best trade" prediction queue. When cash frees
from a trim/stop, inject the top prediction into watchlist for immediate pickup.

Predictions expire after 30 minutes. Must pass all safety gates.

Usage:
  python3 predictive_redeployment.py --once       # Generate predictions
  python3 predictive_redeployment.py --deploy      # Check for freed cash, deploy top prediction
  python3 predictive_redeployment.py               # Run continuously (60s cycle)
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
PREDICTIONS_PATH = WORKSPACE / "logs" / "predictions_queue.json"
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
LOG_PATH = WORKSPACE / "logs" / "predictive_redeployment.log"
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"

PREDICTION_EXPIRY_MINS = 30
MAX_POSITION_PCT = 0.15     # 15% max for redeployment (slightly conservative)
STOP_PCT = 2.0              # Tight stop on redeployments
STARTING_CAPITAL = 50000

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

# Candidates for redeployment — high-conviction tickers we'd buy if cash freed
REDEPLOY_CANDIDATES = [
    {"ticker": "NVDA", "market": "STOCK", "bias": "BUY", "reason": "AI leader, buy dips"},
    {"ticker": "AVGO", "market": "STOCK", "bias": "BUY", "reason": "Semi leader, networking AI"},
    {"ticker": "BTC-USD", "market": "CRYPTO", "bias": "BUY", "reason": "Digital gold, macro hedge"},
    {"ticker": "SOL-USD", "market": "CRYPTO", "bias": "BUY", "reason": "L1 leader, DeFi growth"},
    {"ticker": "META", "market": "STOCK", "bias": "BUY", "reason": "AI capex, ad revenue"},
    {"ticker": "TSLA", "market": "STOCK", "bias": "BUY", "reason": "EV + AI robotics"},
]


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_quote(symbol):
    try:
        if PRICE_CACHE_PATH.exists():
            cache = json.load(open(PRICE_CACHE_PATH))
            prices = cache.get("prices", {})
            if symbol in prices:
                p = prices[symbol]
                return {"price": p.get("price", 0), "change_pct": p.get("change_pct", 0)}
    except Exception:
        pass
    if FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            req = urllib.request.Request(url, headers={"User-Agent": "PredRedeploy/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("c", 0) > 0:
                pct = round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0
                return {"price": data["c"], "change_pct": pct}
        except Exception:
            pass
    return None


def get_cash_balance():
    if not SUPABASE_KEY:
        return STARTING_CAPITAL
    try:
        url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{BOT_ID}&select=cash_usd"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data:
            return float(data[0].get("cash_usd", STARTING_CAPITAL))
    except Exception:
        pass
    return STARTING_CAPITAL


def get_existing_tickers():
    """Get tickers we already hold (don't double up)."""
    if not SUPABASE_KEY:
        return set()
    try:
        url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{BOT_ID}&select=open_positions"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data and data[0].get("open_positions"):
            return {p.get("ticker") for p in data[0]["open_positions"]}
    except Exception:
        pass
    return set()


def generate_predictions():
    """Score candidates and create prediction queue."""
    existing = get_existing_tickers()
    predictions = []

    for candidate in REDEPLOY_CANDIDATES:
        ticker = candidate["ticker"]
        if ticker in existing:
            continue  # Already holding

        quote = fetch_quote(ticker)
        if not quote or quote["price"] <= 0:
            continue

        # Simple scoring: prefer dips (negative change = higher score)
        change = quote.get("change_pct", 0)
        score = 0
        if change < -1:
            score = 80 + abs(change) * 5  # Dip = high score
        elif change < 0:
            score = 60 + abs(change) * 10
        elif change < 2:
            score = 40  # Flat = medium
        else:
            score = 20  # Already ripping = low priority for redeployment

        predictions.append({
            "ticker": ticker,
            "market": candidate["market"],
            "price": quote["price"],
            "change_pct": change,
            "score": min(100, round(score)),
            "reason": candidate["reason"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=PREDICTION_EXPIRY_MINS)).isoformat(),
        })
        time.sleep(0.3)

    # Sort by score descending
    predictions.sort(key=lambda x: x["score"], reverse=True)

    with open(PREDICTIONS_PATH, "w") as f:
        json.dump(predictions, f, indent=2)

    if predictions:
        log(f"📊 Generated {len(predictions)} predictions. Top: {predictions[0]['ticker']} (score={predictions[0]['score']})")
    return predictions


def deploy_prediction():
    """Check if cash is available and deploy top prediction to watchlist."""
    cash = get_cash_balance()
    min_trade = 500  # Don't bother with tiny amounts

    if cash < min_trade:
        return

    # Load predictions
    try:
        predictions = json.load(open(PREDICTIONS_PATH)) if PREDICTIONS_PATH.exists() else []
    except Exception:
        predictions = []

    # Filter expired
    now = datetime.now(timezone.utc).isoformat()
    predictions = [p for p in predictions if p.get("expires_at", "") > now]

    if not predictions:
        return

    # Take top prediction
    top = predictions[0]
    price = top["price"]
    if price <= 0:
        return

    qty = max(1, int(min(cash * MAX_POSITION_PCT, cash * 0.5) / price))

    log(f"💰 REDEPLOYMENT: Cash ${cash:.0f} available. Deploying {top['ticker']} (score={top['score']})")

    # Inject into watchlist
    try:
        wl = json.load(open(WATCHLIST_PATH)) if WATCHLIST_PATH.exists() else {"enabled": True, "tickers": {}}
    except Exception:
        wl = {"enabled": True, "tickers": {}}

    stop_price = round(price * (1 - STOP_PCT / 100), 2)
    wl["tickers"][top["ticker"]] = {
        "action": "BUY",
        "market": top["market"],
        "criteria": {"price_below": round(price * 1.005, 2), "any": True},  # Buy near current price
        "quantity": qty,
        "stop": stop_price,
        "reason": f"[REDEPLOY] {top['reason']} | score={top['score']}",
        "_predictive_redeployment": True,
        "_expires": top["expires_at"],
    }

    with open(WATCHLIST_PATH, "w") as f:
        json.dump(wl, f, indent=2)

    log(f"📋 Injected {top['ticker']} into watchlist: {qty} units @ ~${price:.2f}, stop ${stop_price:.2f}")


def run():
    log(f"🏁 Predictive Redeployment starting — bot={BOT_ID}")
    while True:
        try:
            generate_predictions()
            deploy_prediction()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(60)


if __name__ == "__main__":
    if "--once" in sys.argv:
        generate_predictions()
    elif "--deploy" in sys.argv:
        deploy_prediction()
    else:
        run()
