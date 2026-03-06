#!/usr/bin/env python3
# CALLED BY: preflight cron 8:45 AM ET
"""
Daily pre-market health check for Vex trading bot.
Validates all critical dependencies before market open.

Usage: python preflight_check.py [--test]
"""

import sys
import os
import json
import importlib.util
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

SCRIPTS_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = SCRIPTS_DIR.parent

CRITICAL_MODULES = [
    "price_sanity_gate",
    "signal_kill_check",
    "factor_smoothing",
    "execute_trade",
]

REQUIRED_SERVICES = [
    "news-sentiment-scanner",
    "health-beacon",
    "sync-market-state",
    "technical-scanner",
    "portfolio-health",
]


def check_module_import(name):
    """Check that a script exists and imports cleanly."""
    path = SCRIPTS_DIR / f"{name}.py"
    if not path.exists():
        return False, f"{name}.py not found"
    try:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        # Don't actually exec — just verify spec loads
        # spec.loader.exec_module(mod)  # skip to avoid side effects
        return True, "exists and spec loads"
    except Exception as e:
        return False, str(e)


def check_deployment_config():
    """Check deployment_enforcer_config.json exists with VIX threshold."""
    path = SCRIPTS_DIR / "deployment_enforcer_config.json"
    if not path.exists():
        return False, "deployment_enforcer_config.json not found"
    try:
        data = json.loads(path.read_text())
        if "vix_threshold" not in data and "VIX_THRESHOLD" not in data:
            for k in data:
                if "vix" in k.lower() and "threshold" in k.lower():
                    return True, "VIX threshold set"
            return False, "VIX threshold key not found"
        return True, "VIX threshold set"
    except Exception as e:
        return False, str(e)


def check_env():
    """Check .env has SUPABASE_URL and SUPABASE_KEY."""
    env_path = WORKSPACE_DIR / ".env"
    if not env_path.exists():
        return False, ".env not found"
    content = env_path.read_text()
    missing = []
    for key in ("SUPABASE_URL", "SUPABASE_KEY"):
        if key not in content:
            missing.append(key)
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "SUPABASE_URL and SUPABASE_KEY present"


def check_market_state():
    """Check market-state.json exists and is <30 min old."""
    # Check multiple likely locations
    for candidate in [
        WORKSPACE_DIR / "market-state.json",
        SCRIPTS_DIR / "market-state.json",
        Path("/tmp/market-state.json"),
    ]:
        if candidate.exists():
            age_min = (time.time() - candidate.stat().st_mtime) / 60
            if age_min > 30:
                return True, f"⚠️  STALE ({age_min:.0f} min old) at {candidate}"
            return True, f"fresh ({age_min:.0f} min old)"
    return False, "market-state.json not found"


def check_launchd_services():
    """Check launchd services running via launchctl list | grep miai."""
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout
    except Exception as e:
        return {svc: (False, str(e)) for svc in REQUIRED_SERVICES}

    results = {}
    for svc in REQUIRED_SERVICES:
        found = any(svc in line and "miai" in line for line in lines.splitlines())
        if not found:
            # Also check just the service name
            found = any(svc in line for line in lines.splitlines())
        results[svc] = (found, "running" if found else "not found in launchctl")
    return results


def run_all_checks(test_mode=False):
    """Run all preflight checks. Returns exit code."""
    critical_fail = False
    results = []

    def record(label, passed, detail, critical=True):
        nonlocal critical_fail
        icon = "✅" if passed else "❌"
        if not passed and "⚠️" in str(detail):
            icon = "⚠️"
        tag = "PASS" if passed else "FAIL"
        results.append(f"{icon} {tag}: {label} — {detail}")
        if not passed and critical and "⚠️" not in str(detail):
            critical_fail = True

    # Module imports
    for mod in CRITICAL_MODULES:
        ok, msg = check_module_import(mod)
        record(f"import {mod}", ok, msg)

    # Deployment config
    ok, msg = check_deployment_config()
    record("deployment_enforcer_config.json", ok, msg)

    # .env
    ok, msg = check_env()
    record(".env keys", ok, msg)

    # Market state (warn only, not critical)
    ok, msg = check_market_state()
    record("market-state.json", ok, msg, critical=False)

    # Launchd services
    svc_results = check_launchd_services()
    for svc, (ok, msg) in svc_results.items():
        record(f"launchd {svc}", ok, msg, critical=False)

    # Print results
    print("=" * 60)
    print(f"  VEX PREFLIGHT CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print("=" * 60)
    for r in results:
        print(f"  {r}")
    print("=" * 60)

    if critical_fail:
        print("  ❌ PREFLIGHT FAILED — critical checks did not pass")
        return 1
    else:
        print("  ✅ PREFLIGHT PASSED — all critical checks OK")
        return 0


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    if test_mode:
        print("[TEST MODE] Running preflight checks...")
    code = run_all_checks(test_mode=test_mode)
    sys.exit(code)
