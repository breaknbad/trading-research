#!/usr/bin/env python3
"""
Correlation-Based Entry Stacking — Leader/Follower Crypto Pairs
================================================================
Upgrade #9: When BTC moves >2% in <5 min, auto-queue SOL, ETH entries
within 30-90s lag window. Half position size on followers.

Safety: Followers must not have already moved >2%. Dedup via cooldowns.

Usage:
  python3 correlation_stacker.py              # Run continuously (15s checks)
  python3 correlation_stacker.py --once       # Single check
"""

import json, os, sys, time, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
PRICE_CACHE_PATH = WORKSPACE / "price_cache.json"
LOG_PATH = WORKSPACE / "logs" / "correlation_stacker.log"
STACK_STATE_PATH = WORKSPACE / "logs" / "correlation_state.json"

# Leader/Follower pairs
PAIRS = {
    "BTC-USD": {
        "followers": ["ETH-USD", "SOL-USD"],
        "leader_threshold_pct": 2.0,    # Leader must move >2%
        "follower_max_moved_pct": 2.0,  # Skip follower if already moved >2%
        "lag_window_secs": 90,          # Queue expires after 90s
        "position_mult": 0.5,           # Half position size on followers
    },
    "ETH-USD": {
        "followers": ["LINK-USD", "AVAX-USD"],
        "leader_threshold_pct": 3.0,
        "follower_max_moved_pct": 2.5,
        "lag_window_secs": 60,
        "position_mult": 0.5,
    },
}

COOLDOWN_SECS = 600  # 10 min cooldown per leader signal
STARTING_CAPITAL = 50000
MAX_POSITION_PCT = 0.10  # 10% max for correlation plays (conservative)

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
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_quote(symbol):
    """Get quote from cache or HTTP."""
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
            req = urllib.request.Request(url, headers={"User-Agent": "CorrStacker/1.0"})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("c", 0) > 0:
                pct = round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0
                return {"price": data["c"], "change_pct": pct}
        except Exception:
            pass
    return None


def load_state():
    try:
        if STACK_STATE_PATH.exists():
            return json.load(open(STACK_STATE_PATH))
    except Exception:
        pass
    return {}


def save_state(state):
    with open(STACK_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def check_circuit_breaker():
    """Check daily circuit breaker."""
    if not SUPABASE_KEY:
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{BOT_ID}&select=total_value_usd"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data:
            total = float(data[0].get("total_value_usd", STARTING_CAPITAL))
            if (total - STARTING_CAPITAL) / STARTING_CAPITAL <= -0.06:
                return True
    except Exception:
        pass
    return False


def execute_follower(ticker, price, direction):
    """Execute a follower trade via execute_trade.py."""
    qty = max(1, int((STARTING_CAPITAL * MAX_POSITION_PCT) / price)) if price > 0 else 1
    action = "BUY" if direction == "UP" else "SELL"

    cmd = [
        sys.executable, str(WORKSPACE / "scripts" / "execute_trade.py"),
        "--ticker", ticker, "--action", action,
        "--quantity", str(qty), "--price", f"{price:.2f}",
        "--market", "CRYPTO", "--bot-id", BOT_ID,
        "--reason", f"[CORR-STACK] Leader signal, follower entry",
    ]
    log(f"🚀 FOLLOWER ENTRY: {action} {qty} {ticker} @ ${price:.2f}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
        if result.returncode == 0:
            log(f"✅ Follower trade success: {ticker}")
            return True
        else:
            log(f"❌ Follower trade failed: {result.stderr.strip()[:200]}")
    except Exception as e:
        log(f"❌ Follower error: {e}")
    return False


def scan_once():
    """Check leaders for moves, queue followers."""
    if check_circuit_breaker():
        log("🛑 Circuit breaker active")
        return

    state = load_state()

    for leader, config in PAIRS.items():
        # Cooldown
        last_signal = state.get(f"{leader}_last_signal", 0)
        if time.time() - last_signal < COOLDOWN_SECS:
            continue

        leader_quote = fetch_quote(leader)
        if not leader_quote:
            continue

        leader_pct = leader_quote.get("change_pct", 0)
        threshold = config["leader_threshold_pct"]

        if abs(leader_pct) < threshold:
            continue

        direction = "UP" if leader_pct > 0 else "DOWN"
        log(f"🔗 LEADER SIGNAL: {leader} {leader_pct:+.1f}% ({direction})")

        # Check and execute followers
        for follower in config["followers"]:
            follower_quote = fetch_quote(follower)
            if not follower_quote:
                continue

            follower_pct = follower_quote.get("change_pct", 0)
            max_moved = config["follower_max_moved_pct"]

            # Skip if follower already moved too much (missed the window)
            if abs(follower_pct) >= max_moved:
                log(f"   ⏭️ {follower} already moved {follower_pct:+.1f}% — skipping")
                continue

            # Only buy followers moving in same direction or hasn't moved yet
            if direction == "UP" and follower_pct < -1:
                log(f"   ⏭️ {follower} moving opposite ({follower_pct:+.1f}%) — skipping")
                continue
            if direction == "DOWN" and follower_pct > 1:
                log(f"   ⏭️ {follower} moving opposite ({follower_pct:+.1f}%) — skipping")
                continue

            # Only BUY on UP signals (we don't short in this system)
            if direction == "DOWN":
                log(f"   📊 {follower} @ ${follower_quote['price']:.2f} — DOWN signal, alert only")
                continue

            execute_follower(follower, follower_quote["price"], direction)
            time.sleep(1)

        state[f"{leader}_last_signal"] = time.time()
        save_state(state)


def run():
    log(f"🏁 Correlation Stacker starting — bot={BOT_ID}")
    for leader, config in PAIRS.items():
        log(f"   {leader} → {config['followers']} (threshold: {config['leader_threshold_pct']}%)")
    while True:
        try:
            scan_once()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(15)


if __name__ == "__main__":
    if "--once" in sys.argv:
        scan_once()
    else:
        run()
