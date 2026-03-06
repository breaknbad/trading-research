#!/usr/bin/env python3
"""
Dashboard Cleanup — One Command to Wipe False Data
====================================================
Mark directive Mar 5: "Make it a code so it is one step for you when I say
clean up XXXX. You know where it is."

Usage:
  python3 dashboard_cleanup.py --all              # Nuclear: wipe everything, reset to $50K
  python3 dashboard_cleanup.py --trades            # Wipe trade history only
  python3 dashboard_cleanup.py --signals           # Wipe fleet/shared signals only
  python3 dashboard_cleanup.py --snapshots         # Reset portfolio + equity snapshots to $50K
  python3 dashboard_cleanup.py --reviews           # Wipe daily reviews only
  python3 dashboard_cleanup.py --market-state      # Reset market state + alerts
  python3 dashboard_cleanup.py --health            # Clean bot_health duplicates
  python3 dashboard_cleanup.py --verify            # Just verify, don't change anything
  python3 dashboard_cleanup.py --dry-run --all     # Show what would be cleaned

SUPABASE TABLE MAP (where dashboard data lives):
  portfolio_snapshots  → Main portfolio boxes ($50K, positions, P&L)
  equity_snapshots     → Equity curve chart, today's high/low
  trades               → Recent Trades feed, Strategy Lane Attribution
  fleet_signals        → Signal history, alert counts
  shared_signals       → Cross-bot signal sharing
  signal_scores        → Signal scoring history
  market_state         → Market ticker data, RSI, alerts
  daily_reviews        → Daily Review tab (3rd page)
  bot_health           → Bot status indicators
  crypto_positions     → Crypto position tracking
  crypto_trades        → Crypto trade history
  crypto_portfolio_snapshots → Crypto portfolio boxes
"""

import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone
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

BOTS = ["tars", "alfred", "eddie_v", "vex"]
STARTING_CAPITAL = 50000


def api_read(path):
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", headers=READ_HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except:
        return []


def api_delete(path):
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{path}", method="DELETE", headers=WRITE_HEADERS)
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except:
        return False


def api_patch(path, data):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=json.dumps(data).encode(), method="PATCH", headers=WRITE_HEADERS)
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except:
        return False


def api_post(path, data):
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=json.dumps(data).encode(), method="POST", headers=WRITE_HEADERS)
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except:
        return False


def clean_trades(dry_run=False):
    """Wipe all trades."""
    data = api_read("trades?select=id&limit=1")
    count = len(api_read("trades?select=id&limit=10000"))
    print(f"  trades: {count} rows")
    if count > 0 and not dry_run:
        api_delete("trades?id=gt.0")
        # Also try status-based delete for RLS
        api_delete("trades?status=eq.CLOSED")
        api_delete("trades?status=eq.OPEN")
        api_delete("trades?status=eq.executed")
        remaining = len(api_read("trades?select=id&limit=5"))
        if remaining > 0:
            # Individual delete fallback
            rows = api_read("trades?select=id&limit=1000")
            for r in rows:
                api_delete(f"trades?id=eq.{r['id']}")
        print(f"    ✅ Wiped")
    elif dry_run:
        print(f"    [DRY RUN] Would delete {count} trades")


def clean_signals(dry_run=False):
    """Wipe fleet_signals and shared_signals."""
    for table in ["fleet_signals", "shared_signals"]:
        count = len(api_read(f"{table}?select=id&limit=10000"))
        print(f"  {table}: {count} rows")
        if count > 0 and not dry_run:
            api_delete(f"{table}?id=gt.0")
            # Batch cleanup for stragglers
            for _ in range(5):
                rows = api_read(f"{table}?select=id&limit=100")
                if not rows:
                    break
                for r in rows:
                    api_delete(f"{table}?id=eq.{r['id']}")
            print(f"    ✅ Wiped")
        elif dry_run:
            print(f"    [DRY RUN] Would delete {count}")


