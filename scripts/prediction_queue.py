#!/usr/bin/env python3
"""
Prediction Queue — Always Have the Next Trade Ready
====================================================
Mark directive Mar 5: "Could the scan have prediction cues ready to grab?"

This is the brain that connects scanning → prediction → execution.

How it works:
1. Scans universe for candidates (pre-market movers, volume, sector momentum)
2. Scores each candidate on multiple factors (momentum, volume, correlation, freshness)
3. Maintains a ranked queue of top 5 predictions in prediction_queue.json
4. When cash frees up (trim, stop, glide kill), rapid_scanner grabs from the queue
5. Predictions auto-expire (time decay) — stale predictions get replaced

The queue is ALWAYS hot. Cash should never sit idle waiting for analysis.

Feeds INTO: watchlist.json (rapid_scanner picks up and executes)
Feeds FROM: fleet_signals table, Yahoo/Finnhub quotes, correlation map
"""

import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
QUEUE_PATH = WORKSPACE / "prediction_queue.json"
WATCHLIST_PATH = WORKSPACE / "watchlist.json"
LOG_PATH = WORKSPACE / "logs" / "prediction-queue.log"
SCAN_INTERVAL = 120  # Rebuild queue every 2 minutes

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
MAX_QUEUE_SIZE = 5           # Top 5 predictions ready at all times
PREDICTION_TTL_MIN = 30      # Predictions expire after 30 min
STARTING_CAPITAL = 50000
MAX_POSITION_PCT = 0.20      # 20% max per position
DEFAULT_STOP_PCT = 0.02      # 2% tight stop

# Scoring weights
WEIGHT_MOMENTUM = 0.30       # Current day momentum
WEIGHT_VOLUME = 0.25         # Volume vs average
WEIGHT_CONSENSUS = 0.25      # Fleet signal consensus
WEIGHT_FRESHNESS = 0.20      # How recent the signal is

# Correlation followers — when scanning, boost followers of current winners
CORRELATION_MAP = {
    "BTC-USD":  ["SOL-USD", "ETH-USD", "COIN"],
    "ETH-USD":  ["LINK-USD", "AVAX-USD", "SOL-USD"],
    "SOL-USD":  ["BTC-USD", "ETH-USD", "SUI-USD"],
    "NVDA":     ["AMD", "AVGO", "TSM"],
    "AMD":      ["NVDA", "AVGO", "TSM"],
    "AVGO":     ["NVDA", "AMD"],
    "GLD":      ["GDX", "SLV", "GDXJ"],
    "GDX":      ["GLD", "SLV"],
    "XLE":      ["OXY", "DVN"],
    "CRM":      ["NOW", "WDAY"],
    "NOW":      ["CRM", "WDAY"],
    "COIN":     ["BTC-USD", "MSTR"],
    "TTD":      ["META", "GOOGL"],
    "MRVL":     ["AVGO", "NVDA", "AMD"],
}

