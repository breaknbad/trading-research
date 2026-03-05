#!/usr/bin/env python3
"""
crypto_aggression_tiers.py — Performance unlocks aggression
Owner: Alfred | Created: 2026-03-01

Trade count thresholds, not calendar. Statistics > time.
Tier 1 (0-49 trades): Conservative limits
Tier 2 (50+ trades, >55% WR, avg R >1.3): Moderate
Tier 3 (100+ trades, same metrics): Aggressive

Reads from Supabase crypto_trades to compute metrics automatically.
"""

import os
import json
from datetime import datetime, timezone

FLEET_START_NAV = 100000  # For P&L % calculations

# Eddie's v3.0 — approved by Mark 2026-03-01
TIERS = {
    1: {
        "name": "Learning",
        "min_trades": 0,
        "min_profit_factor": 0.0,
        "min_total_pnl_pct": 0.0,
        "min_home_runs": 0,           # Trades with >3% return
        "min_big_wins": 0,            # Trades with >5% return
        "min_capital_velocity": 0.0,  # Total traded / starting capital
        "max_position_pct": 0.10,     # 10% of CURRENT NAV (compounds)
        "stop_pct": 0.02,             # 2%
        "heat_cap_pct": 0.60,         # 60%
    },
    2: {
        "name": "Proven",
        "min_trades": 20,             # Fast unlock — 20 not 50
        "min_profit_factor": 1.5,
        "min_total_pnl_pct": 0.05,    # 5% total return
        "min_home_runs": 3,           # At least 3 trades with >3% return
        "min_big_wins": 0,
        "min_capital_velocity": 0.0,
        "max_position_pct": 0.15,     # 15% of current NAV
        "stop_pct": 0.03,             # 3%
        "heat_cap_pct": 0.80,         # 80%
    },
    3: {
        "name": "Aggressive",
        "min_trades": 50,             # 50 not 100
        "min_profit_factor": 2.0,
        "min_total_pnl_pct": 0.15,    # 15% total return
        "min_home_runs": 3,
        "min_big_wins": 5,            # At least 5 trades with >5% return
        "min_capital_velocity": 2.0,  # Traded 2x starting capital
        "max_position_pct": 0.25,     # 25% of current NAV
        "stop_pct": 0.04,             # 4%
        "heat_cap_pct": 1.00,         # 100% — fully deployed when conviction
    },
}

# BOOSTERS — temporary tier upgrades (stack but never exceed Tier 3)
BOOSTERS = {
    "hot_hand": {
        "trigger": "3 consecutive winners in same regime",
        "effect": "+1 tier for next trade",
    },
    "regime_fear": {
        "trigger": "F&G < 15 (Extreme Fear)",
        "effect": "+5% max position all tiers",
    },
    "velocity": {
        "trigger": "Daily return > +3% before 2 PM ET",
        "effect": "+1 tier for rest of day (resets midnight)",
    },
}


