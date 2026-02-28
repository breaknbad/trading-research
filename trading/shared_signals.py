#!/usr/bin/env python3
"""Shared Signal Bus — When one bot finds a mover, ALL bots see it.

Writes signals to Supabase `shared_signals` table and posts to #market-triggers.
Every bot runs this on their scanner output. One find = four traders.

Usage:
    # Post a signal (from any bot's scanner)
    python3 shared_signals.py --post --bot vex --ticker BFLY --price 4.35 --change 50.2 --rvol 3.5 --catalyst "Earnings beat, med-tech AI"
    
    # Read latest signals (all bots call this every 5 min)
    python3 shared_signals.py --read --minutes 60
    
    # Programmatic:
    from shared_signals import post_signal, get_recent_signals, broadcast_to_discord
"""
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

from env_loader import SUPABASE_URL, SUPABASE_KEY
from logger import get_logger

log = get_logger('shared_signals')

DISCORD_WEBHOOK = os.environ.get('MARKET_TRIGGERS_WEBHOOK', '')
MARKET_TRIGGERS_CHANNEL = '1474978543564886187'  # #market-triggers

# ── Supabase helpers ─────────────────────────────────────────────────────────

def _supabase(method, endpoint, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation',
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        log.error(f"Supabase {method} {endpoint} failed: {e}")
        return None


# ── Signal Schema ────────────────────────────────────────────────────────────
# Table: shared_signals
# Columns: id (serial), bot_id (text), ticker (text), price (numeric),
#           change_pct (numeric), rvol (numeric), signal_tier (text),
#           catalyst (text), created_at (timestamptz), acted_on_by (jsonb)

TIER_THRESHOLDS = {
    'CONVICTION': {'change': 5.0, 'rvol': 3.0},
    'CONFIRM':    {'change': 3.0, 'rvol': 2.0},
    'SCOUT':      {'change': 1.5, 'rvol': 1.5},
}


def classify_tier(change_pct: float, rvol: float) -> str:
    """Classify signal tier based on price change and relative volume."""
    abs_change = abs(change_pct)
    for tier in ['CONVICTION', 'CONFIRM', 'SCOUT']:
        t = TIER_THRESHOLDS[tier]
        if abs_change >= t['change'] and rvol >= t['rvol']:
            return tier
    return 'WATCH'


def post_signal(bot_id: str, ticker: str, price: float, change_pct: float,
                rvol: float, catalyst: str = '', sector: str = '') -> dict:
    """Post a signal to the shared bus. All bots can read it.
    
    Maps to Supabase schema: id, ticker, price, change_pct, volume, 
    signal_type, source_bot, reason, created_at, claimed_by, status
    """
    
    # Deduplicate: don't post if same bot+ticker within last 30 min
    cutoff = (datetime.utcnow() - timedelta(minutes=30)).isoformat() + 'Z'
    existing = _supabase('GET',
        f"shared_signals?source_bot=eq.{bot_id}&ticker=eq.{ticker}&created_at=gte.{cutoff}&select=id")
    if existing and len(existing) > 0:
        log.info(f"Signal {ticker} already posted by {bot_id} in last 30min, skipping")
        return {'status': 'duplicate', 'ticker': ticker}
    
    tier = classify_tier(change_pct, rvol)
    now = datetime.utcnow().isoformat() + 'Z'
    
    # Map to actual Supabase schema
    signal = {
        'source_bot': bot_id,
        'ticker': ticker,
        'price': price,
        'change_pct': round(change_pct, 2),
        'volume': round(rvol, 1),  # rvol stored in volume column
        'signal_type': tier,
        'reason': catalyst or sector or '',
        'created_at': now,
        'claimed_by': None,
        'status': 'OPEN',
    }
    
    # Also keep local-friendly format for fallback
    signal_local = {
        'bot_id': bot_id,
        'ticker': ticker,
        'price': price,
        'change_pct': round(change_pct, 2),
        'rvol': round(rvol, 1),
        'signal_tier': tier,
        'catalyst': catalyst,
        'sector': sector,
        'created_at': now,
        'acted_on_by': json.dumps([]),
    }
    
    result = _supabase('POST', 'shared_signals', signal)
    if result:
        log.info(f"📡 Signal posted: {tier} {ticker} {change_pct:+.1f}% RVOL {rvol}x by {bot_id}")
    else:
        # Local fallback using local-friendly format
        fallback_path = os.path.join(os.path.dirname(__file__), 'cache', 'shared_signals.jsonl')
        os.makedirs(os.path.dirname(fallback_path), exist_ok=True)
        with open(fallback_path, 'a') as f:
            f.write(json.dumps(signal_local) + '\n')
        log.warning(f"Supabase write failed, saved locally: {fallback_path}")
    
    return {'status': 'posted', 'tier': tier, **signal_local}


def get_recent_signals(minutes: int = 60, min_tier: str = 'SCOUT') -> list:
    """Get all signals from the last N minutes at or above min_tier."""
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat() + 'Z'
    
    tier_order = ['CONVICTION', 'CONFIRM', 'SCOUT', 'WATCH']
    min_idx = tier_order.index(min_tier) if min_tier in tier_order else 3
    allowed_tiers = tier_order[:min_idx + 1]
    
    # Fetch all recent, filter client-side (Supabase OR filters are ugly)
    result = _supabase('GET',
        f"shared_signals?created_at=gte.{cutoff}&order=created_at.desc&select=*")
    
    if not result:
        # Try local fallback
        fallback_path = os.path.join(os.path.dirname(__file__), 'cache', 'shared_signals.jsonl')
        if os.path.exists(fallback_path):
            signals = []
            with open(fallback_path) as f:
                for line in f:
                    s = json.loads(line.strip())
                    if s.get('created_at', '') >= cutoff:
                        signals.append(s)
            result = signals
        else:
            return []
    
    # Handle both DB schema (signal_type) and local schema (signal_tier)
    return [s for s in result if s.get('signal_type', s.get('signal_tier')) in allowed_tiers]


def mark_acted(signal_id: int, bot_id: str, action: str = 'BUY'):
    """Mark that a bot acted on a signal (for tracking hit rate)."""
    # Fetch current acted_on_by
    result = _supabase('GET', f"shared_signals?id=eq.{signal_id}&select=acted_on_by")
    if result and len(result) > 0:
        acted = json.loads(result[0].get('acted_on_by', '[]')) if isinstance(result[0].get('acted_on_by'), str) else result[0].get('acted_on_by', [])
        acted.append({'bot_id': bot_id, 'action': action, 'at': datetime.utcnow().isoformat() + 'Z'})
        _supabase('PATCH', f"shared_signals?id=eq.{signal_id}", {'acted_on_by': json.dumps(acted)})


def format_signal_alert(signal: dict) -> str:
    """Format a signal for Discord posting."""
    tier_emoji = {'CONVICTION': '🔴', 'CONFIRM': '🟡', 'SCOUT': '🟢', 'WATCH': '⚪'}
    direction = '📈' if signal['change_pct'] > 0 else '📉'
    
    emoji = tier_emoji.get(signal['signal_tier'], '⚪')
    lines = [
        f"{emoji} **{signal['signal_tier']}** | {direction} **{signal['ticker']}** "
        f"{signal['change_pct']:+.1f}% @ ${signal['price']:.2f} | RVOL {signal['rvol']}x",
        f"Found by: {signal['bot_id']} | {signal.get('catalyst', 'N/A')}",
    ]
    return '\n'.join(lines)


def format_signal_digest(signals: list) -> str:
    """Format multiple signals as a digest for Discord."""
    if not signals:
        return "**📡 Signal Bus** — No new signals this cycle."
    
    lines = [f"**📡 Shared Signal Bus** — {len(signals)} active signals\n"]
    
    # Group by tier
    for tier in ['CONVICTION', 'CONFIRM', 'SCOUT']:
        tier_signals = [s for s in signals if s['signal_tier'] == tier]
        if tier_signals:
            lines.append(f"**{tier}:**")
            for s in tier_signals:
                lines.append(format_signal_alert(s))
            lines.append("")
    
    lines.append("*All bots: review and act. Log trades via trade.py before posting.*")
    return '\n'.join(lines)


# ── Supabase table creation SQL (run once) ───────────────────────────────────
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS shared_signals (
    id SERIAL PRIMARY KEY,
    bot_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    price NUMERIC NOT NULL,
    change_pct NUMERIC NOT NULL,
    rvol NUMERIC DEFAULT 0,
    signal_tier TEXT NOT NULL DEFAULT 'WATCH',
    catalyst TEXT DEFAULT '',
    sector TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    acted_on_by JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_signals_created ON shared_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON shared_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_tier ON shared_signals(signal_tier);

-- RLS: allow all authenticated reads, restrict writes to service role
ALTER TABLE shared_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Anyone can read signals" ON shared_signals FOR SELECT USING (true);
CREATE POLICY "Service can write signals" ON shared_signals FOR INSERT WITH CHECK (true);
"""


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Shared Signal Bus')
    parser.add_argument('--post', action='store_true', help='Post a new signal')
    parser.add_argument('--read', action='store_true', help='Read recent signals')
    parser.add_argument('--digest', action='store_true', help='Format digest for Discord')
    parser.add_argument('--bot', help='Bot ID')
    parser.add_argument('--ticker', help='Ticker symbol')
    parser.add_argument('--price', type=float, help='Current price')
    parser.add_argument('--change', type=float, help='Change percent')
    parser.add_argument('--rvol', type=float, default=1.0, help='Relative volume')
    parser.add_argument('--catalyst', default='', help='Catalyst description')
    parser.add_argument('--minutes', type=int, default=60, help='Lookback window')
    parser.add_argument('--min-tier', default='SCOUT', help='Minimum tier to show')
    parser.add_argument('--sql', action='store_true', help='Print table creation SQL')
    args = parser.parse_args()
    
    if args.sql:
        print(CREATE_TABLE_SQL)
    elif args.post:
        if not all([args.bot, args.ticker, args.price, args.change]):
            parser.error("--post requires --bot, --ticker, --price, --change")
        result = post_signal(args.bot, args.ticker, args.price, args.change, args.rvol, args.catalyst)
        print(json.dumps(result, indent=2))
    elif args.read or args.digest:
        signals = get_recent_signals(args.minutes, args.min_tier)
        if args.digest:
            print(format_signal_digest(signals))
        else:
            print(json.dumps(signals, indent=2, default=str))
    else:
        parser.print_help()
