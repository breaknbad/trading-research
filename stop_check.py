#!/usr/bin/env python3
"""
Fast Stop-Loss Checker — runs every 1 minute during market hours.
Checks all open positions against their 2% stop threshold.
Auto-executes SELL/COVER if stop is breached. No asking, no delay.

Usage:
  python3 stop_check.py          # Check all bots
  python3 stop_check.py --bot alfred  # Check one bot
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Retry helper for Supabase calls
def supabase_get(url, params, max_retries=3, backoff_s=2):
    """GET with retry + exponential backoff."""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r
            print(f"⚠️ Supabase GET attempt {attempt+1}/{max_retries} failed: HTTP {r.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Supabase GET attempt {attempt+1}/{max_retries} error: {e}")
        if attempt < max_retries - 1:
            time.sleep(backoff_s * (2 ** attempt))
    print(f"❌ Supabase GET failed after {max_retries} attempts")
    return None

STOP_PCT_DEFAULT = 2.0  # 2% stop-loss threshold (NORMAL/SURGE regime)
TARGET_PCT = 5.0  # 5% profit target — auto-take profits
BOTS = ["alfred", "tars", "vex", "eddie_v"]

# Glide killer: regime-adaptive stop tightening
REGIME_STOP_PCT = {
    "SURGE": 2.0,
    "NORMAL": 1.5,
    "FADING": 1.0,
    "DEAD": 0.5,
}

def get_regime_stop_pct():
    """Read volume regime and return appropriate stop %. THIS is the glide killer."""
    regime_file = "/Users/sheridanskala/.openclaw/workspace/logs/volume_regime.json"
    try:
        with open(regime_file, 'r') as f:
            regime = json.load(f)
        # Stale check: if regime data is >30 min old, use default
        from datetime import timedelta
        updated = datetime.fromisoformat(regime["updated_at"])
        if datetime.now() - updated > timedelta(minutes=30):
            return STOP_PCT_DEFAULT, "STALE"
        regime_key = regime.get("regime", "NORMAL")
        stop_pct = REGIME_STOP_PCT.get(regime_key, STOP_PCT_DEFAULT)
        if regime.get("glide_killer_active"):
            print(f"🔪 GLIDE KILLER ACTIVE — stops tightened to {stop_pct}% (regime: {regime_key})")
        return stop_pct, regime_key
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return STOP_PCT_DEFAULT, "DEFAULT"

# Price sanity gate import
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
try:
    from reentry_trigger import record_stop
    HAS_REENTRY = True
except ImportError:
    HAS_REENTRY = False

try:
    from price_sanity_gate import validate_price as sanity_check
    HAS_SANITY = True
except ImportError:
    HAS_SANITY = False

# Yahoo Finance price fetch (lightweight)
# CoinGecko ID mapping for tickers that Yahoo gets wrong
COINGECKO_IDS = {
    "SUI-USD": "sui", "RENDER-USD": "render-token", "STX-USD": "stacks",
    "INJ-USD": "injective-protocol", "TIA-USD": "celestia", "SEI-USD": "sei-network",
    "JUP-USD": "jupiter-exchange-solana", "WIF-USD": "dogwifcoin",
    "FET-USD": "artificial-superintelligence-alliance",
    "ARB-USD": "arbitrum", "OP-USD": "optimism", "NEAR-USD": "near",
    "APT-USD": "aptos", "BONK-USD": "bonk",
}


def get_price_coingecko(ticker):
    """Fallback price from CoinGecko for tickers Yahoo gets wrong."""
    cg_id = COINGECKO_IDS.get(ticker)
    if not cg_id:
        return None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            price = float(data.get(cg_id, {}).get("usd", 0))
            if price > 0:
                return price
    except Exception:
        pass
    return None


def get_price(ticker):
    """Get current price from Yahoo Finance, with CoinGecko fallback. Returns None if insane."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = float(meta.get("regularMarketPrice", 0))
            # PRICE SANITY CHECK — reject garbage prices
            if HAS_SANITY and price > 0:
                is_sane, reason = sanity_check(ticker, price)
                if not is_sane:
                    print(f"⚠️ PRICE SANITY REJECTED for {ticker}: {reason}")
                    # Try CoinGecko fallback before giving up
                    cg_price = get_price_coingecko(ticker)
                    if cg_price:
                        print(f"   ✅ CoinGecko fallback: {ticker} = ${cg_price}")
                        return cg_price
                    return None
            return price if price > 0 else None
    except Exception:
        pass
    # Yahoo failed entirely — try CoinGecko
    cg_price = get_price_coingecko(ticker)
    if cg_price:
        print(f"   ✅ CoinGecko fallback (Yahoo down): {ticker} = ${cg_price}")
        return cg_price
    return None