def get_fleet_metrics() -> dict:
    """Get fleet trade metrics from Supabase."""
    try:
        from crypto_supabase_guard import _get_client
        client = _get_client()
        if client:
            result = client.table("crypto_trades").select(
                "bot_id,pnl,side"
            ).not_.is_("pnl", "null").execute()

            if not result.data:
                return {"total_trades": 0, "win_rate": 0.0, "avg_r": 0.0}

            trades = result.data
            total = len(trades)
            pnls = [float(t.get("pnl", 0)) for t in trades]
            wins = sum(1 for p in pnls if p > 0)
            losses = total - wins
            win_rate = wins / total if total > 0 else 0.0

            winning_pnls = [p for p in pnls if p > 0]
            losing_pnls = [p for p in pnls if p <= 0]
            
            avg_win = sum(winning_pnls) / max(1, wins)
            avg_loss = abs(sum(losing_pnls)) / max(1, losses)
            avg_r = avg_win / avg_loss if avg_loss > 0 else 0.0
            
            # Success metrics (Mark's directive: not just batting avg, but power stats)
            total_pnl = sum(pnls)
            total_pnl_pct = total_pnl / (FLEET_START_NAV if total > 0 else 1)
            gross_profit = sum(winning_pnls)
            gross_loss = abs(sum(losing_pnls))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
            
            # Avg winning trade as % of book (hitting for power)
            avg_win_pct = (avg_win / (FLEET_START_NAV / 4)) if avg_win > 0 else 0.0  # per-bot book

            # Home runs (>3% return) and big wins (>5% return)
            per_bot_book = FLEET_START_NAV / 4  # $25K per bot
            home_runs = sum(1 for p in winning_pnls if p / per_bot_book >= 0.03)
            big_wins = sum(1 for p in winning_pnls if p / per_bot_book >= 0.05)
            
            # Capital velocity: total traded volume / starting capital
            total_volume = sum(abs(float(t.get("notional", t.get("pnl", 0)))) for t in trades)
            capital_velocity = total_volume / per_bot_book if per_bot_book > 0 else 0.0

            return {
                "total_trades": total,
                "win_rate": round(win_rate, 3),
                "avg_r": round(avg_r, 2),
                "wins": wins,
                "losses": losses,
                "total_pnl": round(total_pnl, 2),
                "total_pnl_pct": round(total_pnl_pct, 4),
                "profit_factor": round(profit_factor, 2),
                "avg_win_pct": round(avg_win_pct, 4),
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "home_runs": home_runs,
                "big_wins": big_wins,
                "capital_velocity": round(capital_velocity, 2),
            }
    except Exception:
        pass

    return {"total_trades": 0, "win_rate": 0.0, "avg_r": 0.0}


def get_current_tier() -> dict:
    """Determine current aggression tier based on fleet performance."""
    metrics = get_fleet_metrics()
    current_tier = 1

    for tier_num in [3, 2]:  # Check highest first
        tier = TIERS[tier_num]
        if (metrics["total_trades"] >= tier["min_trades"] and
            metrics.get("profit_factor", 0) >= tier["min_profit_factor"] and
            metrics.get("total_pnl_pct", 0) >= tier["min_total_pnl_pct"] and
            metrics.get("home_runs", 0) >= tier["min_home_runs"] and
            metrics.get("big_wins", 0) >= tier["min_big_wins"] and
            metrics.get("capital_velocity", 0) >= tier["min_capital_velocity"]):
            current_tier = tier_num
            break

    tier_config = TIERS[current_tier]
    return {
        "tier": current_tier,
        "name": tier_config["name"],
        "max_position_pct": tier_config["max_position_pct"],
        "stop_pct": tier_config["stop_pct"],
        "heat_cap_pct": tier_config["heat_cap_pct"],
        "max_positions": tier_config.get("max_positions", 10),
        "metrics": metrics,
        "next_tier": _next_tier_requirements(current_tier, metrics),
    }


def _next_tier_requirements(current: int, metrics: dict) -> dict:
    if current >= 3:
        return {"message": "MAX TIER reached"}
    next_tier = TIERS[current + 1]
    return {
        "tier": current + 1,
        "trades_needed": max(0, next_tier["min_trades"] - metrics["total_trades"]),
        "profit_factor_needed": next_tier["min_profit_factor"],
        "total_pnl_pct_needed": next_tier["min_total_pnl_pct"],
        "home_runs_needed": max(0, next_tier["min_home_runs"] - metrics.get("home_runs", 0)),
        "big_wins_needed": max(0, next_tier["min_big_wins"] - metrics.get("big_wins", 0)),
        "current_profit_factor": metrics.get("profit_factor", 0),
        "current_total_pnl_pct": metrics.get("total_pnl_pct", 0),
    }


if __name__ == "__main__":
    result = get_current_tier()
    print(f"Aggression Tier System")
    print(f"  Current: Tier {result['tier']} — {result['name']}")
    print(f"  Max position: {result['max_position_pct']*100:.0f}%")
    print(f"  Stop: {result['stop_pct']*100:.0f}%")
    print(f"  Heat cap: {result['heat_cap_pct']*100:.0f}%")
    print(f"  Fleet trades: {result['metrics']['total_trades']}")
    print(f"  Win rate: {result['metrics']['win_rate']*100:.1f}%")
    print(f"  Avg R: {result['metrics']['avg_r']:.2f}")
    if result['next_tier'].get('trades_needed'):
        print(f"  Next tier in: {result['next_tier']['trades_needed']} trades")
