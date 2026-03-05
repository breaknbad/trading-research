#!/usr/bin/env python3
"""glide_killer_v3.py — Protect gains + rotate idle positions into correlation followers.

When a position is gliding (giving back gains from session high):
  GREEN  < 1.5% giveback → hold, do nothing
  YELLOW ≥ 1.5% giveback → tighten stop to lock breakeven
  RED    ≥ 2.5% giveback → trim 50%, rotate into correlation follower
  BLACK  ≥ 4.0% giveback → full exit, rotate 100% into follower

"Idle position" = position with <0.5% move in last 2 hours → rotate to follower with tight stop.

Correlation pairs are pre-loaded. When cash frees from a trim/exit, the follower
is queued into watchlist.json for rapid_scanner to execute.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

# Correlation pairs: leader → [followers]
CORRELATION_MAP = {
    "BTC-USD": ["SOL-USD", "ETH-USD", "COIN"],
    "ETH-USD": ["SOL-USD", "BTC-USD", "LINK-USD"],
    "SOL-USD": ["BTC-USD", "ETH-USD"],
    "NVDA": ["AMD", "AVGO", "SMH"],
    "AMD": ["NVDA", "AVGO"],
    "GLD": ["GDX", "SLV"],
    "OXY": ["DVN", "XLE"],
    "DVN": ["OXY", "XLE"],
}

# Glide thresholds (giveback from session high)
GREEN = 0.015   # < 1.5% — hold
YELLOW = 0.015  # ≥ 1.5% — tighten to breakeven
RED = 0.025     # ≥ 2.5% — trim 50%, rotate
BLACK = 0.04    # ≥ 4.0% — full exit, rotate

# Idle threshold
IDLE_THRESHOLD = 0.005  # < 0.5% move = idle
IDLE_HOURS = 2

HIGH_WATER_FILE = WORKSPACE / "data" / "high_water.json"
WATCHLIST_FILE = WORKSPACE / "watchlist.json"

def load_env():
    env = {}
    envfile = WORKSPACE / '.env'
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"')
    return env

def load_high_water():
    if HIGH_WATER_FILE.exists():
        return json.loads(HIGH_WATER_FILE.read_text())
    return {}

def save_high_water(hw):
    HIGH_WATER_FILE.parent.mkdir(exist_ok=True)
    HIGH_WATER_FILE.write_text(json.dumps(hw, indent=2))

def get_positions(url, key, bot_id='vex'):
    import urllib.request
    req = urllib.request.Request(
        f'{url}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=*',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def get_market_prices():
    state_file = WORKSPACE / 'market-state.json'
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            tickers = state.get('tickers', {})
            prices = {}
            for t, d in tickers.items():
                if 'price' in d:
                    prices[t] = d['price']
            return prices
    return {}

def normalize(ticker):
    return ticker.replace('-USD', '').replace('-USDT', '').upper()

def queue_follower(leader_ticker, freed_cash, stop_pct=0.03):
    """Add correlation follower to watchlist.json for rapid_scanner."""
    followers = CORRELATION_MAP.get(leader_ticker, [])
    if not followers:
        return None
    
    follower = followers[0]  # First follower = highest correlation
    
    watchlist = {}
    if WATCHLIST_FILE.exists():
        try:
            watchlist = json.loads(WATCHLIST_FILE.read_text())
        except:
            watchlist = {}
    
    # Queue the follower with tight stop
    watchlist[follower] = {
        "action": "BUY",
        "market": "CRYPTO" if "-USD" in follower else "STOCK",
        "criteria": {"any": True},  # Buy at market
        "max_cost": round(freed_cash * 0.95, 2),  # 95% of freed cash
        "stop_pct": stop_pct,
        "reason": f"Correlation follower: {leader_ticker} exited/trimmed, rotating to {follower}",
        "source": "glide_killer_v3"
    }
    
    WATCHLIST_FILE.write_text(json.dumps(watchlist, indent=2))
    return follower

def run(bot_id='vex'):
    env = load_env()
    url = env.get('SUPABASE_URL', '')
    key = env.get('SUPABASE_KEY', '')
    
    if not url or not key:
        print("ERROR: Missing Supabase credentials")
        return
    
    positions = get_positions(url, key, bot_id)
    prices = get_market_prices()
    hw = load_high_water()
    
    now = datetime.now(timezone.utc).isoformat()
    print(f"=== GLIDE KILLER v3 — {now} ===")
    print(f"Positions: {len(positions)} | Market prices: {len(prices)}")
    
    actions = []
    
    for p in positions:
        ticker = p['ticker']
        base = normalize(ticker)
        entry = float(p['price_usd'])
        current = prices.get(base)
        
        if not current:
            continue
        
        qty = float(p['quantity'])
        
        # Update high water mark
        key_hw = f"{bot_id}:{ticker}"
        prev_high = hw.get(key_hw, entry)
        if current > prev_high:
            hw[key_hw] = current
            prev_high = current
        
        # Calculate giveback from high
        if prev_high > 0:
            giveback = (prev_high - current) / prev_high
        else:
            giveback = 0
        
        gain_pct = (current - entry) / entry
        position_value = qty * current
        
        status = "🟢 GREEN"
        action = None
        
        if giveback >= BLACK:
            status = "⚫ BLACK"
            action = {
                "type": "FULL_EXIT",
                "ticker": ticker,
                "qty": qty,
                "reason": f"BLACK giveback {giveback*100:.1f}% from high ${prev_high:.2f}",
                "freed_cash": position_value
            }
        elif giveback >= RED:
            status = "🔴 RED"
            action = {
                "type": "TRIM_50",
                "ticker": ticker,
                "qty": round(qty * 0.5, 4),
                "reason": f"RED giveback {giveback*100:.1f}% from high ${prev_high:.2f}",
                "freed_cash": position_value * 0.5
            }
        elif giveback >= YELLOW:
            status = "🟡 YELLOW"
            action = {
                "type": "TIGHTEN_STOP",
                "ticker": ticker,
                "new_stop": entry,  # Move stop to breakeven
                "reason": f"YELLOW giveback {giveback*100:.1f}% — tightening to breakeven ${entry:.2f}"
            }
        
        # Check for idle positions
        if abs(gain_pct) < IDLE_THRESHOLD and giveback < YELLOW:
            status = "💤 IDLE"
            action = {
                "type": "IDLE_ROTATE",
                "ticker": ticker,
                "qty": qty,
                "reason": f"IDLE: {gain_pct*100:+.2f}% total move. Consider rotating to follower.",
                "freed_cash": position_value
            }
        
        print(f"  {ticker:12} | ${current:>10.2f} | entry ${entry:.2f} | high ${prev_high:.2f} | "
              f"giveback {giveback*100:.1f}% | gain {gain_pct*100:+.1f}% | {status}")
        
        if action:
            actions.append(action)
            
            # Queue correlation follower for exits and rotations
            if action['type'] in ('FULL_EXIT', 'TRIM_50', 'IDLE_ROTATE'):
                follower = queue_follower(ticker, action.get('freed_cash', 0))
                if follower:
                    print(f"    → Queued follower: {follower} (tight stop)")
    
    save_high_water(hw)
    
    if actions:
        print(f"\n⚠️  GLIDE KILLER ACTIONS: {len(actions)}")
        for a in actions:
            print(f"  {'🔴' if 'EXIT' in a['type'] else '🟡'} {a['type']}: {a.get('ticker','')} — {a['reason']}")
    else:
        print("\n✅ All positions in GREEN zone. No action needed.")
    
    return actions

if __name__ == '__main__':
    bot_id = sys.argv[1] if len(sys.argv) > 1 else 'vex'
    run(bot_id)
