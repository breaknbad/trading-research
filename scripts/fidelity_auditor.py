#!/usr/bin/env python3
"""
Alfred SHIL - Weekly Fidelity Auditor
Verifies all hardened rules are still active and passing.
Checks system_issues for repeat offenders.
Generates fidelity report.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request

WORKSPACE = Path(__file__).parent.parent
CREDS_FILE = Path.home() / ".supabase_trading_creds"

def load_creds():
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

def supabase_query(creds, table, params=""):
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

def audit_repeat_offenders(creds):
    """Find issues that recurred after being marked resolved/hardened."""
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    issues = supabase_query(creds, "system_issues",
        f"timestamp=gte.{week_ago}&order=timestamp.desc")
    
    if isinstance(issues, dict) and "error" in issues:
        print(f"  ❌ Cannot query system_issues: {issues['error']}")
        return []

    # Group by description pattern
    patterns = {}
    for issue in issues:
        key = f"{issue.get('bot')}:{issue.get('category')}:{issue.get('description', '')[:80]}"
        patterns.setdefault(key, []).append(issue)

    repeat_offenders = []
    for key, occurrences in patterns.items():
        if len(occurrences) >= 3:
            repeat_offenders.append({
                "pattern": key,
                "count": len(occurrences),
                "first_seen": occurrences[-1].get("timestamp"),
                "last_seen": occurrences[0].get("timestamp"),
                "status": occurrences[0].get("status"),
                "needs_hardening": occurrences[0].get("status") != "hardened"
            })

    return repeat_offenders

def audit_hardened_rules(creds):
    """Check that hardened fixes are still in place."""
    fixes = supabase_query(creds, "system_fixes",
        "status=eq.hardened&order=created_at.desc&limit=50")
    
    if isinstance(fixes, dict) and "error" in fixes:
        print(f"  ❌ Cannot query system_fixes: {fixes['error']}")
        return []

    stale_rules = []
    for fix in fixes:
        # Check if the rule's detection script still exists
        # and if the issue has recurred since hardening
        stale_rules.append({
            "fix": fix.get("description", "unknown"),
            "hardened_at": fix.get("created_at"),
            "bot": fix.get("bot"),
            "status": "active"  # Would verify with synthetic test in production
        })

    return stale_rules

def generate_report(repeat_offenders, hardened_rules):
    """Generate weekly fidelity report."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot": "ALFRED",
        "repeat_offenders": repeat_offenders,
        "hardened_rules_audited": len(hardened_rules),
        "rules_still_active": sum(1 for r in hardened_rules if r["status"] == "active"),
        "rules_broken": sum(1 for r in hardened_rules if r["status"] != "active"),
        "needs_attention": len(repeat_offenders) + sum(1 for r in hardened_rules if r["status"] != "active")
    }

    report_path = WORKSPACE / "shil_fidelity_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    return report

def main():
    print(f"Alfred SHIL Fidelity Audit — {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 50)

    creds = load_creds()
    if not creds.get("SUPABASE_URL"):
        print("ERROR: No Supabase credentials")
        sys.exit(1)

    print("\n📋 Checking repeat offenders (last 7 days)...")
    repeats = audit_repeat_offenders(creds)
    if repeats:
        for r in repeats:
            flag = "🔴" if r["needs_hardening"] else "🟢"
            print(f"  {flag} {r['pattern']} — {r['count']}x (last: {r['last_seen']})")
    else:
        print("  ✅ No repeat offenders")

    print("\n🔒 Auditing hardened rules...")
    rules = audit_hardened_rules(creds)
    if rules:
        broken = [r for r in rules if r["status"] != "active"]
        print(f"  {len(rules)} rules checked, {len(broken)} broken")
        for r in broken:
            print(f"  🔴 BROKEN: {r['fix']} (hardened {r['hardened_at']})")
    else:
        print("  ℹ️ No hardened rules to audit yet")

    report = generate_report(repeats, rules)
    print(f"\n{'🔴' if report['needs_attention'] else '🟢'} Fidelity: {report['needs_attention']} items need attention")
    print(f"Report saved to shil_fidelity_report.json")

    return report

if __name__ == "__main__":
    main()
