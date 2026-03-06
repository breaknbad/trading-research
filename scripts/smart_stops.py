#!/usr/bin/env python3
"""smart_stops.py — Simple adaptive stop formula.

THE RULE: Fast + Loud = Hold. Slow + Quiet = Bail.

3 questions → 1 stop level:
  Q1: Fast crash or slow bleed? (price change rate)
  Q2: Volume spiking or quiet? (volume vs average)
  Q3: BTC or alt? (asset class)

Usage:
  python3 scripts/smart_stops.py                    # Check all open positions
  python3 scripts/smart_stops.py --ticker BTC-USD   # Check one ticker
"""
import json, sys, os, urllib.request
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent

# Base stops by asset
BASE_STOPS = {
    'BTC': 0.030,    # 3.0% — rebounds 63% from deep dips
    'ETH': 0.025,    # 2.5% — coin flip
    'SOL': 0.020,    # 2.0% — fades 56%, short leash
    'LINK': 0.025,
    'DEFAULT': 0.020  # alts get 2%
}

def get_base_stop(ticker):
    for key, val in BASE_STOPS.items():
        if key in ticker:
            return val
    return BASE_STOPS['DEFAULT']


def calculate_smart_stop(ticker, entry_price, current_price, high_price,
                          dip_rate_pct_per_hour=0, volume_ratio=1.0,
                          position_age_minutes=0):
    """
    Returns (stop_price, stop_pct, reasoning)
    
    dip_rate_pct_per_hour: how fast it's dropping (negative = dropping)
    volume_ratio: current volume / average volume
    position_age_minutes: how long we've held
    """
    base = get_base_stop(ticker)
    reasons = []
    
    # Q1: Fast crash or slow bleed?
    if abs(dip_rate_pct_per_hour) > 1.0:
        # Fast crash — widen stop (rebounds likely)
        modifier = 1.3  # 30% wider
        reasons.append(f"FAST move ({dip_rate_pct_per_hour:+.1f}%/hr) → widen 30%")
    elif abs(dip_rate_pct_per_hour) < 0.3:
        # Slow bleed — tighten stop
        modifier = 0.7  # 30% tighter
        reasons.append(f"SLOW bleed ({dip_rate_pct_per_hour:+.1f}%/hr) → tighten 30%")
    else:
        modifier = 1.0
        reasons.append(f"Normal pace ({dip_rate_pct_per_hour:+.1f}%/hr)")
    
    # Q2: Volume spiking or quiet?
    if volume_ratio > 1.5:
        # High volume — widen (panic selling, rebound likely)
        modifier *= 1.2
        reasons.append(f"HIGH volume ({volume_ratio:.1f}x) → widen 20%")
    elif volume_ratio < 0.5:
        # Low volume — tighten (quiet distribution)
        modifier *= 0.8
        reasons.append(f"LOW volume ({volume_ratio:.1f}x) → tighten 20%")
    else:
        reasons.append(f"Normal volume ({volume_ratio:.1f}x)")
    
    # Q3: Position age — trail if in profit
    adjusted_stop_pct = base * modifier
    
    if position_age_minutes < 30:
        # New position — give it room
        adjusted_stop_pct *= 1.3
        reasons.append("NEW position (<30min) → widen 30%")
        reference_price = entry_price
    elif current_price > entry_price * 1.005:
        # In profit — trail from high water mark
        trail_pct = min(adjusted_stop_pct, 0.015)  # Trail at max 1.5%
        stop_price = high_price * (1 - trail_pct)
        # Don't let trail go below entry (lock breakeven)
        stop_price = max(stop_price, entry_price)
        reasons.append(f"IN PROFIT → trail {trail_pct*100:.1f}% from high ${high_price:,.2f}")
        return stop_price, (current_price - stop_price) / current_price, reasons
    else:
        reference_price = entry_price
    
    # Calculate stop price
    stop_price = reference_price * (1 - adjusted_stop_pct)
    actual_pct = (current_price - stop_price) / current_price
    
    return stop_price, actual_pct, reasons


def check_positions():
    """Check all open positions and calculate smart stops."""
    # Load .env
    env = {}
    env_file = WORKSPACE / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"')
    
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    hdr = {'apikey': key, 'Authorization': f'Bearer {key}'}
    
    # Get open positions
    req = urllib.request.Request(
        f'{url}/rest/v1/trades?bot_id=eq.vex&status=eq.OPEN&select=ticker,quantity,price_usd,created_at,trade_id',
        headers=hdr
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        positions = json.loads(r.read())
    
    if not positions:
        print("No open positions.")
        return
    
    # Get live prices
    gecko_ids = {'BTC-USD': 'bitcoin', 'ETH-USD': 'ethereum', 'SOL-USD': 'solana',
                 'LINK-USD': 'chainlink', 'DOGE-USD': 'dogecoin', 'SUI-USD': 'sui'}
    ids_needed = []
    for p in positions:
        gid = gecko_ids.get(p['ticker'], '')
        if gid:
            ids_needed.append(gid)
    
    if ids_needed:
        price_url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids_needed)}&vs_currencies=usd"
        req = urllib.request.Request(price_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            live_prices = json.loads(r.read())
    
    reverse_gecko = {v: k for k, v in gecko_ids.items()}
    price_map = {}
    for gid, data in live_prices.items():
        ticker = reverse_gecko.get(gid, '')
        if ticker:
            price_map[ticker] = data['usd']
    
    now = datetime.now(timezone.utc)
    
    print(f"=== SMART STOPS — {now.strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Rule: Fast+Loud=Hold. Slow+Quiet=Bail.\n")
    
    for p in positions:
        ticker = p['ticker']
        entry = float(p['price_usd'])
        current = price_map.get(ticker, entry)
        high = max(entry, current)  # Simplified — would need historical tracking
        
        # Calculate age
        created = datetime.fromisoformat(p['created_at'].replace('Z', '+00:00'))
        age_min = (now - created).total_seconds() / 60
        
        # Estimate dip rate (simplified — price change per hour since entry)
        hours = max(age_min / 60, 0.1)
        dip_rate = ((current / entry - 1) * 100) / hours
        
        stop_price, stop_pct, reasons = calculate_smart_stop(
            ticker, entry, current, high,
            dip_rate_pct_per_hour=dip_rate,
            volume_ratio=1.0,  # Would need live volume data
            position_age_minutes=age_min
        )
        
        pl = (current - entry) * float(p['quantity'])
        pl_pct = (current / entry - 1) * 100
        
        print(f"{'='*50}")
        print(f"{ticker}  |  Entry: ${entry:,.2f}  |  Now: ${current:,.2f}  |  P&L: ${pl:+,.2f} ({pl_pct:+.2f}%)")
        print(f"  SMART STOP: ${stop_price:,.2f} ({stop_pct*100:.1f}% cushion)")
        print(f"  Distance: ${current - stop_price:,.2f}")
        for r in reasons:
            print(f"    → {r}")
        
        # Action recommendation
        if current <= stop_price:
            print(f"  🔴 ACTION: STOP HIT — EXIT NOW")
        elif stop_pct < 0.01:
            print(f"  🟡 ACTION: TIGHT — watch closely")
        else:
            print(f"  🟢 ACTION: Hold, {stop_pct*100:.1f}% room")
    
    print(f"\n{'='*50}")
    print("Formula: Stop = Entry × (1 - Base%) × Speed × Volume × Age")
    print("Fast+Loud=Hold (widen). Slow+Quiet=Bail (tighten). Trail winners at 1.5%.")


if __name__ == '__main__':
    check_positions()
