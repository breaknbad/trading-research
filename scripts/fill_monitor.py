#!/usr/bin/env python3
"""
Fill-or-Kill Speed Gate — Execution Speed Monitor
===================================================
Upgrade #8: Track how long trades take to execute. Alert if >5s.
Wraps execute_trade.py calls and logs timing data.

Can also scan recent trades in Supabase for timing analysis.

Usage:
  python3 fill_monitor.py --once       # Analyze recent trade speeds
  python3 fill_monitor.py --wrap -- python3 scripts/execute_trade.py --ticker NVDA ...
"""

import json, os, sys, time, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
LOG_PATH = WORKSPACE / "logs" / "fill_monitor.log"
TIMING_PATH = WORKSPACE / "logs" / "fill_timings.json"

SLOW_THRESHOLD_SECS = 5.0  # Alert if trade takes >5s

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = ""
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
except Exception:
    pass

os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def timed_execute(cmd_args):
    """Execute a command and time it. Alert if slow."""
    log(f"⏱️ Executing: {' '.join(cmd_args)}")
    start = time.monotonic()

    try:
        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
        elapsed = time.monotonic() - start

        timing = {
            "command": " ".join(cmd_args[-8:]),  # Last 8 args for brevity
            "elapsed_secs": round(elapsed, 3),
            "return_code": result.returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "slow": elapsed > SLOW_THRESHOLD_SECS,
        }

        # Log timing
        save_timing(timing)

        if elapsed > SLOW_THRESHOLD_SECS:
            log(f"🐌 SLOW FILL: {elapsed:.1f}s (threshold: {SLOW_THRESHOLD_SECS}s)")
            log(f"   stdout: {result.stdout.strip()[:200]}")
            log(f"   stderr: {result.stderr.strip()[:200]}")
        else:
            log(f"⚡ Fast fill: {elapsed:.3f}s")

        # Pass through output
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        return result.returncode

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        log(f"💀 TIMEOUT: Trade execution took >{elapsed:.0f}s — killed")
        save_timing({"command": " ".join(cmd_args[-8:]), "elapsed_secs": round(elapsed, 3),
                      "return_code": -1, "timestamp": datetime.now(timezone.utc).isoformat(),
                      "slow": True, "timeout": True})
        return 1


def save_timing(timing):
    """Append timing record."""
    try:
        timings = json.load(open(TIMING_PATH)) if TIMING_PATH.exists() else []
    except Exception:
        timings = []
    timings.append(timing)
    # Keep last 500 entries
    timings = timings[-500:]
    with open(TIMING_PATH, "w") as f:
        json.dump(timings, f, indent=2)


def analyze_timings():
    """Analyze recent fill timings and report."""
    try:
        timings = json.load(open(TIMING_PATH)) if TIMING_PATH.exists() else []
    except Exception:
        timings = []

    if not timings:
        log("No timing data yet")
        return

    total = len(timings)
    slow = sum(1 for t in timings if t.get("slow"))
    avg = sum(t.get("elapsed_secs", 0) for t in timings) / total
    fastest = min(t.get("elapsed_secs", 999) for t in timings)
    slowest = max(t.get("elapsed_secs", 0) for t in timings)

    log(f"📊 Fill Speed Analysis ({total} trades)")
    log(f"   Avg: {avg:.2f}s | Fastest: {fastest:.3f}s | Slowest: {slowest:.1f}s")
    log(f"   Slow fills (>{SLOW_THRESHOLD_SECS}s): {slow}/{total} ({slow/total*100:.0f}%)")

    # Show recent slow ones
    recent_slow = [t for t in timings[-20:] if t.get("slow")]
    if recent_slow:
        log("   Recent slow fills:")
        for t in recent_slow[-5:]:
            log(f"     {t.get('elapsed_secs', 0):.1f}s — {t.get('command', '')[:60]}")


if __name__ == "__main__":
    if "--once" in sys.argv:
        analyze_timings()
    elif "--wrap" in sys.argv:
        idx = sys.argv.index("--wrap")
        # Everything after -- is the command
        try:
            sep = sys.argv.index("--", idx)
            cmd = sys.argv[sep + 1:]
        except ValueError:
            cmd = sys.argv[idx + 1:]
        if cmd:
            rc = timed_execute(cmd)
            sys.exit(rc)
        else:
            print("Usage: fill_monitor.py --wrap -- <command>", file=sys.stderr)
            sys.exit(1)
    else:
        analyze_timings()
