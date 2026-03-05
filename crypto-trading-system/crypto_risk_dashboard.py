#!/usr/bin/env python3
"""
crypto_risk_dashboard.py — Alfred's contribution to visibility layer
Owner: Alfred | Created: 2026-03-01

Generates a one-message risk status for the fleet. Designed to be called
by Mark's dashboard or posted on command.

Shows: gate status, open positions risk, stop coverage, fleet VaR, NAV breaker level.
"""

import json
from datetime import datetime, timezone


def generate_risk_status() -> str:
    """Generate a single-message risk status."""
    lines = ["🎩 **RISK STATUS**"]

    # NAV circuit breaker
    try:
        from crypto_nav_circuit_breaker import check_nav
        nav = check_nav()
        emoji = {"OK": "🟢", "WARN": "🟡", "REDUCE": "🟠", "HALT": "🔴"}.get(nav["level"], "⚪")
        lines.append(f"{emoji} Fleet NAV: ${nav['fleet_nav']:,.0f} — {nav['level']}")
    except Exception:
        lines.append("⚪ Fleet NAV: unavailable")

    # Aggression tier
    try:
        from crypto_aggression_tiers import get_current_tier
        tier = get_current_tier()
        lines.append(f"📊 Aggression: Tier {tier['tier']} ({tier['name']}) — {tier['metrics']['total_trades']} trades, {tier['metrics']['win_rate']*100:.0f}% WR")
    except Exception:
        lines.append("📊 Aggression: Tier 1 (default)")

    # Stop enforcer health
    try:
        from crypto_stop_heartbeat import check_heartbeat
        hb = check_heartbeat("alfred")
        emoji = "🟢" if hb["alive"] else "🔴"
        lines.append(f"{emoji} Stop enforcer: {'ALIVE' if hb['alive'] else 'DEAD'} ({hb['age_seconds']}s ago)")
    except Exception:
        lines.append("⚪ Stop enforcer: status unknown")

    # Gate module availability
    try:
        from pretrade_gate_v2 import modules
        loaded = len([k for k, v in modules.items() if v is not None])
        total = 13  # Current check count
        emoji = "🟢" if loaded >= 8 else "🟡" if loaded >= 5 else "🔴"
        lines.append(f"{emoji} Gate modules: {loaded}/{total} loaded")
    except Exception:
        lines.append("⚪ Gate: status unknown")

    lines.append(f"\n_Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}_")
    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_risk_status())
