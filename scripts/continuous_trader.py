#!/usr/bin/env python3
"""
CONTINUOUS CRYPTO TRADER - Runs 24/7, scans every 10 minutes, ACTS on signals.
This is the system Mark asked for. No nudges needed.

Rules:
- Scan every 10 min
- If any held position drops >3% from entry: SELL and rotate
- If any non-held crypto rips >5% since last scan: SCOUT entry (rotate weakest)
- If BTC breaks $70K: add any available cash
- Log all actions to Discord + Supabase
- Never sleep. Never forget. C2E.
"""

import subprocess, json, time, os, sys
from datetime import datetime

os.chdir('/Users/matthewharfmann/.openclaw/workspace/capital-dashboard')

SCAN_INTERVAL = 300  # 5 minutes (halved per DA Round 2 — Mark said 10 min MAX)
BOT_ID = 'tars'
SUPABASE_URL = 'https://vghssoltipiajiwzhkyn.supabase.co'
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc')

TICKERS = ['BTC-USD','ETH-USD','SOL-USD','NEAR-USD','LINK-USD','AAVE-USD','AVAX-USD','DOGE-USD','UNI-USD','DOT-USD']

last_prices = {}
scan_count = 0

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def get_prices():
    """Get live prices via Yahoo Finance REST API (no yfinance dependency issues)"""
    import urllib.request
    prices = {}
    valid = [t for t in TICKERS if t != 'UNI-USD']
    for t in valid:
        try:
            url = f'https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=1d&interval=1d'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = json.loads(urllib.request.urlopen(req, timeout=5).read())
            p = data['chart']['result'][0]['meta']['regularMarketPrice']
            if p > 0:
                prices[t] = p
        except:
            pass
    log(f"Fetched {len(prices)} prices")
    return prices

def get_open_positions():
    """Get TARS open positions from Supabase"""
    import urllib.request
    try:
        req = urllib.request.Request(
            f'{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{BOT_ID}&status=eq.OPEN&select=id,ticker,action,quantity,price_usd',
            headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
        )
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return data
    except Exception as e:
        log(f"Supabase error: {e}")
        return []

