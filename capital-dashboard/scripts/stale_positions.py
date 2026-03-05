#!/usr/bin/env python3
"""Stale position detector - finds positions that aren't moving."""

import argparse
import json
import urllib.request
from datetime import datetime, timezone

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwi"
    "cm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3"
    "MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def supabase_get(path):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def get_current_price(ticker):
    """Get current price from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        meta = data["chart"]["result"][0]["meta"]
        return meta.get("regularMarketPrice") or meta.get("previousClose")
    except Exception:
        return None


def trading_days_since(date_str):
    """Rough trading days: weekdays between date and now."""
    # Python 3.9 doesn't handle all ISO formats; strip fractional+tz and parse
    clean = date_str.split("+")[0].split("Z")[0]
    if "." in clean:
        clean = clean[:clean.index(".")]
    dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days = 0
    current = dt
    from datetime import timedelta
    while current.date() < now.date():
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


def find_stale_positions():
    """Query all open BUY trades and check for staleness."""
    trades = supabase_get(
        "trades?select=*&action=eq.BUY&status=eq.OPEN&order=created_at.asc"
    )

    results = []
    for t in trades:
        ticker = t.get("ticker")
        if not ticker:
            continue
        entry_price = float(t.get("price_usd") or 0)
        if entry_price <= 0:
            continue

        created = t.get("timestamp") or t.get("created_at")
        if not created:
            continue

        days_held = trading_days_since(created)
        current_price = get_current_price(ticker)
        if current_price is None:
            continue

        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        bot = t.get("bot_id") or "unknown"

        flag = None
        if days_held > 3 and pnl_pct < 0:
            flag = "DEAD MONEY"
        elif days_held > 2 and pnl_pct < 1:
            flag = "STALE"

        if flag:
            results.append({
                "flag": flag,
                "bot": bot,
                "ticker": ticker,
                "entry": entry_price,
                "current": current_price,
                "days": days_held,
                "pnl_pct": pnl_pct,
            })

    return results


def format_table(positions):
    if not positions:
        return "✅ No stale or dead money positions found."
    header = f"{'Flag':<12} {'Bot':<15} {'Ticker':<8} {'Entry':>8} {'Now':>8} {'Days':>5} {'P&L%':>7}"
    sep = "-" * len(header)
    lines = [header, sep]
    for p in positions:
        lines.append(
            f"{p['flag']:<12} {p['bot']:<15} {p['ticker']:<8} "
            f"${p['entry']:>7.2f} ${p['current']:>7.2f} {p['days']:>5} "
            f"{p['pnl_pct']:>+6.1f}%"
        )
    return "\n".join(lines)


def execute_sell(bot, ticker, qty, price, reason):
    """Execute a sell via log_trade.py."""
    import subprocess, os
    cmd = [
        "python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_trade.py"),
        "--bot", bot, "--action", "SELL", "--ticker", ticker,
        "--qty", str(qty), "--price", str(price),
        "--reason", f"[STALE_POSITION] {reason}", "--skip-validation"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✅ EXECUTED: SELL {ticker} {qty}x @ ${price:.2f} — {reason}")
            return True
        else:
            print(f"  ❌ FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Stale position detector")
    parser.add_argument("--post", action="store_true", help="Post alert to Discord")
    parser.add_argument("--auto-trim", action="store_true", help="Auto-trim DEAD MONEY positions (sell 50%)")
    args = parser.parse_args()

    print("Scanning open positions...")
    positions = find_stale_positions()
    output = format_table(positions)
    print(output)

    if args.auto_trim and positions:
        for p in positions:
            if p["flag"] == "DEAD MONEY" and p["current"] > 0:
                # Dead money = held >3 days, negative P&L. Trim 50%.
                qty = float(supabase_get(
                    f"trades?bot_id=eq.{p['bot']}&ticker=eq.{p['ticker']}&status=eq.OPEN&action=eq.BUY&select=quantity&limit=1"
                )[0]["quantity"]) * 0.5
                execute_sell(p["bot"], p["ticker"], round(qty, 6), p["current"],
                             f"Held {p['days']} days at {p['pnl_pct']:+.1f}% — dead money trim 50%")
            elif p["flag"] == "STALE" and p["pnl_pct"] < -1:
                # Stale + losing = trim 25%
                qty = float(supabase_get(
                    f"trades?bot_id=eq.{p['bot']}&ticker=eq.{p['ticker']}&status=eq.OPEN&action=eq.BUY&select=quantity&limit=1"
                )[0]["quantity"]) * 0.25
                execute_sell(p["bot"], p["ticker"], round(qty, 6), p["current"],
                             f"Stale {p['days']} days at {p['pnl_pct']:+.1f}% — trim 25%")

    if args.post and positions:
        print("\n--post flag set but Discord posting requires the bot framework.")
        print("Output above can be piped to Discord via webhook or bot command.")


if __name__ == "__main__":
    main()
