#!/usr/bin/env python3
"""Data integrity checker — validates Supabase trade records."""

import sys, os, json, urllib.request
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

TRADES_ENDPOINT = f"{SUPABASE_URL}/rest/v1/trades"
REQUIRED_FIELDS = ["id", "ticker", "action", "qty", "price", "timestamp", "bot_id"]


def _fetch_trades(limit=1000) -> list:
    url = f"{TRADES_ENDPOINT}?bot_id=eq.{BOT_ID}&order=timestamp.asc&limit={limit}"
    req = urllib.request.Request(url, headers=SUPABASE_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _check_duplicates(trades: list) -> list:
    ids = [t["id"] for t in trades]
    dupes = [tid for tid, count in Counter(ids).items() if count > 1]
    return [f"Duplicate trade ID: {d}" for d in dupes]


def _check_orphaned_exits(trades: list) -> list:
    issues = []
    buys = {}  # ticker -> count
    for t in trades:
        ticker = t.get("ticker", "")
        action = t.get("action", "").upper()
        if action == "BUY":
            buys[ticker] = buys.get(ticker, 0) + t.get("qty", 0)
        elif action == "SELL":
            if ticker not in buys or buys[ticker] <= 0:
                issues.append(f"Orphaned SELL for {ticker} at {t.get('timestamp', '?')} — no matching BUY")
            else:
                buys[ticker] -= t.get("qty", 0)
    return issues


def _check_null_fields(trades: list) -> list:
    issues = []
    for t in trades:
        for field in REQUIRED_FIELDS:
            if t.get(field) is None:
                issues.append(f"Null {field} in trade {t.get('id', '?')}")
    return issues


def _check_timestamp_order(trades: list) -> list:
    issues = []
    for i in range(1, len(trades)):
        if trades[i].get("timestamp", "") < trades[i - 1].get("timestamp", ""):
            issues.append(
                f"Timestamp order violation: trade {trades[i].get('id')} "
                f"({trades[i].get('timestamp')}) before {trades[i-1].get('id')} "
                f"({trades[i-1].get('timestamp')})"
            )
    return issues


def _check_qty_mismatches(trades: list) -> list:
    issues = []
    positions = {}
    for t in trades:
        ticker = t.get("ticker", "")
        action = t.get("action", "").upper()
        qty = t.get("qty", 0)
        if action == "BUY":
            positions[ticker] = positions.get(ticker, 0) + qty
        elif action == "SELL":
            positions[ticker] = positions.get(ticker, 0) - qty

    for ticker, net in positions.items():
        if net < 0:
            issues.append(f"Negative position for {ticker}: {net} shares oversold")
    return issues


def run_integrity_check() -> dict:
    """Run all integrity checks on trade data."""
    try:
        trades = _fetch_trades()
    except Exception as e:
        return {"clean": False, "issues": [f"Failed to fetch trades: {e}"], "checked_at": datetime.now(timezone.utc).isoformat()}

    issues = []
    issues.extend(_check_duplicates(trades))
    issues.extend(_check_orphaned_exits(trades))
    issues.extend(_check_null_fields(trades))
    issues.extend(_check_timestamp_order(trades))
    issues.extend(_check_qty_mismatches(trades))

    return {
        "clean": len(issues) == 0,
        "issues": issues,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "trades_checked": len(trades),
    }


def fix_duplicates(dry_run: bool = True) -> dict:
    """Find and optionally remove duplicate trade records."""
    try:
        trades = _fetch_trades()
    except Exception as e:
        return {"error": str(e), "duplicates": [], "removed": 0}

    seen = {}
    duplicates = []
    for t in trades:
        tid = t["id"]
        if tid in seen:
            duplicates.append(t)
        else:
            seen[tid] = t

    removed = 0
    if not dry_run and duplicates:
        for dup in duplicates:
            try:
                url = f"{TRADES_ENDPOINT}?id=eq.{dup['id']}&timestamp=eq.{dup['timestamp']}"
                req = urllib.request.Request(url, method="DELETE", headers=SUPABASE_HEADERS)
                urllib.request.urlopen(req, timeout=10)
                removed += 1
            except Exception:
                pass

    return {
        "dry_run": dry_run,
        "duplicates_found": len(duplicates),
        "removed": removed,
        "duplicate_ids": [d["id"] for d in duplicates],
    }


if __name__ == "__main__":
    result = run_integrity_check()
    print(json.dumps(result, indent=2))
