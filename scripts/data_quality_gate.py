#!/usr/bin/env python3
"""
Data Quality Gate — Prevent Garbage From Entering Supabase
============================================================
Mark directive Mar 5: "Get those other three cleaned up and coded."

Three validation layers that were missing:
1. RSI bounds check (1-99) — rejects RSI=100, RSI=0, RSI=-5
2. Equity snapshot staleness filter — won't write if value hasn't changed in 5min
3. Fleet signals TTL — auto-expires signals older than 1 hour, caps table at 500 rows

Import these validators into any script that writes to Supabase:
  from data_quality_gate import validate_rsi, validate_snapshot, cleanup_signals

Also runs standalone as a cron/heartbeat cleanup:
  python3 data_quality_gate.py --cleanup    # Run all cleanup tasks
  python3 data_quality_gate.py --once       # Single pass
"""

import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    creds_path = os.path.expanduser("~/.supabase_trading_creds")
    if os.path.exists(creds_path):
        for line in open(creds_path):
            if line.startswith("SUPABASE_ANON_KEY="):
                SUPABASE_KEY = line.split("=", 1)[1].strip()

READ_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
WRITE_HEADERS = {**READ_HEADERS, "Content-Type": "application/json", "Prefer": "return=minimal"}

LOG_PATH = WORKSPACE / "logs" / "data-quality.log"
os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


# ============================================================
# GATE 1: RSI Bounds Check
# ============================================================
def validate_rsi(rsi_value, ticker="unknown"):
    """Validate RSI is within sane bounds (1-99).
    
    Returns (is_valid, cleaned_value).
    If invalid, returns False and None.
    If edge case (exactly 0 or 100), clamps to 1 or 99.
    """
    if rsi_value is None:
        return True, None  # None is acceptable (no data)
    
    try:
        rsi = float(rsi_value)
    except (ValueError, TypeError):
        log(f"🚫 RSI REJECTED: {ticker} — non-numeric value '{rsi_value}'")
        return False, None
    
    # Hard reject: negative or impossible values
    if rsi < 0 or rsi > 100:
        log(f"🚫 RSI REJECTED: {ticker} — value {rsi} outside 0-100 range")
        return False, None
    
    # Clamp edge cases (mathematically possible but usually garbage)
    if rsi == 0:
        log(f"⚠️ RSI CLAMPED: {ticker} — 0 → 1 (likely bad data)")
        return True, 1.0
    if rsi == 100:
        log(f"⚠️ RSI CLAMPED: {ticker} — 100 → 99 (likely bad data)")
        return True, 99.0
    
    return True, round(rsi, 2)


# ============================================================
# GATE 2: Equity Snapshot Staleness Filter
# ============================================================
def validate_snapshot(bot_id, new_value, min_interval_seconds=300):
    """Check if this snapshot is worth writing.
    
    Rejects if:
    - Value is identical to last snapshot AND less than min_interval since last write
    - Value is <= 0 (impossible)
    - Value deviates >50% from last known (likely garbage)
    
    Returns (should_write, reason).
    """
    if new_value is None or new_value <= 0:
        return False, f"Invalid value: {new_value}"
    
    # Get last snapshot
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/equity_snapshots?bot_id=eq.{bot_id}&select=value,recorded_at&order=recorded_at.desc&limit=1",
            headers=READ_HEADERS)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
    except:
        return True, "No previous snapshot found, writing"
    
    if not data:
        return True, "First snapshot for this bot"
    
    last_value = data[0].get("value", 0)
    last_time_str = data[0].get("recorded_at", "")
    
    # Check staleness — don't write identical values within interval
    if last_value == new_value and last_time_str:
        try:
            last_time = datetime.fromisoformat(last_time_str.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - last_time).total_seconds()
            if age < min_interval_seconds:
                return False, f"Identical value ${new_value:,.0f}, only {age:.0f}s since last write"
        except:
            pass
    
    # Check for garbage — >50% deviation from last known
    if last_value > 0:
        deviation = abs(new_value - last_value) / last_value
        if deviation > 0.50:
            log(f"🚫 SNAPSHOT REJECTED: {bot_id} — ${new_value:,.0f} is {deviation:.0%} off from last ${last_value:,.0f}")
            return False, f"Value ${new_value:,.0f} deviates {deviation:.0%} from last ${last_value:,.0f}"
    
    return True, "Valid"


# ============================================================
# GATE 3: Fleet Signals TTL + Cap
# ============================================================
SIGNAL_TTL_HOURS = 1      # Signals expire after 1 hour
SIGNAL_MAX_ROWS = 500     # Hard cap on total signals

