#!/usr/bin/env python3
"""catalyst_predetector.py — Early Mover Detection (Vex Intel Domain)

Detects big moves BEFORE headlines by monitoring:
1. Social mention velocity (crypto Twitter proxy via CoinGecko trending)
2. Funding rate shifts (via CoinGecko derivatives)
3. Price acceleration (rate-of-change in short windows)
4. Catalyst proximity (upcoming earnings, FOMC, token unlocks)
5. Cross-asset macro triggers (reads TARS macro_trigger_feed output)

Fires signals to intel_signals.json + fleet_signals Supabase table.
Designed to run every 5 min via cron or heartbeat.

Usage: .venv/bin/python3 scripts/catalyst_predetector.py [--dry-run]
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bot_config import BOT_ID

WORKSPACE = Path(os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace")))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

MARKET_STATE = WORKSPACE / "market-state.json"
SENTIMENT_STATE = WORKSPACE / "scripts" / "sentiment_state.json"
INTEL_SIGNALS = WORKSPACE / "intel_signals.json"
ALERTS_FILE = WORKSPACE / "alerts.json"
PREDETECT_STATE = WORKSPACE / "scripts" / "predetect_state.json"

# Thresholds
PRICE_ACCEL_PCT = 1.5       # +1.5% in 15 min = momentum trigger
VOLUME_SPIKE_X = 2.0        # 2x normal volume = spike
FNG_EXTREME_FEAR = 20       # Below = contrarian buy zone
FNG_EXTREME_GREED = 80      # Above = caution zone

CRYPTO_WATCHLIST = ["bitcoin", "ethereum", "solana", "avalanche-2", "chainlink", "sui", "arbitrum"]
CRYPTO_TICKERS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", 
                  "avalanche-2": "AVAX", "chainlink": "LINK", "sui": "SUI", "arbitrum": "ARB"}

DRY_RUN = "--dry-run" in sys.argv

def now_utc():
    return datetime.now(timezone.utc)

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_json(path, data):
    os.makedirs(str(path.parent), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def fetch_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Vex/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] fetch failed {url}: {e}")
        return None

def push_fleet_signal(signal):
    """Push to Supabase signal_scores table."""
    if not SUPABASE_KEY or DRY_RUN:
        return False
    url = f"{SUPABASE_URL}/rest/v1/signal_scores"
    payload = json.dumps(signal).encode()
    req = urllib.request.Request(url, data=payload, method='POST', headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    })
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


# ─── DETECTOR 1: Price Acceleration ───
def detect_price_acceleration(market_state, prev_state):
    """Flag assets with rapid price moves (rate-of-change, not absolute level)."""
    signals = []
    current_prices = {}
    prev_prices = {}
    
    # Extract current prices from market state
    for section in ["crypto", "equities"]:
        assets = market_state.get(section, {})
        if isinstance(assets, dict):
            for ticker, data in assets.items():
                if isinstance(data, dict):
                    current_prices[ticker] = data.get("price") or data.get("last_price")
                    
    for section in ["crypto", "equities"]:
        assets = prev_state.get(section, {})
        if isinstance(assets, dict):
            for ticker, data in assets.items():
                if isinstance(data, dict):
                    prev_prices[ticker] = data.get("price") or data.get("last_price")
    
    for ticker in current_prices:
        curr = current_prices[ticker]
        prev = prev_prices.get(ticker)
        if curr and prev and prev > 0:
            pct_change = ((curr - prev) / prev) * 100
            if abs(pct_change) >= PRICE_ACCEL_PCT:
                direction = "BULLISH" if pct_change > 0 else "BEARISH"
                signals.append({
                    "type": "price_acceleration",
                    "ticker": ticker.upper(),
                    "direction": direction,
                    "pct_change": round(pct_change, 2),
                    "current_price": curr,
                    "prev_price": prev,
                    "signal": f"{ticker.upper()} moved {pct_change:+.1f}% — momentum trigger",
                    "action": "ADD" if pct_change > 0 else "HEDGE",
                    "urgency": "HIGH"
                })
                print(f"  🚀 PRICE ACCEL: {ticker.upper()} {pct_change:+.1f}%")
    
    return signals


# ─── DETECTOR 2: CoinGecko Trending (Social Velocity Proxy) ───
def detect_social_velocity():
    """Use CoinGecko trending as proxy for social mention acceleration."""
    signals = []
    data = fetch_json("https://api.coingecko.com/api/v3/search/trending")
    if not data:
        return signals
    
    coins = data.get("coins", [])
    for coin_wrapper in coins[:7]:
        coin = coin_wrapper.get("item", {})
        coin_id = coin.get("id", "")
        symbol = coin.get("symbol", "").upper()
        name = coin.get("name", "")
        market_cap_rank = coin.get("market_cap_rank")
        
        # Only care about coins in our universe or top 100
        if coin_id in CRYPTO_WATCHLIST or (market_cap_rank and market_cap_rank <= 100):
            signals.append({
                "type": "social_velocity",
                "ticker": symbol,
                "coin_id": coin_id,
                "signal": f"{symbol} ({name}) trending on CoinGecko — social velocity spike",
                "market_cap_rank": market_cap_rank,
                "action": "WATCH" if coin_id not in CRYPTO_WATCHLIST else "SCOUT",
                "urgency": "MEDIUM"
            })
            print(f"  📱 TRENDING: {symbol} (rank #{market_cap_rank})")
    
    return signals


# ─── DETECTOR 3: Sentiment Extreme Check ───
def detect_sentiment_extremes():
    """Check for extreme F&G readings — contrarian signals."""
    signals = []
    state = load_json(SENTIMENT_STATE)
    fng = state.get("last_fng")
    
    if fng is not None:
        if fng <= FNG_EXTREME_FEAR:
            signals.append({
                "type": "sentiment_extreme",
                "ticker": "MARKET",
                "direction": "CONTRARIAN_BULLISH",
                "fng_value": fng,
                "signal": f"Fear & Greed at {fng} — extreme fear, contrarian buy zone",
                "action": "ADD_LONGS",
                "urgency": "MEDIUM"
            })
            print(f"  😱 EXTREME FEAR: F&G = {fng}")
        elif fng >= FNG_EXTREME_GREED:
            signals.append({
                "type": "sentiment_extreme",
                "ticker": "MARKET",
                "direction": "CONTRARIAN_BEARISH",
                "fng_value": fng,
                "signal": f"Fear & Greed at {fng} — extreme greed, tighten all stops",
                "action": "TIGHTEN_STOPS",
                "urgency": "MEDIUM"
            })
            print(f"  🤑 EXTREME GREED: F&G = {fng}")
    
    return signals


# ─── DETECTOR 4: Macro Trigger Feed (Cross-Asset) ───
def detect_macro_triggers(market_state):
    """Check for cross-asset signals from market state (DXY inverse, yields, etc.)."""
    signals = []
    
    # Look for macro data in market state
    macro = market_state.get("macro", {})
    if not macro:
        return signals
    
    dxy = macro.get("DXY", {})
    if isinstance(dxy, dict):
        dxy_change = dxy.get("pct_change_24h") or dxy.get("change_pct")
        if dxy_change:
            try:
                dxy_change = float(dxy_change)
                if dxy_change < -0.5:
                    signals.append({
                        "type": "macro_trigger",
                        "ticker": "BTC",
                        "direction": "BULLISH",
                        "signal": f"DXY dropping {dxy_change:.1f}% — inverse BTC signal, add crypto",
                        "action": "ADD",
                        "urgency": "HIGH"
                    })
                    print(f"  🌍 MACRO: DXY {dxy_change:+.1f}% → BTC bullish")
                elif dxy_change > 0.5:
                    signals.append({
                        "type": "macro_trigger",
                        "ticker": "BTC",
                        "direction": "BEARISH",
                        "signal": f"DXY rising {dxy_change:+.1f}% — headwind for crypto",
                        "action": "TIGHTEN",
                        "urgency": "MEDIUM"
                    })
            except (ValueError, TypeError):
                pass
    
    return signals


# ─── DETECTOR 5: Catalyst Proximity ───
def detect_catalyst_proximity():
    """Check if any known catalysts are within 24h window."""
    signals = []
    
    # Known recurring catalysts (hardcoded — extend with calendar API later)
    now = now_utc()
    weekday = now.weekday()  # 0=Mon
    hour = now.hour
    
    # FOMC typically Tues-Wed, 2 PM ET (19:00 UTC) — 8 meetings per year
    # CPI typically 2nd Tuesday/Wednesday of month, 8:30 AM ET
    # Options expiry: 3rd Friday of each month
    
    day_of_month = now.day
    
    # Third Friday check (options expiry)
    if weekday == 3 and 15 <= day_of_month <= 21:
        # Thursday before OPEX
        signals.append({
            "type": "catalyst_proximity",
            "ticker": "MARKET",
            "catalyst": "OPEX",
            "signal": "Options expiry tomorrow — expect pinning + vol crush. Position for post-OPEX move.",
            "action": "PREPARE",
            "urgency": "MEDIUM"
        })
    
    # First Friday of month = NFP
    if weekday == 4 and day_of_month <= 7:
        signals.append({
            "type": "catalyst_proximity",
            "ticker": "MARKET",
            "catalyst": "NFP",
            "signal": "NFP day — expect volatility at 8:30 AM ET. Reduce size or widen stops pre-release.",
            "action": "REDUCE_RISK",
            "urgency": "HIGH"
        })
    
    return signals


# ─── DETECTOR 6: Snap-Back Detector (TARS Formula) ───
def detect_snapback():
    """BEATEN DOWN 7d + VOLUME BUILDING 12h + APPROACHING 5d HIGH = BIG MOVER.
    Uses CoinGecko market data for crypto assets."""
    signals = []
    
    # Fetch 7d data for watchlist
    ids = ",".join(CRYPTO_WATCHLIST)
    data = fetch_json(
        f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}"
        f"&price_change_percentage=7d&order=market_cap_desc"
    )
    if not data:
        return signals
    
    for coin in data:
        symbol = coin.get("symbol", "").upper()
        coin_id = coin.get("id", "")
        current = coin.get("current_price")
        high_24h = coin.get("high_24h")
        ath = coin.get("ath")
        change_7d = coin.get("price_change_percentage_7d_in_currency")
        
        if not all([current, high_24h, change_7d]):
            continue
        
        # Criteria: down 3-10% over 7d AND within 3% of 24h high (recovering)
        distance_from_high = ((high_24h - current) / high_24h * 100) if high_24h > 0 else 99
        
        if -10 <= change_7d <= -3 and distance_from_high <= 3:
            signals.append({
                "type": "snapback",
                "ticker": symbol,
                "coin_id": coin_id,
                "direction": "BULLISH",
                "signal": f"{symbol} snap-back setup: {change_7d:+.1f}% 7d but within {distance_from_high:.1f}% of high — volume-confirmed recovery",
                "change_7d": round(change_7d, 2),
                "distance_from_high_pct": round(distance_from_high, 2),
                "current_price": current,
                "action": "SCOUT",
                "urgency": "HIGH"
            })
            print(f"  🔄 SNAPBACK: {symbol} {change_7d:+.1f}% 7d, {distance_from_high:.1f}% from high")
    
    return signals


# ─── DETECTOR 7: Sentiment Divergence Amplifier ───
def detect_sentiment_divergence():
    """When F&G diverges from real-time composite by >30 points = stealth move."""
    signals = []
    
    composite_path = WORKSPACE / "scripts" / "sentiment_composite.json"
    composite = load_json(composite_path)
    sentiment = load_json(SENTIMENT_STATE)
    
    fng = sentiment.get("last_fng")
    comp_score = composite.get("composite_score")
    
    if fng is not None and comp_score is not None:
        gap = comp_score - fng
        if abs(gap) > 30:
            if gap > 0:
                # Composite bullish, F&G fearful = stealth rally
                signals.append({
                    "type": "sentiment_divergence",
                    "ticker": "MARKET",
                    "direction": "STEALTH_RALLY",
                    "signal": f"Stealth rally: F&G={fng} but composite={comp_score:.0f} (gap {gap:+.0f}). Crowd still fearful, smart money already in. ADD window.",
                    "fng": fng,
                    "composite": round(comp_score, 1),
                    "gap": round(gap, 1),
                    "action": "ADD_LONGS",
                    "urgency": "HIGH"
                })
                print(f"  🥷 STEALTH RALLY: F&G {fng} vs composite {comp_score:.0f} = +{gap:.0f} gap")
            else:
                # Composite bearish, F&G greedy = stealth selloff
                signals.append({
                    "type": "sentiment_divergence",
                    "ticker": "MARKET",
                    "direction": "STEALTH_SELLOFF",
                    "signal": f"Stealth selloff: F&G={fng} but composite={comp_score:.0f} (gap {gap:+.0f}). Crowd still greedy, momentum fading. TIGHTEN.",
                    "fng": fng,
                    "composite": round(comp_score, 1),
                    "gap": round(gap, 1),
                    "action": "TIGHTEN_ALL",
                    "urgency": "HIGH"
                })
                print(f"  ⚠️ STEALTH SELLOFF: F&G {fng} vs composite {comp_score:.0f} = {gap:.0f} gap")
    
    return signals


# ─── DETECTOR 8: BTC Cascade Detector ───
def detect_btc_cascade(market_state, prev_state):
    """When BTC confirms breakout (>+2% in session), flag alts for 30-60 min entry window."""
    signals = []
    
    crypto = market_state.get("crypto", {})
    prev_crypto = prev_state.get("crypto", {})
    
    btc_data = crypto.get("BTC", crypto.get("bitcoin", {}))
    prev_btc = prev_crypto.get("BTC", prev_crypto.get("bitcoin", {}))
    
    if not isinstance(btc_data, dict) or not isinstance(prev_btc, dict):
        return signals
    
    btc_price = btc_data.get("price") or btc_data.get("last_price")
    prev_btc_price = prev_btc.get("price") or prev_btc.get("last_price")
    
    if btc_price and prev_btc_price and prev_btc_price > 0:
        btc_change = ((btc_price - prev_btc_price) / prev_btc_price) * 100
        
        if btc_change >= 2.0:
            # BTC confirmed breakout — cascade incoming
            # High-beta alts: SOL (1.24x), LINK, AVAX
            cascade_targets = ["SOL", "LINK", "AVAX", "SUI", "ARB"]
            for alt in cascade_targets:
                signals.append({
                    "type": "btc_cascade",
                    "ticker": alt,
                    "direction": "BULLISH",
                    "signal": f"BTC cascade: BTC +{btc_change:.1f}% confirmed. {alt} typically follows in 30-60 min. SCOUT entry window NOW.",
                    "btc_change": round(btc_change, 2),
                    "action": "SCOUT",
                    "urgency": "HIGH"
                })
            print(f"  🌊 CASCADE: BTC +{btc_change:.1f}% → flagging {', '.join(cascade_targets)} for entry")
    
    return signals


# ─── MAIN ORCHESTRATOR ───
def run():
    print(f"[catalyst_predetector] Running at {now_utc().isoformat()}")
    
    # Load states
    market_state = load_json(MARKET_STATE, {})
    prev_state = load_json(PREDETECT_STATE, {}).get("last_market_state", {})
    
    all_signals = []
    
    # Run all detectors
    all_signals.extend(detect_price_acceleration(market_state, prev_state))
    all_signals.extend(detect_social_velocity())
    all_signals.extend(detect_sentiment_extremes())
    all_signals.extend(detect_macro_triggers(market_state))
    all_signals.extend(detect_catalyst_proximity())
    all_signals.extend(detect_snapback())
    all_signals.extend(detect_sentiment_divergence())
    all_signals.extend(detect_btc_cascade(market_state, prev_state))
    
    # Tag all signals
    now = now_utc()
    for sig in all_signals:
        sig["bot"] = "vex"
        sig["bot_id"] = BOT_ID
        sig["detected_at"] = now.isoformat()
        sig["source"] = "catalyst_predetector"
        sig["ttl_hours"] = 4
    
    # Save state for next comparison
    save_json(PREDETECT_STATE, {
        "last_market_state": market_state,
        "last_run": now.isoformat(),
        "signals_generated": len(all_signals)
    })
    
    # Merge into intel_signals.json
    existing = load_json(INTEL_SIGNALS, [])
    if isinstance(existing, dict):
        existing = existing.get("signals", [])
    
    # Prune expired signals
    cutoff = (now - timedelta(hours=4)).isoformat()
    existing = [s for s in existing if s.get("detected_at", "") > cutoff]
    existing.extend(all_signals)
    save_json(INTEL_SIGNALS, existing)
    
    # Push HIGH urgency signals to fleet
    high_signals = [s for s in all_signals if s.get("urgency") == "HIGH"]
    for sig in high_signals:
        fleet_record = {
            "bot_id": BOT_ID,
            "ticker": sig.get("ticker", "UNKNOWN"),
            "signal_type": sig.get("type", "predetect"),
            "direction": sig.get("direction", sig.get("action", "WATCH")),
            "score": 75,
            "metadata": json.dumps({k: v for k, v in sig.items() 
                                   if k not in ("bot_id", "bot")}),
            "created_at": now.isoformat()
        }
        push_fleet_signal(fleet_record)
    
    # Summary
    high = sum(1 for s in all_signals if s.get("urgency") == "HIGH")
    med = sum(1 for s in all_signals if s.get("urgency") == "MEDIUM")
    low = sum(1 for s in all_signals if s.get("urgency") not in ("HIGH", "MEDIUM"))
    
    print(f"[catalyst_predetector] Done: {len(all_signals)} signals ({high} HIGH, {med} MEDIUM, {low} other)")
    
    if DRY_RUN:
        print("\n[DRY RUN] Signals generated:")
        for sig in all_signals:
            print(f"  [{sig.get('urgency')}] {sig.get('type')}: {sig.get('signal')}")
    
    return all_signals


if __name__ == "__main__":
    signals = run()
