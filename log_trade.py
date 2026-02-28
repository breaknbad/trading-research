#!/usr/bin/env python3
"""
Universal trade logger for the Mi AI trading competition.
Any bot can use this to log trades directly to Supabase.

Usage:
  python3 log_trade.py --bot tars --action BUY --ticker SPY --qty 10 --price 685.56 --reason "Macro momentum play"
  python3 log_trade.py --bot vex --action SELL --ticker EFA --qty 25 --price 87.50 --reason "Taking profits"

Actions: BUY, SELL, SHORT, COVER
Markets: US, CRYPTO, FOREX, COMMODITY, INTL (auto-detected from ticker)
"""

import argparse
import json
import uuid
import sys
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BOT_PREFIXES = {"tars": "TARS", "alfred": "ALF", "vex": "VEX", "eddie_v": "EDV"}

CRYPTO_TICKERS = {"BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "ADA-USD"}
INTL_TICKERS = {"EFA", "EWC", "EWZ", "EWJ", "FXI", "VGK", "INDA"}
COMMODITY_TICKERS = {"GLD", "SLV", "USO", "UNG", "DBA", "WEAT"}


def detect_market(ticker):
    t = ticker.upper()
    if t in CRYPTO_TICKERS or "-USD" in t:
        return "CRYPTO"
    if t in INTL_TICKERS:
        return "INTL"
    if t in COMMODITY_TICKERS:
        return "COMMODITY"
    return "US"


def check_dedup_and_rate_limit(bot_id, action, ticker):
    """
    GUARD 1: Reject same bot+ticker+action within 5 minutes (dedup).
    GUARD 2: Reject if bot has >10 trades in the last hour (rate limit).
    Returns (ok, reason) tuple.
    """
    now = datetime.now(timezone.utc)

    # Fetch recent trades for this bot (last 1 hour)
    from datetime import timedelta
    one_hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades",
            params={"bot_id": f"eq.{bot_id}", "created_at": f"gte.{one_hour_ago}", "order": "created_at.desc"},
            headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
        )
        if r.status_code != 200:
            # If we can't check, allow the trade but warn
            print(f"⚠️  Could not check dedup/rate limit: {r.status_code}")
            return True, ""
        recent = r.json()
    except Exception as e:
        print(f"⚠️  Dedup check failed: {e}")
        return True, ""

    # GUARD 1: Dedup — no same bot+ticker+action within 5 minutes
    five_min_ago = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    for trade in recent:
        if (trade.get("ticker", "").upper() == ticker.upper()
                and trade.get("action", "").upper() == action.upper()
                and trade.get("created_at", "")[:19] >= five_min_ago):
            return False, f"DEDUP BLOCKED: {bot_id} already did {action} {ticker} within 5 minutes"

    # GUARD 2: Rate limit — max 10 trades per hour per bot
    if len(recent) >= 10:
        return False, f"RATE LIMIT: {bot_id} has {len(recent)} trades in the last hour (max 10)"

    return True, ""


def log_trade(bot_id, action, ticker, qty, price, reason, market=None):
    prefix = BOT_PREFIXES.get(bot_id, bot_id.upper()[:3])
    trade_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    if market is None:
        market = detect_market(ticker)

    # GUARD: Dedup + rate limit check
    ok, block_reason = check_dedup_and_rate_limit(bot_id, action, ticker)
    if not ok:
        print(f"❌ {block_reason}")
        return False

    # Pre-validate: SELL/COVER require an existing position
    # Uses portfolio_guard for validation + adds trade-level locking via unique constraint
    if action.upper() in ("SELL", "COVER"):
        side = "LONG" if action.upper() == "SELL" else "SHORT"
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=open_positions",
            headers=HEADERS,
        )
        if r.json():
            positions_check = r.json()[0].get("open_positions", []) or []
            
            # Import guard validation
            try:
                from portfolio_guard import validate_trade
                ok, errors = validate_trade(bot_id, action.upper(), ticker.upper(), float(qty), positions_check)
                if not ok:
                    print(f"❌ GUARD REJECTED: {'; '.join(errors)}")
                    return False
            except ImportError:
                pass  # Fallback to basic check
            
            has_position = any(
                p.get("ticker") == ticker.upper()
                and p.get("side", "LONG") == side
                and float(p.get("quantity", 0)) >= float(qty) - 0.001
                for p in positions_check
            )
            if not has_position:
                print(f"❌ REJECTED: No {side} position for {ticker} with sufficient quantity. Trade not logged.")
                return False

    trade = {
        "bot_id": bot_id,
        "trade_id": trade_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action.upper(),
        "ticker": ticker.upper(),
        "market": market,
        "quantity": float(qty),
        "price_usd": float(price),
        "total_usd": float(qty) * float(price),
        "reason": reason,
        "status": "OPEN" if action.upper() in ("BUY", "SHORT") else "CLOSED",
    }

    # Insert trade
    r = requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=trade)
    if r.status_code not in (200, 201):
        print(f"ERROR logging trade: {r.status_code} {r.text}")
        return False

    # Update portfolio
    update_portfolio(bot_id, action.upper(), ticker, float(qty), float(price), market)

    print(f"✅ Logged: {bot_id} {action} {qty}x {ticker} @ ${price} (${float(qty)*float(price):.2f})")
    print(f"   Trade ID: {trade_id}")
    return True