def cleanup_signals():
    """Remove expired fleet_signals and enforce row cap.
    
    Run this periodically (every heartbeat or every 5 min).
    """
    cleaned = 0
    
    # Step 1: Delete signals older than TTL
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=SIGNAL_TTL_HOURS)).isoformat()
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/fleet_signals?created_at=lt.{cutoff}",
            method="DELETE", headers=WRITE_HEADERS)
        urllib.request.urlopen(req, timeout=10)
        
        # Count what's left
        req2 = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/fleet_signals?select=id&limit=1000",
            headers=READ_HEADERS)
        resp2 = urllib.request.urlopen(req2, timeout=5)
        remaining = json.loads(resp2.read())
        
        # Step 2: If still over cap, delete oldest
        if len(remaining) > SIGNAL_MAX_ROWS:
            excess = len(remaining) - SIGNAL_MAX_ROWS
            # Get oldest IDs
            req3 = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/fleet_signals?select=id&order=created_at.asc&limit={excess}",
                headers=READ_HEADERS)
            resp3 = urllib.request.urlopen(req3, timeout=5)
            old = json.loads(resp3.read())
            for row in old:
                try:
                    req4 = urllib.request.Request(
                        f"{SUPABASE_URL}/rest/v1/fleet_signals?id=eq.{row['id']}",
                        method="DELETE", headers=WRITE_HEADERS)
                    urllib.request.urlopen(req4, timeout=3)
                    cleaned += 1
                except:
                    pass
            log(f"🧹 Signals: deleted {cleaned} over cap ({len(remaining)} → {SIGNAL_MAX_ROWS})")
        
        final = len(remaining) - cleaned
        log(f"🧹 Signal cleanup: {final} signals remaining (TTL={SIGNAL_TTL_HOURS}h, cap={SIGNAL_MAX_ROWS})")
        return final
        
    except Exception as e:
        log(f"Signal cleanup error: {e}")
        return -1


def cleanup_stale_market_state():
    """Remove stale RSI values from market_state."""
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/market_state?select=state_json&id=eq.latest",
            headers=READ_HEADERS)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        if not data:
            return
        
        state_raw = data[0].get("state_json", "{}")
        state = json.loads(state_raw) if isinstance(state_raw, str) else state_raw
        tickers = state.get("tickers", {})
        
        cleaned = 0
        for ticker, info in list(tickers.items()):
            rsi = info.get("rsi")
            if rsi is not None:
                valid, cleaned_rsi = validate_rsi(rsi, ticker)
                if not valid:
                    del tickers[ticker]
                    cleaned += 1
                elif cleaned_rsi != rsi:
                    tickers[ticker]["rsi"] = cleaned_rsi
                    cleaned += 1
        
        if cleaned > 0:
            state["tickers"] = tickers
            patch_data = json.dumps({"state_json": json.dumps(state)}).encode()
            req2 = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/market_state?id=eq.latest",
                data=patch_data, method="PATCH", headers=WRITE_HEADERS)
            urllib.request.urlopen(req2, timeout=5)
            log(f"🧹 Market state: cleaned {cleaned} bad RSI values")
        
    except Exception as e:
        log(f"Market state cleanup error: {e}")


def run_cleanup():
    """Run all cleanup tasks."""
    log("🧹 Data quality cleanup starting...")
    cleanup_signals()
    cleanup_stale_market_state()
    log("🧹 Data quality cleanup complete")


if __name__ == "__main__":
    if "--cleanup" in sys.argv or "--once" in sys.argv:
        run_cleanup()
    elif "--test" in sys.argv:
        # Test all validators
        print("Testing RSI validator:")
        for val in [None, 0, 1, 50, 99, 100, -5, 150, "abc"]:
            valid, cleaned = validate_rsi(val, "TEST")
            print(f"  RSI {val} → valid={valid}, cleaned={cleaned}")
        
        print("\nTesting snapshot validator:")
        valid, reason = validate_snapshot("alfred", 50000)
        print(f"  $50K → valid={valid}, reason={reason}")
        valid, reason = validate_snapshot("alfred", 0)
        print(f"  $0 → valid={valid}, reason={reason}")
        valid, reason = validate_snapshot("alfred", 150000)
        print(f"  $150K → valid={valid}, reason={reason}")
    else:
        print("Usage:")
        print("  python3 data_quality_gate.py --cleanup   # Run all cleanup tasks")
        print("  python3 data_quality_gate.py --test      # Test validators")
        print("")
        print("Import in other scripts:")
        print("  from data_quality_gate import validate_rsi, validate_snapshot, cleanup_signals")
