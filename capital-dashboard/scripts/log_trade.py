# CALLED BY: CLI — every trade execution by all bots. Imports pre_trade_checker.
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

BOT_PREFIXES = {"tars": "TARS", "alfred": "ALF", "vex": "VEX", "eddie_v": "EDV", "tars_crypto": "TCR", "alfred_crypto": "ACR", "vex_crypto": "VCR", "eddie_crypto": "ECR"}

CRYPTO_TICKERS = {"BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "ADA-USD"}
INTL_TICKERS = {"EFA", "EWC", "EWZ", "EWJ", "FXI", "VGK", "INDA"}
COMMODITY_TICKERS = {"GLD", "SLV", "USO", "UNG", "DBA", "WEAT"}


def fetch_atr_min_stop(ticker, multiplier=1.5):
    """Calculate minimum stop distance based on ATR. Returns (atr, min_distance, price) or (None,None,None)."""
    import urllib.request
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        result = data["chart"]["result"][0]
        q = result["indicators"]["quote"][0]
        highs, lows, closes = q["high"], q["low"], q["close"]
        trs = []
        for i in range(1, len(closes)):
            if highs[i] is None or lows[i] is None or closes[i] is None or closes[i-1] is None:
                continue
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        atr = sum(trs[-14:]) / min(len(trs), 14) if trs else 0
        price = next(c for c in reversed(closes) if c is not None)
        return atr, atr * multiplier, price
    except Exception as e:
        print(f"WARNING: Could not fetch ATR for {ticker}: {e}")
        return None, None, None


def fetch_live_price(ticker):
    """Fetch live price from Yahoo Finance. Returns (price, prev_close) or (None, None)."""
    import urllib.request
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1m"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            meta = data["chart"]["result"][0]["meta"]
            return meta["regularMarketPrice"], meta.get("chartPreviousClose", meta.get("previousClose", 0))
    except Exception as e:
        print(f"WARNING: Could not fetch live price for {ticker}: {e}")
        return None, None


def validate_price(ticker, entered_price, tolerance=0.05):
    """Validate entered price is within tolerance of live Yahoo Finance price.
    Returns (is_valid, live_price, pct_diff)."""
    live_price, _ = fetch_live_price(ticker)
    if live_price is None:
        return True, None, 0  # Can't validate, allow trade with warning
    pct_diff = abs(entered_price - live_price) / live_price
    return pct_diff <= tolerance, live_price, pct_diff * 100


def detect_market(ticker):
    t = ticker.upper()
    if t in CRYPTO_TICKERS or "-USD" in t:
        return "CRYPTO"
    if t in INTL_TICKERS:
        return "INTL"
    if t in COMMODITY_TICKERS:
        return "COMMODITY"
    return "US"


def check_dedup(bot_id, action, ticker, window_minutes=3):
    """Reject duplicate trade: same bot+ticker+action within window_minutes.
    Returns True if duplicate found (trade should be REJECTED)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
    url = (f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}"
           f"&action=eq.{action.upper()}&timestamp=gte.{cutoff}&select=id,timestamp&limit=1")
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200 and r.json():
        recent = r.json()[0]
        print(f"❌ DEDUP REJECTED: {bot_id} {action} {ticker} — duplicate within {window_minutes}min (id:{recent['id']})")
        return True
    return False


def check_rate_limit(bot_id, max_per_hour=25):
    """Reject if bot has exceeded max trades per hour.
    Returns True if rate limit hit (trade should be REJECTED).
    Raised from 10→25 per DA Round 2 consensus (cap RISK not ACTIVITY)."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    url = (f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}"
           f"&timestamp=gte.{cutoff}&select=id&limit={max_per_hour + 1}")
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        count = len(r.json())
        if count >= max_per_hour:
            print(f"❌ RATE LIMIT: {bot_id} has {count} trades in last hour (max {max_per_hour})")
            return True
    return False


