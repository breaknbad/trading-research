#!/usr/bin/env python3
"""
Glide Killer — Kill idle positions, rotate into correlated followers.
=====================================================================
Mark directive Mar 5: "Idle positions should rotate to a correlation stock
or crypto. Simple and efficient place to park it with a good chance to hit
a follower."

Logic:
1. Scan open positions for "gliders" — positions that haven't moved >1% in
   either direction for 2+ hours (dead money)
2. For each glider, find its best correlated follower that HAS momentum
3. SELL the glider → BUY the follower with the same capital + tight stop
4. The follower is pre-mapped (same correlation pairs as correlation_stacker.py)

This turns dead money into live money chasing proven momentum.
"""

import json, os, sys, time, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
LOG_PATH = WORKSPACE / "logs" / "glide-killer.log"
GLIDE_STATE_PATH = WORKSPACE / "glide-state.json"

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
GLIDE_THRESHOLD_PCT = 1.0    # Position must move < 1% to be considered gliding
GLIDE_MIN_HOURS = 2          # Must be gliding for at least 2 hours
SCAN_INTERVAL = 300          # Check every 5 minutes
MOMENTUM_MIN_PCT = 1.5       # Follower must have at least 1.5% momentum to be worth rotating into
STOP_PCT = 0.02              # 2% tight stop on rotation entry

