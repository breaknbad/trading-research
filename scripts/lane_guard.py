#!/usr/bin/env python3
"""
Lane Guard — Enforces strategy separation across the fleet.

Two functions:
1. Overlap check: Before BUY/SHORT, check if another bot already holds the ticker.
   Same direction → allowed but combined size capped at 20% of fund.
   Opposite direction → blocked unless tagged as hedge pair.
2. Lane compliance: Ensures 70% of capital stays in PRIMARY lane.

Lanes:
  TARS     → macro (DXY, oil, bonds, BTC-as-macro, cross-market)
  Alfred   → contrarian (mean_reversion, oversold_bounce, outlier, hedge)
  Vex      → event_driven (congressional, earnings, catalyst, sentiment)
  Eddie    → momentum (breakout, velocity, crypto_momentum, day_trade)

Usage:
  from lane_guard import check_overlap, check_lane_compliance
  ok, reason = check_overlap("alfred", "BTC-USD", "LONG")
  ok, reason = check_lane_compliance("alfred", "mean_reversion", 5000)
"""

import json
import os
import sys
import requests

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Fund-level limits
FUND_TOTAL = 200000  # $200K total fund
MAX_TICKER_PCT = 0.20  # 20% max for any single ticker across fleet
MAX_TICKER_USD = FUND_TOTAL * MAX_TICKER_PCT  # $40K

# Lane definitions
BOT_PRIMARY_LANES = {
    "tars": "macro",
    "tars_crypto": "macro",
    "alfred": "contrarian",
    "alfred_crypto": "contrarian",
    "vex": "event_driven",
    "vex_crypto": "event_driven",
    "eddie_v": "momentum",
    "eddie_crypto": "momentum",
}

VALID_LANES = {
    "macro", "contrarian", "event_driven", "momentum", "hedge",
    "mean_reversion", "oversold_bounce", "outlier", "breakout",
    "velocity", "crypto_momentum", "day_trade", "congressional",
    "earnings", "catalyst", "sentiment",
}

# Map sub-lanes to primary lanes
LANE_FAMILIES = {
    "macro": "macro",
    "contrarian": "contrarian",
    "mean_reversion": "contrarian",
    "oversold_bounce": "contrarian",
    "outlier": "contrarian",
    "hedge": "contrarian",
    "event_driven": "event_driven",
    "congressional": "event_driven",
    "earnings": "event_driven",
    "catalyst": "event_driven",
    "sentiment": "event_driven",
    "momentum": "momentum",
    "breakout": "momentum",
    "velocity": "momentum",
    "crypto_momentum": "momentum",
    "day_trade": "momentum",
}

# Lane compliance: max % of capital outside primary lane
MAX_FLEX_PCT = 0.30  # 30% flex allowed

ALL_BOTS = ["alfred", "tars", "vex", "eddie_v",
            "alfred_crypto", "tars_crypto", "vex_crypto", "eddie_crypto"]


def get_fleet_positions(ticker):
    """Get all fleet positions for a specific ticker."""
    positions = []
    for bot in ALL_BOTS:
        try:
            r = requests.get(
                f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
                params={"bot_id": f"eq.{bot}", "select": "open_positions,total_value_usd"},
                headers=HEADERS, timeout=10,
            )
            if r.status_code == 200 and r.json():
                data = r.json()[0]
                total_val = float(data.get("total_value_usd", 50000))
                for pos in (data.get("open_positions", []) or []):
                    if pos.get("ticker", "").upper() == ticker.upper():
                        qty = float(pos.get("quantity", 0))
                        entry = float(pos.get("avg_entry", 0))
                        positions.append({
                            "bot": bot,
                            "ticker": ticker.upper(),
                            "side": pos.get("side", "LONG"),
                            "quantity": qty,
                            "avg_entry": entry,
                            "value_usd": qty * entry,
                            "total_value": total_val,
                        })
        except Exception:
            continue
    return positions


