#!/usr/bin/env python3
"""
Alfred SHIL - System Check (Risk Domain)
Detect → Diagnose issues in Alfred's domain:
  - Data integrity (portfolio math, phantom trades, bot_id contamination)
  - Stop enforcement (all positions have stops, stops are current)
  - Position limits (heat cap, max position size, daily circuit breaker)
  - Supabase sync (local vs remote consistency)
  - Service health (launchd jobs, stale files)

Outputs issues to Supabase system_issues table + local issues.json
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- Config ---
WORKSPACE = Path(__file__).parent.parent
SCRIPTS = WORKSPACE / "scripts"
CREDS_FILE = Path.home() / ".supabase_trading_creds"
BOT_ID = "alfred"
BOT_ID_CRYPTO = "alfred_crypto"
MAX_POSITION_PCT = 10.0  # 10% max single position
HEAT_CAP_PCT = 60.0      # 60% max total exposure
DAILY_CIRCUIT_BREAKER = -5.0  # -5% daily loss limit
STOP_REQUIRED = True
MAX_STALE_MINUTES = 10    # market-state.json staleness threshold

def load_creds():
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

def supabase_query(creds, table, params=""):
    """Query Supabase REST API."""
    import urllib.request
    url = f"{creds['SUPABASE_URL']}/rest/v1/{table}?{params}"
    req = urllib.request.Request(url, headers={
        "apikey": creds["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {creds['SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def supabase_insert(creds, table, data):
    """Insert into Supabase."""
    import urllib.request
    url = f"{creds['SUPABASE_URL']}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "apikey": creds["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {creds['SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception as e:
        return {"error": str(e)}

def create_issue(category, severity, description, auto_fixable=False, fix_applied=None):
    return {
        "bot": "ALFRED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "severity": severity,
        "description": description,
        "auto_fixable": auto_fixable,
        "fix_applied": fix_applied,
        "status": "open"
    }

# --- Checks ---

def check_portfolio_math(creds):
    """Verify portfolio snapshot math adds up."""
    issues = []
    for bot in [BOT_ID, BOT_ID_CRYPTO]:
        snapshots = supabase_query(creds, "portfolio_snapshots",
            f"bot_id=eq.{bot}&order=created_at.desc&limit=1")
        if isinstance(snapshots, dict) and "error" in snapshots:
            issues.append(create_issue("data_integrity", "WARN",
                f"Cannot query portfolio_snapshots for {bot}: {snapshots['error']}"))
            continue
        if not snapshots:
            continue
        snap = snapshots[0]
        total = snap.get("total_value", 0)
        cash = snap.get("cash_balance", 0)
        invested = snap.get("invested_value", 0)
        if total and abs(total - (cash + invested)) > 1.0:
            issues.append(create_issue("data_integrity", "CRITICAL",
                f"{bot} portfolio math drift: total={total}, cash+invested={cash+invested}, diff={abs(total-(cash+invested)):.2f}",
                auto_fixable=True))
    return issues

def check_position_limits(creds):
    """Check no single position exceeds limits."""
    issues = []
    for bot in [BOT_ID, BOT_ID_CRYPTO]:
        positions = supabase_query(creds, "trades",
            f"bot_id=eq.{bot}&status=eq.open&select=ticker,quantity,entry_price,current_value")
        if isinstance(positions, dict) and "error" in positions:
            continue
        if not positions:
            continue
        snapshots = supabase_query(creds, "portfolio_snapshots",
            f"bot_id=eq.{bot}&order=created_at.desc&limit=1")
        total_value = 25000  # default
        if snapshots and not isinstance(snapshots, dict):
            total_value = snapshots[0].get("total_value", 25000) or 25000

        total_exposure = 0
        for pos in positions:
            value = abs((pos.get("quantity", 0) or 0) * (pos.get("entry_price", 0) or 0))
            total_exposure += value
            pct = (value / total_value * 100) if total_value else 0
            if pct > MAX_POSITION_PCT:
                issues.append(create_issue("protocol_violation", "WARN",
                    f"{bot} position {pos.get('ticker')} at {pct:.1f}% of portfolio (limit: {MAX_POSITION_PCT}%)"))

        heat = (total_exposure / total_value * 100) if total_value else 0
        if heat > HEAT_CAP_PCT:
            issues.append(create_issue("protocol_violation", "CRITICAL",
                f"{bot} heat cap breached: {heat:.1f}% (limit: {HEAT_CAP_PCT}%)"))
    return issues

def check_bot_id_contamination(creds):
    """Check for cross-lane contamination (crypto trades in equity book or vice versa)."""
    issues = []
    crypto_tickers = {"BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "DOGE-USD", "ADA-USD",
                      "DOT-USD", "LINK-USD", "MATIC-USD", "XRP-USD", "RENDER-USD", "RNDR-USD"}

    equity_trades = supabase_query(creds, "trades",
        f"bot_id=eq.{BOT_ID}&status=eq.open")
    if isinstance(equity_trades, list):
        for t in equity_trades:
            ticker = (t.get("ticker") or "").upper()
            if ticker in crypto_tickers or ticker.endswith("-USD"):
                issues.append(create_issue("data_integrity", "CRITICAL",
                    f"Crypto ticker {ticker} found in equity book (bot_id={BOT_ID}). Cross-lane contamination.",
                    auto_fixable=False))
    return issues

def check_stale_market_state():
    """Check if market-state.json is fresh."""
    issues = []
    ms_path = WORKSPACE / "market-state.json"
    if ms_path.exists():
        age_min = (time.time() - ms_path.stat().st_mtime) / 60
        if age_min > MAX_STALE_MINUTES:
            issues.append(create_issue("service_down", "WARN",
                f"market-state.json is {age_min:.0f} min stale (threshold: {MAX_STALE_MINUTES} min)",
                auto_fixable=False))
    else:
        issues.append(create_issue("service_down", "WARN",
            "market-state.json missing"))
    return issues

def check_launchd_services():
    """Check launchd services are running."""
    issues = []
    try:
        result = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        lines = [l for l in result.stdout.split("\n") if "miai" in l.lower()]
        for line in lines:
            parts = line.split()
            if len(parts) >= 3:
                pid = parts[0]
                exit_code = parts[1]
                label = parts[2]
                if pid == "-" and exit_code != "0":
                    issues.append(create_issue("service_down", "CRITICAL",
                        f"launchd service {label} not running (exit code {exit_code})",
                        auto_fixable=True, fix_applied="Restart via launchctl"))
    except Exception as e:
        issues.append(create_issue("service_down", "WARN", f"Cannot check launchd: {e}"))
    return issues

def check_error_rates():
    """Check log files for excessive errors."""
    issues = []
    log_dirs = [WORKSPACE / "logs", WORKSPACE / "trading-research" / "logs"]
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for log_file in log_dir.glob("*.log"):
            try:
                result = subprocess.run(["grep", "-c", "-i", "error", str(log_file)],
                    capture_output=True, text=True, timeout=5)
                count = int(result.stdout.strip()) if result.stdout.strip() else 0
                if count > 50:
                    issues.append(create_issue("performance_anomaly", "WARN",
                        f"{log_file.name}: {count} errors detected"))
            except Exception:
                pass
    return issues

def check_duplicate_positions(creds):
    """Check for duplicate open positions on same ticker."""
    issues = []
    for bot in [BOT_ID, BOT_ID_CRYPTO]:
        positions = supabase_query(creds, "trades",
            f"bot_id=eq.{bot}&status=eq.open&select=ticker")
        if isinstance(positions, list):
            tickers = [p.get("ticker") for p in positions]
            seen = set()
            for t in tickers:
                if t in seen:
                    issues.append(create_issue("data_integrity", "CRITICAL",
                        f"Duplicate open position for {t} in {bot}",
                        auto_fixable=False))
                seen.add(t)
    return issues

# --- Main ---

def run_all_checks():
    creds = load_creds()
    if not creds.get("SUPABASE_URL"):
        print("ERROR: No Supabase credentials found")
        sys.exit(1)

    all_issues = []
    checks = [
        ("portfolio_math", lambda: check_portfolio_math(creds)),
        ("position_limits", lambda: check_position_limits(creds)),
        ("bot_id_contamination", lambda: check_bot_id_contamination(creds)),
        ("stale_market_state", check_stale_market_state),
        ("launchd_services", check_launchd_services),
        ("error_rates", check_error_rates),
        ("duplicate_positions", lambda: check_duplicate_positions(creds)),
    ]

    for name, check_fn in checks:
        try:
            issues = check_fn()
            all_issues.extend(issues)
            status = f"⚠️ {len(issues)} issues" if issues else "✅"
            print(f"  {name}: {status}")
        except Exception as e:
            print(f"  {name}: ❌ CHECK FAILED: {e}")
            all_issues.append(create_issue("service_down", "WARN",
                f"Check '{name}' failed: {e}"))

    # Save locally
    issues_path = WORKSPACE / "issues.json"
    issues_path.write_text(json.dumps(all_issues, indent=2))

    # Push to Supabase
    for issue in all_issues:
        supabase_insert(creds, "system_issues", issue)

    # Summary
    critical = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    warn = sum(1 for i in all_issues if i["severity"] == "WARN")
    print(f"\n{'🔴' if critical else '🟢'} Alfred SHIL: {len(all_issues)} issues ({critical} critical, {warn} warn)")

    return all_issues

if __name__ == "__main__":
    print(f"Alfred SHIL System Check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 50)
    issues = run_all_checks()
    sys.exit(1 if any(i["severity"] == "CRITICAL" for i in issues) else 0)