# Correlation map — same pairs used across the fleet
# Format: ticker → [followers in order of correlation strength]
CORRELATION_MAP = {
    # Crypto leaders → followers
    "BTC-USD":  ["SOL-USD", "ETH-USD", "COIN"],
    "ETH-USD":  ["LINK-USD", "AVAX-USD", "SOL-USD"],
    "SOL-USD":  ["BTC-USD", "ETH-USD", "SUI-USD"],
    # Equity leaders → followers
    "NVDA":     ["AMD", "AVGO", "TSM", "SMH"],
    "AMD":      ["NVDA", "AVGO", "TSM"],
    "AVGO":     ["NVDA", "AMD", "TSM"],
    "GLD":      ["GDX", "SLV", "GDXJ"],
    "GDX":      ["GLD", "SLV", "GDXJ"],
    "SLV":      ["GLD", "GDX"],
    "XLE":      ["OXY", "DVN", "CVX"],
    "OXY":      ["DVN", "XLE", "CVX"],
    "CRM":      ["NOW", "WDAY", "ORCL"],
    "NOW":      ["CRM", "WDAY", "ORCL"],
    "COIN":     ["BTC-USD", "MSTR"],
    "TTD":      ["META", "GOOGL"],
    "MRVL":     ["AVGO", "NVDA", "AMD"],
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


def fetch_json(url, headers=None):
    hdrs = {"User-Agent": "GlideKiller/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        log(f"Fetch error: {e}")
        return None


def get_open_positions():
    """Get all open positions from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{BOT_ID}&status=eq.OPEN&select=*"
    data = fetch_json(url, HEADERS)
    return data or []


def get_current_price(ticker):
    """Get real-time price — try WebSocket cache first, then Yahoo."""
    # Check WebSocket cache
    cache_path = WORKSPACE / "price_cache.json"
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
            if ticker in cache:
                entry = cache[ticker]
                age = time.time() - entry.get("timestamp", 0)
                if age < 30:  # Fresh enough
                    return entry.get("price")
        except:
            pass

    # Yahoo fallback
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
        return meta.get("regularMarketPrice", 0)
    except:
        return None


def detect_gliders(positions):
    """Find positions that are gliding — not moving, dead money."""
    gliders = []
    
    # Load previous glide state to track duration
    glide_state = {}
    if GLIDE_STATE_PATH.exists():
        try:
            glide_state = json.loads(GLIDE_STATE_PATH.read_text())
        except:
            pass
    
    now = time.time()
    
    for pos in positions:
        ticker = pos.get("ticker", "")
        entry_price = float(pos.get("price_usd", 0) or pos.get("entry_price", 0) or 0)
        if not ticker or entry_price <= 0:
            continue
        
        current_price = get_current_price(ticker)
        if not current_price:
            continue
        
        # Calculate movement from entry
        move_pct = abs((current_price - entry_price) / entry_price * 100)
        
        if move_pct < GLIDE_THRESHOLD_PCT:
            # Position is gliding — track how long
            if ticker not in glide_state:
                glide_state[ticker] = {"start": now, "entry_price": entry_price}
            
            glide_hours = (now - glide_state[ticker]["start"]) / 3600
            
            if glide_hours >= GLIDE_MIN_HOURS:
                gliders.append({
                    "ticker": ticker,
                    "entry_price": entry_price,
                    "current_price": current_price,
                    "move_pct": round(move_pct, 2),
                    "glide_hours": round(glide_hours, 1),
                    "quantity": pos.get("quantity", 0),
                    "market": pos.get("market", "STOCK"),
                    "trade_id": pos.get("id", ""),
                })
                log(f"🐌 GLIDER: {ticker} — only {move_pct:.1f}% move in {glide_hours:.1f}h")
        else:
            # Not gliding — remove from tracking
            glide_state.pop(ticker, None)
    
    # Save state
    try:
        GLIDE_STATE_PATH.write_text(json.dumps(glide_state, indent=2))
    except:
        pass
    
    return gliders


def find_best_follower(ticker):
    """Find the best correlated follower with momentum."""
    followers = CORRELATION_MAP.get(ticker, [])
    if not followers:
        log(f"  No correlation map for {ticker}")
        return None
    
    best = None
    best_momentum = 0
    
    for follower in followers:
        price = get_current_price(follower)
        if not price:
            continue
        
        # Get previous close for momentum calc
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{follower}?interval=1d&range=2d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            prev_close = meta.get("previousClose", 0) or meta.get("chartPreviousClose", 0)
            if prev_close:
                momentum = (price - prev_close) / prev_close * 100
                if momentum >= MOMENTUM_MIN_PCT and momentum > best_momentum:
                    is_crypto = "-USD" in follower
                    best = {
                        "ticker": follower,
                        "price": price,
                        "momentum_pct": round(momentum, 2),
                        "market": "CRYPTO" if is_crypto else "STOCK",
                    }
                    best_momentum = momentum
        except:
            continue
        
        time.sleep(0.3)  # Rate limit
    
    return best


def execute_rotation(glider, follower):
    """Sell the glider, buy the follower."""
    execute_script = str(WORKSPACE / "scripts" / "execute_trade.py")
    
    # Step 1: SELL the glider
    sell_cmd = [
        sys.executable, execute_script,
        "--ticker", glider["ticker"],
        "--action", "SELL",
        "--quantity", str(glider["quantity"]),
        "--price", f"{glider['current_price']:.2f}",
        "--market", glider["market"],
        "--bot-id", BOT_ID,
        "--reason", f"[GLIDE KILLER] Idle {glider['glide_hours']:.1f}h, rotating to {follower['ticker']} ({follower['momentum_pct']:+.1f}%)"
    ]
    
    log(f"📤 SELLING glider: {glider['quantity']} {glider['ticker']} @ ${glider['current_price']:.2f}")
    try:
        result = subprocess.run(sell_cmd, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
        if result.returncode != 0:
            log(f"❌ Sell failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        log(f"❌ Sell error: {e}")
        return False
    
    # Step 2: BUY the follower with freed capital
    freed_capital = glider["current_price"] * glider["quantity"]
    follower_qty = int(freed_capital / follower["price"])
    if follower_qty < 1:
        log(f"⚠️ Can't afford even 1 share of {follower['ticker']} @ ${follower['price']:.2f}")
        return False
    
    stop_price = round(follower["price"] * (1 - STOP_PCT), 2)
    
    buy_cmd = [
        sys.executable, execute_script,
        "--ticker", follower["ticker"],
        "--action", "BUY",
        "--quantity", str(follower_qty),
        "--price", f"{follower['price']:.2f}",
        "--market", follower["market"],
        "--bot-id", BOT_ID,
        "--reason", f"[GLIDE KILLER] Rotation from {glider['ticker']} → follower with {follower['momentum_pct']:+.1f}% momentum. Stop: ${stop_price}"
    ]
    
    log(f"📥 BUYING follower: {follower_qty} {follower['ticker']} @ ${follower['price']:.2f} (stop ${stop_price})")
    try:
        result = subprocess.run(buy_cmd, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
        if result.returncode == 0:
            log(f"✅ ROTATION COMPLETE: {glider['ticker']} → {follower['ticker']}")
            return True
        else:
            log(f"❌ Buy failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        log(f"❌ Buy error: {e}")
        return False


def scan_once(dry_run=False):
    """Single scan for gliders and rotate."""
    positions = get_open_positions()
    if not positions:
        log("No open positions")
        return
    
    log(f"Scanning {len(positions)} positions for gliders...")
    gliders = detect_gliders(positions)
    
    if not gliders:
        log("No gliders detected — all positions active")
        return
    
    log(f"Found {len(gliders)} glider(s)")
    
    for glider in gliders:
        follower = find_best_follower(glider["ticker"])
        if follower:
            log(f"🎯 Best follower for {glider['ticker']}: {follower['ticker']} ({follower['momentum_pct']:+.1f}%)")
            if dry_run:
                log(f"  [DRY RUN] Would rotate {glider['ticker']} → {follower['ticker']}")
            else:
                execute_rotation(glider, follower)
        else:
            log(f"  No follower with {MOMENTUM_MIN_PCT}%+ momentum for {glider['ticker']} — holding")
        
        time.sleep(1)


def run():
    """Main loop."""
    log(f"🏁 Glide Killer starting — {SCAN_INTERVAL}s interval, bot={BOT_ID}")
    while True:
        try:
            scan_once()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        scan_once(dry_run="--dry-run" in sys.argv)
    elif "--dry-run" in sys.argv:
        scan_once(dry_run=True)
    else:
        run()
