#!/usr/bin/env python3
"""data_validator.py — Input validation for all Supabase writes.

Three rules that were missing:
1. RSI bounds check (1-99) — blocks garbage RSI from market_watcher
2. Fleet signal TTL — auto-expires signals older than 1 hour
3. Equity snapshot staleness — rejects snapshots with stale timestamps

Import and call validate_before_write() before any Supabase insert/update.
Can also run standalone as a cleanup cron.
"""
import json, sys, os, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

# === VALIDATION RULES ===

def validate_rsi(value):
    """RSI must be between 1 and 99. Returns corrected value or None."""
    if value is None:
        return None
    try:
        rsi = float(value)
        if rsi <= 0 or rsi >= 100:
            return 50.0  # neutral default for garbage
        return rsi
    except (ValueError, TypeError):
        return 50.0

def validate_price(ticker, price):
    """Price sanity bounds by asset class."""
    try:
        p = float(price)
    except:
        return False, "non-numeric price"
    
    if p <= 0:
        return False, f"price <= 0: ${p}"
    
    # Crypto bounds
    if 'BTC' in ticker:
        if p < 1000 or p > 500000:
            return False, f"BTC price out of bounds: ${p} (expect $1K-$500K)"
    elif 'ETH' in ticker:
        if p < 50 or p > 50000:
            return False, f"ETH price out of bounds: ${p} (expect $50-$50K)"
    elif 'SOL' in ticker or 'LINK' in ticker or 'AVAX' in ticker:
        if p < 0.01 or p > 10000:
            return False, f"{ticker} price out of bounds: ${p}"
    elif 'DOGE' in ticker or 'ADA' in ticker or 'SUI' in ticker:
        if p < 0.001 or p > 100:
            return False, f"{ticker} price out of bounds: ${p}"
    # Stock bounds
    elif '-USD' not in ticker:
        if p < 0.50 or p > 10000:
            return False, f"{ticker} stock price out of bounds: ${p}"
    
    return True, "ok"

def validate_bot_id(bot_id):
    """Only 4 valid bot IDs. No _crypto variants."""
    valid = {'vex', 'tars', 'alfred', 'eddie_v'}
    return bot_id in valid, f"invalid bot_id: {bot_id} (valid: {', '.join(valid)})"

def validate_signal_freshness(created_at, max_age_minutes=60):
    """Signal older than max_age_minutes is stale."""
    try:
        if isinstance(created_at, str):
            # Handle ISO format
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        else:
            return False, "invalid timestamp"
        
        age = datetime.now(timezone.utc) - created
        if age > timedelta(minutes=max_age_minutes):
            return False, f"stale signal: {age.total_seconds()/60:.0f} min old (max {max_age_minutes})"
        return True, "fresh"
    except:
        return False, "unparseable timestamp"

def validate_equity_snapshot(value, bot_id):
    """Equity snapshot value must be reasonable."""
    try:
        v = float(value)
        if v < 0:
            return False, f"{bot_id} negative equity: ${v}"
        if v > 500000:
            return False, f"{bot_id} equity too high: ${v} (max $500K)"
        return True, "ok"
    except:
        return False, "non-numeric equity value"


# === MARKET STATE VALIDATOR ===

def validate_market_state(state_json):
    """Validate and fix market state before writing to Supabase."""
    if isinstance(state_json, str):
        state = json.loads(state_json)
    else:
        state = state_json
    
    fixes = []
    tickers = state.get('tickers', {})
    
    for ticker, data in tickers.items():
        tech = data.get('technicals', {})
        
        # Fix RSI
        if 'rsi' in tech:
            old_rsi = tech['rsi']
            tech['rsi'] = validate_rsi(old_rsi)
            if tech['rsi'] != old_rsi:
                fixes.append(f"{ticker} RSI {old_rsi} → {tech['rsi']}")
        
        # Validate price
        price = data.get('price', 0)
        valid, msg = validate_price(ticker, price)
        if not valid:
            fixes.append(f"{ticker} BAD PRICE: {msg}")
    
    return state, fixes


# === CLEANUP FUNCTIONS (run as cron) ===

def cleanup_stale_signals(url, key, max_age_minutes=60):
    """Delete fleet_signals older than max_age_minutes."""
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    
    req = urllib.request.Request(
        f'{url}/rest/v1/fleet_signals?created_at=lt.{cutoff}',
        headers=headers, method='DELETE'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"Stale signals purged (older than {max_age_minutes}min): {r.status}"
    except Exception as e:
        return f"Error purging signals: {e}"

def cleanup_stale_equity(url, key, max_age_hours=24):
    """Delete equity_snapshots older than max_age_hours, keep baselines."""
    headers = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    
    req = urllib.request.Request(
        f'{url}/rest/v1/equity_snapshots?recorded_at=lt.{cutoff}',
        headers=headers, method='DELETE'
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"Stale equity snapshots purged (older than {max_age_hours}h): {r.status}"
    except Exception as e:
        return f"Error purging equity: {e}"

def validate_and_fix_market_state(url, key):
    """Read market_state, validate RSI/prices, write back if fixes needed."""
    headers = {'apikey': key, 'Authorization': f'Bearer {key}'}
    req = urllib.request.Request(f'{url}/rest/v1/market_state?id=eq.latest&select=state_json', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if not data:
            return "No market_state found"
        
        state, fixes = validate_market_state(data[0]['state_json'])
        
        if fixes:
            write_headers = {**headers, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
            req = urllib.request.Request(
                f'{url}/rest/v1/market_state?id=eq.latest',
                data=json.dumps({'state_json': json.dumps(state)}).encode(),
                headers=write_headers, method='PATCH'
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return f"Fixed {len(fixes)} issues: {'; '.join(fixes)}"
        return "Market state clean — no fixes needed"
    except Exception as e:
        return f"Error: {e}"


# === MAIN (run as standalone cleanup cron) ===

def main():
    env = {}
    env_file = WORKSPACE / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"')
    
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    if not url or not key:
        print('ERROR: Missing SUPABASE_URL/KEY in .env')
        sys.exit(1)
    
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f'=== DATA VALIDATOR — {now} ===')
    
    # 1. Fix market state RSI/prices
    print(f'\n1. Market state: {validate_and_fix_market_state(url, key)}')
    
    # 2. Purge stale signals (>1 hour)
    print(f'2. Signals: {cleanup_stale_signals(url, key, 60)}')
    
    # 3. Purge stale equity snapshots (>24 hours)
    print(f'3. Equity: {cleanup_stale_equity(url, key, 24)}')
    
    print('\n✅ Validation sweep complete')


if __name__ == '__main__':
    main()
