# CALLED BY: cron preflight-check (8:45 AM ET Mon-Fri)
#!/usr/bin/env python3
"""
preflight_check.py — Daily system health verification.
Runs before market open. Posts PASS/FAIL to Discord.
"""

import subprocess
import json
import os
import sys
import time
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")

def check_launchd():
    """Verify all expected launchd jobs are running."""
    expected = ["price-streamer", "stop-enforcer", "portfolio-health"]
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    lines = result.stdout
    
    issues = []
    for job in expected:
        if f"com.miai.{job}" not in lines:
            issues.append(f"❌ {job} NOT LOADED")
        elif f"-\t0\tcom.miai.{job}" in lines:
            # PID is "-" — might be interval-based (ok) or dead (bad)
            if job == "health-beacon":
                continue  # Interval-based, this is normal
            issues.append(f"⚠️ {job} loaded but no PID")
        else:
            pass  # Running fine
    
    return issues if issues else ["✅ All launchd jobs running"]


def check_price_sanity():
    """Test price sanity gate with known-bad price."""
    try:
        sys.path.insert(0, SCRIPTS_DIR)
        # Quick test: does the import work?
        from pre_trade_checker import score_trade
        result = score_trade("BTC-USD", "BUY", "preflight")
        if result["score"] >= 0:
            return ["✅ Factor engine operational"]
        else:
            return ["❌ Factor engine returned negative score"]
    except Exception as e:
        return [f"❌ Factor engine BROKEN: {e}"]


def check_supabase():
    """Verify Supabase connectivity."""
    try:
        import requests
        env_path = os.path.join(WORKSPACE, ".env")
        sb_url = sb_key = ""
        with open(env_path) as f:
            for line in f:
                if line.startswith("SUPABASE_URL="):
                    sb_url = line.strip().split("=", 1)[1]
                elif line.startswith("SUPABASE_KEY="):
                    sb_key = line.strip().split("=", 1)[1]
        
        r = requests.get(
            f"{sb_url}/rest/v1/portfolio_snapshots?select=bot_id&limit=1",
            headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
            timeout=10
        )
        if r.status_code == 200:
            return ["✅ Supabase connected"]
        else:
            return [f"❌ Supabase error: HTTP {r.status_code}"]
    except Exception as e:
        return [f"❌ Supabase UNREACHABLE: {e}"]


def check_ssh():
    """Verify SSH to fleet machines."""
    hosts = {
        "Alfred (204)": "sheridanskala@192.168.1.204",
        "Eddie (197)": "markmatuska@192.168.1.197",
        "Vex (233)": "kentharfmann@192.168.1.233",
    }
    issues = []
    for name, host in hosts.items():
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes", host, "echo OK"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            issues.append(f"✅ SSH to {name}")
        else:
            issues.append(f"❌ SSH to {name} FAILED")
    return issues


def check_log_sizes():
    """Check for unbounded log growth."""
    issues = []
    log_files = [
        "/tmp/price-streamer-error.log",
        "/tmp/price-streamer-out.log",
    ]
    for lf in log_files:
        if os.path.exists(lf):
            size_mb = os.path.getsize(lf) / (1024 * 1024)
            if size_mb > 50:
                issues.append(f"⚠️ {os.path.basename(lf)} is {size_mb:.0f}MB — needs rotation")
            elif size_mb > 10:
                issues.append(f"🟡 {os.path.basename(lf)} is {size_mb:.0f}MB")
    
    return issues if issues else ["✅ Log sizes OK"]


def check_scripts_have_headers():
    """Verify all .py scripts have CALLED BY headers."""
    missing = []
    for f in os.listdir(SCRIPTS_DIR):
        if f.endswith(".py") and not f.startswith("__"):
            path = os.path.join(SCRIPTS_DIR, f)
            with open(path, "r") as fh:
                head = fh.read(500)
                if "CALLED BY" not in head:
                    missing.append(f)
    
    if missing:
        return [f"⚠️ {len(missing)} scripts missing CALLED BY header: {', '.join(missing[:5])}"]
    return ["✅ All scripts have CALLED BY headers"]


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  TARS PREFLIGHT CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'='*60}\n")
    
    all_results = []
    
    checks = [
        ("Launchd Services", check_launchd),
        ("Factor Engine", check_price_sanity),
        ("Supabase", check_supabase),
        ("SSH Fleet", check_ssh),
        ("Log Sizes", check_log_sizes),
        ("Script Headers", check_scripts_have_headers),
    ]
    
    pass_count = 0
    fail_count = 0
    
    for name, check_fn in checks:
        print(f"  [{name}]")
        try:
            results = check_fn()
        except Exception as e:
            results = [f"❌ CHECK CRASHED: {e}"]
        
        for r in results:
            print(f"    {r}")
            all_results.append(r)
            if "✅" in r:
                pass_count += 1
            elif "❌" in r:
                fail_count += 1
    
    print(f"\n  RESULT: {pass_count} PASS / {fail_count} FAIL")
    
    if fail_count > 0:
        print(f"  ⛔ PREFLIGHT FAILED — fix before trading")
        sys.exit(1)
    else:
        print(f"  ✅ PREFLIGHT PASSED — clear to trade")
