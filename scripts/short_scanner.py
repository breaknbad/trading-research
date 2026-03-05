#!/usr/bin/env python3
"""
Short Scanner — Find and Score Short Setups
=============================================
Mark directive Mar 5: "Build it and make sure it is in the prediction queue."

Scans for SHORT criteria — the inverse of our long scanner:
- RSI overbought (>70)
- Price at/near resistance
- Volume declining (distribution)
- Sector weakness (leader breaking down → short weakest follower)
- Bearish momentum (already falling, catch the continuation)

Outputs to prediction_queue.json alongside long candidates.
Shorts use: 3-4% stops (wider than longs), half position size.

Key insight: "The weakest follower falls hardest."
When BTC drops 3%, don't short BTC — short DOGE (highest beta, weakest hands).
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
QUEUE_PATH = WORKSPACE / "prediction_queue.json"
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
LOG_PATH = WORKSPACE / "logs" / "short-scanner.log"
SCAN_INTERVAL = 120  # Every 2 min, same as prediction queue

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = ""
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
except:
    pass
if not SUPABASE_KEY:
    creds_path = os.path.expanduser("~/.supabase_trading_creds")
    if os.path.exists(creds_path):
        for line in open(creds_path):
            if line.startswith("SUPABASE_ANON_KEY="):
                SUPABASE_KEY = line.split("=", 1)[1].strip()

HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

os.makedirs(WORKSPACE / "logs", exist_ok=True)

# --- Config ---
STARTING_CAPITAL = 50000
SHORT_POSITION_PCT = 0.10    # 10% max per short (HALF of long's 20%)
SHORT_STOP_PCT = 0.035       # 3.5% stop on shorts (wider than long's 2%)
SHORT_TARGET_PCT = 0.05      # 5% profit target

# Weakness map — when leader drops, short the WEAKEST follower
# Ordered by beta/weakness (first = weakest = best short target)
WEAKNESS_MAP = {
    "BTC-USD":  ["DOGE-USD", "SUI-USD", "APT-USD", "SOL-USD"],   # Memes/alts drop hardest
    "ETH-USD":  ["LINK-USD", "AVAX-USD", "ADA-USD"],
    "SOL-USD":  ["SUI-USD", "APT-USD", "NEAR-USD"],
    "NVDA":     ["SMH", "AMD", "MRVL"],                           # Semis sympathy
    "QQQ":      ["PLTR", "TTD", "NET", "DDOG"],                   # High-beta tech
    "SPY":      ["IWM", "QQQ"],                                    # Small caps drop harder
    "GLD":      ["GDXJ", "GDX", "SLV"],                           # Junior miners = leveraged gold
    "XLE":      ["OXY", "DVN"],                                    # Smaller E&P = more volatile
}

# Short universe — tickers we evaluate for short setups
SHORT_UNIVERSE = {
    "stocks": ["SQQQ", "SMH", "PLTR", "TTD", "NET", "DDOG", "CRWD", "PANW",
               "IWM", "COIN", "MSTR", "MRVL", "AMD", "NVDA"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "ADA-USD",
               "AVAX-USD", "LINK-USD", "SUI-USD", "APT-USD", "NEAR-USD"],
}


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def fetch_quote(symbol):
    """Get real-time quote + intraday data from Yahoo."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=5d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read())
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        vol = meta.get("regularMarketVolume", 0)
        high = meta.get("regularMarketDayHigh", price)
        low = meta.get("regularMarketDayLow", price)

        # Extract daily closes for RSI calculation
        timestamps = result.get("timestamp", [])
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in (quotes.get("close") or []) if c is not None]
        volumes = [v for v in (quotes.get("volume") or []) if v is not None]

        if price and prev:
            return {
                "price": price,
                "prev_close": prev,
                "change_pct": round((price - prev) / prev * 100, 2),
                "volume": vol,
                "day_high": high,
                "day_low": low,
                "closes": closes[-100:] if closes else [],     # Last 100 for RSI
                "volumes": volumes[-50:] if volumes else [],   # Last 50 for volume trend
            }
    except Exception as e:
        log(f"Quote error {symbol}: {e}")
    return None


