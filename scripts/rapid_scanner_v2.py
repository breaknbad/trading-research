#!/usr/bin/env python3
"""
Rapid Scanner V2 — WebSocket-Accelerated
=========================================
Upgrade #2 integration: Reads from websocket_feed.py's price cache first,
falls back to HTTP polling if cache is stale (>30s old).

Same logic as rapid_scanner.py but with sub-second price data when available.
Also integrates #6 (Multi-Bot Parallel Scanning) via --segment flag.

Usage:
  python3 rapid_scanner_v2.py                    # Full scan, all tickers
  python3 rapid_scanner_v2.py --once             # Single pass
  python3 rapid_scanner_v2.py --segment 0 --total-segments 4  # Bot segment
"""

import json, os, sys, time, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

# --- Config ---
WORKSPACE = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"
SCAN_LOG = WORKSPACE / "logs" / "rapid-scanner-v2.log"
COOLDOWN_PATH = WORKSPACE / "rapid-cooldowns.json"
SCAN_INTERVAL = 5  # Faster than v1 since we use cached prices
COOLDOWN_SECONDS = 300
MAX_POSITION_PCT = 0.20
STARTING_CAPITAL = 50000
CIRCUIT_BREAKER_PCT = -0.06
CACHE_STALE_SECONDS = 30

# API keys
FINNHUB_KEY = ""
try:
    FINNHUB_KEY = open(os.path.expanduser("~/.finnhub_key")).read().strip()
except Exception:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = ""
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
except Exception:
    pass
if not SUPABASE_KEY:
    try:
        creds_path = os.path.expanduser("~/.supabase_trading_creds")
        for line in open(creds_path):
            if line.startswith("SUPABASE_ANON_KEY="):
                SUPABASE_KEY = line.split("=", 1)[1].strip()
    except Exception:
        pass

