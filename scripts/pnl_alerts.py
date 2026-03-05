#!/usr/bin/env python3
"""
Position P&L Alert System — Offense screams too.

Alerts at +3%, +5%, +8% profit with "trail or add?" prompt.
Also alerts approaching stop (-1.5%) with "review thesis" warning.

Runs every 60s. Writes alerts to logs/pnl_alerts.json for fleet consumption.
Posts to Discord via webhook if configured.

Usage:
  python3 pnl_alerts.py              # Check all bots
  python3 pnl_alerts.py --bot alfred  # One bot
"""

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

ALL_BOTS = ["alfred", "tars", "vex", "eddie_v", "alfred_crypto", "tars_crypto", "vex_crypto", "eddie_crypto"]
ALERT_THRESHOLDS = [3.0, 5.0, 8.0]  # profit % triggers
STOP_WARNING_PCT = -1.5  # warn when approaching stop
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "pnl_alerts_state.json")
ALERTS_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "pnl_alerts.json")


def get_price(ticker):
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


def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"alerted": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def check_pnl(bot_id=None, auto_scale=False):
    bots = [bot_id] if bot_id else ALL_BOTS
    state = load_state()
    alerts = []

    for bot in bots:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
                params={"bot_id": f"eq.{bot}", "select": "open_positions"},
                headers=HEADERS, timeout=10
            )
            if r.status_code != 200 or not r.json():
                continue
        except Exception:
            continue

        positions = r.json()[0].get("open_positions", []) or []
        for pos in positions:
            ticker = pos.get("ticker", "")
            entry = float(pos.get("avg_entry", 0))
            side = pos.get("side", "LONG")
            if entry <= 0:
                continue

            current = get_price(ticker)
            if current is None:
                continue

            if side == "LONG":
                pnl_pct = ((current - entry) / entry) * 100
            else:
                pnl_pct = ((entry - current) / entry) * 100

            key = f"{bot}:{ticker}:{side}"

            # Check profit thresholds
            for threshold in ALERT_THRESHOLDS:
                alert_key = f"{key}:{threshold}"
                if pnl_pct >= threshold and alert_key not in state["alerted"]:
                    action = "🚀 TRAIL OR ADD?" if threshold >= 5 else "📈 Trail or add?"
                    alert = {
                        "bot": bot, "ticker": ticker, "side": side,
                        "pnl_pct": round(pnl_pct, 2), "threshold": threshold,
                        "entry": entry, "current": current,
                        "quantity": float(pos.get("quantity", 0)),
                        "message": f"{action} {bot} {side} {ticker}: +{pnl_pct:.1f}% (entry ${entry:.2f} → ${current:.2f})",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    alerts.append(alert)
                    state["alerted"][alert_key] = datetime.now(timezone.utc).isoformat()
                    print(alert["message"])
                    
                    # AUTO-SCALE execution at thresholds
                    if auto_scale:
                        qty = float(pos.get("quantity", 0))
                        if threshold >= 8.0 and qty > 0:
                            sell_qty = round(qty * 0.50, 6)  # 50% at +8%
                            sell_action = "SELL" if side == "LONG" else "COVER"
                            print(f"  🔪 AUTO-SCALE: {sell_action} {sell_qty}x {ticker} @ ${current:.2f} (+{pnl_pct:.1f}%)")
                            try:
                                from log_trade import log_trade
                                log_trade(bot, sell_action, ticker, sell_qty, current,
                                    f"AUTO-SCALE +{threshold}%: trim 50% at +{pnl_pct:.1f}%")
                            except Exception as e:
                                print(f"  ❌ Auto-scale failed: {e}")
                        elif threshold >= 5.0 and qty > 0:
                            sell_qty = round(qty * 0.25, 6)  # 25% at +5%
                            sell_action = "SELL" if side == "LONG" else "COVER"
                            print(f"  🔪 AUTO-SCALE: {sell_action} {sell_qty}x {ticker} @ ${current:.2f} (+{pnl_pct:.1f}%)")
                            try:
                                from log_trade import log_trade
                                log_trade(bot, sell_action, ticker, sell_qty, current,
                                    f"AUTO-SCALE +{threshold}%: trim 25% at +{pnl_pct:.1f}%")
                            except Exception as e:
                                print(f"  ❌ Auto-scale failed: {e}")

            # Check stop warning
            warn_key = f"{key}:stop_warn"
            if pnl_pct <= STOP_WARNING_PCT and warn_key not in state["alerted"]:
                alert = {
                    "bot": bot, "ticker": ticker, "side": side,
                    "pnl_pct": round(pnl_pct, 2), "threshold": STOP_WARNING_PCT,
                    "message": f"⚠️ APPROACHING STOP: {bot} {side} {ticker} at {pnl_pct:.1f}% — review thesis",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                alerts.append(alert)
                state["alerted"][warn_key] = datetime.now(timezone.utc).isoformat()
                print(alert["message"])

    save_state(state)

    # Write alerts file for fleet consumption
    if alerts:
        os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
        with open(ALERTS_FILE, 'w') as f:
            json.dump(alerts, f, indent=2)

    if not alerts:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"✅ {now} UTC — No new P&L alerts")

    return alerts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", help="Check specific bot")
    parser.add_argument("--reset", action="store_true", help="Reset alert state")
    parser.add_argument("--auto-scale", action="store_true", help="Auto-execute scale-outs at +5% (25%) and +8% (50%)")
    args = parser.parse_args()
    if args.reset:
        save_state({"alerted": {}})
        print("✅ Alert state reset")
    else:
        # Add log_trade to path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'trading-research'))
        check_pnl(args.bot, auto_scale=args.auto_scale)
