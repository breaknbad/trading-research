#!/usr/bin/env python3
"""
Earnings Reaction Sniper — Gap-Up Pullback Buyer
==================================================
Upgrade #5: Pre-load earnings calendar from Finnhub. After market open,
detect gap-ups >5% and queue watchlist entries for first pullback.

Safety: Half position size on earnings plays. 2% stop from pullback entry.

Usage:
  python3 earnings_sniper.py --once          # Check today's earnings, set up watchlist
  python3 earnings_sniper.py --date 2026-03-06  # Check specific date
  python3 earnings_sniper.py --monitor       # Run post-open monitoring for pullbacks
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
EARNINGS_LOG = WORKSPACE / "logs" / "earnings_sniper.log"
EARNINGS_CACHE = WORKSPACE / "logs" / "earnings_today.json"
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"

GAP_UP_THRESHOLD = 5.0     # Minimum gap-up % to trigger
PULLBACK_PCT = 2.0          # Buy when price pulls back this much from day high
STOP_PCT = 2.0              # 2% stop from pullback entry
TARGET_PCT = 5.0            # 5% profit target
POSITION_SIZE_MULT = 0.5    # Half position size for earnings (volatile)
MAX_POSITION_PCT = 0.10     # 10% max (half of normal 20%)
STARTING_CAPITAL = 50000

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

os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(EARNINGS_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_earnings(target_date=None):
    """Fetch earnings calendar from Finnhub for a given date."""
    if not FINNHUB_KEY:
        log("No Finnhub key — cannot fetch earnings")
        return []
    d = target_date or date.today().isoformat()
    try:
        url = f"https://finnhub.io/api/v1/calendar/earnings?from={d}&to={d}&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "EarningsSniper/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        earnings = data.get("earningsCalendar", [])
        log(f"Found {len(earnings)} earnings reports for {d}")
        return earnings
    except Exception as e:
        log(f"Earnings fetch error: {e}")
        return []


def fetch_quote(symbol):
    """Get current quote."""
    # Try price cache first
    try:
        if PRICE_CACHE_PATH.exists():
            cache = json.load(open(PRICE_CACHE_PATH))
            prices = cache.get("prices", {})
            if symbol in prices:
                return prices[symbol]
    except Exception:
        pass
    # HTTP fallback
    if FINNHUB_KEY:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
            req = urllib.request.Request(url, headers={"User-Agent": "EarningsSniper/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("c", 0) > 0:
                return {
                    "price": data["c"], "open": data["o"], "high": data["h"],
                    "low": data["l"], "prev_close": data["pc"],
                    "change_pct": round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0,
                }
        except Exception:
            pass
    return None


def scan_earnings(target_date=None):
    """Scan earnings tickers for gap-ups and set up watchlist entries."""
    earnings = fetch_earnings(target_date)
    if not earnings:
        return

    # Cache earnings for reference
    with open(EARNINGS_CACHE, "w") as f:
        json.dump({"date": target_date or date.today().isoformat(), "earnings": earnings}, f, indent=2)

    gap_ups = []
    for e in earnings:
        symbol = e.get("symbol", "")
        if not symbol:
            continue
        quote = fetch_quote(symbol)
        if not quote:
            continue

        change_pct = quote.get("change_pct", 0)
        if change_pct >= GAP_UP_THRESHOLD:
            gap_ups.append({
                "symbol": symbol,
                "price": quote["price"],
                "change_pct": change_pct,
                "high": quote.get("high", quote["price"]),
                "prev_close": quote.get("prev_close", 0),
            })
            log(f"🎯 EARNINGS GAP-UP: {symbol} +{change_pct:.1f}% @ ${quote['price']:.2f}")

        time.sleep(0.3)  # Rate limit

    if not gap_ups:
        log("No earnings gap-ups found above threshold")
        return

    # Set up watchlist entries for pullback buys
    inject_watchlist_entries(gap_ups)
    return gap_ups


def inject_watchlist_entries(gap_ups):
    """Add pullback buy entries to watchlist.json for rapid_scanner to pick up."""
    try:
        wl = json.load(open(WATCHLIST_PATH)) if WATCHLIST_PATH.exists() else {"enabled": True, "tickers": {}}
    except Exception:
        wl = {"enabled": True, "tickers": {}}

    for g in gap_ups:
        symbol = g["symbol"]
        high = g["high"]
        pullback_price = round(high * (1 - PULLBACK_PCT / 100), 2)
        stop = round(pullback_price * (1 - STOP_PCT / 100), 2)

        # Half position size for earnings volatility
        est_qty = max(1, int((STARTING_CAPITAL * MAX_POSITION_PCT) / pullback_price))

        wl["tickers"][symbol] = {
            "action": "BUY",
            "market": "STOCK",
            "criteria": {"price_below": pullback_price, "any": True},
            "quantity": est_qty,
            "stop": stop,
            "reason": f"[EARNINGS] Gap-up +{g['change_pct']:.1f}%, pullback buy @ ${pullback_price:.2f}",
            "_earnings_sniper": True,
            "_expires": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
        }
        log(f"📋 WATCHLIST: {symbol} pullback buy @ ${pullback_price:.2f}, stop ${stop:.2f}, qty {est_qty}")

    with open(WATCHLIST_PATH, "w") as f:
        json.dump(wl, f, indent=2)
    log(f"Injected {len(gap_ups)} earnings entries into watchlist")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--monitor", action="store_true")
    args = parser.parse_args()

    if args.once or args.date:
        scan_earnings(args.date)
    elif args.monitor:
        log("Monitoring mode — checking every 60s for pullback entries")
        while True:
            scan_earnings()
            time.sleep(60)
    else:
        scan_earnings()