def calc_rsi(closes, period=14):
    """Calculate RSI from close prices."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def detect_volume_decline(volumes):
    """Check if volume is declining (distribution signal)."""
    if len(volumes) < 10:
        return False, 0
    recent = sum(volumes[-5:]) / 5
    earlier = sum(volumes[-10:-5]) / 5
    if earlier == 0:
        return False, 0
    ratio = recent / earlier
    return ratio < 0.7, round(ratio, 2)  # 30%+ decline = distribution


def detect_resistance_rejection(price, day_high, prev_close):
    """Check if price got rejected from highs (bearish)."""
    if not day_high or not prev_close or day_high <= 0:
        return False, 0
    # Price ran up but gave back most gains = rejection
    day_range = day_high - min(price, prev_close)
    if day_range <= 0:
        return False, 0
    giveback = (day_high - price) / day_range
    return giveback > 0.6, round(giveback, 2)  # Gave back 60%+ of day's range


def score_short(ticker, quote, leaders_dropping):
    """Score a short candidate (0-100)."""
    score = 0
    reasons = []
    price = quote["price"]
    change = quote["change_pct"]

    # 1. Already falling = momentum short (0-25)
    if change <= -5.0:
        score += 25
        reasons.append(f"strong downtrend {change:+.1f}%")
    elif change <= -3.0:
        score += 20
        reasons.append(f"falling {change:+.1f}%")
    elif change <= -1.5:
        score += 12
        reasons.append(f"weakening {change:+.1f}%")

    # 2. RSI overbought = mean reversion short (0-20)
    rsi = calc_rsi(quote.get("closes", []))
    if rsi is not None:
        if rsi > 80:
            score += 20
            reasons.append(f"RSI overbought {rsi}")
        elif rsi > 70:
            score += 12
            reasons.append(f"RSI elevated {rsi}")

    # 3. Volume declining = distribution (0-15)
    declining, vol_ratio = detect_volume_decline(quote.get("volumes", []))
    if declining:
        score += 15
        reasons.append(f"volume declining ({vol_ratio}x)")

    # 4. Resistance rejection (0-15)
    rejected, giveback = detect_resistance_rejection(
        price, quote.get("day_high", 0), quote.get("prev_close", 0))
    if rejected:
        score += 15
        reasons.append(f"resistance rejection ({giveback:.0%} giveback)")

    # 5. Weakness follower bonus — leader is dropping, this is the weakest follower (0-25)
    is_weak_follower = False
    for leader, followers in WEAKNESS_MAP.items():
        if leader in leaders_dropping and ticker in followers:
            # Bonus based on position in weakness list (first = weakest = highest bonus)
            position = followers.index(ticker)
            bonus = max(25 - (position * 5), 10)
            score += bonus
            is_weak_follower = True
            reasons.append(f"weak follower of {leader} (rank #{position+1})")
            break

    return {
        "score": min(score, 100),
        "reasons": reasons,
        "rsi": rsi,
        "is_weak_follower": is_weak_follower,
    }


def find_dropping_leaders():
    """Find which leaders are dropping >2% — triggers weakness follower shorts."""
    leaders = list(WEAKNESS_MAP.keys())
    dropping = set()
    for leader in leaders:
        quote = fetch_quote(leader)
        if quote and quote.get("change_pct", 0) <= -2.0:
            dropping.add(leader)
            log(f"📉 Leader dropping: {leader} ({quote['change_pct']:+.1f}%)")
        time.sleep(0.2)
    return dropping


def get_open_tickers():
    """Get tickers we already hold."""
    if not SUPABASE_KEY:
        return set()
    try:
        url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{BOT_ID}&status=eq.OPEN&select=ticker"
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        return {d["ticker"] for d in (data or [])}
    except:
        return set()


def scan_shorts():
    """Scan universe for short setups, return scored candidates."""
    log("🔻 Scanning for short setups...")

    leaders_dropping = find_dropping_leaders()
    open_tickers = get_open_tickers()

    all_tickers = SHORT_UNIVERSE["stocks"] + SHORT_UNIVERSE["crypto"]
    candidates = []

    for ticker in all_tickers:
        if ticker in open_tickers:
            continue

        quote = fetch_quote(ticker)
        if not quote:
            continue

        result = score_short(ticker, quote, leaders_dropping)

        if result["score"] >= 25:  # Minimum threshold for shorts (higher bar than longs)
            is_crypto = "-USD" in ticker
            price = quote["price"]

            # Half position size for shorts
            max_dollars = STARTING_CAPITAL * SHORT_POSITION_PCT
            quantity = int(max_dollars / price) if not is_crypto else round(max_dollars / price, 4)
            if not is_crypto and quantity < 1:
                continue

            stop_price = round(price * (1 + SHORT_STOP_PCT), 2)   # Stop ABOVE for shorts
            target_price = round(price * (1 - SHORT_TARGET_PCT), 2)  # Target BELOW

            candidates.append({
                "ticker": ticker,
                "action": "SELL",
                "market": "CRYPTO" if is_crypto else "STOCK",
                "price": price,
                "quantity": quantity,
                "stop": stop_price,
                "target": target_price,
                "score": result["score"],
                "reasons": result["reasons"],
                "momentum_pct": quote.get("change_pct", 0),
                "rsi": result.get("rsi"),
                "is_follower": result.get("is_weak_follower", False),
                "side": "SHORT",
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            })

        time.sleep(0.3)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:5]  # Top 5 short candidates


def merge_into_prediction_queue(short_candidates):
    """Merge short candidates into the prediction queue alongside longs."""
    queue_data = {"updated_at": "", "bot_id": BOT_ID, "queue_size": 0, "predictions": []}

    if QUEUE_PATH.exists():
        try:
            queue_data = json.loads(QUEUE_PATH.read_text())
        except:
            pass

    # Remove old short entries
    longs = [p for p in queue_data.get("predictions", []) if p.get("side") != "SHORT"]

    # Combine longs + shorts, sort by score, keep top 7 (5 + 2 short slots)
    combined = longs + short_candidates
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Keep top 7 but ensure at least 2 short slots if available
    shorts_in = [c for c in combined if c.get("side") == "SHORT"]
    longs_in = [c for c in combined if c.get("side") != "SHORT"]

    # Take top 5 longs + top 2 shorts (7 total max)
    final = longs_in[:5] + shorts_in[:2]
    final.sort(key=lambda x: x.get("score", 0), reverse=True)

    queue_data["predictions"] = final
    queue_data["queue_size"] = len(final)
    queue_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    QUEUE_PATH.write_text(json.dumps(queue_data, indent=2))

    short_count = len([f for f in final if f.get("side") == "SHORT"])
    log(f"📋 Queue updated: {len(final)} total ({short_count} shorts)")


def inject_best_short_to_watchlist(candidates):
    """If top short scores high enough, inject into watchlist."""
    if not candidates:
        return

    top = candidates[0]
    if top["score"] < 40:  # Need higher conviction for auto-short
        return

    watchlist = {"enabled": True, "tickers": {}}
    if WATCHLIST_PATH.exists():
        try:
            watchlist = json.loads(WATCHLIST_PATH.read_text())
        except:
            pass

    ticker = top["ticker"]
    if ticker not in watchlist.get("tickers", {}):
        watchlist.setdefault("tickers", {})[ticker] = {
            "action": "SELL",
            "market": top["market"],
            "criteria": {
                "price_above": top["price"] * 0.999,  # Short at or near current
                "price_below": None,
                "any": True,
            },
            "quantity": top["quantity"],
            "stop": top["stop"],
            "reason": f"[SHORT SCANNER] score={top['score']} | {', '.join(top['reasons'][:2])}",
            "_from_prediction": True,
            "_expires_at": top["expires_at"],
            "_side": "SHORT",
        }
        WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
        log(f"💉 Injected SHORT {ticker} into watchlist (score {top['score']})")


def scan_once():
    """Single scan pass."""
    candidates = scan_shorts()
    if candidates:
        log(f"🔻 Found {len(candidates)} short candidates:")
        for i, c in enumerate(candidates, 1):
            follower_tag = " 🔗" if c["is_follower"] else ""
            log(f"  #{i} SHORT {c['ticker']} — score {c['score']}, @ ${c['price']:.2f}, "
                f"stop ${c['stop']:.2f}{follower_tag}")
            log(f"      Reasons: {', '.join(c['reasons'])}")

        merge_into_prediction_queue(candidates)
        inject_best_short_to_watchlist(candidates)
    else:
        log("🔻 No short setups above threshold")


def run():
    """Main loop."""
    log(f"🏁 Short Scanner starting — {SCAN_INTERVAL}s interval, bot={BOT_ID}")
    while True:
        try:
            scan_once()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        scan_once()
    else:
        run()