def check_stops(bot_id=None):
    """Check all positions for stop-loss breaches."""
    bots_to_check = [bot_id] if bot_id else BOTS
    stops_hit = []
    STOP_PCT, current_regime = get_regime_stop_pct()
    print(f"📊 Stop threshold: {STOP_PCT}% (regime: {current_regime})")

    for bot in bots_to_check:
        r = supabase_get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
            params={"bot_id": f"eq.{bot}", "select": "open_positions,cash_usd"},
        )
        if r is None or not r.json():
            continue

        positions = r.json()[0].get("open_positions", []) or []

        for pos in positions:
            ticker = pos.get("ticker", "")
            entry = float(pos.get("avg_entry", 0))
            qty = float(pos.get("quantity", 0))
            side = pos.get("side", "LONG")

            if entry <= 0 or qty <= 0:
                continue

            # Normalize bare crypto tickers → Yahoo format (BTC → BTC-USD)
            CRYPTO_BARE = {"BTC", "ETH", "SOL", "LINK", "DOGE", "SUI", "AVAX", "ADA",
                           "NEAR", "APT", "RENDER", "STX", "MATIC", "DOT", "INJ", "JUP",
                           "SEI", "TIA", "ARB", "OP", "RNDR", "FET", "WIF", "BONK"}
            yahoo_ticker = ticker
            if ticker in CRYPTO_BARE:
                yahoo_ticker = f"{ticker}-USD"
            # Strip -USD suffix from equity tickers that got tagged wrong
            EQUITY_TICKERS = {"GDX", "GLD", "XLE", "ROST", "COIN", "HOOD", "AMD",
                              "INTC", "NVDA", "TSLA", "PLTR", "MRNA", "SQQQ"}
            bare = ticker.replace("-USD", "")
            if bare in EQUITY_TICKERS and ticker.endswith("-USD"):
                yahoo_ticker = bare

            current = get_price(yahoo_ticker)
            if current is None:
                continue

            # Check if trailing stop system is managing this position
            trail_state_path = os.path.join(os.path.dirname(__file__), "..", "logs", "trailing_stop_state.json")
            trailing_stop = None
            try:
                if os.path.exists(trail_state_path):
                    with open(trail_state_path, 'r') as _tf:
                        _ts = json.load(_tf)
                    _key = f"{bot}:{ticker}:{side}"
                    if _key in _ts and _ts[_key].get("trailing_stop") is not None:
                        trailing_stop = float(_ts[_key]["trailing_stop"])
            except Exception:
                pass

            # If trailing stop is active, use IT instead of fixed 2%
            if trailing_stop is not None:
                if side == "LONG" and current <= trailing_stop:
                    drawdown_pct = STOP_PCT + 1  # force trigger
                elif side == "SHORT" and current >= trailing_stop:
                    drawdown_pct = STOP_PCT + 1
                elif side == "LONG":
                    # Positive = below trail (bad), negative = above trail (safe)
                    drawdown_pct = ((trailing_stop - current) / trailing_stop) * 100
                else:
                    # SHORT: positive = above trail (bad), negative = below trail (safe)
                    drawdown_pct = ((current - trailing_stop) / trailing_stop) * 100
                # Skip the fixed % check below — trailing stop manages this position
                if drawdown_pct < STOP_PCT:
                    continue  # trailing stop not hit, skip fixed stop check

            # Calculate drawdown based on side (fixed stop for non-trailed positions)
            if trailing_stop is None:
                if side == "LONG":
                    drawdown_pct = ((entry - current) / entry) * 100
                else:  # SHORT
                    drawdown_pct = ((current - entry) / entry) * 100

            # TARGET CHECK: 5%+ gain = take profits (20-sec rule)
            if side == "LONG":
                gain_pct = ((current - entry) / entry) * 100
            else:
                gain_pct = ((entry - current) / entry) * 100

            if gain_pct >= TARGET_PCT:
                # DISABLED 2026-03-04: Auto-profit-take disabled pending review.
                # Pyramid scaler + manual scale-outs handle profit-taking now.
                # Re-enable only after SHIL review confirms logic is correct.
                print(f"📊 TARGET REACHED (no auto-exit): {bot} {side} {ticker} — entry ${entry:.2f}, now ${current:.2f}, gain {gain_pct:.1f}%")
                continue
                action = "SELL" if side == "LONG" else "COVER"
                print(f"🎯 TARGET HIT: {bot} {side} {ticker} — entry ${entry:.2f}, now ${current:.2f}, gain {gain_pct:.1f}%")
                try:
                    from log_trade import log_trade
                    success = log_trade(
                        bot, action, ticker, qty, current,
                        f"TARGET AUTO-EXIT: {gain_pct:.1f}% gain (threshold {TARGET_PCT}%)"
                    )
                    if success:
                        print(f"   ✅ Auto-executed: {action} {qty}x {ticker} @ ${current:.2f}")
                        stops_hit.append({"bot": bot, "ticker": ticker, "action": action, "price": current, "gain": gain_pct})
                    else:
                        print(f"   ❌ Auto-execute failed for {ticker}")
                except Exception as e:
                    print(f"   ❌ Error executing target exit: {e}")
                continue  # Don't also check stop on same position

            if drawdown_pct >= STOP_PCT:
                # SAFETY GUARD (2026-03-04): Never sell a profitable position as a "stop loss"
                # This catches the inverted P&L bug that liquidated TARS's winners
                if gain_pct > 0:
                    print(f"⚠️ STOP GUARD: {bot} {side} {ticker} — drawdown calc says {drawdown_pct:.1f}% but position is PROFITABLE ({gain_pct:.1f}%). SKIPPING. Likely inverted P&L bug.")
                    continue
                action = "SELL" if side == "LONG" else "COVER"
                print(f"🚨 STOP HIT: {bot} {side} {ticker} — entry ${entry:.2f}, now ${current:.2f}, drawdown {drawdown_pct:.1f}%")

                # Auto-execute via log_trade
                # PRICE SANITY GATE (SHIL HARDENED 2026-03-04)
                from price_sanity import validate_price
                pcheck = validate_price(ticker, current, entry)
                if not pcheck['valid']:
                    print(f'   🚫 PRICE SANITY BLOCKED stop-sell: {pcheck["reason"]}')
                    continue
                try:
                    from log_trade import log_trade
                    success = log_trade(
                        bot, action, ticker, qty, current,
                        f"STOP-LOSS AUTO-EXIT: {drawdown_pct:.1f}% drawdown (threshold {STOP_PCT}%)"
                    )
                    if success:
                        print(f"   ✅ Auto-executed: {action} {qty}x {ticker} @ ${current:.2f}")
                        stops_hit.append({"bot": bot, "ticker": ticker, "action": action, "price": current, "drawdown": drawdown_pct})
                        # Register for re-entry monitoring
                        if HAS_REENTRY:
                            try:
                                record_stop(bot, ticker, side, entry, qty)
                            except Exception:
                                pass
                    else:
                        print(f"   ❌ Auto-execute failed for {ticker}")
                except Exception as e:
                    print(f"   ❌ Error executing stop: {e}")
            elif drawdown_pct >= STOP_PCT * 0.75:
                print(f"⚠️  NEAR STOP: {bot} {side} {ticker} — {drawdown_pct:.1f}% drawdown (stop at {STOP_PCT}%)")

    if not stops_hit:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"✅ {now} UTC — No stops breached across {len(bots_to_check)} bot(s)")

    # HEAT CAP CHECK: total stop exposure ≤6% of portfolio
    for bot in bots_to_check:
        check_heat_cap(bot)

    return stops_hit


