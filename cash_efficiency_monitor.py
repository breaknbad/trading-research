#!/usr/bin/env python3
"""Cash efficiency monitor — tracks idle cash and opportunity cost vs SPY."""

import sys, os, json, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CACHE_DIR

CASH_HISTORY_FILE = os.path.join(CACHE_DIR, "cash_history.json")


def _load_history():
    if os.path.exists(CASH_HISTORY_FILE):
        with open(CASH_HISTORY_FILE) as f:
            return json.load(f)
    return {"snapshots": []}


def _save_history(data):
    os.makedirs(os.path.dirname(CASH_HISTORY_FILE), exist_ok=True)
    with open(CASH_HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def check_cash_efficiency(cash: float, portfolio_value: float, spy_change_pct: float) -> dict:
    """Check current cash efficiency and log snapshot.

    Returns dict with cash_pct, opportunity_cost, alert, message.
    """
    cash_pct = (cash / portfolio_value * 100) if portfolio_value > 0 else 0.0
    # Opportunity cost: what the idle cash would have earned tracking SPY today
    opportunity_cost = cash * (spy_change_pct / 100)

    # Record snapshot
    now = datetime.now(timezone.utc).isoformat()
    history = _load_history()
    history["snapshots"].append({
        "ts": now,
        "cash": cash,
        "portfolio_value": portfolio_value,
        "cash_pct": round(cash_pct, 2),
        "spy_change_pct": spy_change_pct,
        "opportunity_cost": round(opportunity_cost, 2),
    })
    # Keep last 500 snapshots
    history["snapshots"] = history["snapshots"][-500:]
    _save_history(history)

    # Alert if cash > 30% — check if it's been that way for >2 hours
    alert = False
    message = f"Cash {cash_pct:.1f}% of portfolio"
    trending = abs(spy_change_pct) > 0.5  # SPY moving > 0.5% = trending day

    if cash_pct > 30 and trending:
        # Count how long cash has been >30%
        high_cash_minutes = 0
        for snap in reversed(history["snapshots"]):
            if snap["cash_pct"] > 30:
                high_cash_minutes += 5  # assume ~5 min between snapshots
            else:
                break
        if high_cash_minutes >= 120:
            alert = True
            message = (
                f"⚠️ Cash at {cash_pct:.1f}% for ~{high_cash_minutes}min on a trending day "
                f"(SPY {spy_change_pct:+.2f}%). Opportunity cost: ${opportunity_cost:+.2f}"
            )

    return {
        "cash_pct": round(cash_pct, 2),
        "opportunity_cost": round(opportunity_cost, 2),
        "alert": alert,
        "message": message,
    }


def daily_cash_report() -> dict:
    """Summarize cash utilization for today."""
    history = _load_history()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_snaps = [s for s in history["snapshots"] if s["ts"].startswith(today)]

    if not today_snaps:
        return {"date": today, "snapshots": 0, "message": "No cash data recorded today."}

    cash_pcts = [s["cash_pct"] for s in today_snaps]
    opp_costs = [s["opportunity_cost"] for s in today_snaps]

    return {
        "date": today,
        "snapshots": len(today_snaps),
        "avg_cash_pct": round(sum(cash_pcts) / len(cash_pcts), 2),
        "max_cash_pct": round(max(cash_pcts), 2),
        "min_cash_pct": round(min(cash_pcts), 2),
        "total_opportunity_cost": round(sum(opp_costs), 2),
        "time_above_30pct": sum(1 for p in cash_pcts if p > 30),
        "message": (
            f"📊 Cash Report {today}\n"
            f"Avg cash: {sum(cash_pcts)/len(cash_pcts):.1f}% | "
            f"Range: {min(cash_pcts):.1f}%-{max(cash_pcts):.1f}%\n"
            f"Total opportunity cost: ${sum(opp_costs):+.2f}\n"
            f"Snapshots above 30%: {sum(1 for p in cash_pcts if p > 30)}/{len(cash_pcts)}"
        ),
    }


if __name__ == "__main__":
    print(check_cash_efficiency(8000, 25000, 1.2))
    print(daily_cash_report())