# Universe — tickers we actively scan for predictions
# This gets filtered down each morning to movers only
SCAN_UNIVERSE = {
    "stocks": ["NVDA", "AMD", "AVGO", "TSM", "MRVL", "CRM", "NOW", "WDAY",
               "META", "GOOGL", "AMZN", "MSFT", "AAPL", "COIN", "MSTR",
               "GLD", "GDX", "SLV", "GDXJ", "XLE", "OXY", "DVN",
               "TTD", "PLTR", "MDB", "DDOG", "NET", "CRWD", "PANW",
               "SMH", "QQQ", "SPY", "IWM"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "AVAX-USD",
               "ADA-USD", "SUI-USD", "APT-USD", "DOGE-USD", "NEAR-USD"],
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
    """Get real-time quote from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
        vol = meta.get("regularMarketVolume", 0)
        
        # Get average volume from quote summary if available
        avg_vol = vol  # Fallback
        
        if price and prev:
            return {
                "price": price,
                "prev_close": prev,
                "momentum_pct": round((price - prev) / prev * 100, 2),
                "volume": vol,
                "day_high": meta.get("regularMarketDayHigh", price),
                "day_low": meta.get("regularMarketDayLow", price),
            }
    except:
        pass
    return None


def get_fleet_signals():
    """Get recent fleet signals from Supabase for consensus scoring."""
    if not SUPABASE_KEY:
        return {}
    try:
        # Get signals from last hour
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/fleet_signals?created_at=gte.{cutoff}&select=ticker,direction,bot_id,score"
        req = urllib.request.Request(url, headers={**HEADERS, "User-Agent": "PredictionQueue/1.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        
        # Count signals per ticker
        consensus = {}
        for sig in (data or []):
            ticker = sig.get("ticker", "")
            if ticker not in consensus:
                consensus[ticker] = {"bullish": 0, "bearish": 0, "bots": set()}
            direction = sig.get("direction", "")
            if direction == "bullish":
                consensus[ticker]["bullish"] += 1
            elif direction == "bearish":
                consensus[ticker]["bearish"] += 1
            consensus[ticker]["bots"].add(sig.get("bot_id", ""))
        
        # Convert sets to counts for JSON
        for t in consensus:
            consensus[t]["bot_count"] = len(consensus[t]["bots"])
            del consensus[t]["bots"]
        
        return consensus
    except:
        return {}


def get_open_tickers():
    """Get tickers we already hold — don't predict what we already own."""
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


def score_candidate(ticker, quote, fleet_signals, is_follower_of_winner=False):
    """Score a candidate for the prediction queue (0-100)."""
    score = 0
    reasons = []
    
    momentum = abs(quote.get("momentum_pct", 0))
    direction = "BUY" if quote.get("momentum_pct", 0) > 0 else "SELL"
    
    # Momentum score (0-30)
    if momentum >= 5.0:
        score += 30
        reasons.append(f"strong momentum {quote['momentum_pct']:+.1f}%")
    elif momentum >= 3.0:
        score += 22
        reasons.append(f"good momentum {quote['momentum_pct']:+.1f}%")
    elif momentum >= 1.5:
        score += 15
        reasons.append(f"moderate momentum {quote['momentum_pct']:+.1f}%")
    elif momentum >= 0.5:
        score += 8
        reasons.append(f"slight momentum {quote['momentum_pct']:+.1f}%")
    
    # Volume score (0-25) — placeholder until we have avg volume
    vol = quote.get("volume", 0)
    if vol > 0:
        score += 12  # Base volume score — will improve with avg vol comparison
        reasons.append(f"volume {vol:,.0f}")
    
    # Consensus score (0-25)
    signals = fleet_signals.get(ticker, {})
    bot_count = signals.get("bot_count", 0)
    if bot_count >= 3:
        score += 25
        reasons.append(f"fleet consensus ({bot_count} bots)")
    elif bot_count >= 2:
        score += 18
        reasons.append(f"multi-bot signal ({bot_count} bots)")
    elif bot_count >= 1:
        score += 8
        reasons.append("single bot signal")
    
    # Freshness score (0-20) — all scans are fresh in this context
    score += 15  # Default freshness for current scan
    
    # Correlation bonus — if this is a follower of something winning
    if is_follower_of_winner:
        score += 10
        reasons.append("correlation follower of winner")
    
    return {
        "score": min(score, 100),
        "direction": direction,
        "reasons": reasons,
    }


def build_queue():
    """Scan universe, score candidates, build prediction queue."""
    log("🔄 Rebuilding prediction queue...")
    
    fleet_signals = get_fleet_signals()
    open_tickers = get_open_tickers()
    
    # Determine which tickers are "winning" for correlation boost
    winning_tickers = set()
    
    candidates = []
    all_tickers = SCAN_UNIVERSE["stocks"] + SCAN_UNIVERSE["crypto"]
    
    # First pass — get quotes and find winners
    quotes = {}
    for ticker in all_tickers:
        quote = fetch_quote(ticker)
        if quote:
            quotes[ticker] = quote
            if quote.get("momentum_pct", 0) >= 2.0:
                winning_tickers.add(ticker)
        time.sleep(0.2)  # Rate limit
    
    # Second pass — score everyone
    for ticker, quote in quotes.items():
        # Skip tickers we already hold
        if ticker in open_tickers:
            continue
        
        # Check if this ticker is a follower of a winner
        is_follower = False
        for winner in winning_tickers:
            followers = CORRELATION_MAP.get(winner, [])
            if ticker in followers:
                is_follower = True
                break
        
        result = score_candidate(ticker, quote, fleet_signals, is_follower)
        
        if result["score"] >= 20:  # Minimum threshold
            is_crypto = "-USD" in ticker
            price = quote["price"]
            
            # Calculate quantity based on 20% max position
            max_dollars = STARTING_CAPITAL * MAX_POSITION_PCT
            quantity = int(max_dollars / price) if not is_crypto else round(max_dollars / price, 4)
            if not is_crypto and quantity < 1:
                continue
            
            stop_price = round(price * (1 - DEFAULT_STOP_PCT), 2)
            target_price = round(price * 1.05, 2)  # +5% target
            
            candidates.append({
                "ticker": ticker,
                "action": result["direction"],
                "market": "CRYPTO" if is_crypto else "STOCK",
                "price": price,
                "quantity": quantity,
                "stop": stop_price,
                "target": target_price,
                "score": result["score"],
                "reasons": result["reasons"],
                "momentum_pct": quote.get("momentum_pct", 0),
                "is_follower": is_follower,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=PREDICTION_TTL_MIN)).isoformat(),
            })
    
    # Sort by score descending, take top N
    candidates.sort(key=lambda x: x["score"], reverse=True)
    queue = candidates[:MAX_QUEUE_SIZE]
    
    # Write queue
    queue_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "bot_id": BOT_ID,
        "queue_size": len(queue),
        "predictions": queue,
    }
    
    try:
        QUEUE_PATH.write_text(json.dumps(queue_data, indent=2))
    except Exception as e:
        log(f"Error writing queue: {e}")
    
    # Log results
    if queue:
        log(f"📋 Prediction queue updated — {len(queue)} candidates:")
        for i, pred in enumerate(queue, 1):
            follower_tag = " 🔗" if pred["is_follower"] else ""
            log(f"  #{i} {pred['ticker']} — score {pred['score']}, {pred['action']} @ ${pred['price']:.2f}, "
                f"stop ${pred['stop']:.2f}{follower_tag}")
            log(f"      Reasons: {', '.join(pred['reasons'])}")
    else:
        log("📋 No candidates above threshold")
    
    return queue


