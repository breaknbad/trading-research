#!/usr/bin/env python3
"""
cash_deployer.py — Anti-idle-cash enforcer for Mi AI trading bots.

Checks each bot's cash percentage. If cash >50% for >30 minutes during
market hours (9:30-3:30 ET), generates an alert with the top 3 momentum
setups from the shared_signals table.

Not auto-trading — returns structured data that a bot's scanner can act on.

Usage:
  python3 cash_deployer.py                # Check all bots
  python3 cash_deployer.py --bot tars     # Check specific bot
  python3 cash_deployer.py create-table   # Create alerts table
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

from shared_signals import get_signals

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
CASH_THRESHOLD_PCT = 50
IDLE_MINUTES = 30
ALERTS_TABLE = "cash_deploy_alerts"


def is_market_hours():
    """Check if 9:30 AM - 3:30 PM ET (deployment window)."""
    now_utc = datetime.now(timezone.utc)
    et_offset = timedelta(hours=-5)  # EST (adjust for EDT as needed)
    now_et = now_utc + et_offset
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    deploy_close = now_et.replace(hour=15, minute=30, second=0, microsecond=0)
    return now_et.weekday() < 5 and market_open <= now_et <= deploy_close


def create_table():
    """Create or verify cash_deploy_alerts table."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{ALERTS_TABLE}?limit=0",
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )
    if r.status_code == 200:
        print(f"✅ {ALERTS_TABLE} table exists.")
        return True
    print(f"⚠️  Create {ALERTS_TABLE} in Supabase SQL editor:")
    print(f"""
    CREATE TABLE IF NOT EXISTS {ALERTS_TABLE} (
        id BIGSERIAL PRIMARY KEY,
        bot_id TEXT NOT NULL,
        cash_pct REAL NOT NULL,
        cash_usd REAL NOT NULL,
        suggested_tickers JSONB,
        alert_type TEXT DEFAULT 'idle_cash',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)
    return False


def get_portfolios(bot_filter=None):
    url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?select=*"
    if bot_filter:
        url += f"&bot_id=eq.{bot_filter}"
    r = requests.get(url, headers={k: v for k, v in HEADERS.items() if k != "Prefer"})
    return r.json() if r.status_code == 200 else []


def get_last_alert(bot_id: str) -> dict:
    """Get most recent alert for this bot."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{ALERTS_TABLE}?bot_id=eq.{bot_id}&order=created_at.desc&limit=1",
        headers={k: v for k, v in HEADERS.items() if k != "Prefer"},
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def check_idle_cash(bot_filter=None) -> list:
    """
    Check all bots for idle cash. Returns list of alert dicts.

    Each alert contains:
      - bot_id, cash_pct, cash_usd
      - suggested: top 3 momentum signals from shared_signals
    """
    if not is_market_hours():
        print("⏸️  Outside market hours (9:30-3:30 ET). Skipping.")
        return []

    alerts = []
    portfolios = get_portfolios(bot_filter)

    for portfolio in portfolios:
        bot_id = portfolio.get("bot_id")
        cash = float(portfolio.get("cash_usd", 0))
        total = float(portfolio.get("total_value_usd", 25000))

        if total <= 0:
            continue

        cash_pct = cash / total * 100

        if cash_pct <= CASH_THRESHOLD_PCT:
            print(f"✅ {bot_id}: {cash_pct:.0f}% cash — deployed adequately.")
            continue

        # Check if we already alerted recently (within 30 min)
        last_alert = get_last_alert(bot_id)
        if last_alert:
            alert_time = last_alert.get("created_at", "")
            try:
                at = datetime.fromisoformat(alert_time.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - at < timedelta(minutes=IDLE_MINUTES):
                    print(f"⏭️  {bot_id}: Already alerted {int((datetime.now(timezone.utc) - at).seconds/60)}m ago.")
                    continue
            except (ValueError, TypeError):
                pass

        # Get top momentum signals
        signals = get_signals(since_minutes=60)
        # Sort by conviction, take top 3
        signals.sort(key=lambda s: s.get("conviction_score", 0) or 0, reverse=True)
        top_3 = signals[:3]

        suggested = [
            {
                "ticker": s["ticker"],
                "pct_change": s["pct_change"],
                "rvol": s.get("rvol"),
                "conviction": s.get("conviction_score"),
                "source": s.get("source_bot"),
            }
            for s in top_3
        ]

        alert = {
            "bot_id": bot_id,
            "cash_pct": round(cash_pct, 1),
            "cash_usd": round(cash, 2),
            "suggested_tickers": suggested,
            "alert_type": "idle_cash",
        }

        # Log to Supabase
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{ALERTS_TABLE}",
            headers=HEADERS,
            json=alert,
        )

        emoji = "🚨" if cash_pct > 75 else "⚠️"
        print(f"{emoji} {bot_id}: {cash_pct:.0f}% CASH (${cash:,.0f} of ${total:,.0f})")
        if suggested:
            print(f"   Top signals to consider:")
            for s in suggested:
                print(f"     {s['ticker']:6s} +{s['pct_change']:.1f}%  Conv={s.get('conviction','?')}/10")
        else:
            print(f"   No shared signals available. Scanners need to post setups.")

        alerts.append(alert)

    return alerts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anti-idle-cash enforcer")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "create-table"])
    parser.add_argument("--bot", choices=BOTS)

    args = parser.parse_args()

    if args.command == "create-table":
        create_table()
    else:
        print(f"\n💰 Cash Deployer Check — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print("=" * 60)
        alerts = check_idle_cash(args.bot)
        if not alerts:
            print("All bots adequately deployed (or outside market hours).")
        print("=" * 60)
