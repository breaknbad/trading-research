#!/usr/bin/env python3
"""
crypto_stop_heartbeat.py — F10: Stop enforcer health monitor
Owner: Alfred | Created: 2026-03-01

Writes a heartbeat to Supabase every 60s proving the stop enforcer is alive.
Other bots check this — if heartbeat age > 3 min, backup bot takes over stops.
"""

import os
import json
import time
from datetime import datetime, timezone

HEARTBEAT_FILE = os.path.join(
    os.path.dirname(__file__), "stop_enforcer_heartbeat.json"
)

def write_heartbeat(bot_id: str = "alfred", positions_monitored: int = 0, status: str = "active"):
    """Write stop enforcer heartbeat to local file + Supabase."""
    heartbeat = {
        "bot_id": bot_id,
        "service": "stop_enforcer",
        "status": status,
        "positions_monitored": positions_monitored,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "epoch": int(time.time())
    }

    # Local file (always works)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump(heartbeat, f, indent=2)

    # Supabase (best effort)
    try:
        from crypto_supabase_guard import guarded_upsert
        result = guarded_upsert("bot_health", {
            "bot_id": bot_id,
            "service": "stop_enforcer",
            "status": status,
            "positions_monitored": positions_monitored,
            "last_heartbeat": heartbeat["timestamp"]
        }, on_conflict="bot_id,service")
        return result
    except Exception as e:
        return {"ok": False, "error": str(e), "local": True}

def check_heartbeat(bot_id: str = "alfred", max_age_seconds: int = 180) -> dict:
    """Check if a bot's stop enforcer is alive. Returns status."""
    # Try Supabase first
    try:
        from crypto_supabase_guard import _get_client
        client = _get_client()
        if client:
            result = client.table("bot_health").select("*").eq(
                "bot_id", bot_id
            ).eq("service", "stop_enforcer").execute()
            if result.data:
                last = result.data[0]
                last_ts = datetime.fromisoformat(last["last_heartbeat"].replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - last_ts).total_seconds()
                return {
                    "alive": age < max_age_seconds,
                    "age_seconds": int(age),
                    "max_age": max_age_seconds,
                    "status": last.get("status", "unknown"),
                    "positions": last.get("positions_monitored", 0)
                }
    except Exception:
        pass

    # Fallback to local file
    try:
        with open(HEARTBEAT_FILE) as f:
            hb = json.load(f)
        age = int(time.time()) - hb.get("epoch", 0)
        return {
            "alive": age < max_age_seconds,
            "age_seconds": age,
            "max_age": max_age_seconds,
            "source": "local_file"
        }
    except Exception:
        return {"alive": False, "error": "No heartbeat found", "age_seconds": 999999}


if __name__ == "__main__":
    print("crypto_stop_heartbeat.py — Stop enforcer health monitor")
    result = write_heartbeat("alfred", 0, "test")
    print(f"  Write heartbeat: {result}")
    check = check_heartbeat("alfred")
    print(f"  Check heartbeat: {check}")
    print("  Status: READY")
