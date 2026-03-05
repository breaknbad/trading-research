#!/usr/bin/env python3
"""
ATR Trailing Stop Manager — Let winners run.

Replaces fixed % scale-out with ATR-based trailing stops and partial exits.

Strategy:
  - After +1.5x ATR profit: move stop to BREAKEVEN, scale out 1/3
  - After +2.5x ATR profit: trail stop at entry + 1x ATR, scale out 1/3
  - After +4.0x ATR profit: trail stop at current - 1x ATR, let final 1/3 ride
  - Trail updates every check (stop only moves UP for longs, DOWN for shorts)

Usage:
  python3 atr_trailing_stop.py                    # Check all bots
  python3 atr_trailing_stop.py --bot alfred        # Check one bot
  python3 atr_trailing_stop.py --bot alfred --dry  # Dry run (no executions)

Designed to run every 60s via launchd alongside stop_check.py.
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add scripts dir for imports
sys.path.insert(0, str(Path(__file__).parent))

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOTS_EQUITY = ["alfred", "tars", "vex", "eddie_v"]
BOTS_CRYPTO = ["alfred_crypto", "tars_crypto", "vex_crypto", "eddie_crypto"]
ALL_BOTS = BOTS_EQUITY + BOTS_CRYPTO

# ATR scale-out tiers
TIER_1_ATR = 1.5   # Move stop to breakeven, sell 1/3
TIER_2_ATR = 2.5   # Trail stop at entry + 1x ATR, sell 1/3
TIER_3_ATR = 4.0   # Trail stop at current - 1x ATR, let final 1/3 ride

# State file for tracking trail levels per position
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "trailing_stop_state.json")

# Default ATR estimates by asset class (used when no ATR data available)
DEFAULT_ATR_PCT = {
    "BTC": 3.0, "ETH": 4.0, "SOL": 6.0, "NEAR": 8.0, "AVAX": 7.0,
    "LINK": 6.0, "AAVE": 6.0, "SUI": 8.0, "APT": 7.0, "DOGE": 7.0,
    "SQQQ": 4.0, "TQQQ": 4.0, "SPY": 1.2, "QQQ": 1.5,
    "GLD": 1.5, "SLV": 2.5, "XLE": 2.0, "GDX": 3.5,
    "_DEFAULT": 2.5,
}


def supabase_get(url, params, max_retries=3, backoff_s=2):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                return r
        except requests.exceptions.RequestException:
            pass
        if attempt < max_retries - 1:
            time.sleep(backoff_s * (2 ** attempt))
    return None


def get_price(ticker):
    """Get current price from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            meta = r.json().get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = float(meta.get("regularMarketPrice", 0))
            return price if price > 0 else None
    except Exception:
        pass
    return None


def get_atr(ticker):
    """Get ATR from market-state.json or fall back to default estimates."""
    # Try market-state.json first
    for path in [
        os.path.join(os.path.dirname(__file__), "..", "market-state.json"),
        os.path.join(os.path.dirname(__file__), "..", "trading-research", "market-state.json"),
    ]:
        try:
            if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < 600:
                with open(path, 'r') as f:
                    data = json.load(f)
                lookup = ticker.replace("-USD", "").upper()
                if "tickers" in data and lookup in data["tickers"]:
                    tech = data["tickers"][lookup].get("technicals", {})
                    if tech.get("atr"):
                        return float(tech["atr"])
        except Exception:
            pass

    # Fallback: estimate ATR from default percentages
    base = ticker.replace("-USD", "").upper()
    atr_pct = DEFAULT_ATR_PCT.get(base, DEFAULT_ATR_PCT["_DEFAULT"])
    price = get_price(ticker)
    if price and price > 0:
        return price * (atr_pct / 100)
    return None


