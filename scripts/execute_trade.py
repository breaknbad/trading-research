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

if not SUPABASE_URL or not SUPABASE_KEY:
    print(f"ERROR: Missing env vars. SUPABASE_URL={'set' if SUPABASE_URL else 'MISSING'}, "
          f"SUPABASE_KEY={'set' if SUPABASE_KEY else 'MISSING'}", file=sys.stderr)
    print(f"Looked for .env at: {WORKSPACE / '.env'}", file=sys.stderr)
    sys.exit(1)

HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json", "Prefer": "return=representation"}
READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

STATE_FILE = WORKSPACE / "market-state.json"

# Import price sanity gate
sys.path.insert(0, str(Path(__file__).parent))
try:
    from price_sanity_gate import validate_price as sanity_check, update_price as cache_price
    HAS_SANITY_GATE = True
except ImportError:
    HAS_SANITY_GATE = False

# Import trade journal
try:
    from trade_journal import add_entry as journal_entry, check_ticker as journal_check
    HAS_JOURNAL = True
except ImportError:
    HAS_JOURNAL = False

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


def check_position_value_limit(bot_id, ticker, quantity, price):
    """Max 20% of portfolio in any single position. Returns False if would exceed."""
    try:
        # Get snapshot for total portfolio value
        parent = bot_id.replace("_crypto", "") if bot_id.endswith("_crypto") else bot_id
        r = _retry(lambda: requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{parent}&select=total_value_usd",
            headers=READ_HEADERS, timeout=10))
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return True  # No snapshot = can't check, allow trade
        total_value = rows[0].get("total_value_usd", 50000)
        if total_value <= 0:
            total_value = 50000  # Fallback to starting capital
        
        trade_value = quantity * price
        max_value = total_value * 0.20  # 20% limit
        
        # Also check existing position in same ticker
        r2 = _retry(lambda: requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker}&status=eq.OPEN&select=quantity,price_usd",
            headers=READ_HEADERS, timeout=10))
        existing_value = 0
        if r2.ok:
            for t in r2.json():
                existing_value += t["quantity"] * t["price_usd"]
        
        total_position = existing_value + trade_value
        if total_position > max_value:
            log.warning(f"Position value limit: {ticker} would be ${total_position:,.0f} ({total_position/total_value*100:.1f}% of ${total_value:,.0f}). Max 20% = ${max_value:,.0f}")
            return False
        return True
    except Exception as e:
        log.warning(f"Position value check failed: {e} — allowing trade")
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

    # Use parent bot_id for trades table (dashboard reads by bot_id)
    # No more _crypto suffix — lane is tracked via market field
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
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "SHORT", "COVER", "buy", "sell", "short", "cover"])
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

    # PRICE SANITY GATE — runs even with --skip-validation (non-negotiable)
    if HAS_SANITY_GATE:
        is_sane, reason = sanity_check(args.ticker, args.price)
        if not is_sane:
            log.error(f"PRICE SANITY REJECTED: {reason}")
            sys.exit(1)
        else:
            log.info(f"Price sanity: {reason}")
            # Update cache with this price (it passed sanity)
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
            if args.action.upper() == "BUY" and not check_position_value_limit(args.bot_id, args.ticker, args.quantity, args.price):
                log.error("Trade exceeds 20% position value limit. Use --skip-validation to override.")
                sys.exit(1)
        except Exception as e:
            log.error(f"Validation check failed (Supabase down?): {e}")
            log.error("Refusing to trade without safety checks. Use --skip-validation to override.")
            sys.exit(1)

    # Trade journal — log thesis on BUY, check for failed theses on re-entry
    if HAS_JOURNAL and args.action.upper() == "BUY":
        try:
            journal_entry(args.ticker, args.bot_id, args.reason or "No thesis provided", args.price)
        except Exception as e:
            log.warning(f"Trade journal entry failed (non-blocking): {e}")

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

    # Update portfolio snapshot — deduct/add cash for the PARENT bot_id
    # alfred_crypto trades should update alfred's snapshot, etc.
    PARENT_BOT = {
        "alfred_crypto": "alfred",
        "tars_crypto": "tars",
        "vex_crypto": "vex",
        "eddie_crypto": "eddie_v",
    }
    snapshot_bot = PARENT_BOT.get(args.bot_id, args.bot_id)
    try:
        snap_url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{snapshot_bot}&select=cash_usd,open_positions,trade_count,total_value_usd"
        snap_r = requests.get(snap_url, headers=HEADERS)
        if snap_r.status_code == 200 and snap_r.json():
            snap = snap_r.json()[0]
            cash = float(snap.get("cash_usd", 0))
            positions = snap.get("open_positions", []) or []
            trade_count = int(snap.get("trade_count", 0))

            action = args.action.upper()
            if action == "BUY":
                cash -= total
                # Add or update LONG position
                found = False
                for p in positions:
                    if p.get("ticker") == args.ticker.upper() and p.get("side", "LONG") == "LONG":
                        old_qty = float(p.get("quantity", 0))
                        old_entry = float(p.get("avg_entry", args.price))
                        new_qty = old_qty + args.quantity
                        p["avg_entry"] = round((old_entry * old_qty + args.price * args.quantity) / new_qty, 4)
                        p["quantity"] = new_qty
                        p["current_price"] = args.price
                        found = True
                        break
                if not found:
                    positions.append({
                        "ticker": args.ticker.upper(),
                        "side": "LONG",
                        "quantity": args.quantity,
                        "avg_entry": args.price,
                        "current_price": args.price,
                        "market": args.market.upper(),
                        "unrealized_pl": 0,
                    })
            elif action == "SELL":
                cash += total
                positions = [p for p in positions if p.get("ticker") != args.ticker.upper() or p.get("side") == "SHORT"]
            elif action == "SHORT":
                # Short sale: receive cash proceeds, create SHORT liability
                cash += total
                found = False
                for p in positions:
                    if p.get("ticker") == args.ticker.upper() and p.get("side") == "SHORT":
                        old_qty = float(p.get("quantity", 0))
                        old_entry = float(p.get("avg_entry", args.price))
                        new_qty = old_qty + args.quantity
                        p["avg_entry"] = round((old_entry * old_qty + args.price * args.quantity) / new_qty, 4)
                        p["quantity"] = new_qty
                        p["current_price"] = args.price
                        found = True
                        break
                if not found:
                    positions.append({
                        "ticker": args.ticker.upper(),
                        "side": "SHORT",
                        "quantity": args.quantity,
                        "avg_entry": args.price,
                        "current_price": args.price,
                        "market": args.market.upper(),
                        "unrealized_pl": 0,
                    })
            elif action == "COVER":
                # Cover short: pay cash to buy back, remove SHORT position
                cash -= total
                positions = [p for p in positions if p.get("ticker") != args.ticker.upper() or p.get("side") != "SHORT"]

            # Calculate total value: cash + longs - short liabilities
            long_val = sum(
                float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
                for p in positions if p.get("side", "LONG") == "LONG"
            )
            short_val = sum(
                float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
                for p in positions if p.get("side") == "SHORT"
            )
            total_value = cash + long_val - short_val

            patch = {
                "cash_usd": round(cash, 2),
                "open_positions": positions,
                "total_value_usd": round(total_value, 2),
                "trade_count": trade_count + 1,
                "total_return_pct": round(((total_value - 50000) / 50000) * 100, 2),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            patch_r = requests.patch(
                f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{snapshot_bot}",
                headers=HEADERS,
                json=patch,
            )
            if patch_r.status_code in (200, 204):
                log.info(f"Portfolio snapshot updated: ${round(cash,2)} cash, ${round(total_value,2)} total")
            else:
                log.warning(f"Portfolio snapshot update failed: {patch_r.status_code} {patch_r.text}")
    except Exception as e:
        log.warning(f"Portfolio snapshot update failed (non-blocking): {e}")

    # Confirmation
    msg = (f"✅ Trade Executed: {trade_id}\n"
           f"{args.ticker.upper()} {args.action.upper()} x{args.quantity} @ ${args.price:.2f}\n"
           f"Total: ${total:,.2f} | Bot: {args.bot_id} | Market: {args.market.upper()}")
    print(msg)
    log.info("Trade complete")


if __name__ == "__main__":
    main()
