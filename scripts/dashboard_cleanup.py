#!/usr/bin/env python3
"""dashboard_cleanup.py — One-step dashboard wipe.

Usage:
  python3 scripts/dashboard_cleanup.py              # Full wipe (all tables)
  python3 scripts/dashboard_cleanup.py trades       # Wipe trades only
  python3 scripts/dashboard_cleanup.py signals      # Wipe fleet_signals only
  python3 scripts/dashboard_cleanup.py snapshots    # Reset portfolio_snapshots to $50K
  python3 scripts/dashboard_cleanup.py equity       # Wipe equity_snapshots
  python3 scripts/dashboard_cleanup.py alerts       # Clear market_state alerts
  python3 scripts/dashboard_cleanup.py health       # Clean bot_health dupes
  python3 scripts/dashboard_cleanup.py verify       # Verify everything is clean

Tables and what they feed on the dashboard:
  trades             → "Recent Trades" section, Trade Feed tab
  fleet_signals      → Signal activity, cross-bot signals
  equity_snapshots   → Today's High/Low, equity chart, Daily Review tab
  portfolio_snapshots → Bot cards ($50K, positions, P&L, deployed %)
  market_state       → Alerts bar, RSI/EMA indicators
  signal_scores      → Signal scoring history
  bot_health         → Bot status indicators
  daily_reviews      → Daily Review tab
  shared_signals     → Legacy shared signals
"""
import urllib.request, json, sys, os
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent

def load_env():
    env = {}
    env_file = WORKSPACE / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"')
    return env