def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def execute_partial_sell(bot_id, ticker, qty, price, reason, side="LONG"):
    """Execute a partial scale-out via log_trade."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "trading-research"))
        from log_trade import log_trade
        action = "SELL" if side == "LONG" else "COVER"
        return log_trade(bot_id, action, ticker, qty, price, reason, risk_override=True)
    except Exception as e:
        print(f"❌ Partial sell failed: {e}")
        return False


def check_trailing_stops(bot_id=None, dry_run=False):
    """Check all positions for ATR-based trailing stop management."""
    bots = [bot_id] if bot_id else ALL_BOTS
    state = load_state()
    actions_taken = []

    for bot in bots:
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

            current = get_price(ticker)
            if current is None:
                continue

            atr = get_atr(ticker)
            if atr is None or atr <= 0:
                continue

            # Calculate profit in ATR multiples
            if side == "LONG":
                profit = current - entry
            else:
                profit = entry - current
            atr_profit = profit / atr

            # State key for this position
            key = f"{bot}:{ticker}:{side}"
            pos_state = state.get(key, {
                "original_qty": qty,
                "tier_1_done": False,
                "tier_2_done": False,
                "trailing_stop": None,
                "highest_profit_atr": 0,
            })

            # Track if this is a new position (qty increased = new entry, reset state)
            if qty > pos_state.get("original_qty", 0) * 1.1:
                pos_state = {
                    "original_qty": qty,
                    "tier_1_done": False,
                    "tier_2_done": False,
                    "trailing_stop": None,
                    "highest_profit_atr": 0,
                }

            # Update high water mark
            pos_state["highest_profit_atr"] = max(pos_state.get("highest_profit_atr", 0), atr_profit)

            # --- TIER 1: +1.5x ATR → breakeven stop, sell 1/3 ---
            if atr_profit >= TIER_1_ATR and not pos_state.get("tier_1_done"):
                scale_qty = round(qty / 3, 6)
                if scale_qty > 0:
                    if side == "LONG":
                        new_stop = entry  # breakeven
                    else:
                        new_stop = entry

                    print(f"📈 TIER 1: {bot} {side} {ticker} — +{atr_profit:.1f}x ATR. Stop → breakeven (${entry:.2f}). Scaling out 1/3 ({scale_qty})")
                    if not dry_run:
                        reason = f"ATR TRAIL T1: +{atr_profit:.1f}x ATR, scaling out 1/3 at ${current:.2f}"
                        execute_partial_sell(bot, ticker, scale_qty, current, reason, side)
                    pos_state["tier_1_done"] = True
                    pos_state["trailing_stop"] = new_stop
                    actions_taken.append({"bot": bot, "ticker": ticker, "tier": 1, "action": "scale_out_33pct"})

            # --- TIER 2: +2.5x ATR → trail at entry + 1x ATR, sell 1/3 ---
            elif atr_profit >= TIER_2_ATR and not pos_state.get("tier_2_done") and pos_state.get("tier_1_done"):
                remaining = qty  # qty already reduced by tier 1
                scale_qty = round(remaining / 2, 6)  # half of remaining = 1/3 of original
                if scale_qty > 0:
                    if side == "LONG":
                        new_stop = entry + atr  # entry + 1x ATR
                    else:
                        new_stop = entry - atr

                    print(f"📈 TIER 2: {bot} {side} {ticker} — +{atr_profit:.1f}x ATR. Stop → ${new_stop:.2f} (entry + 1xATR). Scaling out 1/3 ({scale_qty})")
                    if not dry_run:
                        reason = f"ATR TRAIL T2: +{atr_profit:.1f}x ATR, scaling out 1/3 at ${current:.2f}"
                        execute_partial_sell(bot, ticker, scale_qty, current, reason, side)
                    pos_state["tier_2_done"] = True
                    pos_state["trailing_stop"] = new_stop
                    actions_taken.append({"bot": bot, "ticker": ticker, "tier": 2, "action": "scale_out_33pct"})

            # --- TIER 3+: +4x ATR → tight trail at current - 1x ATR ---
            elif atr_profit >= TIER_3_ATR and pos_state.get("tier_2_done"):
                if side == "LONG":
                    new_stop = current - atr
                else:
                    new_stop = current + atr

                old_stop = pos_state.get("trailing_stop")
                # Only move stop in favorable direction
                if side == "LONG" and (old_stop is None or new_stop > old_stop):
                    pos_state["trailing_stop"] = new_stop
                    print(f"📈 TIER 3: {bot} {side} {ticker} — +{atr_profit:.1f}x ATR. Trailing stop → ${new_stop:.2f} (current - 1xATR)")
                elif side == "SHORT" and (old_stop is None or new_stop < old_stop):
                    pos_state["trailing_stop"] = new_stop
                    print(f"📈 TIER 3: {bot} {side} {ticker} — +{atr_profit:.1f}x ATR. Trailing stop → ${new_stop:.2f} (current + 1xATR)")

            # --- CHECK TRAILING STOP HIT ---
            trail = pos_state.get("trailing_stop")
            if trail is not None:
                hit = False
                if side == "LONG" and current <= trail:
                    hit = True
                elif side == "SHORT" and current >= trail:
                    hit = True

                if hit:
                    print(f"🎯 TRAIL STOP HIT: {bot} {side} {ticker} — price ${current:.2f} hit trail ${trail:.2f}. Closing remaining position.")
                    if not dry_run:
                        reason = f"ATR TRAILING STOP: price ${current:.2f} hit trail ${trail:.2f} (+{pos_state.get('highest_profit_atr', 0):.1f}x ATR peak)"
                        execute_partial_sell(bot, ticker, qty, current, reason, side)
                    # Clear state
                    if key in state:
                        del state[key]
                    actions_taken.append({"bot": bot, "ticker": ticker, "tier": "trail_hit", "action": "close_remaining"})
                    continue

            # --- NO PROFIT ZONE: position underwater, let stop_check.py handle ---
            if atr_profit < 0:
                # Don't interfere with hard stops
                pass
            else:
                # Profitable but below tier 1 — just monitor
                if atr_profit > 0 and atr_profit < TIER_1_ATR:
                    pass  # Let it cook

            state[key] = pos_state

    save_state(state)

    if not actions_taken:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"✅ {now} UTC — No trailing stop actions across {len(bots)} bot(s)")

    return actions_taken


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATR Trailing Stop Manager")
    parser.add_argument("--bot", choices=ALL_BOTS, help="Check specific bot only")
    parser.add_argument("--dry", action="store_true", help="Dry run — no executions")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()

    # Run for crypto bots 24/7, equity bots during market hours only
    if args.bot and args.bot in BOTS_CRYPTO:
        check_trailing_stops(args.bot, args.dry)
    elif args.force:
        check_trailing_stops(args.bot, args.dry)
    else:
        # Check market hours for equity bots
        now_utc = datetime.now(timezone.utc)
        et = now_utc.astimezone(timezone(timedelta(hours=-5)))
        market_open = et.weekday() < 5 and 9 <= et.hour < 16
        if market_open or args.bot in BOTS_CRYPTO:
            check_trailing_stops(args.bot, args.dry)
        else:
            # After hours: only check crypto bots
            for bot in BOTS_CRYPTO:
                check_trailing_stops(bot, args.dry)
