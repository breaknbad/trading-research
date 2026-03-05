#!/usr/bin/env python3
"""SHIL Phase 1 — Vex Domain Checks (Intel/Sentiment)

Checks:
1. Sentiment state freshness (F&G index, headline scan)
2. Intel signals TTL (expired signals still active)
3. News sentiment scanner launchd health
4. Factor engine input freshness (sentiment_state.json, volume_state.json)
5. Alerts.json integrity
6. Pattern frequency tracking (same issue class 3x/week = design flaw)

Output: issues.json (shared schema) + Supabase system_issues table
"""
import json, os, sys, time, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BOT_NAME = "vex"

ISSUES_PATH = os.path.join(WORKSPACE, "issues.json")
PATTERN_PATH = os.path.join(WORKSPACE, "scripts", "issue_patterns.json")
SENTIMENT_STATE = os.path.join(WORKSPACE, "scripts", "sentiment_state.json")
VOLUME_STATE = os.path.join(WORKSPACE, "volume_state.json")
INTEL_SIGNALS = os.path.join(WORKSPACE, "intel_signals.json")
ALERTS_PATH = os.path.join(WORKSPACE, "alerts.json")
LANE_CONFIG = os.path.join(WORKSPACE, "scripts", "lane_config.json")

# Freshness thresholds (seconds)
SENTIMENT_STALE_THRESHOLD = 3600      # 1 hour
VOLUME_STALE_THRESHOLD = 3600         # 1 hour
INTEL_TTL_CHECK = True
PATTERN_ESCALATION_COUNT = 3          # 3x same issue class in 7 days = CRITICAL

def now_utc():
    return datetime.now(timezone.utc)

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def make_issue(severity, category, description, details=None):
    return {
        "id": f"vex-{int(time.time())}-{hash(description) % 10000:04d}",
        "bot": BOT_NAME,
        "severity": severity,
        "category": category,
        "description": description,
        "details": details or {},
        "detected_at": now_utc().isoformat(),
        "fixed_at": None,
        "hardened_at": None,
        "fidelity_last_checked": None
    }

def push_to_supabase(issue):
    """Best-effort push to system_issues table."""
    if not SUPABASE_KEY:
        return False
    import urllib.request, urllib.error
    url = f"{SUPABASE_URL}/rest/v1/system_issues"
    payload = json.dumps(issue).encode()
    req = urllib.request.Request(url, data=payload, method='POST', headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    })
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False

# ─── CHECK 1: Sentiment State Freshness ───
def check_sentiment_freshness():
    issues = []
    state = load_json(SENTIMENT_STATE)
    if not state:
        issues.append(make_issue("CRITICAL", "data_integrity",
            "sentiment_state.json missing or empty",
            {"file": SENTIMENT_STATE}))
        return issues

    last_run = state.get("last_run")
    if last_run:
        try:
            lr = datetime.fromisoformat(last_run)
            age_s = (now_utc() - lr).total_seconds()
            if age_s > SENTIMENT_STALE_THRESHOLD:
                sev = "CRITICAL" if age_s > SENTIMENT_STALE_THRESHOLD * 3 else "WARN"
                issues.append(make_issue(sev, "data_integrity",
                    f"Sentiment state stale ({int(age_s/60)} min old)",
                    {"last_run": last_run, "age_seconds": int(age_s)}))
        except (ValueError, TypeError):
            issues.append(make_issue("WARN", "data_integrity",
                "sentiment_state.json has unparseable last_run"))

    fng = state.get("last_fng")
    if fng is None:
        issues.append(make_issue("WARN", "data_integrity",
            "Fear & Greed index missing from sentiment state"))

    return issues

# ─── CHECK 2: Intel Signals TTL ───
def check_intel_signals_ttl():
    issues = []
    signals = load_json(INTEL_SIGNALS, [])
    if not isinstance(signals, list):
        signals = signals.get("signals", []) if isinstance(signals, dict) else []

    now = now_utc()
    expired_count = 0
    for sig in signals:
        ttl = sig.get("ttl_hours") or sig.get("ttl")
        created = sig.get("created_at") or sig.get("timestamp")
        if ttl and created:
            try:
                created_dt = datetime.fromisoformat(str(created))
                if (now - created_dt).total_seconds() > float(ttl) * 3600:
                    expired_count += 1
            except (ValueError, TypeError):
                pass

    if expired_count > 0:
        issues.append(make_issue("WARN", "data_integrity",
            f"{expired_count} intel signal(s) past TTL still active",
            {"expired_count": expired_count}))
    return issues