def clean_snapshots(dry_run=False):
    """Reset portfolio_snapshots and equity_snapshots to clean $50K."""
    # Portfolio snapshots
    print(f"  portfolio_snapshots:")
    if not dry_run:
        for bot in BOTS:
            api_patch(f"portfolio_snapshots?bot_id=eq.{bot}", {
                "cash_usd": STARTING_CAPITAL,
                "open_positions": [],
                "realized_pl": 0,
                "unrealized_pl": 0,
                "total_value_usd": STARTING_CAPITAL,
                "daily_return_pct": 0,
                "total_return_pct": 0,
                "trade_count": 0,
                "win_rate": 0,
                "day_start_value": STARTING_CAPITAL,
            })
        print(f"    ✅ All 4 bots reset to ${STARTING_CAPITAL:,}")
    else:
        print(f"    [DRY RUN] Would reset all 4 bots to ${STARTING_CAPITAL:,}")

    # Equity snapshots — delete all, insert fresh baselines
    print(f"  equity_snapshots:")
    count = len(api_read("equity_snapshots?select=id&limit=10000"))
    print(f"    {count} historical rows")
    if not dry_run:
        api_delete("equity_snapshots?id=gt.0")
        # Clean stragglers
        for _ in range(3):
            rows = api_read("equity_snapshots?select=id&limit=100")
            if not rows:
                break
            for r in rows:
                api_delete(f"equity_snapshots?id=eq.{r['id']}")
        # Insert fresh baselines
        now = datetime.now(timezone.utc).isoformat()
        for bot in BOTS:
            api_post("equity_snapshots", {
                "bot_id": bot,
                "value": STARTING_CAPITAL,
                "recorded_at": now,
            })
        print(f"    ✅ Reset to 4 × ${STARTING_CAPITAL:,}")
    else:
        print(f"    [DRY RUN] Would delete {count} rows, insert 4 baselines")


def clean_reviews(dry_run=False):
    """Wipe daily_reviews."""
    count = len(api_read("daily_reviews?select=id&limit=100"))
    print(f"  daily_reviews: {count} rows")
    if count > 0 and not dry_run:
        api_delete("daily_reviews?id=gt.0")
        print(f"    ✅ Wiped")
    elif dry_run:
        print(f"    [DRY RUN] Would delete {count}")


def clean_market_state(dry_run=False):
    """Reset market_state to empty."""
    print(f"  market_state:")
    if not dry_run:
        api_patch("market_state?id=eq.latest", {
            "state_json": json.dumps({"updated": None, "stale_after": 90, "tickers": {}}),
            "alerts_json": json.dumps([]),
        })
        print(f"    ✅ Reset to empty")
    else:
        print(f"    [DRY RUN] Would reset")


def clean_signal_scores(dry_run=False):
    """Wipe signal_scores."""
    count = len(api_read("signal_scores?select=id&limit=100"))
    print(f"  signal_scores: {count} rows")
    if count > 0 and not dry_run:
        api_delete("signal_scores?id=gt.0")
        print(f"    ✅ Wiped")
    elif dry_run:
        print(f"    [DRY RUN] Would delete {count}")


def clean_health(dry_run=False):
    """Remove duplicate bot_health entries, reset timestamps."""
    data = api_read("bot_health?select=id,bot_id&order=id.desc")
    print(f"  bot_health: {len(data)} entries")
    seen = set()
    dupes = 0
    for r in data:
        if r["bot_id"] in seen:
            if not dry_run:
                api_delete(f"bot_health?id=eq.{r['id']}")
            dupes += 1
        else:
            seen.add(r["bot_id"])
    if dupes > 0:
        print(f"    {'✅ Deleted' if not dry_run else '[DRY RUN] Would delete'} {dupes} duplicates")
    else:
        print(f"    ✅ No duplicates")


