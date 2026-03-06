#!/usr/bin/env python3
"""prediction_scanner.py — Predictions become watchlist entries. Scanner executes them.

Flow:
  Night: Bots write predictions to fleet_signals or predictions.json
  Morning: This script converts predictions into watchlist.json entries
  Intraday: rapid_scanner checks watchlist every 10s, executes when criteria hit

Predictions cascade: leader prediction auto-queues correlation followers.
"""
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PREDICTIONS_FILE = WORKSPACE / "data" / "predictions.json"
WATCHLIST_FILE = WORKSPACE / "watchlist.json"

# Correlation pairs for cascade
CORRELATION_MAP = {
    "BTC-USD": ["SOL-USD", "ETH-USD", "COIN"],
    "ETH-USD": ["SOL-USD", "BTC-USD"],
    "SOL-USD": ["BTC-USD", "ETH-USD"],
    "NVDA": ["AMD", "AVGO", "SMH"],
    "AMD": ["NVDA", "AVGO"],
    "AVGO": ["NVDA", "AMD"],
    "GLD": ["GDX", "SLV"],
    "OXY": ["DVN", "XLE"],
}

# Default stop percentages by tier
STOP_PCT = {
    "CONVICTION": 0.03,
    "CONFIRM": 0.025,
    "SCOUT": 0.02,
}

# Default position sizing by tier (% of available cash)
SIZE_PCT = {
    "CONVICTION": 0.15,
    "CONFIRM": 0.08,
    "SCOUT": 0.04,
}


def load_predictions():
    """Load predictions from local file or Supabase fleet_signals."""
    predictions = []
    
    # Local predictions file
    if PREDICTIONS_FILE.exists():
        try:
            data = json.loads(PREDICTIONS_FILE.read_text())
            if isinstance(data, list):
                predictions.extend(data)
            elif isinstance(data, dict):
                predictions.extend(data.get("predictions", []))
        except (json.JSONDecodeError, KeyError):
            pass
    
    return predictions


def prediction_to_watchlist_entry(pred):
    """Convert a prediction dict into a watchlist entry for rapid_scanner."""
    ticker = pred.get("ticker", "")
    action = pred.get("action", "BUY")
    tier = pred.get("tier", "SCOUT")
    
    entry = {
        "action": action,
        "market": pred.get("market", "CRYPTO" if "-USD" in ticker else "STOCK"),
        "criteria": {},
        "stop_pct": STOP_PCT.get(tier, 0.025),
        "size_pct": SIZE_PCT.get(tier, 0.04),
        "reason": pred.get("thesis", f"Prediction: {ticker} {action}"),
        "source": f"prediction:{pred.get('bot_id', 'unknown')}",
        "tier": tier,
        "expires": pred.get("expires", ""),
    }
    
    # Build criteria from prediction
    if "trigger_price" in pred:
        if action == "BUY":
            if pred.get("direction", "up") == "down":
                entry["criteria"]["price_below"] = pred["trigger_price"]
            else:
                entry["criteria"]["price_above"] = pred["trigger_price"]
        elif action == "SELL":
            entry["criteria"]["price_below"] = pred["trigger_price"]
    
    if "min_volume_ratio" in pred:
        entry["criteria"]["volume_above"] = pred["min_volume_ratio"]
    
    if not entry["criteria"]:
        entry["criteria"]["any"] = True  # No specific trigger = buy at market
    
    return ticker, entry


def add_correlation_followers(watchlist, ticker, pred):
    """Auto-queue correlation followers when leader prediction is loaded."""
    followers = CORRELATION_MAP.get(ticker, [])
    tier = pred.get("tier", "SCOUT")
    
    for follower in followers[:2]:  # Max 2 followers per leader
        if follower not in watchlist:
            watchlist[follower] = {
                "action": "BUY",
                "market": "CRYPTO" if "-USD" in follower else "STOCK",
                "criteria": {"leader_confirmed": ticker},  # Only fires after leader executes
                "stop_pct": STOP_PCT.get("SCOUT", 0.02),  # Tighter stop on followers
                "size_pct": SIZE_PCT.get("SCOUT", 0.04) * 0.5,  # Half size on followers
                "reason": f"Correlation follower: {ticker} prediction triggered, {follower} expected to follow",
                "source": f"correlation:{ticker}",
                "tier": "SCOUT",
            }
    
    return watchlist


def build_watchlist():
    """Convert all predictions into watchlist entries."""
    predictions = load_predictions()
    
    if not predictions:
        print("No predictions found. Create data/predictions.json with prediction entries.")
        print("\nExample format:")
        print(json.dumps([{
            "ticker": "AVGO",
            "action": "BUY",
            "trigger_price": 240,
            "direction": "up",
            "min_volume_ratio": 2.0,
            "tier": "CONFIRM",
            "thesis": "Post-earnings momentum, AI capex thesis",
            "bot_id": "vex",
            "expires": "2026-03-06T16:00:00"
        }], indent=2))
        return {}
    
    # Load existing watchlist (don't overwrite manual entries)
    watchlist = {}
    if WATCHLIST_FILE.exists():
        try:
            existing = json.loads(WATCHLIST_FILE.read_text())
            # Keep non-prediction entries
            for k, v in existing.items():
                if not str(v.get("source", "")).startswith("prediction:"):
                    watchlist[k] = v
        except:
            pass
    
    loaded = 0
    expired = 0
    now = datetime.now(timezone.utc).isoformat()
    
    for pred in predictions:
        # Check expiry
        expires = pred.get("expires", "")
        if expires and expires < now:
            expired += 1
            continue
        
        ticker, entry = prediction_to_watchlist_entry(pred)
        if ticker:
            watchlist[ticker] = entry
            loaded += 1
            
            # Add correlation followers
            watchlist = add_correlation_followers(watchlist, ticker, pred)
    
    # Write watchlist
    WATCHLIST_FILE.write_text(json.dumps(watchlist, indent=2))
    
    print(f"=== PREDICTION SCANNER — {now} ===")
    print(f"Predictions loaded: {loaded} | Expired: {expired}")
    print(f"Watchlist entries: {len(watchlist)} (including correlation followers)")
    
    for ticker, entry in watchlist.items():
        src = entry.get("source", "")
        tier = entry.get("tier", "?")
        criteria = entry.get("criteria", {})
        print(f"  {ticker:12} | {tier:10} | {entry['action']:4} | criteria: {json.dumps(criteria)} | {src}")
    
    return watchlist


if __name__ == "__main__":
    build_watchlist()
