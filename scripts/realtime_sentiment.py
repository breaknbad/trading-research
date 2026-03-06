#!/usr/bin/env python3
"""realtime_sentiment.py — Hourly Sentiment Composite (replaces daily F&G)

Builds a real-time sentiment score from:
1. Crypto Fear & Greed Index (baseline, daily)
2. CoinGecko market data (hourly — total market cap change, BTC dominance shift)
3. Funding rates proxy (via price premium between spot/futures indicators)

Outputs: sentiment_composite.json with hourly score (0-100)
Designed to run every 15 min via cron.

Usage: .venv/bin/python3 scripts/realtime_sentiment.py
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace")))
COMPOSITE_PATH = WORKSPACE / "scripts" / "sentiment_composite.json"
SENTIMENT_STATE = WORKSPACE / "scripts" / "sentiment_state.json"

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
        print(f"  [WARN] fetch failed: {e}")
        return None


def get_fng_score():
    """Get Fear & Greed from local state (updated by news_sentiment_scanner)."""
    state = load_json(SENTIMENT_STATE)
    return state.get("last_fng")


def get_market_momentum():
    """CoinGecko global data — market cap change as momentum proxy."""
    data = fetch_json("https://api.coingecko.com/api/v3/global")
    if not data or "data" not in data:
        return None
    
    gdata = data["data"]
    mcap_change = gdata.get("market_cap_change_percentage_24h_usd")
    btc_dom = gdata.get("market_cap_percentage", {}).get("btc")
    
    # Convert market cap change to 0-100 score
    # -5% = 0, 0% = 50, +5% = 100
    if mcap_change is not None:
        momentum_score = max(0, min(100, 50 + (mcap_change * 10)))
    else:
        momentum_score = 50
    
    return {
        "momentum_score": round(momentum_score, 1),
        "mcap_change_24h": round(mcap_change, 2) if mcap_change else None,
        "btc_dominance": round(btc_dom, 1) if btc_dom else None
    }


def get_btc_24h_trend():
    """BTC price trend as additional sentiment input."""
    data = fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true")
    if not data or "bitcoin" not in data:
        return None
    
    btc = data["bitcoin"]
    change = btc.get("usd_24h_change")
    if change is None:
        return None
    
    # Convert to 0-100: -10% = 0, 0% = 50, +10% = 100
    trend_score = max(0, min(100, 50 + (change * 5)))
    return {
        "trend_score": round(trend_score, 1),
        "btc_24h_change": round(change, 2)
    }


def compute_composite():
    """Weighted composite: F&G 30%, Market Momentum 40%, BTC Trend 30%."""
    print(f"[realtime_sentiment] Computing composite at {now_utc().isoformat()}")
    
    fng = get_fng_score()
    momentum = get_market_momentum()
    btc_trend = get_btc_24h_trend()
    
    components = {}
    weights = {}
    
    if fng is not None:
        components["fng"] = fng
        weights["fng"] = 0.30
        print(f"  F&G: {fng}")
    
    if momentum:
        components["momentum"] = momentum["momentum_score"]
        weights["momentum"] = 0.40
        print(f"  Momentum: {momentum['momentum_score']} (mcap {momentum.get('mcap_change_24h')}%)")
    
    if btc_trend:
        components["btc_trend"] = btc_trend["trend_score"]
        weights["btc_trend"] = 0.30
        print(f"  BTC Trend: {btc_trend['trend_score']} ({btc_trend.get('btc_24h_change')}%)")
    
    if not weights:
        print("  [ERROR] No data sources available")
        return None
    
    # Normalize weights if some sources missing
    total_weight = sum(weights.values())
    composite = sum(components[k] * (weights[k] / total_weight) for k in components)
    composite = round(composite, 1)
    
    # Classify
    if composite <= 20:
        regime = "EXTREME_FEAR"
    elif composite <= 35:
        regime = "FEAR"
    elif composite <= 65:
        regime = "NEUTRAL"
    elif composite <= 80:
        regime = "GREED"
    else:
        regime = "EXTREME_GREED"
    
    result = {
        "composite_score": composite,
        "regime": regime,
        "components": {
            "fng": fng,
            "momentum": momentum,
            "btc_trend": btc_trend
        },
        "weights_used": weights,
        "sources_available": len(weights),
        "updated_at": now_utc().isoformat()
    }
    
    # Load history for trend detection
    prev = load_json(COMPOSITE_PATH)
    if prev and "composite_score" in prev:
        prev_score = prev["composite_score"]
        delta = composite - prev_score
        result["delta_from_last"] = round(delta, 1)
        result["trend"] = "IMPROVING" if delta > 3 else ("DETERIORATING" if delta < -3 else "STABLE")
        print(f"  Delta: {delta:+.1f} ({result['trend']})")
    
    save_json(COMPOSITE_PATH, result)
    print(f"[realtime_sentiment] Composite: {composite} ({regime})")
    
    return result


if __name__ == "__main__":
    compute_composite()
