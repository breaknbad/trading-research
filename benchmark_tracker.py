#!/usr/bin/env python3
"""Benchmark tracker — bot performance vs SPY/QQQ with alpha calculation."""

import sys, os, json, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CACHE_DIR, FINNHUB_KEY, STARTING_CAPITAL

BENCHMARK_FILE = os.path.join(CACHE_DIR, "benchmark_history.json")


def _load():
    if os.path.exists(BENCHMARK_FILE):
        with open(BENCHMARK_FILE) as f:
            return json.load(f)
    return {"days": [], "spy_start": None, "qqq_start": None}


def _save(data):
    os.makedirs(os.path.dirname(BENCHMARK_FILE), exist_ok=True)
    with open(BENCHMARK_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _finnhub_quote(symbol: str) -> dict:
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def log_daily_return(date: str, portfolio_value: float, starting_value: float = STARTING_CAPITAL):
    """Log end-of-day portfolio value and fetch benchmark prices."""
    data = _load()

    spy_q = _finnhub_quote("SPY")
    qqq_q = _finnhub_quote("QQQ")

    # Set starting benchmark prices on first log
    if data["spy_start"] is None:
        data["spy_start"] = spy_q["pc"]  # previous close as baseline
        data["qqq_start"] = qqq_q["pc"]

    bot_return = ((portfolio_value - starting_value) / starting_value) * 100

    entry = {
        "date": date,
        "portfolio_value": portfolio_value,
        "bot_return_pct": round(bot_return, 4),
        "spy_price": spy_q["c"],
        "qqq_price": qqq_q["c"],
        "spy_daily_pct": round(((spy_q["c"] - spy_q["pc"]) / spy_q["pc"]) * 100, 4),
        "qqq_daily_pct": round(((qqq_q["c"] - qqq_q["pc"]) / qqq_q["pc"]) * 100, 4),
    }

    # Replace if same date exists
    data["days"] = [d for d in data["days"] if d["date"] != date]
    data["days"].append(entry)
    data["days"].sort(key=lambda d: d["date"])
    _save(data)
    return entry


def get_performance_summary() -> dict:
    """Compute cumulative performance vs benchmarks."""
    data = _load()
    if not data["days"]:
        return {"bot_return_pct": 0, "spy_return_pct": 0, "alpha": 0, "cumulative_alpha": 0, "days_tracked": 0}

    latest = data["days"][-1]
    spy_cumulative = ((latest["spy_price"] - data["spy_start"]) / data["spy_start"] * 100) if data["spy_start"] else 0
    bot_cumulative = latest["bot_return_pct"]
    alpha = bot_cumulative - spy_cumulative

    # Daily alpha sum
    cum_alpha = sum(d["bot_return_pct"] - d.get("spy_daily_pct", 0) for d in data["days"])

    return {
        "bot_return_pct": round(bot_cumulative, 2),
        "spy_return_pct": round(spy_cumulative, 2),
        "alpha": round(alpha, 2),
        "cumulative_alpha": round(cum_alpha, 2),
        "days_tracked": len(data["days"]),
    }


def format_benchmark_report() -> str:
    """Format performance summary for Discord."""
    s = get_performance_summary()
    data = _load()
    latest = data["days"][-1] if data["days"] else {}

    alpha_emoji = "🟢" if s["alpha"] >= 0 else "🔴"

    return (
        f"📈 **Performance Report** ({s['days_tracked']} days)\n"
        f"Bot: {s['bot_return_pct']:+.2f}% | SPY: {s['spy_return_pct']:+.2f}%\n"
        f"{alpha_emoji} Alpha: {s['alpha']:+.2f}% | Cumulative: {s['cumulative_alpha']:+.2f}%\n"
        f"Latest: ${latest.get('portfolio_value', 0):,.2f}"
    )


if __name__ == "__main__":
    print(format_benchmark_report())
