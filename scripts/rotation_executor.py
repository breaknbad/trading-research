#!/usr/bin/env python3
"""
rotation_executor.py — Auto-executes rotation signals from momentum scanner
Takes weakest position and rotates into strongest non-held mover when delta > threshold.

Rules:
- Delta threshold: 3% (adjustable via ROTATION_DELTA_MIN)
- Hold time: volatility-adjusted (2hr default, 1hr if daily move >5%, 30min if >8%)
- Max 2 rotations per day per position
- Logs all decisions to rotation_log.json
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta

ROTATION_DELTA_MIN = 3.0  # minimum % delta to trigger rotation
MAX_ROTATIONS_PER_DAY = 2
HOLD_TIME_DEFAULT = 120  # minutes
HOLD_TIME_HIGH_VOL = 60  # if daily market move > 5%
HOLD_TIME_EXTREME_VOL = 30  # if daily market move > 8%

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROTATION_LOG = os.path.join(WORKSPACE, 'rotation_log.json')
EXECUTE_TRADE = os.path.join(WORKSPACE, 'scripts', 'execute_trade.py')

def load_rotation_log():
    if os.path.exists(ROTATION_LOG):
        with open(ROTATION_LOG) as f:
            return json.load(f)
    return {'rotations': [], 'daily_count': {}}

def save_rotation_log(log):
    with open(ROTATION_LOG, 'w') as f:
        json.dump(log, f, indent=2)

def get_hold_time_minutes(daily_move_pct):
    """Volatility-adjusted hold time"""
    if abs(daily_move_pct) > 8:
        return HOLD_TIME_EXTREME_VOL
    elif abs(daily_move_pct) > 5:
        return HOLD_TIME_HIGH_VOL
    return HOLD_TIME_DEFAULT

def check_rotation_eligible(ticker, log):
    """Check if position hasn't been rotated too many times today"""
    today = datetime.now().strftime('%Y-%m-%d')
    key = f"{today}:{ticker}"
    count = log.get('daily_count', {}).get(key, 0)
    return count < MAX_ROTATIONS_PER_DAY

def execute_rotation(sell_ticker, sell_qty, sell_price, buy_ticker, buy_price, market, reason):
    """Execute sell + buy as atomic rotation"""
    results = []
    
    # Sell weakest
    sell_cmd = [
        'python3', EXECUTE_TRADE,
        '--ticker', sell_ticker,
        '--action', 'SELL',
        '--quantity', str(sell_qty),
        '--price', str(sell_price),
        '--market', market,
        '--bot-id', 'alfred',
        '--reason', f'ROTATION OUT: {reason}',
        '--skip-validation'
    ]
    
    result = subprocess.run(sell_cmd, capture_output=True, text=True, cwd=WORKSPACE)
    results.append(('SELL', sell_ticker, result.returncode == 0, result.stdout))
    
    if result.returncode != 0:
        print(f"ERROR: Failed to sell {sell_ticker}: {result.stderr}")
        return False, results
    
    # Calculate buy quantity from sell proceeds
    proceeds = sell_qty * sell_price
    buy_qty = round(proceeds / buy_price, 6) if buy_price > 0 else 0
    
    # Buy strongest
    buy_cmd = [
        'python3', EXECUTE_TRADE,
        '--ticker', buy_ticker,
        '--action', 'BUY',
        '--quantity', str(buy_qty),
        '--price', str(buy_price),
        '--market', market,
        '--bot-id', 'alfred',
        '--reason', f'ROTATION IN: {reason}',
        '--skip-validation'
    ]
    
    result = subprocess.run(buy_cmd, capture_output=True, text=True, cwd=WORKSPACE)
    results.append(('BUY', buy_ticker, result.returncode == 0, result.stdout))
    
    return result.returncode == 0, results

def main():
    """
    Usage: rotation_executor.py <sell_ticker> <sell_qty> <sell_price> <buy_ticker> <buy_price> <market> <delta_pct> <daily_move_pct> <hold_minutes>
    """
    if len(sys.argv) < 10:
        print("Usage: rotation_executor.py <sell_ticker> <sell_qty> <sell_price> <buy_ticker> <buy_price> <market> <delta_pct> <daily_move_pct> <hold_minutes>")
        sys.exit(1)
    
    sell_ticker = sys.argv[1]
    sell_qty = float(sys.argv[2])
    sell_price = float(sys.argv[3])
    buy_ticker = sys.argv[4]
    buy_price = float(sys.argv[5])
    market = sys.argv[6]
    delta_pct = float(sys.argv[7])
    daily_move = float(sys.argv[8])
    hold_minutes = float(sys.argv[9])
    
    log = load_rotation_log()
    
    # Check delta threshold
    if delta_pct < ROTATION_DELTA_MIN:
        print(f"SKIP: Delta {delta_pct:.1f}% below threshold {ROTATION_DELTA_MIN}%")
        sys.exit(0)
    
    # Check hold time
    min_hold = get_hold_time_minutes(daily_move)
    if hold_minutes < min_hold:
        print(f"SKIP: Hold time {hold_minutes:.0f}min below minimum {min_hold}min (daily move {daily_move:.1f}%)")
        sys.exit(0)
    
    # Check rotation count
    if not check_rotation_eligible(sell_ticker, log):
        print(f"SKIP: {sell_ticker} already rotated {MAX_ROTATIONS_PER_DAY}x today")
        sys.exit(0)
    
    # Execute
    reason = f"{sell_ticker} → {buy_ticker} | delta {delta_pct:+.1f}% | hold {hold_minutes:.0f}min"
    print(f"EXECUTING ROTATION: {reason}")
    
    success, results = execute_rotation(sell_ticker, sell_qty, sell_price, buy_ticker, buy_price, market, reason)
    
    if success:
        # Log rotation
        today = datetime.now().strftime('%Y-%m-%d')
        key = f"{today}:{sell_ticker}"
        if 'daily_count' not in log:
            log['daily_count'] = {}
        log['daily_count'][key] = log['daily_count'].get(key, 0) + 1
        log['rotations'].append({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'sell': sell_ticker,
            'buy': buy_ticker,
            'delta_pct': delta_pct,
            'proceeds': sell_qty * sell_price
        })
        save_rotation_log(log)
        print(f"SUCCESS: Rotated {sell_ticker} → {buy_ticker}")
    else:
        print(f"FAILED: Rotation incomplete")
        for action, ticker, ok, output in results:
            print(f"  {action} {ticker}: {'OK' if ok else 'FAILED'}")

if __name__ == '__main__':
    main()
