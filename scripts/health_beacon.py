#!/usr/bin/env python3
"""health_beacon.py — Bot health heartbeat (run every 60s)."""

import json, os, sys, time, logging
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
load_dotenv(WORKSPACE / ".env")
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json"}

STATE_FILE = WORKSPACE / "market-state.json"
BOT_ID = "TARS"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [HEALTH] %(message)s")
log = logging.getLogger("health")

def _retry(fn, retries=3):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)

def check_watcher_freshness():
    if not STATE_FILE.exists():
        return "degraded"
    try:
        data = json.loads(STATE_FILE.read_text())
        updated = datetime.fromisoformat(data["updated"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - updated).total_seconds()
        if age > 90:
            log.warning(f"market-state.json is {age:.0f}s old — stale")
            return "degraded"
    except Exception as e:
        log.error(f"Error reading market-state.json: {e}")
        return "degraded"
    return "alive"

def send_heartbeat():
    status = check_watcher_freshness()
    now = datetime.now(timezone.utc).isoformat()
    payload = {"bot_id": BOT_ID, "status": status, "last_heartbeat": now}

    def _do():
        # PATCH existing row
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/bot_health?bot_id=eq.{BOT_ID}&service=eq.main",
            headers=HEADERS, json={"status": status, "last_heartbeat": now},
            timeout=10)
        if r.status_code == 404 or (r.status_code == 200 and r.text == '[]'):
            # No row yet, insert
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/bot_health",
                headers=HEADERS, json=payload, timeout=10)
        r.raise_for_status()
        return r

    try:
        _retry(_do)
        log.info(f"Heartbeat sent: status={status}")
    except Exception as e:
        log.error(f"Heartbeat failed: {e}")

def main():
    send_heartbeat()

if __name__ == "__main__":
    main()
