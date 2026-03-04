#!/usr/bin/env python3
"""Position reconciliation script for Vex.
Compares Supabase OPEN positions vs intended portfolio.
Flags duplicates, missing positions, and ticker inconsistencies.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

def load_env():
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"')
    return env

def get_open_positions(url, key, bot_id='vex'):
    req = urllib.request.Request(
        f'{url}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=*',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

CRYPTO_TICKERS = {'BTC', 'ETH', 'SOL', 'SUI', 'AVAX', 'LINK', 'DOT', 'ADA', 'DOGE', 'INJ', 'RNDR', 'PENDLE', 'NEAR', 'MARA', 'RIOT'}

def normalize_ticker(ticker):
    """Normalize to standard format: crypto = TICKER-USD, equity = bare"""
    base = ticker.replace('-USD', '').replace('-USDT', '').upper()
    if base in CRYPTO_TICKERS:
        return f'{base}-USD'
    return base

def main():
    env = load_env()
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    
    if not url or not key:
        print("ERROR: Missing SUPABASE_URL or SUPABASE_KEY in .env")
        return
    
    positions = get_open_positions(url, key, 'vex')
    
    print(f"=== VEX POSITION RECONCILIATION — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===\n")
    print(f"Total OPEN records: {len(positions)}\n")
    
    # Group by normalized ticker
    grouped = {}
    for p in positions:
        norm = normalize_ticker(p['ticker'])
        if norm not in grouped:
            grouped[norm] = []
        grouped[norm].append(p)
    
    issues = []
    
    for ticker, records in sorted(grouped.items()):
        total_qty = sum(float(r['quantity']) for r in records)
        avg_price = sum(float(r['quantity']) * float(r['price_usd']) for r in records) / total_qty if total_qty else 0
        total_cost = sum(float(r['quantity']) * float(r['price_usd']) for r in records)
        
        # Check for ticker inconsistency
        raw_tickers = set(r['ticker'] for r in records)
        if len(raw_tickers) > 1:
            issues.append(f"TICKER MISMATCH: {ticker} has variants: {raw_tickers}")
        
        # Check for duplicate records (same ticker, multiple BUY records)
        if len(records) > 1:
            issues.append(f"DUPLICATE: {ticker} has {len(records)} separate OPEN records (should consolidate)")
        
        # Check for price sanity
        for r in records:
            price = float(r['price_usd'])
            if ticker.startswith('BTC') and price < 10000:
                issues.append(f"GARBAGE PRICE: {ticker} record at ${price} (trade_id: {r['trade_id']})")
            if ticker.startswith('ETH') and price < 100:
                issues.append(f"GARBAGE PRICE: {ticker} record at ${price} (trade_id: {r['trade_id']})")
        
        print(f"{ticker:12} | Qty: {total_qty:>12.4f} | Avg: ${avg_price:>10.2f} | Cost: ${total_cost:>10.2f} | Records: {len(records)}")
        for r in records:
            print(f"  └ {r['ticker']:10} {float(r['quantity']):>10.4f} @ ${float(r['price_usd']):>10.2f} | {r['trade_id'][:25]}")
    
    print(f"\n{'='*60}")
    total_deployed = sum(float(r['quantity']) * float(r['price_usd']) for r in positions)
    print(f"Total deployed (cost basis): ${total_deployed:,.2f}")
    print(f"Estimated cash (from $50K):  ${50000 - total_deployed:,.2f}")
    
    if issues:
        print(f"\n⚠️  ISSUES FOUND: {len(issues)}")
        for i in issues:
            print(f"  🔴 {i}")
    else:
        print("\n✅ No issues found.")
    
    return issues

if __name__ == '__main__':
    main()