def update_portfolio(bot_id, action, ticker, qty, price, market):
    # Fetch current portfolio
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=*",
        headers=HEADERS,
    )
    if not r.json():
        print("WARNING: No portfolio found for", bot_id)
        return

    portfolio = r.json()[0]
    positions = portfolio.get("open_positions", []) or []
    cash = float(portfolio.get("cash_usd", 0))
    trade_count = int(portfolio.get("trade_count", 0))

    if action == "BUY":
        cost = qty * price
        cash -= cost
        # Check if position exists
        found = False
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side", "LONG") == "LONG":
                old_qty = float(pos.get("quantity", 0))
                old_avg = float(pos.get("avg_entry", 0))
                new_qty = old_qty + qty
                new_avg = ((old_avg * old_qty) + (price * qty)) / new_qty
                pos["quantity"] = new_qty
                pos["avg_entry"] = round(new_avg, 4)
                pos["current_price"] = price
                found = True
                break
        if not found:
            positions.append({
                "ticker": ticker,
                "market": market,
                "quantity": qty,
                "avg_entry": price,
                "current_price": price,
                "unrealized_pl": 0,
                "side": "LONG",
            })

    elif action == "SELL":
        proceeds = qty * price
        # Validate position exists before selling
        found_pos = None
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side", "LONG") == "LONG":
                found_pos = pos
                break
        if not found_pos:
            print(f"⚠️  SELL REJECTED: No open LONG position for {ticker}. Cannot sell what you don't own.")
            return
        old_qty = float(found_pos.get("quantity", 0))
        if qty > old_qty + 0.001:
            print(f"⚠️  SELL REJECTED: Trying to sell {qty} {ticker} but only hold {old_qty}.")
            return
        cash += proceeds
        new_qty = old_qty - qty
        if new_qty <= 0.001:
            positions.remove(found_pos)
        else:
            found_pos["quantity"] = new_qty

    elif action == "SHORT":
        proceeds = qty * price
        cash += proceeds
        found = False
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side") == "SHORT":
                old_qty = float(pos.get("quantity", 0))
                old_avg = float(pos.get("avg_entry", 0))
                new_qty = old_qty + qty
                new_avg = ((old_avg * old_qty) + (price * qty)) / new_qty
                pos["quantity"] = new_qty
                pos["avg_entry"] = round(new_avg, 4)
                pos["current_price"] = price
                found = True
                break
        if not found:
            positions.append({
                "ticker": ticker,
                "market": market,
                "quantity": qty,
                "avg_entry": price,
                "current_price": price,
                "unrealized_pl": 0,
                "side": "SHORT",
            })

    elif action == "COVER":
        # Validate short position exists before covering
        found_pos = None
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side") == "SHORT":
                found_pos = pos
                break
        if not found_pos:
            print(f"⚠️  COVER REJECTED: No open SHORT position for {ticker}. Cannot cover what you haven't shorted.")
            return
        old_qty = float(found_pos.get("quantity", 0))
        if qty > old_qty + 0.001:
            print(f"⚠️  COVER REJECTED: Trying to cover {qty} {ticker} but only short {old_qty}.")
            return
        cost = qty * price
        cash -= cost
        new_qty = old_qty - qty
        if new_qty <= 0.001:
            positions.remove(found_pos)
        else:
            found_pos["quantity"] = new_qty

    # Recalculate total value: Cash + Long_value - Short_obligation
    # Cash already includes short proceeds, so we subtract the current obligation
    long_value = 0
    short_obligation = 0
    for p in positions:
        qty_val = float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
        if p.get("side") == "SHORT":
            short_obligation += qty_val
        else:
            long_value += qty_val
    total_value = cash + long_value - short_obligation

    # Portfolio guard: validate before writing
    try:
        from portfolio_guard import validate_portfolio
        ok, errors = validate_portfolio(bot_id, cash, positions, total_value)
        if not ok:
            print(f"⚠️  GUARD BLOCKED portfolio update:")
            for e in errors:
                print(f"   ❌ {e}")
            return
    except ImportError:
        pass  # Guard not available, use basic check

    # 3% spike guard: reject suspicious values
    prev_total = float(portfolio.get("total_value_usd", 25000))
    if prev_total > 0:
        change_pct = abs(total_value - prev_total) / prev_total * 100
        if change_pct > 3:
            print(f"⚠️  SPIKE GUARD: value changed {change_pct:.1f}% (${prev_total:.2f} → ${total_value:.2f}) — skipping portfolio update")
            print(f"   This is likely bad data. Investigate before retrying.")
            return

    patch = {
        "cash_usd": round(cash, 2),
        "open_positions": positions,
        "total_value_usd": round(total_value, 2),
        "trade_count": trade_count + 1,
        "total_return_pct": round(((total_value - 25000) / 25000) * 100, 2),
    }

    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}",
        headers=HEADERS,
        json=patch,
    )
    if r.status_code not in (200, 204):
        print(f"WARNING: Portfolio update failed: {r.status_code} {r.text}")
    else:
        print(f"   Portfolio: ${round(cash,2)} cash, ${round(total_value,2)} total")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Log a trade to the Mi AI dashboard")
    parser.add_argument("--bot", required=True, choices=["tars", "alfred", "vex", "eddie_v"])
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "SHORT", "COVER"])
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--qty", required=True, type=float)
    parser.add_argument("--price", required=True, type=float)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--market", choices=["US", "CRYPTO", "FOREX", "COMMODITY", "INTL"])

    args = parser.parse_args()
    log_trade(args.bot, args.action, args.ticker, args.qty, args.price, args.reason, args.market)
