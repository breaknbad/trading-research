#!/usr/bin/env python3
"""
Alfred — Volume Spike Detector
Monitors crypto for abnormal volume that precedes big moves.
Volume spike >2x in 15-min window = early warning signal.
Designed to run frequently (every 5 min) and fire alerts BEFORE price moves.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
CREDS_FILE = Path.home() / ".supabase_trading_creds"
STATE_FILE = WORKSPACE / "volume_spike_state.json"

# Crypto pairs to monitor
PAIRS = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "AVAX-USD": "avalanche-2",
    "DOGE-USD": "dogecoin",
    "XRP-USD": "ripple",
    "LINK-USD": "chainlink",
    "ADA-USD": "cardano"
}

VOLUME_SPIKE_THRESHOLD = 2.0  # 2x normal = spike
PRICE_ROC_THRESHOLD = 1.5     # 1.5% in 15 min = momentum

def load_creds():
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"last_prices": {}, "last_check": None, "alerts_fired": {}}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def get_market_data():
    """Get price + volume data from CoinGecko."""
    ids = ",".join(PAIRS.values())
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_vol=true&include_24hr_change=true"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ❌ CoinGecko error: {e}")
        return {}

def get_bitget_volume(symbol="BTCUSDT"):
    """Get recent volume from Bitget for more granular data."""
    url = f"https://api.bitget.com/api/v2/mix/market/ticker?symbol={symbol}&productType=USDT-FUTURES"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("data"):
                return {
                    "volume24h": float(data["data"][0].get("baseVolume", 0)),
                    "price": float(data["data"][0].get("lastPr", 0)),
                    "high24h": float(data["data"][0].get("high24h", 0)),
                    "low24h": float(data["data"][0].get("low24h", 0))
                }
    except:
        pass
    return None

def detect_spikes(market_data, state):
    """Compare current data against state to detect spikes."""
    alerts = []
    now = datetime.now(timezone.utc)
    cg_to_ticker = {v: k for k, v in PAIRS.items()}
    
    for cg_id, ticker in cg_to_ticker.items():
        if cg_id not in market_data:
            continue
            
        current_price = market_data[cg_id].get("usd", 0)
        volume_24h = market_data[cg_id].get("usd_24h_vol", 0)
        change_24h = market_data[cg_id].get("usd_24h_change", 0)
        
        prev = state.get("last_prices", {}).get(ticker, {})
        prev_price = prev.get("price", current_price)
        
        # Rate of change since last check
        if prev_price > 0:
            roc_pct = ((current_price - prev_price) / prev_price) * 100
        else:
            roc_pct = 0
        
        # Check for alert conditions
        alert = None
        
        # Big price move since last check
        if abs(roc_pct) >= PRICE_ROC_THRESHOLD:
            direction = "🟢 BULLISH" if roc_pct > 0 else "🔴 BEARISH"
            alert = {
                "ticker": ticker,
                "type": "MOMENTUM",
                "direction": direction,
                "roc_pct": round(roc_pct, 2),
                "price": current_price,
                "change_24h": round(change_24h, 2),
                "message": f"{ticker} {direction} momentum: {roc_pct:+.2f}% since last check @ ${current_price:,.2f}"
            }
        
        # 24h change acceleration (big mover developing)
        if abs(change_24h) >= 5.0:
            # Check cooldown — don't re-alert same ticker within 30 min
            last_alert = state.get("alerts_fired", {}).get(ticker, "")
            if last_alert:
                try:
                    last_time = datetime.fromisoformat(last_alert)
                    if (now - last_time).total_seconds() < 1800:
                        continue
                except:
                    pass
            
            direction = "🟢 BULLISH" if change_24h > 0 else "🔴 BEARISH"
            alert = {
                "ticker": ticker,
                "type": "BIG_MOVER",
                "direction": direction,
                "change_24h": round(change_24h, 2),
                "price": current_price,
                "message": f"🚨 {ticker} BIG MOVER: {change_24h:+.1f}% in 24h @ ${current_price:,.2f} — evaluate ADD position"
            }
        
        if alert:
            alerts.append(alert)
            state.setdefault("alerts_fired", {})[ticker] = now.isoformat()
        
        # Update state
        state.setdefault("last_prices", {})[ticker] = {
            "price": current_price,
            "volume_24h": volume_24h,
            "timestamp": now.isoformat()
        }
    
    state["last_check"] = now.isoformat()
    return alerts, state

def supabase_insert(creds, table, data):
    url = f"{creds['SUPABASE_URL']}/rest/v1/{table}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "apikey": creds["SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {creds['SUPABASE_ANON_KEY']}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status
    except Exception as e:
        return {"error": str(e)}

def check_funding_rates():
    """Check funding rates for short squeeze signals."""
    pairs = [("BTCUSDT","BTC-USD"), ("ETHUSDT","ETH-USD"), ("SOLUSDT","SOL-USD"),
             ("AVAXUSDT","AVAX-USD"), ("DOGEUSDT","DOGE-USD"), ("XRPUSDT","XRP-USD"), ("LINKUSDT","LINK-USD")]
    squeeze_signals = []
    for symbol, ticker in pairs:
        try:
            url = f"https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol={symbol}&productType=USDT-FUTURES"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("data"):
                    rate = float(data["data"][0].get("fundingRate", 0))
                    if rate < -0.005:  # Negative funding = shorts paying longs
                        squeeze_signals.append({
                            "ticker": ticker,
                            "funding_rate": rate,
                            "message": f"🔴 {ticker} SHORT SQUEEZE SETUP: funding {rate*100:+.4f}% (shorts paying longs)"
                        })
        except:
            pass
    return squeeze_signals

def check_fear_greed_divergence(market_data):
    """Detect F&G extreme fear + rising prices = contrarian BUY."""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        fg_value = int(data["data"][0]["value"])
        
        # Check if prices are rising despite extreme fear
        cg_to_ticker = {v: k for k, v in PAIRS.items()}
        rising_count = 0
        for cg_id in market_data:
            change = market_data[cg_id].get("usd_24h_change", 0)
            if change > 3.0:
                rising_count += 1
        
        if fg_value <= 15 and rising_count >= 3:
            return {
                "type": "FG_DIVERGENCE",
                "fg_value": fg_value,
                "rising_assets": rising_count,
                "message": f"🚨 CONTRARIAN BUY SIGNAL: F&G={fg_value} (extreme fear) but {rising_count} assets up 3%+. Short squeeze likely."
            }
    except:
        pass
    return None

def main():
    print(f"Alfred Volume Spike Detector — {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print("=" * 50)
    
    creds = load_creds()
    state = load_state()
    
    print("\n📊 Fetching market data...")
    market_data = get_market_data()
    if not market_data:
        print("  ❌ No market data available")
        sys.exit(1)
    
    # Also get Bitget BTC for granular data
    btc_bitget = get_bitget_volume("BTCUSDT")
    if btc_bitget:
        print(f"  BTC Bitget: ${btc_bitget['price']:,.0f} | 24h range: ${btc_bitget['low24h']:,.0f}-${btc_bitget['high24h']:,.0f}")
    
    print("\n🔍 Scanning for spikes...")
    alerts, state = detect_spikes(market_data, state)
    
    # NEW: Check funding rates for squeeze signals
    print("\n💰 Checking funding rates...")
    squeeze_signals = check_funding_rates()
    for s in squeeze_signals:
        print(f"  {s['message']}")
        alerts.append({"ticker": s["ticker"], "type": "SQUEEZE", "message": s["message"]})
    if not squeeze_signals:
        print("  ✅ No squeeze signals")
    
    # NEW: Check F&G divergence
    print("\n😱 Checking F&G divergence...")
    fg_div = check_fear_greed_divergence(market_data)
    if fg_div:
        print(f"  {fg_div['message']}")
        alerts.append({"ticker": "MARKET", "type": "FG_DIVERGENCE", "message": fg_div["message"]})
    else:
        print("  ✅ No F&G divergence")
    
    save_state(state)
    
    if alerts:
        print(f"\n🚨 {len(alerts)} ALERTS:")
        for a in alerts:
            print(f"  {a['message']}")
            
            # Log to Supabase
            if creds.get("SUPABASE_URL"):
                signal = {
                    "bot": "ALFRED",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "category": "performance_anomaly",
                    "severity": "WARN" if a["type"] == "MOMENTUM" else "CRITICAL",
                    "description": a["message"],
                    "auto_fixable": False,
                    "status": "open"
                }
                supabase_insert(creds, "system_issues", signal)
    else:
        print("  ✅ No spikes detected — markets stable")
    
    # Check volume regime for glide killer status
    regime_file = WORKSPACE / "logs" / "volume_regime.json"
    if regime_file.exists():
        try:
            regime = json.loads(regime_file.read_text())
            if regime.get("glide_killer_active"):
                print(f"\n🚨 GLIDE KILLER ACTIVE — regime {regime.get('regime')}, RVOL {regime.get('rvol'):.2f}x")
                print(f"   Suppressing ADD signals. Only TRIM/PROTECT actions allowed.")
                # Filter out ADD signals when glide killer is active
                alerts = [a for a in alerts if a.get("type") in ("SQUEEZE", "FG_DIVERGENCE")]
        except:
            pass
    
    # Print current state summary
    print(f"\n📋 Tracking {len(state.get('last_prices', {}))} assets")
    for ticker, data in sorted(state.get("last_prices", {}).items()):
        print(f"  {ticker}: ${data['price']:,.2f}")
    
    return alerts

if __name__ == "__main__":
    main()
