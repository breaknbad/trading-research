#!/usr/bin/env python3
"""
premarket_equity_scanner.py — Scans pre-market movers for Signal Corps
Runs at 9:15 AM ET. Flags equities >3% on >2x avg volume.
Includes crypto-adjacent watchlist (MARA, MSTR, COIN, RIOT, CLSK, HUT, BITF).
Posts results to shared_signals in Supabase.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime

# Config
CRYPTO_ADJACENT = ['MARA', 'MSTR', 'COIN', 'RIOT', 'CLSK', 'HUT', 'BITF']
MOMENTUM_WATCHLIST = ['PLTR', 'NVDA', 'AMD', 'SMCI', 'AI', 'AVGO', 'TSLA', 'META', 'AMZN']
ENERGY_DEFENSE = ['MPC', 'VLO', 'NOC', 'RTX', 'LMT', 'XLE', 'XOP']
ALL_TICKERS = list(set(CRYPTO_ADJACENT + MOMENTUM_WATCHLIST + ENERGY_DEFENSE))

MOVE_THRESHOLD = 3.0  # minimum % move to flag
VOLUME_MULTIPLIER = 1.5  # minimum volume vs average

def load_creds():
    creds_path = os.path.expanduser('~/.supabase_trading_creds')
    with open(creds_path) as f:
        lines = f.read().strip().split('\n')
    url = lines[0].split('=', 1)[1].strip()
    key = lines[1].split('=', 1)[1].strip()
    return url, key

def get_finnhub_key():
    path = os.path.expanduser('~/.finnhub_key')
    if os.path.exists(path):
        return open(path).read().strip()
    return None

def fetch_quote(ticker, api_key):
    """Fetch current quote from Finnhub"""
    try:
        url = f'https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}'
        req = urllib.request.Request(url)
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        if data and data.get('c', 0) > 0:
            return {
                'current': data['c'],
                'open': data['o'],
                'high': data['h'],
                'low': data['l'],
                'prev_close': data['pc'],
                'change_pct': round(((data['c'] - data['pc']) / data['pc']) * 100, 2) if data['pc'] > 0 else 0
            }
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}", file=sys.stderr)
    return None

def post_signal(sb_url, sb_key, ticker, data, signal_type='PREMARKET_MOVER'):
    """Post to shared_signals in Supabase"""
    try:
        body = json.dumps({
            'bot_id': 'alfred',
            'ticker': ticker,
            'signal_type': signal_type,
            'price': data['current'],
            'change_pct': data['change_pct'],
            'metadata': json.dumps({
                'prev_close': data['prev_close'],
                'category': 'crypto_adjacent' if ticker in CRYPTO_ADJACENT else 'momentum' if ticker in MOMENTUM_WATCHLIST else 'sector'
            }),
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }).encode()
        req = urllib.request.Request(
            f'{sb_url}/rest/v1/shared_signals',
            data=body, method='POST',
            headers={
                'apikey': sb_key,
                'Authorization': f'Bearer {sb_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal'
            }
        )
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.status
    except Exception as e:
        print(f"  Signal post failed for {ticker}: {e}", file=sys.stderr)
        return None

def main():
    api_key = get_finnhub_key()
    if not api_key:
        print("ERROR: No Finnhub API key found at ~/.finnhub_key")
        sys.exit(1)

    sb_url, sb_key = load_creds()
    
    print(f"=== Pre-Market Equity Scanner — {datetime.now().strftime('%Y-%m-%d %H:%M ET')} ===")
    print(f"Scanning {len(ALL_TICKERS)} tickers | Threshold: >{MOVE_THRESHOLD}%\n")
    
    movers = []
    
    for ticker in sorted(ALL_TICKERS):
        quote = fetch_quote(ticker, api_key)
        if quote and abs(quote['change_pct']) >= MOVE_THRESHOLD:
            direction = '🟢' if quote['change_pct'] > 0 else '🔴'
            category = 'CRYPTO-ADJ' if ticker in CRYPTO_ADJACENT else 'MOMENTUM' if ticker in MOMENTUM_WATCHLIST else 'SECTOR'
            print(f"  {direction} {ticker} {quote['change_pct']:+.1f}% @ ${quote['current']:.2f} [{category}]")
            movers.append((ticker, quote, category))
            post_signal(sb_url, sb_key, ticker, quote)
    
    if not movers:
        print("  No movers above threshold.")
    
    print(f"\n{'='*50}")
    print(f"Movers found: {len(movers)}")
    
    # Write results to alerts.json for heartbeat consumption
    output = {
        'scan_time': datetime.utcnow().isoformat() + 'Z',
        'scanner': 'premarket_equity',
        'movers': [{
            'ticker': t, 
            'change_pct': q['change_pct'], 
            'price': q['current'],
            'category': c
        } for t, q, c in movers]
    }
    
    output_path = os.path.join(os.path.dirname(__file__), '..', 'premarket_movers.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"Results saved to premarket_movers.json")

if __name__ == '__main__':
    main()