def check_max_open_positions(bot_id, action, ticker, max_open=5):
    """Reject if bot already has max_open OPEN positions on this ticker+action side.
    Prevents position stacking / scout loop bug. Returns True if should REJECT.
    Raised from 3→5 per DA Round 2 (allows scale-in). Crypto: no limit."""
    if action.upper() not in ("BUY", "SHORT"):
        return False  # Only gate entries, not exits
    url = (f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}"
           f"&action=eq.{action.upper()}&status=eq.OPEN&select=id&limit={max_open + 1}")
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        count = len(r.json())
        if count >= max_open:
            print(f"❌ POSITION CAP: {bot_id} already has {count} OPEN {action} {ticker} (max {max_open})")
            return True
    return False


def check_position_exists(bot_id, action, ticker, qty):
    """CRITICAL GUARD: Verify you actually own what you're selling/covering.
    Rebuilds net position from full trade history (source of truth).
    Returns True if trade should be REJECTED."""
    if action.upper() not in ("SELL", "COVER"):
        return False  # Only gate exits

    # Rebuild net position from Week 2 trades only (OPEN status = source of truth)
    url = (f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}"
           f"&status=eq.OPEN&select=action,quantity&order=timestamp.asc")
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"⚠️  WARNING: Could not verify position for {ticker} — allowing trade")
        return False

    net_qty = 0
    for t in r.json():
        if t['action'] in ('BUY', 'COVER'):
            net_qty += float(t['quantity'])
        elif t['action'] in ('SELL', 'SHORT'):
            net_qty -= float(t['quantity'])

    if action.upper() == "SELL":
        # Must have positive (long) position >= qty
        if net_qty < qty:
            print(f"❌ POSITION CHECK FAILED: {bot_id} trying to SELL {qty} {ticker} but only owns {max(0, net_qty)}")
            print(f"   Net position: {net_qty} (positive=long, negative=short)")
            return True
    elif action.upper() == "COVER":
        # Must have negative (short) position with abs >= qty
        if net_qty > -qty:
            print(f"❌ POSITION CHECK FAILED: {bot_id} trying to COVER {qty} {ticker} but only short {max(0, abs(min(0, net_qty)))}")
            print(f"   Net position: {net_qty} (positive=long, negative=short)")
            return True

    return False


def check_cash_sufficient(bot_id, action, qty, price):
    """Verify bot has enough cash for BUY/COVER trades.
    Rebuilds cash from full trade history.
    Returns True if trade should be REJECTED."""
    if action.upper() not in ("BUY", "COVER"):
        return False

    cost = float(qty) * float(price)

    # Rebuild cash from OPEN positions only (Week 2 fresh start)
    url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=action,total_usd&order=id.asc"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"⚠️  WARNING: Could not verify cash for {bot_id} — allowing trade")
        return False

    # Simple model: cash = portfolio_snapshots.cash_usd (written by price_streamer)
    snap_url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=cash_usd"
    snap_r = requests.get(snap_url, headers=HEADERS)
    if snap_r.status_code == 200 and snap_r.json():
        cash = float(snap_r.json()[0].get('cash_usd', 0))
    else:
        # Fallback: $50K minus OPEN buy cost
        cash = 50000.0
        for t in r.json():
            if t['action'] in ('BUY', 'COVER'):
                cash -= float(t['total_usd'])

    if cost > cash:
        print(f"❌ INSUFFICIENT CASH: {bot_id} needs ${cost:.2f} but has ${cash:.2f}")
        return True

    return False


