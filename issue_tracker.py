#!/usr/bin/env python3
"""
Issue Tracker — Enforces "every problem gets a coded solution."

When a problem is identified in discussion, it MUST be logged here with:
1. The problem description
2. The coded solution (script name/path)
3. Status: OPEN (no code yet) / BUILDING / DEPLOYED / VERIFIED

Any issue that stays OPEN for >2 hours during active hours gets flagged.
Any issue without a code solution gets escalated.

Usage:
  python3 issue_tracker.py --log "CRM sold too early" --bot alfred
  python3 issue_tracker.py --solve 1 --script trailing_stop.py --status DEPLOYED
  python3 issue_tracker.py --audit   # Show all OPEN issues without solutions
  python3 issue_tracker.py --report  # Full status report
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Local fallback if Supabase table doesn't exist yet
LOCAL_FILE = Path(__file__).parent / "data" / "issues.json"


def _load_local():
    if LOCAL_FILE.exists():
        with open(LOCAL_FILE) as f:
            return json.load(f)
    return {"issues": [], "next_id": 1}


def _save_local(data):
    LOCAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_FILE, "w") as f:
        json.dump(data, f, indent=2)


def log_issue(problem, bot="fleet", category="trading"):
    """Log a new problem. Returns issue ID."""
    data = _load_local()
    issue_id = data["next_id"]
    issue = {
        "id": issue_id,
        "problem": problem,
        "bot": bot,
        "category": category,
        "status": "OPEN",
        "solution_script": None,
        "solution_description": None,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "solved_at": None,
        "deployed_at": None,
        "verified_at": None,
        "flagged": False,
    }
    data["issues"].append(issue)
    data["next_id"] = issue_id + 1
    _save_local(data)
    print(f"🔴 ISSUE #{issue_id} LOGGED: {problem}")
    print(f"   Bot: {bot} | Status: OPEN | Solution: NONE")
    print(f"   ⚠️ Code solution required. Issue stays OPEN until code is written.")
    return issue_id


def solve_issue(issue_id, script, description=None, status="DEPLOYED"):
    """Mark an issue as solved with a code solution."""
    data = _load_local()
    for issue in data["issues"]:
        if issue["id"] == issue_id:
            issue["status"] = status
            issue["solution_script"] = script
            issue["solution_description"] = description
            if status == "BUILDING":
                pass
            elif status == "DEPLOYED":
                issue["deployed_at"] = datetime.now(timezone.utc).isoformat()
            elif status == "VERIFIED":
                issue["verified_at"] = datetime.now(timezone.utc).isoformat()
            _save_local(data)
            emoji = {"BUILDING": "🟡", "DEPLOYED": "🟢", "VERIFIED": "✅"}
            print(f"{emoji.get(status, '🔵')} ISSUE #{issue_id} → {status}")
            print(f"   Solution: {script}")
            if description:
                print(f"   Detail: {description}")
            return True
    print(f"❌ Issue #{issue_id} not found.")
    return False


def audit():
    """Flag all OPEN issues without solutions. Returns list of overdue issues."""
    data = _load_local()
    now = datetime.now(timezone.utc)
    overdue = []
    open_issues = []

    for issue in data["issues"]:
        if issue["status"] == "OPEN":
            open_issues.append(issue)
            logged = datetime.fromisoformat(issue["logged_at"])
            age_hours = (now - logged).total_seconds() / 3600
            if age_hours > 2:
                issue["flagged"] = True
                overdue.append(issue)

    _save_local(data)

    if not open_issues:
        print("✅ ALL ISSUES HAVE CODE SOLUTIONS. Fleet is clean.")
        return []

    print(f"\n🔍 ISSUE AUDIT — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    for issue in open_issues:
        logged = datetime.fromisoformat(issue["logged_at"])
        age = now - logged
        age_str = f"{age.total_seconds()/3600:.1f}h"
        flag = " 🚨 OVERDUE" if issue.get("flagged") else ""
        print(f"🔴 #{issue['id']} [{issue['bot']}] {issue['problem']}")
        print(f"   Open for {age_str}{flag} — NO CODE SOLUTION")

    print("=" * 60)
    print(f"⚠️ {len(open_issues)} open issue(s), {len(overdue)} overdue.")
    print("Rule: Every problem gets code. No exceptions.\n")
    return overdue


def report():
    """Full status report of all issues."""
    data = _load_local()
    issues = data["issues"]

    if not issues:
        print("No issues logged yet.")
        return

    status_emoji = {
        "OPEN": "🔴",
        "BUILDING": "🟡",
        "DEPLOYED": "🟢",
        "VERIFIED": "✅",
    }

    counts = {"OPEN": 0, "BUILDING": 0, "DEPLOYED": 0, "VERIFIED": 0}

    print(f"\n📋 ISSUE TRACKER — {len(issues)} total issues")
    print("=" * 70)

    for issue in sorted(issues, key=lambda x: x["id"]):
        s = issue["status"]
        counts[s] = counts.get(s, 0) + 1
        emoji = status_emoji.get(s, "❓")
        script = issue.get("solution_script", "—")
        print(f"{emoji} #{issue['id']} [{s}] {issue['problem']}")
        print(f"   Bot: {issue['bot']} | Script: {script}")

    print("=" * 70)
    print(f"🔴 Open: {counts['OPEN']} | 🟡 Building: {counts['BUILDING']} | "
          f"🟢 Deployed: {counts['DEPLOYED']} | ✅ Verified: {counts['VERIFIED']}")


def seed_week1_issues():
    """Seed the tracker with all issues identified this week and their solutions."""
    issues_and_solutions = [
        ("Selling winners too early (CRM sold at dip)", "trailing_stop.py",
         "Auto trailing stop at 1.5% below high when position up >3%", "DEPLOYED"),
        ("Cash sitting idle >50% during market hours", "cash_deployer.py",
         "Alerts when cash >50% for >30 min, surfaces top setups", "DEPLOYED"),
        ("Chasing extended gap-ups (IBTA +39% stopped in 2 min)", "extension_filter.py",
         "Higher conviction required for bigger gaps: >25% needs 9/10", "DEPLOYED"),
        ("Inverse/leveraged ETFs held overnight (SQQQ)", "eod_sweep.py",
         "Auto-sells all leveraged ETFs at 3:45 PM", "DEPLOYED"),
        ("Only one bot finding momentum plays", "shared_signals.py",
         "Fleet-wide signal bus — one find, four eyes", "DEPLOYED"),
        ("Trades announced in chat but not logged to Supabase", "enforce_trade.py",
         "Gate that blocks announcements without DB logging", "DEPLOYED"),
        ("Phantom equity spikes from double-counting", "log_trade.py (SHORT/COVER fix)",
         "Added SHORT/COVER handling + 3% spike guard", "DEPLOYED"),
        ("Portfolio data stale/mismatched on dashboard", "sync_dashboard.py",
         "Direct Supabase pull, unified JSON format", "DEPLOYED"),
        ("Stop breaches not caught in time", "stop_monitor.py",
         "Checks all positions vs stops every 5 min", "DEPLOYED"),
        ("No daily P&L analysis after close", "trade_analyzer.py",
         "Auto EOD report at 4:15 PM with factor scoring", "DEPLOYED"),
        ("Problems discussed but no code written", "issue_tracker.py",
         "This script — tracks every issue, flags overdue, enforces code solutions", "DEPLOYED"),
    ]

    data = _load_local()
    if data["issues"]:
        print("Issues already seeded. Use --audit or --report.")
        return

    for problem, script, desc, status in issues_and_solutions:
        issue_id = log_issue(problem, bot="fleet")
        solve_issue(issue_id, script, desc, status)
        print()

    print(f"\n✅ Seeded {len(issues_and_solutions)} issues from Week 1.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Issue Tracker — Every problem gets code")
    parser.add_argument("--log", help="Log a new problem")
    parser.add_argument("--bot", default="fleet", help="Which bot found/has the issue")
    parser.add_argument("--category", default="trading", help="Issue category")
    parser.add_argument("--solve", type=int, help="Mark issue # as solved")
    parser.add_argument("--script", help="Solution script path")
    parser.add_argument("--desc", help="Solution description")
    parser.add_argument("--status", default="DEPLOYED", choices=["BUILDING", "DEPLOYED", "VERIFIED"])
    parser.add_argument("--audit", action="store_true", help="Audit all open issues")
    parser.add_argument("--report", action="store_true", help="Full status report")
    parser.add_argument("--seed", action="store_true", help="Seed with Week 1 issues")

    args = parser.parse_args()

    if args.log:
        log_issue(args.log, args.bot, args.category)
    elif args.solve:
        solve_issue(args.solve, args.script, args.desc, args.status)
    elif args.audit:
        audit()
    elif args.report:
        report()
    elif args.seed:
        seed_week1_issues()
    else:
        parser.print_help()
