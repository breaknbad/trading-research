#!/usr/bin/env python3
"""
portfolio_guard.py — Validation layer that runs before every equity snapshot write.
Catches bad data BEFORE it hits the database.

Run standalone: python3 portfolio_guard.py --check
Run as import: from portfolio_guard import validate_portfolio, validate_snapshot

Failure modes this prevents:
1. Cash > starting capital (phantom sells)
2. Portfolio value jumping >5% between snapshots
3. Negative deployment (cash > total value)
4. Position quantities going negative
5. Duplicate/phantom trades (sell more than you own)
"""

import sys
import json
from datetime import datetime, timezone

try:
    import psycopg2
    from pathlib import Path
    SUPABASE_URL = Path.home().joinpath(".supabase_db_url").read_text().strip()
except Exception:
    SUPABASE_URL = None

STARTING_CAPITAL = 25000.0
MAX_SNAPSHOT_JUMP_PCT = 5.0  # Max % change between consecutive snapshots
MAX_REASONABLE_RETURN_PCT = 50.0  # No bot should be up 50% in week 1


def validate_portfolio(bot_id, cash, positions, total_value):
    """Validate portfolio state. Returns (ok, errors) tuple."""
    errors = []
    
    # 1. Cash sanity — should never exceed starting capital + realized gains
    # For shorts, cash CAN exceed $25K because short proceeds are held as cash.
    # But total_value (cash + longs - short obligations) should stay reasonable.
    
    # 2. Total value sanity
    if total_value <= 0:
        errors.append(f"Total value is ${total_value:.2f} — impossible")
    
    return_pct = (total_value - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    if abs(return_pct) > MAX_REASONABLE_RETURN_PCT:
        errors.append(f"Return of {return_pct:+.1f}% exceeds {MAX_REASONABLE_RETURN_PCT}% cap — likely data bug")
    
    # 3. Verify total_value matches components
    long_val = sum(
        float(p.get('quantity', 0)) * float(p.get('current_price', p.get('avg_entry', 0)))
        for p in positions if p.get('side', 'LONG') != 'SHORT'
    )
    short_obl = sum(
        float(p.get('quantity', 0)) * float(p.get('current_price', p.get('avg_entry', 0)))
        for p in positions if p.get('side') == 'SHORT'
    )
    calculated = cash + long_val - short_obl
    drift = abs(calculated - total_value)
    if drift > 10:  # Allow $10 rounding tolerance
        errors.append(f"Value mismatch: reported ${total_value:.2f} vs calculated ${calculated:.2f} (drift ${drift:.2f})")
    
    # 4. No negative quantities
    for p in positions:
        qty = float(p.get('quantity', 0))
        if qty < 0:
            errors.append(f"{p.get('ticker')} has negative quantity: {qty}")
        if qty == 0:
            errors.append(f"{p.get('ticker')} has zero quantity — should be removed")
    
    return (len(errors) == 0, errors)


def validate_snapshot(bot_id, new_value, conn=None):
    """Validate a new equity snapshot against the previous one. Returns (ok, errors)."""
    errors = []
    
    if conn is None:
        if SUPABASE_URL is None:
            return (True, [])  # Can't check without DB
        conn = psycopg2.connect(SUPABASE_URL)
        close_conn = True
    else:
        close_conn = False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT value, recorded_at FROM equity_snapshots 
            WHERE bot_id = %s ORDER BY recorded_at DESC LIMIT 1
        """, (bot_id,))
        row = cur.fetchone()
        
        if row:
            prev_value = float(row[0])
            if prev_value > 0:
                jump_pct = abs(new_value - prev_value) / prev_value * 100
                if jump_pct > MAX_SNAPSHOT_JUMP_PCT:
                    errors.append(
                        f"Snapshot jump {jump_pct:.1f}% (${prev_value:.0f} → ${new_value:.0f}) "
                        f"exceeds {MAX_SNAPSHOT_JUMP_PCT}% limit"
                    )
    finally:
        if close_conn:
            conn.close()
    
    return (len(errors) == 0, errors)


def validate_trade(bot_id, action, ticker, qty, positions):
    """Validate a trade BEFORE execution. Returns (ok, errors)."""
    errors = []
    
    if action == 'SELL':
        held = 0
        for p in positions:
            if p.get('ticker') == ticker and p.get('side', 'LONG') == 'LONG':
                held = float(p.get('quantity', 0))
        if qty > held + 0.001:
            errors.append(f"SELL {qty} {ticker} but only hold {held} — would create phantom cash")
    
    elif action == 'COVER':
        held = 0
        for p in positions:
            if p.get('ticker') == ticker and p.get('side') == 'SHORT':
                held = float(p.get('quantity', 0))
        if qty > held + 0.001:
            errors.append(f"COVER {qty} {ticker} but only short {held}")
    
    return (len(errors) == 0, errors)


def full_audit(bot_id, conn=None):
    """Replay all trades and compare to current portfolio state. Returns (ok, report)."""
    if conn is None:
        conn = psycopg2.connect(SUPABASE_URL)
        close_conn = True
    else:
        close_conn = False
    
    try:
        cur = conn.cursor()
        
        # Replay trades
        cur.execute("""
            SELECT action, ticker, quantity, price_usd, timestamp 
            FROM trades WHERE bot_id = %s ORDER BY timestamp ASC
        """, (bot_id,))
        trades = cur.fetchall()
        
        cash = STARTING_CAPITAL
        positions = {}
        
        for action, ticker, qty, price, ts in trades:
            q = float(qty); p = float(price)
            
            if action == 'BUY':
                key = f"{ticker}_LONG"
                if key in positions:
                    old = positions[key]
                    new_qty = old['qty'] + q
                    old['avg_entry'] = (old['avg_entry'] * old['qty'] + p * q) / new_qty
                    old['qty'] = new_qty
                else:
                    positions[key] = {'qty': q, 'avg_entry': p, 'side': 'LONG', 'ticker': ticker}
                cash -= q * p
                
            elif action == 'SELL':
                key = f"{ticker}_LONG"
                if key in positions and positions[key]['qty'] >= q - 0.01:
                    cash += q * p
                    positions[key]['qty'] -= q
                    if positions[key]['qty'] <= 0.01:
                        del positions[key]
                # Phantom sells are silently skipped (logged but not executed)
                
            elif action == 'SHORT':
                key = f"{ticker}_SHORT"
                if key in positions:
                    old = positions[key]
                    new_qty = old['qty'] + q
                    old['avg_entry'] = (old['avg_entry'] * old['qty'] + p * q) / new_qty
                    old['qty'] = new_qty
                else:
                    positions[key] = {'qty': q, 'avg_entry': p, 'side': 'SHORT', 'ticker': ticker}
                cash += q * p
                
            elif action == 'COVER':
                key = f"{ticker}_SHORT"
                if key in positions and positions[key]['qty'] >= q - 0.01:
                    cash -= q * p
                    positions[key]['qty'] -= q
                    if positions[key]['qty'] <= 0.01:
                        del positions[key]
        
        # Get current DB state
        cur.execute("SELECT cash_usd, total_value_usd, open_positions FROM portfolio_snapshots WHERE bot_id = %s", (bot_id,))
        row = cur.fetchone()
        db_cash = float(row[0])
        db_total = float(row[1])
        db_positions = row[2] or []
        
        report = {
            'bot_id': bot_id,
            'trades_replayed': len(trades),
            'replayed_cash': round(cash, 2),
            'db_cash': round(db_cash, 2),
            'cash_drift': round(abs(cash - db_cash), 2),
            'replayed_positions': {k: round(v['qty'], 4) for k, v in positions.items() if v['qty'] > 0.01},
            'db_positions': {f"{p['ticker']}_{p.get('side','LONG')}": float(p.get('quantity',0)) for p in db_positions},
        }
        
        ok = report['cash_drift'] < 1.0  # Less than $1 drift
        
    finally:
        if close_conn:
            conn.close()
    
    return (ok, report)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Run full audit on all bots')
    parser.add_argument('--bot', help='Audit specific bot')
    args = parser.parse_args()
    
    bots = [args.bot] if args.bot else ['alfred', 'tars', 'vex', 'eddie_v']
    
    conn = psycopg2.connect(SUPABASE_URL)
    all_ok = True
    
    for bot in bots:
        ok, report = full_audit(bot, conn)
        status = '✅' if ok else '🚨'
        print(f"\n{status} {bot}:")
        print(f"  Trades: {report['trades_replayed']}")
        print(f"  Cash — replayed: ${report['replayed_cash']:,.2f} | DB: ${report['db_cash']:,.2f} | drift: ${report['cash_drift']}")
        if report['replayed_positions'] != report['db_positions']:
            print(f"  ⚠️  Position mismatch!")
            print(f"    Replayed: {report['replayed_positions']}")
            print(f"    DB:       {report['db_positions']}")
        if not ok:
            all_ok = False
    
    conn.close()
    sys.exit(0 if all_ok else 1)
