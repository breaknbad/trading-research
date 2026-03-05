"""Slippage Tracker - Records and analyzes execution slippage per trade."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

import requests
from datetime import datetime, timezone


def log_slippage(ticker, signal_price, fill_price, side, quantity):
    """Log a single trade's slippage to Supabase."""
    slippage_pct = abs(fill_price - signal_price) / signal_price * 100 if signal_price else 0
    slippage_dollars = abs(fill_price - signal_price) * quantity

    record = {
        "bot_id": BOT_ID,
        "ticker": ticker.upper(),
        "signal_price": signal_price,
        "fill_price": fill_price,
        "side": side,
        "quantity": quantity,
        "slippage_pct": round(slippage_pct, 6),
        "slippage_dollars": round(slippage_dollars, 4),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }

    headers = {**SUPABASE_HEADERS, "Prefer": "resolution=merge-duplicates"}
    r = requests.post(f"{SUPABASE_URL}/rest/v1/slippage_log", headers=headers, json=record)

    alert = slippage_pct > 0.15
    return {
        "ticker": ticker,
        "slippage_pct": round(slippage_pct, 6),
        "slippage_dollars": round(slippage_dollars, 4),
        "alert": alert,
        "stored": r.status_code in (200, 201),
    }


def daily_slippage_report(date_str=None):
    """Aggregate slippage stats for a given day (default: today)."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    start = f"{date_str}T00:00:00Z"
    end = f"{date_str}T23:59:59Z"

    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/slippage_log"
        f"?bot_id=eq.{BOT_ID}&logged_at=gte.{start}&logged_at=lte.{end}&select=*",
        headers=SUPABASE_HEADERS,
    )
    rows = r.json() if r.status_code == 200 else []

    if not rows:
        return {"date": date_str, "trade_count": 0, "avg_slippage_pct": 0, "total_slippage_dollars": 0, "alert": False}

    pcts = [row["slippage_pct"] for row in rows]
    dollars = [row["slippage_dollars"] for row in rows]
    avg_pct = sum(pcts) / len(pcts)

    return {
        "date": date_str,
        "trade_count": len(rows),
        "avg_slippage_pct": round(avg_pct, 6),
        "max_slippage_pct": round(max(pcts), 6),
        "total_slippage_dollars": round(sum(dollars), 2),
        "alert": avg_pct > 0.15,
        "worst_ticker": max(rows, key=lambda x: x["slippage_pct"])["ticker"],
    }


if __name__ == "__main__":
    print("=== Slippage Tracker Test ===")
    result = log_slippage("AAPL", 185.50, 185.62, "buy", 100)
    print(f"Log result: {result}")
    report = daily_slippage_report()
    print(f"Daily report: {report}")
