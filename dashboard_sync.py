#!/usr/bin/env python3
"""Dashboard sync: updates alfred.json and pushes to git."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    sys.exit(1)

import config


def _supabase_get(path):
    try:
        r = requests.get(f"{config.SUPABASE_URL}/rest/v1/{path}", headers=config.SUPABASE_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [ERR] Supabase: {e}")
    return None


def _finnhub_price(ticker):
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": config.FINNHUB_KEY},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("c", 0)
    except Exception:
        pass
    return None


def sync_dashboard(verbose=True, push=True):
    """Pull data from Supabase, update dashboard JSON, optionally git push."""
    if verbose:
        print("[DASHBOARD] Syncing alfred.json...")

    # Get portfolio
    portfolio_data = _supabase_get(f"portfolio_snapshots?bot_id=eq.{config.BOT_ID}&select=*")
    if not portfolio_data:
        print("  [WARN] No portfolio data")
        return False

    portfolio = portfolio_data[0]
    positions = portfolio.get("open_positions", []) or []

    # Update live prices
    for i, pos in enumerate(positions):
        ticker = pos.get("ticker", "")
        if i > 0 and i % 30 == 0:
            time.sleep(1)
        price = _finnhub_price(ticker)
        if price and price > 0:
            pos["current_price"] = price
            entry = float(pos.get("avg_entry", price))
            qty = float(pos.get("quantity", 0))
            side = pos.get("side", "LONG")
            if side == "LONG":
                pos["unrealized_pl"] = round((price - entry) * qty, 2)
            else:
                pos["unrealized_pl"] = round((entry - price) * qty, 2)

    # Recalc totals
    cash = float(portfolio.get("cash_usd", 0))
    pos_value = sum(float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0))) for p in positions)
    total_value = cash + pos_value

    # Get recent trades
    trades_data = _supabase_get(
        f"trades?bot_id=eq.{config.BOT_ID}&select=*&order=timestamp.desc&limit=20"
    ) or []

    # Build dashboard JSON
    dashboard = {
        "bot_id": config.BOT_ID,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_value_usd": round(total_value, 2),
        "cash_usd": round(cash, 2),
        "total_return_pct": round(((total_value - config.STARTING_CAPITAL) / config.STARTING_CAPITAL) * 100, 2),
        "positions": positions,
        "recent_trades": [
            {
                "trade_id": t.get("trade_id"),
                "timestamp": t.get("timestamp"),
                "action": t.get("action"),
                "ticker": t.get("ticker"),
                "quantity": t.get("quantity"),
                "price_usd": t.get("price_usd"),
                "reason": t.get("reason"),
            }
            for t in trades_data
        ],
        "trade_count": int(portfolio.get("trade_count", 0)),
    }

    # Write JSON
    os.makedirs(config.DASHBOARD_DIR, exist_ok=True)
    json_path = os.path.join(config.DASHBOARD_DIR, "alfred.json")
    with open(json_path, "w") as f:
        json.dump(dashboard, f, indent=2)

    if verbose:
        print(f"  Wrote {json_path}")
        print(f"  Total: ${total_value:.2f} | Cash: ${cash:.2f} | Positions: {len(positions)}")

    # Git push
    if push:
        try:
            dashboard_root = os.path.join(config.BASE_DIR, "dashboard")
            if os.path.isdir(os.path.join(dashboard_root, ".git")):
                git_dir = dashboard_root
            elif os.path.isdir(os.path.join(config.BASE_DIR, ".git")):
                git_dir = config.BASE_DIR
            else:
                if verbose:
                    print("  [SKIP] No git repo found")
                return True

            subprocess.run(["git", "add", json_path], cwd=git_dir, capture_output=True, timeout=10)
            result = subprocess.run(
                ["git", "commit", "-m", f"alfred dashboard sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
                cwd=git_dir, capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                subprocess.run(["git", "push", "origin", "main"], cwd=git_dir, capture_output=True, timeout=30)
                if verbose:
                    print("  Git push complete")
            else:
                if verbose:
                    print("  [SKIP] Nothing to commit")
        except Exception as e:
            if verbose:
                print(f"  [WARN] Git: {e}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync dashboard data")
    parser.add_argument("--no-push", action="store_true", help="Skip git push")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    sync_dashboard(verbose=not args.quiet, push=not args.no_push)