def check_heat_cap(bot_id):
    """Check total portfolio heat (sum of all position risk at stop level). Cap: 6%."""
    r = supabase_get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
        params={"bot_id": f"eq.{bot_id}", "select": "open_positions,total_value_usd"},
    )
    if r is None or not r.json():
        return

    data = r.json()[0]
    positions = data.get("open_positions", []) or []
    total_value = float(data.get("total_value_usd", 25000))

    if total_value <= 0:
        return

    total_heat = 0
    for pos in positions:
        entry = float(pos.get("avg_entry", 0))
        qty = float(pos.get("quantity", 0))
        if entry <= 0 or qty <= 0:
            continue
        # Heat = position_size * stop_distance (2% default)
        position_value = qty * entry
        heat = position_value * (STOP_PCT_DEFAULT / 100)
        total_heat += heat

    heat_pct = (total_heat / total_value) * 100
    if heat_pct > 6.0:
        print(f"🔴 HEAT CAP BREACH: {bot_id} total heat {heat_pct:.1f}% (cap: 6%). Reduce positions or tighten stops.")
    elif heat_pct > 5.0:
        print(f"🟡 HEAT WARNING: {bot_id} total heat {heat_pct:.1f}% (cap: 6%). Approaching limit.")


def is_market_hours():
    """Check if within US market hours (9:30 AM - 4:00 PM ET)."""
    from datetime import timedelta
    import subprocess
    now_utc = datetime.now(timezone.utc)
    # Use system timezone (machine is in America/Indianapolis = ET)
    try:
        now_et = datetime.now()
    except Exception:
        et_offset = timezone(timedelta(hours=-5))
        now_et = now_utc.astimezone(et_offset)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    weekday = now_et.weekday()
    return weekday < 5 and market_open <= now_et <= market_close


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast stop-loss checker")
    parser.add_argument("--bot", choices=BOTS, help="Check specific bot only")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()

    # Always run — crypto is 24/7, stops must be checked around the clock.
    # Market hours check removed. Equity positions still have stops that need
    # monitoring even after hours (gap risk on next open).
    check_stops(args.bot)
