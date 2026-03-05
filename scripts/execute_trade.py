#!/usr/bin/env python3
"""execute_trade.py — Atomic trade execution CLI.

Writes to Mi AI Supabase `trades` table.
Validates price, deduplicates, rate-limits, and rolls back on failure.
On SELL: also closes the matching OPEN position.
"""

import argparse, json, os, sys, time, logging, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Setup ---
WORKSPACE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass  # Fall back to system env vars

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Run: pip3 install requests", file=sys.stderr)
    sys.exit(1)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- Price Sanity Gate ---
sys.path.insert(0, str(Path(__file__).parent))
try:
    from price_sanity_gate import validate_price as sanity_check, update_price as cache_price
    HAS_SANITY_GATE = True
except ImportError:
    HAS_SANITY_GATE = False

if not SUPABASE_URL or not SUPABASE_KEY:
    print(f"ERROR: Missing env vars. SUPABASE_URL={'set' if SUPABASE_URL else 'MISSING'}, "
          f"SUPABASE_KEY={'set' if SUPABASE_KEY else 'MISSING'}", file=sys.stderr)
    print(f"Looked for .env at: {WORKSPACE / '.env'}", file=sys.stderr)
    sys.exit(1)

HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json", "Prefer": "return=representation"}
READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

STATE_FILE = WORKSPACE / "market-state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [TRADE] %(message)s")
log = logging.getLogger("trade")


def _retry(fn, retries=3):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)


def validate_price(ticker, price):
    """Check entry within 2% of live market price."""
    if not STATE_FILE.exists():
        log.warning("market-state.json not found, skipping price validation")
        return True
    try:
        data = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Could not read market-state.json: {e}")
        return True
    tickers = data.get("tickers", {})
    key = ticker.upper()
    if key not in tickers:
        log.warning(f"{key} not in market-state.json, skipping price validation")
        return True
    live = tickers[key].get("price")
    if not live or live == 0:
        return True
    diff = abs(price - live) / live * 100
    if diff > 2:
        log.error(f"Entry {price} is {diff:.1f}% from live price {live} (max 2%)")
        return False
    return True


def check_dedup(ticker, action, bot_id):
    """No same ticker+action+bot in last 5 min. Returns False if duplicate found OR if check fails."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    r = _retry(lambda: requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?ticker=eq.{ticker.upper()}&action=eq.{action}&bot_id=eq.{bot_id}&created_at=gte.{cutoff}&select=id",
        headers=READ_HEADERS, timeout=10))
    r.raise_for_status()
    dupes = r.json()
    if dupes:
        log.error(f"Duplicate: {ticker} {action} trade by {bot_id} exists from last 5 min")
        return False
    return True


def check_rate_limit(bot_id):
    """Max 10 trades/hour per bot. Returns False if over limit OR if check fails."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = _retry(lambda: requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&created_at=gte.{cutoff}&select=id",
        headers=READ_HEADERS, timeout=10))
    r.raise_for_status()
    count = len(r.json())
    if count >= 10:
        log.error(f"Rate limit: {bot_id} has {count} trades in last hour (max 10)")
        return False
    return True


def check_position_limit(bot_id):
    """Max 10 open positions per bot. Returns False if over limit OR if check fails."""
    r = _retry(lambda: requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=id",
        headers=READ_HEADERS, timeout=10))
    r.raise_for_status()
    count = len(r.json())
    if count >= 10:
        log.error(f"Position limit: {bot_id} has {count} open positions (max 10)")
        return False
    return True


def close_matching_position(ticker, bot_id):
    """Find and close the matching OPEN position for a SELL. Returns the closed trade_id or None."""
    r = _retry(lambda: requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}&status=eq.OPEN&action=eq.BUY&order=created_at.desc&limit=1&select=id,trade_id",
        headers=READ_HEADERS, timeout=10))
    r.raise_for_status()
    rows = r.json()
    if not rows:
        log.warning(f"No OPEN BUY position found for {ticker} by {bot_id} — SELL will still record")
        return None
    open_id = rows[0]["id"]
    open_trade_id = rows[0]["trade_id"]
    _retry(lambda: requests.patch(
        f"{SUPABASE_URL}/rest/v1/trades?id=eq.{open_id}",
        headers={**HEADERS, "Prefer": "return=minimal"},
        json={"status": "CLOSED"}, timeout=10))
    log.info(f"Closed matching position: {open_trade_id} (db id: {open_id})")
    return open_trade_id


