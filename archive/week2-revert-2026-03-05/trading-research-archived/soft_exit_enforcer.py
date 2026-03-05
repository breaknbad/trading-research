"""
soft_exit_enforcer.py — Monitors soft exit signals and force-closes after timeout.
"""
import sys, os, time, requests, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY

SOFT_EXIT_WINDOW = 15 * 60  # 15 minutes
GRACE_PERIOD = 5 * 60       # 5 minutes
TOTAL_TIMEOUT = SOFT_EXIT_WINDOW + GRACE_PERIOD  # 20 minutes

# In-memory tracking: {ticker: {triggered_at, exit_type, price_at_trigger}}
active_soft_exits: dict = {}


def register_soft_exit(ticker: str, exit_type: str, price: float) -> dict:
    """Register a soft exit signal for a ticker."""
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "triggered_at": now,
        "exit_type": exit_type,
        "price_at_trigger": price,
    }
    active_soft_exits[ticker] = entry

    # Log to Supabase
    _log_to_supabase(ticker, "REGISTERED", exit_type, price, f"Soft exit registered at {now}")
    print(f"[SOFT_EXIT] Registered {exit_type} for {ticker} @ ${price:.2f}")
    return entry


def check_timeouts() -> list:
    """Check all active soft exits for timeouts. Returns list of tickers needing force-close."""
    now = datetime.now(timezone.utc)
    force_close = []

    for ticker, info in list(active_soft_exits.items()):
        triggered = datetime.fromisoformat(info["triggered_at"])
        elapsed = (now - triggered).total_seconds()

        if elapsed >= TOTAL_TIMEOUT:
            force_close.append(ticker)
            _log_to_supabase(
                ticker, "FORCE_CLOSE_REQUIRED", info["exit_type"],
                info["price_at_trigger"],
                f"Position still open after {elapsed:.0f}s (limit: {TOTAL_TIMEOUT}s)"
            )
            print(f"[SOFT_EXIT] TIMEOUT: {ticker} needs force-close ({elapsed:.0f}s elapsed)")

    return force_close


def acknowledge_exit(ticker: str, action: str, reason: str) -> bool:
    """Acknowledge that a soft exit was handled. Removes from tracking."""
    info = active_soft_exits.pop(ticker, None)
    if not info:
        print(f"[SOFT_EXIT] No active soft exit for {ticker}")
        return False

    _log_to_supabase(
        ticker, action, info["exit_type"],
        info["price_at_trigger"], reason
    )
    print(f"[SOFT_EXIT] Acknowledged {ticker}: {action} — {reason}")
    return True


def get_active_exits() -> dict:
    """Return current active soft exits."""
    return dict(active_soft_exits)


def _log_to_supabase(ticker: str, action: str, exit_type: str, price: float, notes: str):
    """Log a soft exit event to Supabase."""
    payload = {
        "bot_id": BOT_ID,
        "ticker": ticker,
        "action": action,
        "exit_type": exit_type,
        "price_at_trigger": price,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/soft_exit_log",
            headers=SUPABASE_HEADERS,
            json=payload,
            timeout=5,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[SOFT_EXIT] Failed to log to Supabase: {e}")


if __name__ == "__main__":
    # Quick test
    register_soft_exit("SQQQ", "trailing_stop", 25.50)
    register_soft_exit("TQQQ", "momentum_fade", 42.10)
    print("Active:", get_active_exits())
    print("Timeouts:", check_timeouts())
