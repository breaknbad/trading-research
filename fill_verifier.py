"""Fill Verifier - Post-order verification for paper trades logged to Supabase."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

import requests
from datetime import datetime, timezone, timedelta

REQUIRED_FIELDS = ["trade_id", "bot_id", "ticker", "side", "quantity", "fill_price", "filled_at"]


def verify_fill(trade_id):
    """Verify a single trade was logged correctly."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?trade_id=eq.{trade_id}&select=*",
        headers=SUPABASE_HEADERS,
    )
    rows = r.json() if r.status_code == 200 else []
    issues = []

    if not rows:
        return {"verified": False, "issues": ["Trade not found in database."]}

    if len(rows) > 1:
        issues.append(f"Duplicate trade_id: {len(rows)} records found.")

    trade = rows[0]

    # Missing fields
    for field in REQUIRED_FIELDS:
        val = trade.get(field)
        if val is None or val == "":
            issues.append(f"Missing field: {field}")

    # Price sanity
    price = float(trade.get("fill_price", 0) or 0)
    if price <= 0:
        issues.append(f"Impossible price: {price} (<=0)")

    prev_close = float(trade.get("prev_close", 0) or 0)
    if prev_close > 0 and price > prev_close * 10:
        issues.append(f"Price {price} exceeds 10x previous close {prev_close}")

    # Quantity sanity
    qty = float(trade.get("quantity", 0) or 0)
    if qty <= 0:
        issues.append(f"Invalid quantity: {qty}")

    return {"verified": len(issues) == 0, "issues": issues, "trade_id": trade_id}


def verify_all_recent(minutes=30):
    """Verify all trades logged in the last N minutes."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{BOT_ID}&filled_at=gte.{cutoff}&select=trade_id",
        headers=SUPABASE_HEADERS,
    )
    rows = r.json() if r.status_code == 200 else []

    results = []
    for row in rows:
        tid = row.get("trade_id")
        if tid:
            results.append(verify_fill(tid))

    passed = sum(1 for r in results if r["verified"])
    failed = [r for r in results if not r["verified"]]

    return {
        "checked": len(results),
        "passed": passed,
        "failed": len(failed),
        "failures": failed,
    }


if __name__ == "__main__":
    print("=== Fill Verifier Test ===")
    recent = verify_all_recent(minutes=60)
    print(f"Recent verification: {recent}")
