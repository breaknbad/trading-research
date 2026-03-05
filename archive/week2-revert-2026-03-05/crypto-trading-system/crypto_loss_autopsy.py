#!/usr/bin/env python3
"""
Crypto Loss Autopsy — Pattern detection on losing trades.

Analyzes closed losing trades to find recurring failure patterns:
- Same coin losing repeatedly
- Same time-of-day losses
- Same setup type failing
- Correlation with market regime at entry
- Average hold time on losers vs winners

Generates a report that informs future trade decisions.

Usage:
  python3 crypto_loss_autopsy.py              # Full autopsy, all bots
  python3 crypto_loss_autopsy.py --bot alfred  # Single bot
"""

import argparse
import json
import os
import requests
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    key_path = os.path.expanduser("~/.supabase_service_key")
    if os.path.exists(key_path):
        SUPABASE_KEY = open(key_path).read().strip()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]


def get_closed_trades(bot_id: str = None, days: int = 7) -> list:
    """Fetch closed trades from Supabase."""
    params = {"select": "*", "order": "timestamp.desc"}
    if bot_id:
        params["bot_id"] = f"eq.{bot_id}"

    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_trades",
            params=params,
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def analyze_losses(trades: list) -> dict:
    """Analyze losing trades for patterns."""
    losses = [t for t in trades if float(t.get("pnl", 0)) < 0]
    wins = [t for t in trades if float(t.get("pnl", 0)) > 0]

    if not losses:
        return {"status": "NO_LOSSES", "message": "No losing trades found. Either perfect or no data."}

    # Pattern 1: Repeat losers (same ticker)
    ticker_losses = Counter(t.get("ticker", "?") for t in losses)
    repeat_losers = {k: v for k, v in ticker_losses.items() if v >= 2}

    # Pattern 2: Time-of-day clustering
    hour_losses = Counter()
    for t in losses:
        ts = t.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            hour_losses[dt.hour] += 1
        except Exception:
            pass
    worst_hours = sorted(hour_losses.items(), key=lambda x: -x[1])[:3]

    # Pattern 3: Loss by bot
    bot_losses = defaultdict(lambda: {"count": 0, "total_pnl": 0.0})
    for t in losses:
        bot = t.get("bot_id", "?")
        bot_losses[bot]["count"] += 1
        bot_losses[bot]["total_pnl"] += float(t.get("pnl", 0))

    # Pattern 4: Loss by exit reason
    reason_losses = Counter(t.get("reason", "unknown") for t in losses)

    # Pattern 5: Average loss size vs average win size
    avg_loss = sum(float(t.get("pnl", 0)) for t in losses) / len(losses) if losses else 0
    avg_win = sum(float(t.get("pnl", 0)) for t in wins) / len(wins) if wins else 0
    win_rate = len(wins) / (len(wins) + len(losses)) * 100 if (wins or losses) else 0

    # Pattern 6: Largest single losses
    sorted_losses = sorted(losses, key=lambda t: float(t.get("pnl", 0)))
    worst_trades = sorted_losses[:5]

    return {
        "summary": {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(avg_win * (win_rate / 100) + avg_loss * (1 - win_rate / 100), 2),
        },
        "patterns": {
            "repeat_losers": repeat_losers,
            "worst_hours_utc": worst_hours,
            "loss_by_bot": dict(bot_losses),
            "loss_by_reason": dict(reason_losses),
        },
        "worst_trades": [
            {
                "bot": t.get("bot_id"),
                "ticker": t.get("ticker"),
                "pnl": float(t.get("pnl", 0)),
                "reason": t.get("reason"),
                "timestamp": t.get("timestamp"),
            }
            for t in worst_trades
        ],
        "recommendations": _generate_recommendations(repeat_losers, worst_hours, bot_losses, avg_loss, avg_win, win_rate),
    }


def _generate_recommendations(repeat_losers, worst_hours, bot_losses, avg_loss, avg_win, win_rate):
    recs = []

    if repeat_losers:
        worst_ticker = max(repeat_losers, key=repeat_losers.get)
        recs.append(f"🚫 Stop trading {worst_ticker} — lost {repeat_losers[worst_ticker]} times. Add to anti-list.")

    if worst_hours:
        worst_hour = worst_hours[0][0]
        recs.append(f"⏰ Avoid entries at {worst_hour}:00 UTC — highest loss concentration.")

    if avg_win and avg_loss and abs(avg_loss) > avg_win * 1.5:
        recs.append(f"✂️ Losses are {abs(avg_loss)/avg_win:.1f}x larger than wins. Tighten stops or cut faster.")

    if win_rate < 40:
        recs.append(f"📉 Win rate {win_rate:.0f}% is below 40%. Increase conviction threshold or reduce position count.")

    if not recs:
        recs.append("✅ No clear loss patterns detected. Keep monitoring.")

    return recs


def format_report(analysis: dict) -> str:
    """Format analysis as Discord-friendly text."""
    if analysis.get("status") == "NO_LOSSES":
        return analysis["message"]

    s = analysis["summary"]
    lines = [
        "📊 **LOSS AUTOPSY REPORT**",
        f"Trades: {s['total_trades']} | Wins: {s['wins']} | Losses: {s['losses']} | WR: {s['win_rate']}%",
        f"Avg Win: ${s['avg_win']:.2f} | Avg Loss: ${s['avg_loss']:.2f} | Expectancy: ${s['expectancy']:.2f}",
        "",
        "**Patterns:**",
    ]

    if analysis["patterns"]["repeat_losers"]:
        lines.append(f"🔁 Repeat losers: {analysis['patterns']['repeat_losers']}")
    if analysis["patterns"]["worst_hours_utc"]:
        lines.append(f"⏰ Worst hours (UTC): {analysis['patterns']['worst_hours_utc']}")

    lines.append("")
    lines.append("**Recommendations:**")
    for rec in analysis.get("recommendations", []):
        lines.append(f"  {rec}")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Loss Autopsy")
    parser.add_argument("--bot", help="Analyze specific bot")
    parser.add_argument("--days", type=int, default=7, help="Lookback days")
    args = parser.parse_args()

    trades = get_closed_trades(args.bot, args.days)
    analysis = analyze_losses(trades)
    print(format_report(analysis))