os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(SCAN_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# --- Price Cache (from WebSocket feed) ---
def read_price_cache():
    """Read cached prices from websocket_feed.py. Returns dict or None if stale/missing."""
    try:
        if not PRICE_CACHE_PATH.exists():
            return None
        data = json.load(open(PRICE_CACHE_PATH))
        updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        if age > CACHE_STALE_SECONDS:
            return None  # Stale
        return data.get("prices", {})
    except Exception:
        return None


def get_cached_price(symbol, cache):
    """Get price from WebSocket cache."""
    if cache and symbol in cache:
        entry = cache[symbol]
        return {
            "price": entry.get("price", 0),
            "open": entry.get("open", 0),
            "high": entry.get("high", 0),
            "low": entry.get("low", 0),
            "prev_close": entry.get("prev_close", 0),
            "change_pct": entry.get("change_pct", 0),
        }
    return None


# --- HTTP Fallback (from v1) ---
def fetch_quote_http(symbol):
    if not FINNHUB_KEY:
        return None
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "RapidScannerV2/1.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        if data.get("c", 0) > 0:
            return {
                "price": data["c"], "open": data["o"], "high": data["h"],
                "low": data["l"], "prev_close": data["pc"],
                "change_pct": round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0,
            }
    except Exception as e:
        log(f"HTTP quote error {symbol}: {e}")
    return None


def fetch_quote(symbol, cache):
    """Get quote: WebSocket cache first, HTTP fallback."""
    quote = get_cached_price(symbol, cache)
    if quote and quote["price"] > 0:
        return quote
    return fetch_quote_http(symbol)


# --- Reuse v1 logic for watchlist, cooldowns, portfolio, criteria, execution ---
def load_watchlist():
    if not WATCHLIST_PATH.exists():
        return None
    try:
        data = json.load(open(WATCHLIST_PATH))
        if not data.get("enabled", True):
            return None
        return data.get("tickers", {})
    except Exception as e:
        log(f"ERROR loading watchlist: {e}")
        return None


def is_on_cooldown(ticker):
    try:
        if COOLDOWN_PATH.exists():
            cd = json.load(open(COOLDOWN_PATH))
            if ticker in cd and time.time() - cd[ticker] < COOLDOWN_SECONDS:
                return True
    except Exception:
        pass
    return False


def set_cooldown(ticker):
    try:
        cd = json.load(open(COOLDOWN_PATH)) if COOLDOWN_PATH.exists() else {}
    except Exception:
        cd = {}
    cd[ticker] = time.time()
    with open(COOLDOWN_PATH, "w") as f:
        json.dump(cd, f, indent=2)


def get_portfolio_cash():
    if not SUPABASE_KEY:
        return STARTING_CAPITAL
    try:
        url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{BOT_ID}&select=cash_balance&order=snapshot_date.desc&limit=1"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data:
            return float(data[0].get("cash_balance", STARTING_CAPITAL))
    except Exception:
        pass
    return STARTING_CAPITAL


def check_daily_pnl():
    if not SUPABASE_KEY:
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{BOT_ID}&select=total_value&order=snapshot_date.desc&limit=1"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data:
            total = float(data[0].get("total_value", STARTING_CAPITAL))
            if (total - STARTING_CAPITAL) / STARTING_CAPITAL <= CIRCUIT_BREAKER_PCT:
                log("🚨 CIRCUIT BREAKER ACTIVE")
                return True
    except Exception:
        pass
    return False


def check_criteria(ticker, config, quote):
    criteria = config.get("criteria", {})
    match_any = criteria.get("any", True)
    matches, checks = [], 0
    price = quote["price"]

    if criteria.get("price_below") is not None:
        checks += 1
        if price <= criteria["price_below"]:
            matches.append(f"price ${price:.2f} <= ${criteria['price_below']}")
    if criteria.get("price_above") is not None:
        checks += 1
        if price >= criteria["price_above"]:
            matches.append(f"price ${price:.2f} >= ${criteria['price_above']}")

    if checks == 0:
        return False, "No criteria"
    if match_any and matches:
        return True, " | ".join(matches)
    if not match_any and len(matches) == checks:
        return True, " | ".join(matches)
    return False, "No triggers"


def execute_trade(ticker, config, quote, match_reason):
    action = config.get("action", "BUY")
    market = config.get("market", "STOCK")
    quantity = config.get("quantity", 1)
    reason = config.get("reason", "Rapid scanner v2 trigger")
    price = quote["price"]

    cash = get_portfolio_cash()
    trade_value = price * quantity
    max_value = cash * MAX_POSITION_PCT
    if trade_value > max_value:
        quantity = int(max_value / price)
        if quantity < 1:
            log(f"⚠️ SKIP {ticker}: exceeds 20% cap")
            return False

    cmd = [
        sys.executable, str(WORKSPACE / "scripts" / "execute_trade.py"),
        "--ticker", ticker, "--action", action,
        "--quantity", str(quantity), "--price", f"{price:.2f}",
        "--market", market, "--bot-id", BOT_ID,
        "--reason", f"[RAPID-V2] {reason} | {match_reason}",
    ]
    log(f"🚀 EXECUTING: {action} {quantity} {ticker} @ ${price:.2f} | {match_reason}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
        if result.returncode == 0:
            log(f"✅ SUCCESS: {action} {quantity} {ticker} @ ${price:.2f}")
            set_cooldown(ticker)
            return True
        else:
            log(f"❌ FAILED: {result.stderr.strip() or result.stdout.strip()}")
    except Exception as e:
        log(f"❌ ERROR: {e}")
    return False


# --- Segment logic for #6 Multi-Bot Parallel Scanning ---
def get_segment_tickers(tickers, segment, total_segments):
    """Return only tickers belonging to this bot's segment."""
    if total_segments <= 1:
        return tickers
    sorted_tickers = sorted(tickers.keys())
    return {t: tickers[t] for i, t in enumerate(sorted_tickers) if i % total_segments == segment}


def scan_once(segment=0, total_segments=1):
    watchlist = load_watchlist()
    if not watchlist:
        return
    if check_daily_pnl():
        log("🛑 Circuit breaker — no trades")
        return

    # Apply segment filter
    watchlist = get_segment_tickers(watchlist, segment, total_segments)

    # Read WebSocket price cache once per scan
    cache = read_price_cache()
    cache_status = "WS" if cache else "HTTP"
    log(f"Scanning {len(watchlist)} tickers (source: {cache_status})")

    for ticker, config in watchlist.items():
        if ticker.startswith("_"):
            continue
        if is_on_cooldown(ticker):
            continue

        quote = fetch_quote(ticker, cache)
        if not quote:
            continue

        triggered, reason = check_criteria(ticker, config, quote)
        if triggered:
            log(f"🎯 TRIGGER: {ticker} — {reason}")
            execute_trade(ticker, config, quote, reason)
        time.sleep(0.1)  # Lighter pause since we're mostly reading cache


def run(segment=0, total_segments=1):
    log(f"🏁 Rapid Scanner V2 — {SCAN_INTERVAL}s interval, bot={BOT_ID}, segment={segment}/{total_segments}")
    while True:
        try:
            scan_once(segment, total_segments)
        except Exception as e:
            log(f"Scan error: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--segment", type=int, default=0)
    parser.add_argument("--total-segments", type=int, default=1)
    args = parser.parse_args()

    if args.once:
        scan_once(args.segment, args.total_segments)
    else:
        run(args.segment, args.total_segments)
