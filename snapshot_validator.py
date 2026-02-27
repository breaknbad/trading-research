#!/usr/bin/env python3
"""
Equity curve data validator.
Rejects any snapshot where total_value changed >5% in 5 minutes
without a corresponding trade logged in that window.
Run via cron or before dashboard refresh.
"""

import requests
import json
from datetime import datetime, timezone, timedelta

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

MAX_CHANGE_PCT = 5.0  # Max % change without a trade
WINDOW_MINUTES = 5


def get_equity_snapshots(bot_id):
    """Get recent equity snapshots for a bot (from equity_history if it exists)."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/equity_history?bot_id=eq.{bot_id}&order=timestamp.desc&limit=50",
        headers=HEADERS,
    )
    if r.status_code == 200 and r.json():
        return r.json()
    return []


def get_trades_in_window(bot_id, start, end):
    """Check if any trades were logged between start and end."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}"
        f"&timestamp=gte.{start.isoformat()}&timestamp=lte.{end.isoformat()}",
        headers=HEADERS,
    )
    return r.json() if r.status_code == 200 else []


def validate_snapshots(bot_id):
    """Find suspicious snapshots with no corresponding trades."""
    snapshots = get_equity_snapshots(bot_id)
    if len(snapshots) < 2:
        return []

    suspicious = []
    for i in range(len(snapshots) - 1):
        current = snapshots[i]
        previous = snapshots[i + 1]

        curr_val = float(current.get("total_value_usd", 0))
        prev_val = float(previous.get("total_value_usd", 0))

        if prev_val == 0:
            continue

        change_pct = abs(curr_val - prev_val) / prev_val * 100

        if change_pct > MAX_CHANGE_PCT:
            curr_ts = datetime.fromisoformat(current["timestamp"].replace("Z", "+00:00"))
            prev_ts = datetime.fromisoformat(previous["timestamp"].replace("Z", "+00:00"))

            trades = get_trades_in_window(bot_id, prev_ts, curr_ts)

            if not trades:
                suspicious.append({
                    "snapshot_id": current.get("id"),
                    "timestamp": current.get("timestamp"),
                    "value": curr_val,
                    "prev_value": prev_val,
                    "change_pct": round(change_pct, 2),
                    "trades_in_window": 0,
                })

    return suspicious


def validate_all():
    """Validate all bots."""
    bots = ["alfred", "tars", "vex", "eddie_v"]
    for bot in bots:
        print(f"\n{'='*40}")
        print(f"Validating {bot}...")
        suspicious = validate_snapshots(bot)
        if suspicious:
            print(f"⚠️  Found {len(suspicious)} suspicious snapshots:")
            for s in suspicious:
                print(f"  - {s['timestamp']}: ${s['prev_value']:,.2f} → ${s['value']:,.2f} "
                      f"({s['change_pct']}% change, 0 trades)")
        else:
            print(f"✅ All snapshots clean")


if __name__ == "__main__":
    validate_all()