def inject_top_prediction():
    """Inject the #1 prediction into watchlist.json for rapid_scanner to grab."""
    if not QUEUE_PATH.exists():
        return
    
    try:
        queue_data = json.loads(QUEUE_PATH.read_text())
        predictions = queue_data.get("predictions", [])
        if not predictions:
            return
        
        top = predictions[0]
        
        # Check expiry
        expires = datetime.fromisoformat(top["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires:
            log(f"⏰ Top prediction {top['ticker']} expired — skipping injection")
            return
        
        # Load or create watchlist
        watchlist = {"enabled": True, "tickers": {}}
        if WATCHLIST_PATH.exists():
            try:
                watchlist = json.loads(WATCHLIST_PATH.read_text())
            except:
                pass
        
        # Only inject if ticker isn't already in watchlist
        if top["ticker"] not in watchlist.get("tickers", {}):
            is_buy = top["action"] == "BUY"
            watchlist.setdefault("tickers", {})[top["ticker"]] = {
                "action": top["action"],
                "market": top["market"],
                "criteria": {
                    "price_below": top["price"] * 1.001 if is_buy else None,  # Buy at or near current
                    "price_above": top["price"] * 0.999 if not is_buy else None,
                    "any": True,
                },
                "quantity": top["quantity"],
                "stop": top["stop"],
                "reason": f"[PREDICTION Q#{1}] score={top['score']} | {', '.join(top['reasons'][:2])}",
                "_from_prediction": True,
                "_expires_at": top["expires_at"],
            }
            
            WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
            log(f"💉 Injected {top['ticker']} into watchlist (score {top['score']})")
    except Exception as e:
        log(f"Injection error: {e}")


def clean_expired_predictions():
    """Remove expired prediction entries from watchlist."""
    if not WATCHLIST_PATH.exists():
        return
    try:
        watchlist = json.loads(WATCHLIST_PATH.read_text())
        tickers = watchlist.get("tickers", {})
        now = datetime.now(timezone.utc)
        
        expired = []
        for ticker, config in list(tickers.items()):
            if config.get("_from_prediction"):
                exp = config.get("_expires_at", "")
                if exp:
                    exp_time = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                    if now > exp_time:
                        expired.append(ticker)
                        del tickers[ticker]
        
        if expired:
            WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
            log(f"🧹 Cleaned {len(expired)} expired predictions: {', '.join(expired)}")
    except:
        pass


def scan_once():
    """Single pass: clean expired, rebuild queue, inject top prediction."""
    clean_expired_predictions()
    build_queue()
    inject_top_prediction()


def run():
    """Main loop."""
    log(f"🏁 Prediction Queue starting — {SCAN_INTERVAL}s interval, bot={BOT_ID}")
    while True:
        try:
            scan_once()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        scan_once()
    elif "--queue" in sys.argv:
        # Just show current queue
        if QUEUE_PATH.exists():
            data = json.loads(QUEUE_PATH.read_text())
            print(json.dumps(data, indent=2))
        else:
            print("No prediction queue exists yet")
    else:
        run()