# ─── CHECK 3: News Sentiment Scanner Health ───
def check_scanner_health():
    issues = []
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.miai.news-sentiment-scanner"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            issues.append(make_issue("CRITICAL", "service_down",
                "news-sentiment-scanner launchd service not found",
                {"stderr": result.stderr[:200]}))
        else:
            # Check PID exists in output
            lines = result.stdout.strip().split('\n')
            if lines:
                parts = lines[0].split('\t') if '\t' in lines[0] else lines[0].split()
                pid = parts[0] if parts else "-"
                if pid == "-" or pid == "0":
                    issues.append(make_issue("WARN", "service_down",
                        "news-sentiment-scanner has no running PID (may have crashed)",
                        {"output": result.stdout[:200]}))
    except subprocess.TimeoutExpired:
        issues.append(make_issue("WARN", "infrastructure",
            "launchctl list timed out checking scanner"))
    except Exception as e:
        issues.append(make_issue("INFO", "infrastructure",
            f"Could not check scanner health: {e}"))
    return issues

# ─── CHECK 4: Factor Engine Input Freshness ───
def check_factor_inputs():
    issues = []
    now = now_utc()

    # Volume state
    vol = load_json(VOLUME_STATE)
    if vol:
        ts = vol.get("timestamp") or vol.get("last_updated")
        if ts:
            try:
                vol_dt = datetime.fromisoformat(str(ts))
                age_s = (now - vol_dt).total_seconds()
                if age_s > VOLUME_STALE_THRESHOLD:
                    issues.append(make_issue("WARN", "data_integrity",
                        f"volume_state.json stale ({int(age_s/60)} min)",
                        {"age_seconds": int(age_s)}))
            except (ValueError, TypeError):
                pass
    # Lane config existence
    if not os.path.exists(LANE_CONFIG):
        issues.append(make_issue("INFO", "config_drift",
            "lane_config.json missing — factor engine using defaults"))

    return issues

# ─── CHECK 5: Alerts.json Integrity ───
def check_alerts_integrity():
    issues = []
    alerts = load_json(ALERTS_PATH, [])
    if not isinstance(alerts, list):
        if isinstance(alerts, dict):
            alerts = alerts.get("alerts", [])
        else:
            issues.append(make_issue("WARN", "data_integrity",
                "alerts.json has unexpected format"))
            return issues

    # Check for very old uncleared alerts (>24h)
    now = now_utc()
    stale_count = 0
    for alert in alerts:
        ts = alert.get("timestamp") or alert.get("created_at")
        if ts:
            try:
                alert_dt = datetime.fromisoformat(str(ts))
                if (now - alert_dt).total_seconds() > 86400:
                    stale_count += 1
            except (ValueError, TypeError):
                pass
    if stale_count > 0:
        issues.append(make_issue("INFO", "data_integrity",
            f"{stale_count} alert(s) older than 24h not cleared",
            {"stale_count": stale_count}))
    return issues

# ─── CHECK 6: Pattern Frequency Tracker ───
def check_pattern_frequency(new_issues):
    """Track issue patterns. If same category fires 3x in 7 days, escalate."""
    escalated = []
    patterns = load_json(PATTERN_PATH, {"history": []})
    history = patterns.get("history", [])

    # Add new issues to history
    cutoff = (now_utc() - timedelta(days=7)).isoformat()
    # Prune old entries
    history = [h for h in history if h.get("detected_at", "") > cutoff]

    for issue in new_issues:
        history.append({
            "category": issue["category"],
            "description": issue["description"],
            "detected_at": issue["detected_at"]
        })

    # Count by category in last 7 days
    category_counts = {}
    for h in history:
        cat = h.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    for cat, count in category_counts.items():
        if count >= PATTERN_ESCALATION_COUNT:
            escalated.append(make_issue("CRITICAL", "pattern_recurrence",
                f"Issue category '{cat}' fired {count}x in 7 days — design flaw, not incident",
                {"category": cat, "count": count, "threshold": PATTERN_ESCALATION_COUNT}))

    patterns["history"] = history
    save_json(PATTERN_PATH, patterns)
    return escalated

# ─── MAIN ───
def run_checks():
    all_issues = []

    all_issues.extend(check_sentiment_freshness())
    all_issues.extend(check_intel_signals_ttl())
    all_issues.extend(check_scanner_health())
    all_issues.extend(check_factor_inputs())
    all_issues.extend(check_alerts_integrity())

    # Pattern frequency on all found issues
    all_issues.extend(check_pattern_frequency(all_issues))

    # Save locally
    save_json(ISSUES_PATH, {
        "bot": BOT_NAME,
        "checked_at": now_utc().isoformat(),
        "issue_count": len(all_issues),
        "issues": all_issues
    })

    # Push to Supabase
    for issue in all_issues:
        push_to_supabase(issue)

    # Summary
    crits = sum(1 for i in all_issues if i["severity"] == "CRITICAL")
    warns = sum(1 for i in all_issues if i["severity"] == "WARN")
    infos = sum(1 for i in all_issues if i["severity"] == "INFO")

    print(f"[SHIL] Vex system check complete: {crits} CRITICAL, {warns} WARN, {infos} INFO")
    for issue in all_issues:
        print(f"  [{issue['severity']}] {issue['category']}: {issue['description']}")

    return all_issues

if __name__ == "__main__":
    issues = run_checks()
    sys.exit(1 if any(i["severity"] == "CRITICAL" for i in issues) else 0)
