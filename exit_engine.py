#!/usr/bin/env python3
"""
Exit Engine v1.0 — When to Dump
Companion to pretrade_factor_engine.py (entry).
Scores every held position against exit factors.

Usage:
  python3 exit_engine.py --bot alfred                 # Score all positions
  python3 exit_engine.py --bot alfred --ticker NVDA   # Score one position
  python3 exit_engine.py --bot alfred --sweep         # Run full exit sweep

Integrates with Supabase portfolio_snapshots for live positions.
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone, timedelta

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# ============================================================
# EXIT SIGNAL DEFINITIONS
# ============================================================

# Priority levels: ABSOLUTE (must exit), HIGH (strong exit signal), MEDIUM (consider exit)
EXIT_SIGNALS = {
    # MECHANICAL EXITS (auto-fire, no discretion)
    "hard_stop": {
        "id": 1, "name": "Hard Stop 2%",
        "priority": "ABSOLUTE",
        "check": lambda pos: pos.get("unrealized_pct", 0) <= -2.0,
        "action": "SELL 100% at market. Non-negotiable.",
    },
    "circuit_breaker": {
        "id": 3, "name": "Daily Circuit Breaker -5%",
        "priority": "ABSOLUTE",
        "check": lambda pos: pos.get("portfolio_day_pnl_pct", 0) <= -5.0,
        "action": "Freeze all new entries. Evaluate all positions for exit.",
    },
    "inverse_etf_overnight": {
        "id": 8, "name": "Inverse/Leveraged ETF Sweep",
        "priority": "ABSOLUTE",
        "check": lambda pos: pos.get("ticker", "").upper() in [
            "SQQQ", "TQQQ", "UVXY", "SVXY", "SPXU", "SPXL", "TZA", "TNA",
            "SOXS", "SOXL", "LABU", "LABD", "FNGU", "FNGD", "QID", "QLD",
        ],
        "action": "SELL at 3:45 PM or at open if held overnight.",
    },
    "position_size_breach": {
        "id": 5, "name": "Position >10% of Portfolio",
        "priority": "HIGH",
        "check": lambda pos: pos.get("position_pct", 0) > 10.0,
        "action": "Trim to 10% of portfolio value.",
    },

    # TIME-BASED EXITS
    "scout_time_stop": {
        "id": 6, "name": "Scout Not Profitable in 3 Days",
        "priority": "MEDIUM",
        "check": lambda pos: (
            pos.get("tier", "scout") == "scout"
            and pos.get("days_held", 0) >= 3
            and pos.get("unrealized_pct", 0) <= 0
        ),
        "action": "Exit scout. Thesis didn't confirm in time.",
    },
    "confirm_time_stop": {
        "id": 7, "name": "Confirm Not +5% in 5 Days",
        "priority": "MEDIUM",
        "check": lambda pos: (
            pos.get("tier", "") == "confirm"
            and pos.get("days_held", 0) >= 5
            and pos.get("unrealized_pct", 0) < 5.0
        ),
        "action": "Exit confirm. Momentum stalled.",
    },
    "dead_money": {
        "id": 134, "name": "Dead Money (No Movement 10 Days)",
        "priority": "MEDIUM",
        "check": lambda pos: (
            pos.get("days_held", 0) >= 10
            and abs(pos.get("unrealized_pct", 0)) < 1.0
        ),
        "action": "Exit and redeploy. Capital has opportunity cost.",
    },

    # TECHNICAL EXITS
    "below_200dma": {
        "id": 32, "name": "Close Below 200-Day MA",
        "priority": "HIGH",
        "check": lambda pos: pos.get("below_200dma", False),
        "action": "Reduce 50%. Second consecutive close below = exit fully.",
    },
    "vwap_rejection": {
        "id": 11, "name": "VWAP Rejection",
        "priority": "MEDIUM",
        "check": lambda pos: pos.get("below_vwap", False) and pos.get("unrealized_pct", 0) < 0,
        "action": "Tighten stop to -1% from current price.",
    },
    "peak_drawback": {
        "id": 30, "name": "Gave Back >50% of Peak Gain",
        "priority": "HIGH",
        "check": lambda pos: (
            pos.get("peak_gain_pct", 0) > 2.0
            and pos.get("unrealized_pct", 0) < pos.get("peak_gain_pct", 0) * 0.5
        ),
        "action": "Exit. Winner turning into loser.",
    },

    # MACRO EXITS
    "vix_elevated": {
        "id": 91, "name": "VIX >25 — Elevated Fear",
        "priority": "HIGH",
        "check": lambda pos: pos.get("vix", 0) > 25,
        "action": "Tighten all stops to 1.5%. Exit all scouts.",
    },

    # FUNDAMENTAL EXITS
    "earnings_tomorrow": {
        "id": 9, "name": "Earnings Within 24 Hours",
        "priority": "HIGH",
        "check": lambda pos: pos.get("earnings_within_24h", False),
        "action": "Exit unless conviction 8+/10. Binary event.",
    },

    # BEHAVIORAL EXITS
    "revenge_trade": {
        "id": 121, "name": "Revenge Trade Detection",
        "priority": "HIGH",
        "check": lambda pos: pos.get("is_revenge_reentry", False),
        "action": "BLOCKED. 10-min cooldown, 24hr blacklist after stop-out.",
    },
    "sunk_cost": {
        "id": 122, "name": "Sunk Cost Trap",
        "priority": "MEDIUM",
        "check": lambda pos: pos.get("unrealized_pct", 0) < -5.0 and pos.get("factor_score", 10) < 5,
        "action": "Would you buy this here today? If no, exit.",
    },

    # PORTFOLIO EXITS
    "factor_decay": {
        "id": 138, "name": "Factor Score Decayed Below 4/10",
        "priority": "HIGH",
        "check": lambda pos: pos.get("factor_score", 10) < 4,
        "action": "Exit within 24 hours. Edge is gone.",
    },
    "max_positions": {
        "id": 145, "name": "Max 15 Open Positions",
        "priority": "MEDIUM",
        "check": lambda pos: pos.get("total_positions", 0) > 15,
        "action": "Close weakest position to make room.",
    },
}


def get_positions(bot_id):
    """Fetch current positions from Supabase."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=*",
        headers=HEADERS,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0].get("open_positions", []) or []
    return []