def log_trade(bot_id, action, ticker, qty, price, reason, market=None, lane=None):
    # CRITICAL: Position existence check — can't sell what you don't own
    if check_position_exists(bot_id, action, ticker, float(qty)):
        return False

    # Cash check — temporarily relaxed due to Week 2 accounting reset issues
    # TODO: Fix cash tracking pipeline properly
    if check_cash_sufficient(bot_id, action, float(qty), float(price)):
        print("⚠️  Cash check failed but proceeding (Week 2 accounting reset)")
        # return False  # Temporarily bypassed

    # Dedup guard: reject same bot+ticker+action within 5 min
    if check_dedup(bot_id, action, ticker):
        return False

    # Rate limit: max 10 trades per hour per bot (prevents runaway scouts)
    if check_rate_limit(bot_id):
        return False

    # Position stacking guard: 5 for equities, 10 for crypto (effectively no limit)
    is_crypto_ticker = ticker.endswith("-USD") or market == "crypto"
    pos_limit = 10 if is_crypto_ticker else 5
    if check_max_open_positions(bot_id, action, ticker, max_open=pos_limit):
        return False

    prefix = BOT_PREFIXES.get(bot_id, bot_id.upper()[:3])
    trade_id = f"{prefix}-{uuid.uuid4().hex[:8]}"
    if market is None:
        market = detect_market(ticker)

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

    # Add lane tag to reason field (Supabase trades table doesn't have a lane column yet)
    if lane:
        trade["reason"] = f"[{lane.upper()}] {trade['reason']}"

    # Insert trade
    r = requests.post(f"{SUPABASE_URL}/rest/v1/trades", headers=HEADERS, json=trade)
    if r.status_code not in (200, 201):
        print(f"ERROR logging trade: {r.status_code} {r.text}")
        return False

    # Auto-close matching BUY trades when SELL is logged (prevents double-counting)
    if action.upper() == "SELL":
        close_r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}&action=eq.BUY&status=eq.OPEN&select=id,quantity&order=timestamp.asc",
            headers=HEADERS,
        )
        if close_r.status_code == 200 and close_r.json():
            remaining_qty = float(qty)
            for open_buy in close_r.json():
                if remaining_qty <= 0:
                    break
                buy_qty = float(open_buy.get('quantity', 0))
                if buy_qty <= remaining_qty:
                    # Close entire BUY record
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/trades?id=eq.{open_buy['id']}",
                        headers=HEADERS,
                        json={"status": "CLOSED"},
                    )
                    remaining_qty -= buy_qty
                    print(f"   ↳ Auto-closed BUY {ticker.upper()} (id:{open_buy['id']}, qty:{buy_qty})")
                else:
                    # Partial close — reduce BUY quantity, keep it OPEN with remaining
                    new_qty = buy_qty - remaining_qty
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/trades?id=eq.{open_buy['id']}",
                        headers=HEADERS,
                        json={"quantity": new_qty},
                    )
                    print(f"   ↳ Partial close BUY {ticker.upper()} (id:{open_buy['id']}, {buy_qty}→{new_qty})")
                    remaining_qty = 0
    elif action.upper() == "COVER":
        close_r = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker.upper()}&action=eq.SHORT&status=eq.OPEN&select=id,quantity&order=timestamp.asc",
            headers=HEADERS,
        )
        if close_r.status_code == 200 and close_r.json():
            remaining_qty = float(qty)
            for open_short in close_r.json():
                if remaining_qty <= 0:
                    break
                short_qty = float(open_short.get('quantity', 0))
                if short_qty <= remaining_qty:
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/trades?id=eq.{open_short['id']}",
                        headers=HEADERS,
                        json={"status": "CLOSED"},
                    )
                    remaining_qty -= short_qty
                    print(f"   ↳ Auto-closed SHORT {ticker.upper()} (id:{open_short['id']}, qty:{short_qty})")
                else:
                    new_qty = short_qty - remaining_qty
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/trades?id=eq.{open_short['id']}",
                        headers=HEADERS,
                        json={"quantity": new_qty},
                    )
                    print(f"   ↳ Partial close SHORT {ticker.upper()} (id:{open_short['id']}, {short_qty}→{new_qty})")
                    remaining_qty = 0

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

    if action in ("BUY",):
        cost = qty * price
        cash -= cost
        # Check if position exists
        found = False
        for pos in positions:
            if pos.get("ticker") == ticker:
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

    elif action in ("SELL",):
        proceeds = qty * price
        cash += proceeds
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side", "LONG") == "LONG":
                old_qty = float(pos.get("quantity", 0))
                new_qty = old_qty - qty
                if new_qty <= 0:
                    positions.remove(pos)
                else:
                    pos["quantity"] = new_qty
                break

    elif action in ("SHORT",):
        # Short sale: receive cash, create SHORT position (liability)
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

    elif action in ("COVER",):
        # Cover short: pay cash to buy back shares, remove SHORT position
        cost = qty * price
        cash -= cost
        for pos in positions:
            if pos.get("ticker") == ticker and pos.get("side") == "SHORT":
                old_qty = float(pos.get("quantity", 0))
                new_qty = old_qty - qty
                if new_qty <= 0:
                    positions.remove(pos)
                else:
                    pos["quantity"] = new_qty
                break

    # Recalculate total value: Cash + Long Market Value - Short Market Value
    long_value = sum(
        float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
        for p in positions if p.get("side", "LONG") == "LONG"
    )
    short_value = sum(
        float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
        for p in positions if p.get("side") == "SHORT"
    )
    total_value = cash + long_value - short_value

    patch = {
        "cash_usd": round(cash, 2),
        "open_positions": positions,
        "total_value_usd": round(total_value, 2),
        "trade_count": trade_count + 1,
        "total_return_pct": round(((total_value - 50000) / 50000) * 100, 2),
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
    parser.add_argument("--bot", required=True, choices=["tars", "alfred", "vex", "eddie_v", "tars_crypto", "alfred_crypto", "vex_crypto", "eddie_crypto"])
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "SHORT", "COVER"])
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--qty", required=True, type=float)
    parser.add_argument("--price", required=True, type=float)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--market", choices=["US", "CRYPTO", "FOREX", "COMMODITY", "INTL"])
    parser.add_argument("--score", type=float, help="Factor score from pre_trade_checker (0-10)")
    parser.add_argument("--score-profile", choices=["MOMENTUM", "ROTATION"], help="Factor profile used")
    parser.add_argument("--stop", type=float, help="Stop-loss price (validated against ATR minimum)")
    parser.add_argument("--skip-validation", action="store_true", help="Skip price validation")
    parser.add_argument("--lane", choices=["macro", "cross_asset", "regime", "rates", "commodities", "crypto_macro",
                                           "mean_reversion", "oversold_bounce", "hedge", "outlier",
                                           "earnings", "congressional", "geopolitical", "catalyst", "news_sentiment",
                                           "breakout", "velocity", "rotation", "day_trade", "crypto_momentum"],
                        help="Strategy lane tag for lane attribution tracking")

    args = parser.parse_args()

    # Pre-trade gate: cooldown + dead signal check (BUY/SHORT only)
    if args.action in ("BUY", "SHORT") and not args.skip_validation:
        # --- REGIME GATE: check volume regime entry lockout ---
        try:
            import os
            regime_paths = [
                os.path.expanduser("~/.openclaw/workspace/capital-dashboard/scripts/volume_state.json"),
                os.path.expanduser("~/workspace/capital-dashboard/scripts/volume_state.json"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "volume_state.json"),
            ]
            regime_data = None
            for rp in regime_paths:
                if os.path.exists(rp):
                    with open(rp) as rf:
                        regime_data = json.load(rf)
                    break
            
            if regime_data and regime_data.get("last_regime"):
                regime_str = regime_data["last_regime"]
                # Determine team: crypto tickers vs equity
                is_crypto = args.ticker.endswith("-USD") or args.market == "crypto"
                
                if "DEAD" in regime_str:
                    print(f"❌ REGIME LOCKOUT: Volume regime is {regime_str} — NO new entries allowed")
                    print(f"   Wait for volume to return. Use --skip-validation to override.")
                    sys.exit(1)
                elif "FADING" in regime_str:
                    # FADING = SCOUT only, half size. Warn but allow.
                    print(f"⚠️  REGIME WARNING: Volume is {regime_str} — SCOUT ONLY, half size recommended")
                    print(f"   Proceeding, but consider reducing quantity by 50%.")
                
                # Check cascade from stop_history
                try:
                    with open("/tmp/stop_history.json", "r") as sf:
                        stop_hist = json.load(sf)
                    from datetime import timezone, timedelta
                    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
                    cutoff_str = cutoff.isoformat()
                    recent_stops = sum(1 for ts_list in stop_hist.values() for ts in ts_list if ts > cutoff_str)
                    if recent_stops >= 3:
                        print(f"❌ CASCADE HALT: {recent_stops} stops in last 30 min — ALL entries blocked")
                        print(f"   Circuit breaker active. Wait for regime change.")
                        sys.exit(1)
                except (FileNotFoundError, json.JSONDecodeError):
                    pass  # No stop history yet — that's fine
        except Exception as e:
            pass  # Regime check failed — don't block trade for infra issues

        # --- COOLDOWN + DEAD SIGNAL GATES ---
        try:
            from pre_trade_checker import check_cooldown, check_signal_dead
            cool_ok, cool_reason = check_cooldown(args.ticker, args.bot)
            if not cool_ok:
                print(f"❌ BLOCKED: {cool_reason}")
                sys.exit(1)
            sig_ok, sig_reason = check_signal_dead(args.ticker)
            if not sig_ok:
                print(f"❌ BLOCKED: {sig_reason}")
                sys.exit(1)
        except ImportError:
            pass  # pre_trade_checker not available on this machine

    # ATR stop validation (BUY/SHORT only, when --stop provided)
    if args.stop and args.action in ("BUY", "SHORT") and not args.skip_validation:
        atr, min_dist, _ = fetch_atr_min_stop(args.ticker)
        if atr is not None and min_dist is not None:
            if args.action == "BUY":
                actual_dist = args.price - args.stop
            else:  # SHORT
                actual_dist = args.stop - args.price
            if actual_dist < min_dist:
                print(f"⚠️  ATR WARNING: {args.ticker} stop distance ${actual_dist:.2f} is below 1.5x ATR minimum ${min_dist:.2f}")
                print(f"   ATR(14): ${atr:.2f} | Your stop: ${args.stop:.2f} | Min stop: ${args.price - min_dist:.2f}" if args.action == "BUY" else f"   ATR(14): ${atr:.2f} | Your stop: ${args.stop:.2f} | Min stop: ${args.price + min_dist:.2f}")
                print(f"   Trade allowed but stop may get hit by noise. Consider widening.")

    # Price validation
    if not args.skip_validation:
        is_valid, live_price, pct_diff = validate_price(args.ticker, args.price)
        if live_price is not None:
            if not is_valid:
                print(f"❌ REJECTED: {args.ticker} entered @ ${args.price:.2f} but Yahoo Finance shows ${live_price:.2f} ({pct_diff:.1f}% off)")
                print(f"   Use --skip-validation to override, or fix your price.")
                sys.exit(1)
            elif pct_diff > 2:
                print(f"⚠️  WARNING: {args.ticker} entered @ ${args.price:.2f}, Yahoo shows ${live_price:.2f} ({pct_diff:.1f}% off)")

    # MANDATORY FACTOR GATE: Auto-score if no --score provided (BUY/SHORT only)
    if args.action in ("BUY", "SHORT") and args.score is None and not args.skip_validation:
        try:
            from pre_trade_checker import score_trade
            result = score_trade(args.ticker, args.action, args.bot)
            args.score = result["score"]
            args.score_profile = result.get("tier", "")
            if not result["go"]:
                print(f"❌ FACTOR GATE REJECTED: {args.ticker} scored {result['score']}/10 ({result['tier']})")
                print(f"   Minimum required: 2/10. Use --skip-validation to override.")
                sys.exit(1)
            else:
                print(f"✅ Factor score: {result['score']}/10 ({result['tier']}) — {result['sizing']}")
        except ImportError:
            pass  # pre_trade_checker not available
        except Exception as e:
            print(f"⚠️ Factor check failed ({e}) — proceeding with trade")

    # Build reason with factor score if provided
    reason = args.reason
    if args.score is not None:
        score_info = f" [Score: {args.score}/10"
        if args.score_profile:
            score_info += f" ({args.score_profile})"
        score_info += "]"
        reason += score_info

    log_trade(args.bot, args.action, args.ticker, args.qty, args.price, reason, args.market, getattr(args, 'lane', None))

    # Record stop-loss hits for cooldown tracking
    if args.action == "SELL" and "stop" in reason.lower():
        try:
            from pre_trade_checker import record_stop
            record_stop(args.ticker, args.bot)
            print(f"📝 Stop recorded for cooldown tracking: {args.ticker}")
        except ImportError:
            pass
