#!/usr/bin/env python3
"""exit_signals.py — Minimum viable exit factor engine for Vex.
Checks 5 exit factors on open positions. Alert only, no auto-execution.
Run alongside stop_check every 60s.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

def load_env():
    env = {}
    with open(WORKSPACE / '.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"')
    return env

def get_positions(url, key, bot_id='vex'):
    req = urllib.request.Request(
        f'{url}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=*',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_market_state():
    state_file = WORKSPACE / 'market-state.json'
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            return state.get('tickers', {})
    return {}

CRYPTO_TICKERS = {'BTC', 'ETH', 'SOL', 'SUI', 'AVAX', 'LINK', 'DOT', 'ADA', 'DOGE', 'INJ', 'RNDR', 'PENDLE'}
DEFENSIVE_TICKERS = {'GDX', 'GLD', 'SLV', 'XLE', 'SQQQ', 'TLT', 'UUP'}

def normalize_base(ticker):
    return ticker.replace('-USD', '').replace('-USDT', '').upper()

def get_live_price(ticker, market_state):
    base = normalize_base(ticker)
    td = market_state.get(base, {})
    return td.get('price')

def check_exit_factors(positions, market_state):
    signals = []
    
    # Calculate portfolio totals for concentration check
    total_value = 0
    position_values = {}
    for p in positions:
        base = normalize_base(p['ticker'])
        price = get_live_price(p['ticker'], market_state)
        if price:
            val = float(p['quantity']) * price
        else:
            val = float(p['quantity']) * float(p['price_usd'])  # fallback to entry
        position_values[p['trade_id']] = val
        total_value += val
    
    # Determine regime from BTC
    btc_data = market_state.get('BTC', {})
    btc_change = btc_data.get('change_pct', btc_data.get('change_24h_pct', 0))
    btc_rsi = btc_data.get('rsi_14')
    
    regime = 'NEUTRAL'
    if btc_change and float(btc_change) > 3:
        regime = 'RISK_ON'
    elif btc_change and float(btc_change) < -3:
        regime = 'RISK_OFF'
    
    for p in positions:
        base = normalize_base(p['ticker'])
        entry_price = float(p['price_usd'])
        current_price = get_live_price(p['ticker'], market_state)
        exit_reasons = []
        
        if not current_price:
            continue
        
        pnl_pct = (current_price - entry_price) / entry_price * 100
        
        # FACTOR 1: REGIME MISMATCH
        if base in DEFENSIVE_TICKERS and regime == 'RISK_ON':
            exit_reasons.append(f"REGIME_MISMATCH: Defensive position ({base}) in RISK_ON regime. Thesis conflict.")
        
        # FACTOR 2: RELATIVE WEAKNESS (crypto vs BTC benchmark)
        if base in CRYPTO_TICKERS and base != 'BTC' and btc_change:
            ticker_data = market_state.get(base, {})
            ticker_change = ticker_data.get('change_pct', ticker_data.get('change_24h_pct', 0))
            if ticker_change and float(btc_change) > 2 and float(ticker_change) < float(btc_change) - 3:
                exit_reasons.append(f"RELATIVE_WEAKNESS: {base} +{float(ticker_change):.1f}% vs BTC +{float(btc_change):.1f}%. Lagging >3%.")
        
        # FACTOR 3: CATALYST EXPIRY (simplified — flag large gains on event-driven positions)
        # Full implementation needs catalyst timestamps in Supabase
        if pnl_pct > 8 and base in ('MRNA', 'ROST', 'STX'):
            exit_reasons.append(f"CATALYST_CHECK: {base} at +{pnl_pct:.1f}%. Is the catalyst priced in? Consider scaling out.")
        
        # FACTOR 4: CONCENTRATION DRIFT (aggregate by base ticker)
        # Sum all positions with same base ticker
        base_total = sum(v for tid, v in position_values.items() 
                        if any(normalize_base(pp['ticker']) == base and pp['trade_id'] == tid for pp in positions))
        if total_value > 0:
            concentration = base_total / total_value * 100
            if concentration > 30:
                exit_reasons.append(f"CONCENTRATION: {base} is {concentration:.1f}% of portfolio (all records combined). Max 25%. Trim needed.")
        
        # FACTOR 5: PRICE SANITY
        if current_price < entry_price * 0.5:
            exit_reasons.append(f"PRICE_SANITY: {base} current ${current_price:.2f} is >50% below entry ${entry_price:.2f}. GARBAGE DATA or catastrophic loss.")
        if current_price > entry_price * 3:
            exit_reasons.append(f"PRICE_SANITY: {base} current ${current_price:.2f} is >3x entry ${entry_price:.2f}. Verify price accuracy.")
        
        if exit_reasons:
            signals.append({
                'ticker': p['ticker'],
                'base': base,
                'entry': entry_price,
                'current': current_price,
                'pnl_pct': pnl_pct,
                'signals': exit_reasons
            })
    
    return signals, regime

def main():
    env = load_env()
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    
    if not url or not key:
        print("ERROR: Missing Supabase credentials")
        return
    
    positions = get_positions(url, key, 'vex')
    market_state = get_market_state()
    
    print(f"=== EXIT SIGNAL CHECK — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Positions: {len(positions)} | Market tickers: {len(market_state)}")
    
    signals, regime = check_exit_factors(positions, market_state)
    
    print(f"Regime: {regime}")
    
    if signals:
        print(f"\n⚠️  EXIT SIGNALS DETECTED: {sum(len(s['signals']) for s in signals)}")
        for s in signals:
            print(f"\n  {s['base']} | Entry: ${s['entry']:.2f} → ${s['current']:.2f} ({s['pnl_pct']:+.1f}%)")
            for reason in s['signals']:
                print(f"    🔴 {reason}")
    else:
        print("\n✅ No exit signals. All positions clean.")

if __name__ == '__main__':
    main()
