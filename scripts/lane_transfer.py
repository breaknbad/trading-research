#!/usr/bin/env python3
"""
Lane Transfer — Atomically move positions between bots for strategy separation.

Re-tags bot_id in portfolio_snapshots without creating buy/sell trades.
Adjusts cash in both source and destination portfolios.

Usage:
  python3 lane_transfer.py --from alfred_crypto --to tars_crypto --ticker BTC-USD --dry
  python3 lane_transfer.py --from alfred_crypto --to eddie_crypto --ticker NEAR-USD
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def get_portfolio(bot_id):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
        params={"bot_id": f"eq.{bot_id}", "select": "*"},
        headers=HEADERS, timeout=10,
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def update_portfolio(bot_id, patch):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}",
        headers=HEADERS, json=patch, timeout=10,
    )
    return r.status_code in (200, 204)


def transfer_position(from_bot, to_bot, ticker, dry_run=False):
    """Transfer a position from one bot to another."""
    ticker = ticker.upper()
    
    # Get both portfolios
    src = get_portfolio(from_bot)
    dst = get_portfolio(to_bot)
    
    if not src:
        print(f"❌ Source bot {from_bot} has no portfolio")
        return False
    if not dst:
        print(f"❌ Destination bot {to_bot} has no portfolio")
        return False
    
    src_positions = src.get("open_positions", []) or []
    dst_positions = dst.get("open_positions", []) or []
    src_cash = float(src.get("cash_usd", 0))
    dst_cash = float(dst.get("cash_usd", 0))
    
    # Find the position to transfer
    transfer_pos = None
    transfer_idx = None
    for i, pos in enumerate(src_positions):
        if pos.get("ticker", "").upper() == ticker:
            transfer_pos = pos
            transfer_idx = i
            break
    
    if transfer_pos is None:
        print(f"❌ {from_bot} has no position in {ticker}")
        return False
    
    qty = float(transfer_pos.get("quantity", 0))
    entry = float(transfer_pos.get("avg_entry", 0))
    side = transfer_pos.get("side", "LONG")
    position_value = qty * entry
    
    print(f"📋 Transfer: {side} {qty}x {ticker} @ ${entry:.2f} (${position_value:,.0f})")
    print(f"   From: {from_bot} (cash: ${src_cash:,.2f})")
    print(f"   To:   {to_bot} (cash: ${dst_cash:,.2f})")
    
    if dry_run:
        print("   🔸 DRY RUN — no changes made")
        return True
    
    # Remove from source
    new_src_positions = [p for i, p in enumerate(src_positions) if i != transfer_idx]
    
    # For LONG positions: source gets cash back, destination loses cash
    # For SHORT positions: source loses the proceeds, destination gains them
    if side == "LONG":
        new_src_cash = src_cash + position_value
        new_dst_cash = dst_cash - position_value
    else:
        new_src_cash = src_cash - position_value
        new_dst_cash = dst_cash + position_value
    
    # Add to destination (merge if already holds same ticker)
    merged = False
    for pos in dst_positions:
        if pos.get("ticker", "").upper() == ticker and pos.get("side") == side:
            old_qty = float(pos.get("quantity", 0))
            old_entry = float(pos.get("avg_entry", 0))
            new_qty = old_qty + qty
            new_entry = ((old_entry * old_qty) + (entry * qty)) / new_qty
            pos["quantity"] = new_qty
            pos["avg_entry"] = round(new_entry, 4)
            merged = True
            print(f"   Merged into existing {to_bot} position: {new_qty}x @ ${new_entry:.4f}")
            break
    
    if not merged:
        dst_positions.append(transfer_pos.copy())
        print(f"   Created new position in {to_bot}")
    
    # Recalculate total values
    def calc_total(cash, positions):
        long_val = sum(float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
                      for p in positions if p.get("side", "LONG") == "LONG")
        short_val = sum(float(p.get("quantity", 0)) * float(p.get("current_price", p.get("avg_entry", 0)))
                       for p in positions if p.get("side") == "SHORT")
        return cash + long_val - short_val
    
    src_total = calc_total(new_src_cash, new_src_positions)
    dst_total = calc_total(new_dst_cash, dst_positions)
    
    # Update source
    src_ok = update_portfolio(from_bot, {
        "open_positions": new_src_positions,
        "cash_usd": round(new_src_cash, 2),
        "total_value_usd": round(src_total, 2),
        "total_return_pct": round(((src_total - 25000) / 25000) * 100, 2),
    })
    
    # Update destination
    dst_ok = update_portfolio(to_bot, {
        "open_positions": dst_positions,
        "cash_usd": round(new_dst_cash, 2),
        "total_value_usd": round(dst_total, 2),
        "total_return_pct": round(((dst_total - 25000) / 25000) * 100, 2),
    })
    
    if src_ok and dst_ok:
        print(f"   ✅ Transfer complete!")
        print(f"   {from_bot}: ${src_total:,.2f} total, ${new_src_cash:,.2f} cash, {len(new_src_positions)} positions")
        print(f"   {to_bot}: ${dst_total:,.2f} total, ${new_dst_cash:,.2f} cash, {len(dst_positions)} positions")
        return True
    else:
        print(f"   ❌ Transfer FAILED — source ok: {src_ok}, dest ok: {dst_ok}")
        print(f"   ⚠️ MANUAL RECONCILIATION NEEDED")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lane Transfer — move positions between bots")
    parser.add_argument("--from", dest="from_bot", required=True)
    parser.add_argument("--to", dest="to_bot", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--dry", action="store_true", help="Dry run")
    args = parser.parse_args()
    
    transfer_position(args.from_bot, args.to_bot, args.ticker, args.dry)