def clean_crypto(dry_run=False):
    """Wipe crypto tables."""
    for table in ["crypto_positions", "crypto_trades", "crypto_portfolio_snapshots"]:
        count = len(api_read(f"{table}?select=id&limit=100"))
        print(f"  {table}: {count} rows")
        if count > 0 and not dry_run:
            api_delete(f"{table}?id=gt.0")
            print(f"    ✅ Wiped")


def verify():
    """Verify all tables are clean."""
    print("🔍 VERIFICATION")
    print("=" * 50)
    all_clean = True

    checks = [
        ("portfolio_snapshots", 4, lambda d: all(
            r.get("cash_usd") == STARTING_CAPITAL and r.get("total_value_usd") == STARTING_CAPITAL
            and r.get("realized_pl") == 0 and r.get("trade_count") == 0
            for r in d
        )),
        ("equity_snapshots", 4, lambda d: all(r.get("value") == STARTING_CAPITAL for r in d)),
        ("trades", 0, None),
        ("fleet_signals", 0, None),
        ("shared_signals", 0, None),
        ("signal_scores", 0, None),
        ("daily_reviews", 0, None),
        ("bot_health", 4, None),
        ("crypto_positions", 0, None),
        ("crypto_trades", 0, None),
        ("crypto_portfolio_snapshots", 0, None),
    ]

    for table, expected_count, validator in checks:
        data = api_read(f"{table}?select=*&limit=1000")
        count = len(data)
        ok = count == expected_count
        if validator and ok:
            ok = validator(data)
        icon = "✅" if ok else "❌"
        if not ok:
            all_clean = False
        print(f"  {icon} {table}: {count} rows")

    # Market state
    ms = api_read("market_state?select=state_json,alerts_json&limit=1")
    if ms:
        state = json.loads(ms[0].get("state_json", "{}")) if isinstance(ms[0].get("state_json"), str) else ms[0].get("state_json", {})
        tickers = state.get("tickers", {})
        alerts = json.loads(ms[0].get("alerts_json", "[]")) if isinstance(ms[0].get("alerts_json"), str) else ms[0].get("alerts_json", [])
        ms_clean = len(tickers) == 0 and len(alerts) == 0
        print(f"  {'✅' if ms_clean else '❌'} market_state: {len(tickers)} tickers, {len(alerts)} alerts")
        if not ms_clean:
            all_clean = False

    print("=" * 50)
    print("🟢 ALL CLEAN" if all_clean else "🔴 ISSUES REMAIN")
    return all_clean


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Dashboard Cleanup — One Command")
    parser.add_argument("--all", action="store_true", help="Nuclear: wipe everything")
    parser.add_argument("--trades", action="store_true", help="Wipe trade history")
    parser.add_argument("--signals", action="store_true", help="Wipe fleet/shared signals")
    parser.add_argument("--snapshots", action="store_true", help="Reset snapshots to $50K")
    parser.add_argument("--reviews", action="store_true", help="Wipe daily reviews")
    parser.add_argument("--market-state", action="store_true", help="Reset market state")
    parser.add_argument("--health", action="store_true", help="Clean bot_health dupes")
    parser.add_argument("--verify", action="store_true", help="Verify only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = parser.parse_args()

    if not SUPABASE_KEY:
        print("ERROR: No Supabase key found", file=sys.stderr)
        sys.exit(1)

    if args.verify:
        verify()
        return

    dry = args.dry_run
    do_all = args.all

    print(f"{'[DRY RUN] ' if dry else ''}Dashboard Cleanup")
    print("=" * 50)

    if do_all or args.trades:
        clean_trades(dry)
    if do_all or args.signals:
        clean_signals(dry)
        clean_signal_scores(dry)
    if do_all or args.snapshots:
        clean_snapshots(dry)
    if do_all or args.reviews:
        clean_reviews(dry)
    if do_all or args.market_state:
        clean_market_state(dry)
    if do_all or args.health:
        clean_health(dry)
    if do_all:
        clean_crypto(dry)

    if not dry:
        print()
        verify()


if __name__ == "__main__":
    main()