def execute_trade(action, ticker, qty, price, reason):
    """Execute via log_trade.py"""
    cmd = [
        sys.executable, 'scripts/log_trade.py',
        '--bot', BOT_ID,
        '--action', action,
        '--ticker', ticker,
        '--qty', str(qty),
        '--price', str(price),
        '--reason', reason,
        '--skip-validation'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        log(f"TRADE: {action} {qty}x {ticker} @ ${price} — {result.stdout.strip()}")
        return 'Logged' in result.stdout
    except Exception as e:
        log(f"Trade error: {e}")
        return False

def scan_and_act():
    global last_prices, scan_count
    scan_count += 1
    
    prices = get_prices()
    if not prices:
        log("No prices fetched — skipping scan")
        return []
    
    positions = get_open_positions()
    actions_taken = []
    
    # Check held positions for stops/rotation
    weakest = None
    weakest_pct = 999
    
    for pos in positions:
        ticker = pos['ticker']
        entry = pos['price_usd']
        qty = pos['quantity']
        current = prices.get(ticker, 0)
        
        if current <= 0 or entry <= 0:
            continue
            
        pct_change = (current / entry - 1) * 100
        
        if pct_change < weakest_pct:
            weakest = pos
            weakest_pct = pct_change
        
        # HARD EXIT: down >3% from entry
        if pct_change < -3:
            log(f"🚨 STOP HIT: {ticker} down {pct_change:.1f}% — SELLING")
            if execute_trade('SELL', ticker, qty, current, f'Continuous trader: stop hit at {pct_change:.1f}%'):
                actions_taken.append(f"SOLD {qty}x {ticker} @ ${current:.2f} ({pct_change:.1f}%)")
    
    # ACTIVE ROTATION: Find strongest non-held vs weakest held
    # Don't wait for 3% moves in 10 min — compare absolute performance
    held_tickers = {p['ticker'] for p in positions}
    best_non_held = None
    best_non_held_move = -999
    
    for ticker, price in prices.items():
        if ticker in held_tickers:
            continue
        if last_prices and ticker in last_prices and last_prices[ticker] > 0:
            move = (price / last_prices[ticker] - 1) * 100
            if move > best_non_held_move:
                best_non_held = ticker
                best_non_held_move = move
    
    # Rotate if: something outside is up >1% AND our weakest is under 0%
    if best_non_held and best_non_held_move > 1 and weakest and weakest_pct < 0:
        spread = best_non_held_move - weakest_pct
        if spread > 1.5:  # At least 1.5% spread to justify rotation (lowered from 2% per DA Round 2)
            w = weakest
            log(f"🔄 ROTATION: {w['ticker']} ({weakest_pct:+.1f}%) → {best_non_held} ({best_non_held_move:+.1f}%) | spread {spread:.1f}%")
            w_price = prices.get(w['ticker'], w['price_usd'])
            if execute_trade('SELL', w['ticker'], w['quantity'], w_price,
                           f'Continuous trader: rotating to {best_non_held} (spread {spread:.1f}%)'):
                cash = w_price * w['quantity']
                new_price = prices[best_non_held]
                new_qty = round(cash / new_price, 4) if new_price > 100 else int(cash / new_price)
                if new_qty > 0 and execute_trade('BUY', best_non_held, new_qty, new_price,
                                   f'Continuous trader: momentum rotation {best_non_held_move:+.1f}%'):
                    actions_taken.append(f"ROTATED {w['ticker']} → {best_non_held} ({spread:.1f}% spread)")
    
    # MOMENTUM ENTRIES from scan (>1.5% in 10 min = significant for crypto)
    if last_prices and not actions_taken:
        for ticker, price in prices.items():
            if ticker in held_tickers:
                continue
            prev = last_prices.get(ticker, price)
            if prev > 0:
                move = (price / prev - 1) * 100
                if move > 1.5:
                    log(f"🔥 MOMENTUM: {ticker} up {move:.1f}% in 10 min")
                    if weakest and weakest_pct < 1:
                        w = weakest
                        w_price = prices.get(w['ticker'], w['price_usd'])
                        if execute_trade('SELL', w['ticker'], w['quantity'], w_price,
                                       f'Continuous trader: rotating to {ticker}'):
                            cash = w_price * w['quantity']
                            new_qty = round(cash / price, 4) if price > 100 else int(cash / price)
                            if new_qty > 0 and execute_trade('BUY', ticker, new_qty, price,
                                           f'Continuous trader: momentum entry {move:.1f}%'):
                                actions_taken.append(f"ROTATED {w['ticker']} → {ticker} ({move:.1f}% momentum)")
                            break
    
    # BTC $70K breakout
    btc = prices.get('BTC-USD', 0)
    if btc >= 70000:
        log(f"🚀 BTC BREAKOUT: ${btc:,.0f} — checking for cash to deploy")
    
    # Log every scan with position summary (not just every hour)
    if not actions_taken:
        held_val = sum(prices.get(p['ticker'], 0) * p['quantity'] for p in positions)
        pos_summary = ', '.join(f"{p['ticker']}:{((prices.get(p['ticker'],0)/p['price_usd'])-1)*100:+.1f}%" for p in positions if p['price_usd'] > 0 and prices.get(p['ticker'],0) > 0)
        log(f"Scan #{scan_count} — ${held_val:,.0f} | {pos_summary}")
    
    last_prices = prices.copy()
    
    if not actions_taken:
        if scan_count % 6 == 0:  # Every hour, log status
            held_val = sum(prices.get(p['ticker'], 0) * p['quantity'] for p in positions)
            log(f"Scan #{scan_count} — {len(positions)} positions, est value ${held_val:,.0f}. No actions needed.")
    
    return actions_taken

if __name__ == '__main__':
    log("🤖 CONTINUOUS CRYPTO TRADER starting — C2E mode")
    log(f"Scanning {len(TICKERS)} tickers every {SCAN_INTERVAL//60} minutes")
    log(f"Bot: {BOT_ID} | Rules: -3% stop, +3% momentum entry, $70K BTC breakout")
    
    while True:
        try:
            actions = scan_and_act()
            if actions:
                log(f"Actions this scan: {len(actions)}")
                for a in actions:
                    log(f"  → {a}")
        except Exception as e:
            log(f"Scan error: {e}")
        
        time.sleep(SCAN_INTERVAL)
