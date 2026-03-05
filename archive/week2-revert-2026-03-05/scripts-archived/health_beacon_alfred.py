#!/usr/bin/env python3
"""Alfred's health beacon — writes to Supabase bot_health every 5 min."""
import json, os, time, urllib.request
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc")
BOT_ID = "alfred"
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
ALERTS_FILE = os.path.join(WORKSPACE, "alerts.json")

def get_status():
    """Check if portfolio health monitor is producing fresh alerts."""
    try:
        with open(ALERTS_FILE) as f:
            data = json.load(f)
        updated = data.get("lastUpdated", "")
        if updated:
            from datetime import datetime as dt
            ts = dt.fromisoformat(updated.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > 120:
                return "degraded"
        return "alive"
    except Exception:
        return "degraded"

def get_position_count():
    try:
        with open(os.path.join(WORKSPACE, "trading-state.json")) as f:
            data = json.load(f)
        return len(data.get("positions", []))
    except Exception:
        return 0

def send_heartbeat():
    now = datetime.now(timezone.utc).isoformat()
    status = get_status()
    positions = get_position_count()
    
    payload = json.dumps({
        "bot_id": BOT_ID,
        "service": "main",
        "status": status,
        "positions_monitored": positions,
        "last_heartbeat": now
    }).encode()
    
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/bot_health?bot_id=eq.{BOT_ID}&service=eq.main",
        data=payload,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        },
        method="PATCH"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"[{now}] Heartbeat sent: status={status}, positions={positions}")
    except Exception as e:
        print(f"[{now}] Heartbeat failed: {e}")

def main():
    print(f"Health beacon started for {BOT_ID}")
    while True:
        try:
            send_heartbeat()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(300)  # 5 min

if __name__ == "__main__":
    main()