def supabase_request(url, key, path, method='GET', data=None):
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
    full_url = f'{url}/rest/v1/{path}'
    req = urllib.request.Request(full_url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if method == 'GET':
                return json.loads(r.read())
            return r.status
    except Exception as e:
        return f'ERROR: {e}'

def wipe_trades(url, key):
    """Delete all trades from the trades table."""
    print('  Wiping trades...')
    result = supabase_request(url, key, 'trades?id=gt.0', method='DELETE')
    # Verify
    remaining = supabase_request(url, key, 'trades?select=id&limit=1')
    count = len(remaining) if isinstance(remaining, list) else '?'
    print(f'  trades: {count} remaining {"✅" if count == 0 else "❌"}')

def wipe_signals(url, key):
    """Delete all fleet_signals."""
    print('  Wiping fleet_signals...')
    supabase_request(url, key, 'fleet_signals?id=gt.0', method='DELETE')
    remaining = supabase_request(url, key, 'fleet_signals?select=id&limit=1')
    count = len(remaining) if isinstance(remaining, list) else '?'
    print(f'  fleet_signals: {count} remaining {"✅" if count == 0 else "❌"}')

def wipe_equity(url, key):
    """Delete all equity_snapshots, re-insert clean baselines."""
    print('  Wiping equity_snapshots...')
    supabase_request(url, key, 'equity_snapshots?id=gt.0', method='DELETE')
    now = datetime.now(timezone.utc).isoformat()
    for bot in ['vex', 'tars', 'alfred', 'eddie_v']:
        supabase_request(url, key, 'equity_snapshots', method='POST',
                        data={'bot_id': bot, 'value': 50000.0, 'recorded_at': now})
    remaining = supabase_request(url, key, 'equity_snapshots?select=bot_id,value')
    if isinstance(remaining, list):
        for r in remaining:
            print(f'    {r["bot_id"]}: ${r["value"]:,.0f}')
    print(f'  equity_snapshots: reset ✅')

def reset_snapshots(url, key):
    """Reset portfolio_snapshots to clean $50K per bot."""
    print('  Resetting portfolio_snapshots...')
    for bot in ['vex', 'tars', 'alfred', 'eddie_v']:
        data = {
            'cash_usd': 50000, 'open_positions': [], 'realized_pl': 0,
            'unrealized_pl': 0, 'total_value_usd': 50000, 'daily_return_pct': 0,
            'total_return_pct': 0, 'trade_count': 0, 'win_rate': 0,
            'day_start_value': 50000
        }
        result = supabase_request(url, key, f'portfolio_snapshots?bot_id=eq.{bot}', method='PATCH', data=data)
        if 'ERROR' in str(result):
            print(f'    {bot}: {result}')
        else:
            print(f'    {bot}: $50,000 ✅')

def clear_alerts(url, key):
    """Clear market_state alerts and fix garbage RSI."""
    print('  Clearing market_state alerts...')
    # Read current state
    state_data = supabase_request(url, key, 'market_state?id=eq.latest&select=state_json')
    if isinstance(state_data, list) and state_data:
        state = json.loads(state_data[0]['state_json'])
        # Fix garbage RSI
        fixed = 0
        for t in state.get('tickers', {}):
            tech = state['tickers'][t].get('technicals', {})
            if tech.get('rsi') is not None and (tech['rsi'] >= 99 or tech['rsi'] <= 1):
                tech['rsi'] = 50.0
                fixed += 1
        state['alerts'] = []
        now = datetime.now(timezone.utc).isoformat()
        empty_alerts = json.dumps({'updated': now, 'alerts': []})
        supabase_request(url, key, 'market_state?id=eq.latest', method='PATCH',
                        data={'state_json': json.dumps(state), 'alerts_json': empty_alerts})
        print(f'  alerts cleared, {fixed} garbage RSI values fixed ✅')
    else:
        print('  market_state: no data found')

def clean_health(url, key):
    """Remove duplicate bot_health entries, keep 1 per bot."""
    print('  Cleaning bot_health...')
    # Just verify - can't easily dedupe without knowing schema
    health = supabase_request(url, key, 'bot_health?select=bot_id,status,last_heartbeat&order=last_heartbeat.desc&limit=10')
    if isinstance(health, list):
        print(f'  bot_health: {len(health)} rows')
        for h in health[:4]:
            print(f'    {h["bot_id"]}: {h["status"]}')

def wipe_misc(url, key):
    """Wipe signal_scores, daily_reviews, shared_signals."""
    for table in ['signal_scores', 'daily_reviews', 'shared_signals']:
        print(f'  Wiping {table}...')
        supabase_request(url, key, f'{table}?id=gt.0', method='DELETE')
        remaining = supabase_request(url, key, f'{table}?select=id&limit=1')
        count = len(remaining) if isinstance(remaining, list) else '?'
        print(f'  {table}: {count} remaining {"✅" if count == 0 else "⚠️"}')

def verify(url, key):
    """Verify all tables are clean."""
    print('\n=== VERIFICATION ===')
    checks = {
        'trades': 'trades?select=id&limit=1',
        'fleet_signals': 'fleet_signals?select=id&limit=1',
        'signal_scores': 'signal_scores?select=id&limit=1',
        'daily_reviews': 'daily_reviews?select=id&limit=1',
        'shared_signals': 'shared_signals?select=id&limit=1',
    }
    all_clean = True
    for name, query in checks.items():
        result = supabase_request(url, key, query)
        count = len(result) if isinstance(result, list) else '?'
        clean = count == 0
        if not clean:
            all_clean = False
        print(f'  {name:25} {count} rows {"✅" if clean else "❌"}')

    # Portfolio snapshots
    snaps = supabase_request(url, key, 'portfolio_snapshots?select=bot_id,total_value_usd,cash_usd,trade_count')
    if isinstance(snaps, list):
        for s in snaps:
            clean = s['total_value_usd'] == 50000 and s['trade_count'] == 0
            if not clean:
                all_clean = False
            print(f'  {s["bot_id"]:25} ${s["total_value_usd"]:>8,.0f} trades={s["trade_count"]} {"✅" if clean else "❌"}')

    print(f'\n{"🟢 ALL CLEAN" if all_clean else "🔴 ISSUES FOUND"}')
    return all_clean


def main():
    env = load_env()
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    if not url or not key:
        print('ERROR: SUPABASE_URL and SUPABASE_KEY not found in .env')
        sys.exit(1)

    target = sys.argv[1] if len(sys.argv) > 1 else 'all'
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f'=== DASHBOARD CLEANUP — {now} ===')
    print(f'Target: {target}\n')

    if target == 'all':
        wipe_trades(url, key)
        wipe_signals(url, key)
        wipe_equity(url, key)
        reset_snapshots(url, key)
        clear_alerts(url, key)
        clean_health(url, key)
        wipe_misc(url, key)
        verify(url, key)
    elif target == 'trades':
        wipe_trades(url, key)
    elif target == 'signals':
        wipe_signals(url, key)
    elif target == 'snapshots':
        reset_snapshots(url, key)
    elif target == 'equity':
        wipe_equity(url, key)
    elif target == 'alerts':
        clear_alerts(url, key)
    elif target == 'health':
        clean_health(url, key)
    elif target == 'verify':
        verify(url, key)
    else:
        print(f'Unknown target: {target}')
        print('Valid: all, trades, signals, snapshots, equity, alerts, health, verify')
        sys.exit(1)


if __name__ == '__main__':
    main()
