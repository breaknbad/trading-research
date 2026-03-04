#!/usr/bin/env python3
"""
stop_check_watchdog.py — Dead-man switch for stop enforcement.
If stop_check.log hasn't been written to in >5 minutes, alert Discord.
Run as launchd StartInterval (every 120s).
"""

import os
import sys
import time
import json
import requests
from pathlib import Path

LOG_FILE = Path(__file__).parent / "logs" / "stop_check.log"
STATE_FILE = Path(__file__).parent / "logs" / "watchdog_state.json"
MAX_STALE_SECONDS = 300  # 5 minutes
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")

def check():
    if not LOG_FILE.exists():
        print(f"❌ stop_check.log not found at {LOG_FILE}")
        return False, "Log file missing"

    mtime = os.path.getmtime(LOG_FILE)
    age = time.time() - mtime
    
    if age > MAX_STALE_SECONDS:
        msg = f"🚨 WATCHDOG ALERT: stop_check.log is {int(age)}s old (>{MAX_STALE_SECONDS}s). Stop enforcement may be DOWN."
        print(msg)
        
        # Check if we already alerted recently (don't spam)
        try:
            if STATE_FILE.exists():
                state = json.loads(STATE_FILE.read_text())
                last_alert = state.get("last_alert", 0)
                if time.time() - last_alert < 600:  # Don't alert more than once per 10 min
                    print("   (Already alerted recently, skipping)")
                    return False, msg
        except Exception:
            pass
        
        # Save alert timestamp
        STATE_FILE.write_text(json.dumps({"last_alert": time.time(), "stale_seconds": int(age)}))
        
        return False, msg
    else:
        print(f"✅ stop_check.log is {int(age)}s old — alive")
        return True, f"Healthy ({int(age)}s)"


def main():
    ok, msg = check()
    if not ok:
        # Write to a local alert file that heartbeat can pick up
        alert_file = Path(__file__).parent.parent / "alerts.json"
        try:
            alerts = json.loads(alert_file.read_text()) if alert_file.exists() else []
        except Exception:
            alerts = []
        alerts.append({
            "type": "WATCHDOG",
            "message": msg,
            "timestamp": time.time(),
            "source": "stop_check_watchdog"
        })
        alert_file.write_text(json.dumps(alerts, indent=2))
        print(f"   Alert written to {alert_file}")
    
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
