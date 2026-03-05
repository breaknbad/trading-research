#!/usr/bin/env python3
"""
Intraday Equity Sizer — Size positions off CURRENT equity, not opening equity.

If we start at $50K and are up $2K at noon, size off $52K.
Free compounding within the day.

Usage:
    from equity_sizer import get_position_size
    size = get_position_size("alfred_crypto", tier="CONFIRM", book_size=50000)
    # Returns dollar amount for the position

    python3 equity_sizer.py --bot alfred_crypto  # Show current sizing
"""

import json
import sys
import requests

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Tier → max % of current equity
TIER_SIZES = {
    "SCOUT": 0.02,      # 2%
    "CONFIRM": 0.08,    # 8%
    "CONVICTION": 0.15, # 15%
}

DEFAULT_BOOK = 50000  # fallback if can't read Supabase


def get_current_equity(bot_id):
    """Get current total equity from Supabase (live, not opening)."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
            params={"bot_id": f"eq.{bot_id}", "select": "total_value_usd,cash_usd"},
            headers=HEADERS, timeout=10,
        )
        if r.status_code == 200 and r.json():
            data = r.json()[0]
            total = float(data.get("total_value_usd", DEFAULT_BOOK))
            cash = float(data.get("cash_usd", 0))
            return total, cash
    except Exception:
        pass
    return DEFAULT_BOOK, DEFAULT_BOOK * 0.5


def get_position_size(bot_id, tier="CONFIRM", book_size=None):
    """
    Calculate position size in dollars based on CURRENT equity and tier.
    
    Returns: (dollar_amount, equity_used, tier)
    """
    if book_size is None:
        equity, cash = get_current_equity(bot_id)
    else:
        equity = book_size
        cash = book_size * 0.5

    tier = tier.upper()
    pct = TIER_SIZES.get(tier, TIER_SIZES["SCOUT"])
    dollar_size = equity * pct

    # Don't exceed available cash
    if dollar_size > cash:
        dollar_size = cash
        if dollar_size <= 0:
            return 0, equity, tier

    return round(dollar_size, 2), round(equity, 2), tier


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", required=True)
    args = parser.parse_args()

    equity, cash = get_current_equity(args.bot)
    print(f"Bot: {args.bot}")
    print(f"Current equity: ${equity:,.2f}")
    print(f"Available cash: ${cash:,.2f}")
    print(f"---")
    for tier in ["SCOUT", "CONFIRM", "CONVICTION"]:
        size, _, _ = get_position_size(args.bot, tier, equity)
        print(f"  {tier}: ${size:,.2f} ({TIER_SIZES[tier]*100:.0f}% of ${equity:,.2f})")