def check_overlap(bot_id, ticker, side, trade_value_usd=0):
    """
    Check if this trade creates dangerous fleet overlap.
    Returns (ok, reason).
    """
    ticker = ticker.upper()
    side = side.upper()

    fleet_positions = get_fleet_positions(ticker)

    # Calculate current fleet exposure to this ticker
    total_long = sum(p["value_usd"] for p in fleet_positions if p["side"] == "LONG")
    total_short = sum(p["value_usd"] for p in fleet_positions if p["side"] == "SHORT")

    # Check for opposite direction conflict
    for pos in fleet_positions:
        if pos["bot"] != bot_id and pos["bot"].replace("_crypto", "") != bot_id.replace("_crypto", ""):
            if pos["side"] != side:
                return False, (
                    f"🔴 LANE CONFLICT: {bot_id} wants {side} {ticker} but "
                    f"{pos['bot']} holds {pos['side']} {ticker} (${pos['value_usd']:.0f}). "
                    f"Opposite direction blocked unless tagged as hedge pair."
                )

    # Check combined size cap
    if side == "LONG":
        new_total = total_long + trade_value_usd
    else:
        new_total = total_short + trade_value_usd

    if new_total > MAX_TICKER_USD:
        return False, (
            f"🟡 FLEET CONCENTRATION: {ticker} would be ${new_total:.0f} across fleet "
            f"(cap: ${MAX_TICKER_USD:.0f} = {MAX_TICKER_PCT*100:.0f}% of fund). "
            f"Current: ${total_long:.0f} long, ${total_short:.0f} short."
        )

    return True, ""


def check_lane_compliance(bot_id, lane_tag, trade_value_usd):
    """
    Check if this trade keeps the bot within 70/30 lane split.
    Returns (ok, reason).
    """
    bot_base = bot_id.replace("_crypto", "")
    primary_lane = BOT_PRIMARY_LANES.get(bot_id, BOT_PRIMARY_LANES.get(bot_base, "unknown"))
    trade_family = LANE_FAMILIES.get(lane_tag, lane_tag)

    # If trade is in primary lane, always allowed
    if trade_family == primary_lane:
        return True, ""

    # Trade is outside primary lane — check flex budget
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
            params={"bot_id": f"eq.{bot_id}", "select": "open_positions,total_value_usd"},
            headers=HEADERS, timeout=10,
        )
        if r.status_code != 200 or not r.json():
            return True, ""  # Can't check, allow

        data = r.json()[0]
        total_val = float(data.get("total_value_usd", 50000))
        positions = data.get("open_positions", []) or []

        # Calculate how much is already outside primary lane
        out_of_lane_value = 0
        for pos in positions:
            pos_lane = pos.get("lane", "unknown")
            pos_family = LANE_FAMILIES.get(pos_lane, pos_lane)
            if pos_family != primary_lane:
                out_of_lane_value += float(pos.get("quantity", 0)) * float(pos.get("avg_entry", 0))

        flex_budget = total_val * MAX_FLEX_PCT
        new_out_of_lane = out_of_lane_value + trade_value_usd

        if new_out_of_lane > flex_budget:
            return False, (
                f"🔴 LANE DRIFT: {bot_id} has ${out_of_lane_value:.0f} outside {primary_lane} lane "
                f"(flex budget: ${flex_budget:.0f} = {MAX_FLEX_PCT*100:.0f}%). "
                f"Adding ${trade_value_usd:.0f} in '{lane_tag}' would exceed limit. "
                f"Close out-of-lane positions first."
            )
    except Exception:
        pass

    return True, ""


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Lane Guard — strategy separation enforcement")
    parser.add_argument("--check-overlap", nargs=3, metavar=("BOT", "TICKER", "SIDE"))
    parser.add_argument("--check-lane", nargs=3, metavar=("BOT", "LANE", "VALUE_USD"))
    parser.add_argument("--fleet-exposure", metavar="TICKER", help="Show fleet exposure for ticker")
    args = parser.parse_args()

    if args.check_overlap:
        bot, ticker, side = args.check_overlap
        ok, reason = check_overlap(bot, ticker, side)
        print(f"{'✅ OK' if ok else '❌ BLOCKED'}: {reason if reason else 'No overlap issues'}")

    elif args.check_lane:
        bot, lane, val = args.check_lane
        ok, reason = check_lane_compliance(bot, lane, float(val))
        print(f"{'✅ OK' if ok else '❌ BLOCKED'}: {reason if reason else 'Within lane budget'}")

    elif args.fleet_exposure:
        positions = get_fleet_positions(args.fleet_exposure)
        if not positions:
            print(f"No fleet positions in {args.fleet_exposure}")
        else:
            total = sum(p["value_usd"] for p in positions)
            print(f"Fleet exposure: {args.fleet_exposure} = ${total:,.0f} ({total/FUND_TOTAL*100:.1f}% of fund)")
            for p in positions:
                print(f"  {p['bot']}: {p['side']} {p['quantity']}x @ ${p['avg_entry']:.2f} = ${p['value_usd']:,.0f}")
