#!/usr/bin/env python3
"""
Buddy Check System — Anti-sleep protocol.
Pairs: Alfred↔Eddie, Vex↔TARS
Each bot pings Supabase bot_health. If buddy is stale >15 min, alert Discord.

Usage:
  python3 buddy_check.py --ping alfred         # Record heartbeat
  python3 buddy_check.py --check alfred        # Check buddy's status
  python3 buddy_check.py --status              # Show all bot statuses
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed", file=sys.stderr)
    sys.exit(1)

WORKSPACE = Path(__file__).parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json"}

# Buddy pairs
BUDDIES = {
    "alfred": "eddie_v",
    "eddie_v": "alfred",
    "vex": "tars",
    "tars": "vex",
}

STALE_THRESHOLD_MIN = 15
BOT_IDS = ["tars", "alfred", "eddie_v", "vex"]

# SSH restart config — auto-restart buddy if stale
SSH_KEY = os.path.expanduser("~/.ssh/miai_bot")
BOT_SSH = {
    "tars":    {"user": "mharfmann",     "ip": "192.168.1.234"},
    "alfred":  {"user": "sheridanskala", "ip": "192.168.1.204"},
    "eddie_v": {"user": "",              "ip": "192.168.1.197"},  # Fill in username
    "vex":     {"user": "",              "ip": "192.168.1.233"},  # Fill in username
}
RESTART_COOLDOWN_MIN = 30  # Don't restart same bot more than once per 30 min
RESTART_LOG = WORKSPACE / "logs" / "buddy-restarts.json"


def ping(bot_id: str):
    """Record heartbeat to bot_health table."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "bot_id": bot_id,
        "last_heartbeat": now,
        "status": "alive"
    }

    # Try upsert
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/bot_health",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=payload,
            timeout=10
        )
        if r.status_code in (200, 201):
            print(f"✅ {bot_id} heartbeat recorded at {now[:19]}")
        else:
            # If upsert fails, try update
            r2 = requests.patch(
                f"{SUPABASE_URL}/rest/v1/bot_health?bot_id=eq.{bot_id}",
                headers=HEADERS,
                json={"last_heartbeat": now, "status": "alive"},
                timeout=10
            )
            print(f"✅ {bot_id} heartbeat updated at {now[:19]}" if r2.ok else f"⚠️ Heartbeat failed: {r2.status_code}")
    except Exception as e:
        print(f"⚠️  Heartbeat failed: {e}")


def check_buddy(bot_id: str):
    """Check if buddy is alive."""
    buddy = BUDDIES.get(bot_id)
    if not buddy:
        print(f"⚠️  No buddy configured for {bot_id}")
        return True

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/bot_health?bot_id=eq.{buddy}&select=bot_id,last_heartbeat,status",
            headers=HEADERS,
            timeout=10
        )
        r.raise_for_status()
        data = r.json()

        if not data:
            print(f"🔴 ALERT: Buddy {buddy} has NO heartbeat record!")
            return False

        last_hb = data[0].get("last_heartbeat")
        if not last_hb:
            print(f"🔴 ALERT: Buddy {buddy} has no last_heartbeat!")
            return False

        last_time = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - last_time
        age_min = age.total_seconds() / 60

        if age_min > STALE_THRESHOLD_MIN:
            print(f"🔴 ALERT: Buddy {buddy} is STALE — last heartbeat {age_min:.0f}m ago (threshold: {STALE_THRESHOLD_MIN}m)")
            # Auto-restart via SSH
            ssh_restart(buddy)
            return False
        else:
            print(f"✅ Buddy {buddy} is alive — last heartbeat {age_min:.0f}m ago")
            return True

    except Exception as e:
        print(f"⚠️  Failed to check buddy {buddy}: {e}")
        return False


def show_status():
    """Show all bot statuses."""
    print(f"{'Bot':12s} {'Status':8s} {'Last Heartbeat':>25s} {'Age':>8s}")
    print("-" * 58)

    for bot_id in BOT_IDS:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/bot_health?bot_id=eq.{bot_id}&select=bot_id,last_heartbeat,status",
                headers=HEADERS,
                timeout=10
            )
            data = r.json()
            if data:
                last_hb = data[0].get("last_heartbeat", "")
                status = data[0].get("status", "unknown")
                if last_hb:
                    last_time = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
                    age = datetime.now(timezone.utc) - last_time
                    age_min = age.total_seconds() / 60
                    stale = " 🔴" if age_min > STALE_THRESHOLD_MIN else ""
                    print(f"  {bot_id:10s} {status:8s} {last_hb[:19]:>25s} {age_min:>5.0f}m{stale}")
                else:
                    print(f"  {bot_id:10s} {status:8s} {'N/A':>25s}")
            else:
                print(f"  {bot_id:10s} {'MISSING':8s}")
        except Exception as e:
            print(f"  {bot_id:10s} {'ERROR':8s} {str(e)[:30]}")

    print(f"\nBuddy pairs: Alfred↔Eddie, Vex↔TARS | Stale threshold: {STALE_THRESHOLD_MIN}m")


def ssh_restart(bot_id: str):
    """Attempt SSH restart of a stale buddy."""
    import subprocess
    
    ssh_info = BOT_SSH.get(bot_id)
    if not ssh_info or not ssh_info["user"]:
        print(f"⚠️  No SSH config for {bot_id} — can't auto-restart")
        return False
    
    if not os.path.exists(SSH_KEY):
        print(f"⚠️  SSH key {SSH_KEY} not found — run SSH setup first")
        return False
    
    # Cooldown check
    try:
        if RESTART_LOG.exists():
            restarts = json.loads(RESTART_LOG.read_text())
        else:
            restarts = {}
        last = restarts.get(bot_id, 0)
        age_min = (datetime.now(timezone.utc).timestamp() - last) / 60
        if age_min < RESTART_COOLDOWN_MIN:
            print(f"⏳ {bot_id} restart on cooldown ({age_min:.0f}m < {RESTART_COOLDOWN_MIN}m)")
            return False
    except:
        restarts = {}
    
    # Attempt restart
    user = ssh_info["user"]
    ip = ssh_info["ip"]
    cmd = ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
           f"{user}@{ip}", "openclaw gateway restart"]
    
    print(f"🔄 Attempting SSH restart of {bot_id} ({user}@{ip})...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✅ {bot_id} restarted successfully via SSH")
            restarts[bot_id] = datetime.now(timezone.utc).timestamp()
            os.makedirs(RESTART_LOG.parent, exist_ok=True)
            RESTART_LOG.write_text(json.dumps(restarts, indent=2))
            return True
        else:
            print(f"❌ SSH restart failed: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ SSH restart timed out for {bot_id}")
        return False
    except Exception as e:
        print(f"❌ SSH restart error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Buddy Check System")
    parser.add_argument("--ping", help="Record heartbeat for bot")
    parser.add_argument("--check", help="Check buddy status for bot")
    parser.add_argument("--status", action="store_true", help="Show all bot statuses")

    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY required", file=sys.stderr)
        sys.exit(1)

    if args.ping:
        ping(args.ping)
    elif args.check:
        alive = check_buddy(args.check)
        sys.exit(0 if alive else 1)
    elif args.status:
        show_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
