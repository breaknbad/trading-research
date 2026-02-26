#!/usr/bin/env python3
"""Trade executor: sizes positions, executes trades via Supabase."""

import argparse
import json
import math
import sys
from datetime import datetime, timezone

import config
import risk_manager
from log_trade import log_trade


def calculate_position_size(signal, portfolio_value, existing_position_value=0):
    """
    Calculate shares to buy based on signal tier and portfolio value.
    Returns (shares, dollar_amount, size_pct).
    """
    tier = signal["tier"]
    price = signal["price"]
    tier_config = config.TIERS[tier]

    if tier == "SCOUT":
        # 2-6% of portfolio, use midpoint (4%) for auto
        target_pct = (tier_config["size_min_pct"] + tier_config["size_max_pct"]) / 2
    elif tier == "CONFIRM":
        # Add equal to existing, cap at 10%
        if existing_position_value > 0:
            target_dollars = existing_position_value
            target_pct = (target_dollars / portfolio_value) * 100
        else:
            target_pct = tier_config["size_min_pct"]
        target_pct = min(target_pct, config.MAX_POSITION_PCT)
    elif tier == "CONVICTION":
        target_pct = tier_config["size_max_pct"]
    else:
        target_pct = 4.0

    # Cap at max position size minus existing
    existing_pct = (existing_position_value / portfolio_value * 100) if portfolio_value > 0 else 0
    remaining_pct = config.MAX_POSITION_PCT - existing_pct
    if tier == "CONVICTION":
        remaining_pct = tier_config["size_max_pct"] - existing_pct

    target_pct = min(target_pct, remaining_pct)
    if target_pct <= 0:
        return 0, 0, 0

    dollar_amount = portfolio_value * (target_pct / 100)
    shares = math.floor(dollar_amount / price) if price > 0 else 0

    if shares <= 0:
        return 0, 0, 0

    actual_dollars = shares * price
    actual_pct = (actual_dollars / portfolio_value) * 100 if portfolio_value > 0 else 0

    return shares, round(actual_dollars, 2), round(actual_pct, 2)


def execute_open(signal, portfolio, verbose=True):
    """
    Execute a new trade based on a scanner signal.
    Returns dict with trade details or None.
    """
    ticker = signal["ticker"]
    tier = signal["tier"]
    direction = signal["direction"]
    price = signal["price"]

    total_value = float(portfolio.get("total_value_usd", config.STARTING_CAPITAL))
    cash = float(portfolio.get("cash_usd", 0))
    positions = portfolio.get("open_positions", []) or []

    # Check existing position
    existing_value = 0
    for pos in positions:
        if pos.get("ticker") == ticker:
            existing_value = float(pos.get("quantity", 0)) * float(pos.get("current_price", pos.get("avg_entry", 0)))

    shares, dollar_amount, size_pct = calculate_position_size(signal, total_value, existing_value)

    if shares <= 0:
        if verbose:
            print(f"  [SKIP] {ticker}: position size too small or maxed out")
        return None

    if dollar_amount > cash:
        # Reduce to fit cash
        shares = math.floor(cash / price) if price > 0 else 0
        if shares <= 0:
            if verbose:
                print(f"  [SKIP] {ticker}: insufficient cash (${cash:.2f})")
            return None
        dollar_amount = shares * price
        size_pct = (dollar_amount / total_value) * 100

    action = "BUY" if direction == "LONG" else "SHORT"
    reason = f"[{tier}] {direction} | {signal['pct_change']:+.2f}% move | RVOL={signal.get('rvol', 'N/A')} | Score={signal['score']}"

    if verbose:
        print(f"  📈 EXECUTING: {action} {shares}x {ticker} @ ${price:.2f} ({size_pct:.1f}% of portfolio)")

    success = log_trade(config.BOT_ID, action, ticker, shares, price, reason)

    if success:
        risk_manager.save_trade_timestamp()
        return {
            "action": action,
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "dollar_amount": dollar_amount,
            "size_pct": size_pct,
            "tier": tier,
            "reason": reason,
        }
    else:
        if verbose:
            print(f"  [ERR] Trade logging failed for {ticker}")
        return None


def execute_close(position_info, verbose=True):
    """
    Close a position flagged by risk manager.
    position_info: dict from risk_manager with ticker, quantity, side, reason.
    """
    ticker = position_info["ticker"]
    qty = position_info["quantity"]
    current = position_info["current"]
    side = position_info.get("side", "LONG")

    action = "SELL" if side == "LONG" else "COVER"
    reason = f"[RISK] {position_info['reason']}"

    if verbose:
        print(f"  📉 CLOSING: {action} {qty}x {ticker} @ ${current:.2f} - {reason}")

    success = log_trade(config.BOT_ID, action, ticker, qty, current, reason)

    if success:
        risk_manager.save_trade_timestamp()
        return {
            "action": action,
            "ticker": ticker,
            "shares": qty,
            "price": current,
            "reason": reason,
        }
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute a trade")
    parser.add_argument("--action", choices=["BUY", "SELL", "SHORT", "COVER"], required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--shares", type=float, required=True)
    parser.add_argument("--price", type=float, required=True)
    parser.add_argument("--reason", default="Manual trade")
    args = parser.parse_args()

    success = log_trade(config.BOT_ID, args.action, args.ticker, args.shares, args.price, args.reason)
    if success:
        risk_manager.save_trade_timestamp()
        print("Trade executed successfully")
    else:
        print("Trade failed")