def insert_trade(args, entry_factors=None):
    now = datetime.now(timezone.utc)
    trade_id = f"{args.bot_id.upper()}-{uuid.uuid4().hex[:8]}"
    total = args.quantity * args.price

    payload = {
        "bot_id": args.bot_id,
        "trade_id": trade_id,
        "timestamp": now.isoformat(),
        "action": args.action.upper(),
        "ticker": args.ticker.upper(),
        "market": args.market.upper(),
        "quantity": args.quantity,
        "price_usd": args.price,
        "total_usd": total,
        "reason": args.reason or "",
        "status": "OPEN" if args.action.upper() == "BUY" else "CLOSED",
        "entry_factors": entry_factors,
        "factor_score": args.score,
    }

    r = _retry(lambda: requests.post(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=HEADERS, json=payload, timeout=10))
    r.raise_for_status()
    data = r.json()
    db_id = data[0]["id"] if data else None
    log.info(f"Trade inserted: {trade_id} (db id: {db_id})")
    return db_id, trade_id, total


def rollback_trade(db_id):
    if db_id:
        try:
            requests.delete(
                f"{SUPABASE_URL}/rest/v1/trades?id=eq.{db_id}",
                headers=READ_HEADERS, timeout=10)
            log.info(f"Rolled back trade {db_id}")
        except Exception as e:
            log.error(f"ROLLBACK FAILED for trade {db_id}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Execute a trade (Mi AI Supabase)")
    parser.add_argument("--ticker", required=True, help="e.g. AAPL, BTC-USD")
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "buy", "sell"])
    parser.add_argument("--quantity", required=True, type=float)
    parser.add_argument("--price", required=True, type=float, help="Entry/exit price in USD")
    parser.add_argument("--market", default="STOCK", choices=["STOCK", "CRYPTO", "stock", "crypto"])
    parser.add_argument("--bot-id", required=True, help="e.g. tars, alfred, eddie_v, vex")
    parser.add_argument("--reason", default="", help="Trade rationale")
    parser.add_argument("--factors", default=None, help="JSON string of entry factors")
    parser.add_argument("--score", default=None, type=float, help="Factor score")
    parser.add_argument("--skip-validation", action="store_true", help="Skip price/dedup/rate checks")
    args = parser.parse_args()

    # Parse factors JSON early so bad input fails before any DB writes
    entry_factors = None
    if args.factors:
        try:
            entry_factors = json.loads(args.factors)
        except json.JSONDecodeError as e:
            log.error(f"Invalid --factors JSON: {e}")
            sys.exit(1)

    # Price sanity gate — reject garbage prices BEFORE any other validation
    if HAS_SANITY_GATE:
        is_sane, reason = sanity_check(args.ticker, args.price)
        if not is_sane:
            log.error(f"PRICE SANITY REJECTED: {reason}")
            sys.exit(1)
        cache_price(args.ticker, args.price)

    # Validation (unless skipped) — failures here are HARD stops, not warnings
    if not args.skip_validation:
        try:
            if not validate_price(args.ticker, args.price):
                sys.exit(1)
            if not check_dedup(args.ticker, args.action.upper(), args.bot_id):
                sys.exit(1)
            if not check_rate_limit(args.bot_id):
                sys.exit(1)
            if args.action.upper() == "BUY" and not check_position_limit(args.bot_id):
                sys.exit(1)
        except Exception as e:
            log.error(f"Validation check failed (Supabase down?): {e}")
            log.error("Refusing to trade without safety checks. Use --skip-validation to override.")
            sys.exit(1)

    # Execute
    db_id = None
    try:
        db_id, trade_id, total = insert_trade(args, entry_factors)

        # On SELL, close the matching OPEN BUY position
        if args.action.upper() == "SELL":
            close_matching_position(args.ticker, args.bot_id)

    except Exception as e:
        log.error(f"Execution failed: {e}")
        rollback_trade(db_id)
        sys.exit(2)

    # Confirmation
    msg = (f"✅ Trade Executed: {trade_id}\n"
           f"{args.ticker.upper()} {args.action.upper()} x{args.quantity} @ ${args.price:.2f}\n"
           f"Total: ${total:,.2f} | Bot: {args.bot_id} | Market: {args.market.upper()}")
    print(msg)
    log.info("Trade complete")


if __name__ == "__main__":
    main()
