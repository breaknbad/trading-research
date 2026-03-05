"""
cooldown_enforcer.py — Prevents rapid re-trading on the same ticker (600s cooldown).
"""
import sys, os, json, time, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY

try:
    from config import COOLDOWN_SECONDS
except ImportError:
    COOLDOWN_SECONDS = 600

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "cooldown_state.json")
os.makedirs(CACHE_DIR, exist_ok=True)

# In-memory state: {ticker: epoch_timestamp}
_cooldowns: dict = {}


def _load_cache():
    """Load persisted cooldown state from disk."""
    global _cooldowns
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                _cooldowns = json.load(f)
        except Exception:
            _cooldowns = {}


def _save_cache():
    """Persist cooldown state to disk."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(_cooldowns, f, indent=2)
    except Exception as e:
        print(f"[COOLDOWN] Cache write failed: {e}")


def record_trade(ticker: str) -> None:
    """Record that a trade just occurred on this ticker."""
    now = time.time()
    _cooldowns[ticker] = now
    _save_cache()

    # Also log to Supabase
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/cooldown_log",
            headers=SUPABASE_HEADERS,
            json={
                "bot_id": BOT_ID,
                "ticker": ticker,
                "traded_at": datetime.now(timezone.utc).isoformat(),
            },
            timeout=5,
        )
    except Exception:
        pass  # Local cache is the source of truth

    print(f"[COOLDOWN] Recorded trade for {ticker}")


def check_cooldown(ticker: str) -> dict:
    """
    Check if a ticker is in cooldown.
    Returns {allowed: bool, seconds_remaining: int, last_trade_at: str}
    """
    last = _cooldowns.get(ticker)
    if last is None:
        return {"allowed": True, "seconds_remaining": 0, "last_trade_at": None}

    elapsed = time.time() - last
    remaining = max(0, COOLDOWN_SECONDS - elapsed)

    if remaining > 0:
        last_dt = datetime.fromtimestamp(last, tz=timezone.utc).isoformat()
        print(f"[COOLDOWN] {ticker} blocked — {remaining:.0f}s remaining")
        return {"allowed": False, "seconds_remaining": int(remaining), "last_trade_at": last_dt}

    return {
        "allowed": True,
        "seconds_remaining": 0,
        "last_trade_at": datetime.fromtimestamp(last, tz=timezone.utc).isoformat(),
    }


def cleanup_expired():
    """Remove expired cooldowns from memory and cache."""
    now = time.time()
    expired = [t for t, ts in _cooldowns.items() if now - ts > COOLDOWN_SECONDS]
    for t in expired:
        del _cooldowns[t]
    if expired:
        _save_cache()
    return expired


# Load cache on import
_load_cache()


if __name__ == "__main__":
    record_trade("SQQQ")
    print(check_cooldown("SQQQ"))
    print(check_cooldown("AAPL"))