def get_trade_history(bot_id, ticker):
    """Get trade history for a specific ticker."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&ticker=eq.{ticker}&order=created_at.desc&limit=10",
        headers=HEADERS,
    )
    return r.json() if r.status_code == 200 else []


def enrich_position(pos, all_positions):
    """Add computed fields for exit signal evaluation."""
    qty = float(pos.get("quantity", 0))
    entry = float(pos.get("avg_entry", 0))
    current = float(pos.get("current_price", entry))
    side = pos.get("side", "LONG")

    if side == "SHORT":
        unrealized_pct = ((entry - current) / entry * 100) if entry > 0 else 0
    else:
        unrealized_pct = ((current - entry) / entry * 100) if entry > 0 else 0

    pos["unrealized_pct"] = round(unrealized_pct, 2)
    pos["total_positions"] = len(all_positions)

    # Calculate days held (from trade log if available)
    pos.setdefault("days_held", 0)
    pos.setdefault("tier", "scout")
    pos.setdefault("peak_gain_pct", max(0, unrealized_pct))
    pos.setdefault("factor_score", 5)
    pos.setdefault("vix", 0)
    pos.setdefault("below_200dma", False)
    pos.setdefault("below_vwap", False)
    pos.setdefault("earnings_within_24h", False)
    pos.setdefault("is_revenge_reentry", False)
    pos.setdefault("portfolio_day_pnl_pct", 0)

    return pos


def score_position(pos, all_positions):
    """Run all exit signals against a position."""
    pos = enrich_position(pos, all_positions)
    triggered = []
    warnings = []

    for key, signal in EXIT_SIGNALS.items():
        try:
            if signal["check"](pos):
                entry = {
                    "signal": signal["name"],
                    "id": signal["id"],
                    "priority": signal["priority"],
                    "action": signal["action"],
                }
                if signal["priority"] == "ABSOLUTE":
                    triggered.append(entry)
                elif signal["priority"] == "HIGH":
                    triggered.append(entry)
                else:
                    warnings.append(entry)
        except Exception:
            pass  # Skip signals that can't evaluate (missing data)

    return {
        "ticker": pos.get("ticker", "?"),
        "side": pos.get("side", "LONG"),
        "unrealized_pct": pos.get("unrealized_pct", 0),
        "days_held": pos.get("days_held", 0),
        "triggered_exits": triggered,
        "warnings": warnings,
        "verdict": "EXIT" if any(t["priority"] == "ABSOLUTE" for t in triggered) else
                   "REDUCE" if triggered else
                   "WATCH" if warnings else
                   "HOLD",
    }


def sweep_all(bot_id):
    """Run exit sweep on all positions."""
    positions = get_positions(bot_id)
    if not positions:
        print(f"No open positions for {bot_id}")
        return []

    results = []
    print(f"\n{'='*60}")
    print(f"EXIT ENGINE SWEEP — {bot_id.upper()}")
    print(f"Positions: {len(positions)} | Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    for pos in positions:
        result = score_position(pos, positions)
        results.append(result)

        ticker = result["ticker"]
        side = result["side"]
        pnl = result["unrealized_pct"]
        verdict = result["verdict"]

        emoji = {"EXIT": "🔴", "REDUCE": "🟡", "WATCH": "🟠", "HOLD": "🟢"}[verdict]
        print(f"\n{emoji} {side} {ticker}: {pnl:+.2f}% → {verdict}")

        for t in result["triggered_exits"]:
            print(f"   [{t['priority']}] #{t['id']}: {t['signal']}")
            print(f"   → {t['action']}")

        for w in result["warnings"]:
            print(f"   [WATCH] #{w['id']}: {w['signal']}")

    # Summary
    exits = [r for r in results if r["verdict"] == "EXIT"]
    reduces = [r for r in results if r["verdict"] == "REDUCE"]
    watches = [r for r in results if r["verdict"] == "WATCH"]
    holds = [r for r in results if r["verdict"] == "HOLD"]

    print(f"\n{'='*60}")
    print(f"SUMMARY: 🔴 EXIT {len(exits)} | 🟡 REDUCE {len(reduces)} | 🟠 WATCH {len(watches)} | 🟢 HOLD {len(holds)}")
    print(f"{'='*60}")

    return results


def format_discord(results, bot_id):
    """Format results for Discord posting."""
    lines = [f"**🚪 EXIT SWEEP — {bot_id.upper()}**\n"]

    for r in results:
        emoji = {"EXIT": "🔴", "REDUCE": "🟡", "WATCH": "🟠", "HOLD": "🟢"}[r["verdict"]]
        lines.append(f"{emoji} **{r['side']} {r['ticker']}**: {r['unrealized_pct']:+.2f}% → **{r['verdict']}**")
        for t in r["triggered_exits"]:
            lines.append(f"  ↳ {t['signal']}: {t['action']}")

    exits = sum(1 for r in results if r["verdict"] == "EXIT")
    reduces = sum(1 for r in results if r["verdict"] == "REDUCE")
    lines.append(f"\n🔴 {exits} exits | 🟡 {reduces} reduces | {len(results)} total positions")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exit Engine — When to Dump")
    parser.add_argument("--bot", required=True, choices=["tars", "alfred", "vex", "eddie_v"])
    parser.add_argument("--ticker", help="Score a single position")
    parser.add_argument("--sweep", action="store_true", help="Sweep all positions")
    parser.add_argument("--discord", action="store_true", help="Output Discord-formatted")

    args = parser.parse_args()

    if args.sweep or not args.ticker:
        results = sweep_all(args.bot)
        if args.discord:
            print("\n" + format_discord(results, args.bot))
    elif args.ticker:
        positions = get_positions(args.bot)
        pos = next((p for p in positions if p.get("ticker", "").upper() == args.ticker.upper()), None)
        if pos:
            result = score_position(pos, positions)
            print(json.dumps(result, indent=2))
        else:
            print(f"No open position for {args.ticker} in {args.bot}'s portfolio")
