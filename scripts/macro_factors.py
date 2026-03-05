#!/usr/bin/env python3
"""
Macro Factors Module — DXY, Funding Rates, VIX Regime
Provides factor scores for the new factor engine v2.

Usage:
  python3 macro_factors.py --dxy                    # Get DXY factor score
  python3 macro_factors.py --funding BTC-USD        # Get funding rate factor
  python3 macro_factors.py --vix                    # Get VIX regime + weight modifier
  python3 macro_factors.py --all BTC-USD            # All macro factors for a ticker

Import: from macro_factors import get_dxy_factor, get_funding_factor, get_vix_regime
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed", file=sys.stderr)
    sys.exit(1)


# ─── DXY (Dollar Strength) ───

def get_dxy_price():
    """Fetch DXY from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=5d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            result = data["chart"]["result"][0]
            closes = result["indicators"]["quote"][0]["close"]
            # Filter None values
            valid = [c for c in closes if c is not None]
            if len(valid) >= 2:
                return valid[-1], valid[-2]  # current, previous
            elif valid:
                return valid[-1], valid[-1]
    except Exception as e:
        print(f"⚠️ DXY fetch failed: {e}", file=sys.stderr)
    return None, None


def get_dxy_factor(side: str = "long", asset_class: str = "crypto"):
    """
    DXY factor score (0.0 to 1.0).
    - Rising DXY = bearish for gold/commodities/crypto
    - Falling DXY = bullish for gold/commodities/crypto
    
    Returns: (score, direction, change_pct)
    """
    current, previous = get_dxy_price()
    if current is None or previous is None:
        return 0.5, "unknown", 0.0  # Neutral if no data
    
    change_pct = (current - previous) / previous * 100
    
    # Weight by asset class
    weight_map = {
        "gold": 1.0, "commodities": 0.9, "crypto": 0.7,
        "international": 0.8, "tech": 0.3, "equity": 0.2
    }
    sensitivity = weight_map.get(asset_class, 0.5)
    
    # Gradient scoring
    # DXY up 1% = very negative for gold, moderately negative for crypto
    # DXY down 1% = very positive for gold, moderately positive for crypto
    raw_impact = -change_pct * sensitivity  # Negative because DXY up = assets down
    
    if side == "short":
        raw_impact = -raw_impact  # Flip for shorts
    
    # Map to 0-1 range: -2% impact → 0.0, 0% → 0.5, +2% impact → 1.0
    score = max(0.0, min(1.0, 0.5 + raw_impact / 4.0))
    
    direction = "rising" if change_pct > 0 else "falling" if change_pct < 0 else "flat"
    return round(score, 3), direction, round(change_pct, 2)


# ─── Funding Rates (Crypto) ───

FUNDING_APIS = {
    "BTC": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES",
    "ETH": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=ETHUSDT&productType=USDT-FUTURES",
    "SOL": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=SOLUSDT&productType=USDT-FUTURES",
    "NEAR": "https://www.okx.com/api/v5/public/funding-rate?instId=NEAR-USDT-SWAP",
    "DOGE": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=DOGEUSDT&productType=USDT-FUTURES",
    "ADA": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=ADAUSDT&productType=USDT-FUTURES",
    "AVAX": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=AVAXUSDT&productType=USDT-FUTURES",
    "LINK": "https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=LINKUSDT&productType=USDT-FUTURES",
}


def get_funding_rate(ticker: str):
    """Fetch current funding rate for a crypto ticker."""
    base = ticker.upper().replace("-USD", "").replace("USD", "")
    
    # Try Bitget first
    bitget_url = FUNDING_APIS.get(base)
    if bitget_url and "bitget" in bitget_url:
        try:
            r = requests.get(bitget_url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("data"):
                    rate = float(data["data"][0].get("fundingRate", 0))
                    return rate
        except Exception:
            pass
    
    # Try OKX
    okx_url = FUNDING_APIS.get(base)
    if okx_url and "okx" in okx_url:
        try:
            r = requests.get(okx_url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("data"):
                    rate = float(data["data"][0].get("fundingRate", 0))
                    return rate
        except Exception:
            pass
    
    # Fallback: try OKX for any ticker
    try:
        url = f"https://www.okx.com/api/v5/public/funding-rate?instId={base}-USDT-SWAP"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data.get("data"):
                return float(data["data"][0].get("fundingRate", 0))
    except Exception:
        pass
    
    return None


def get_funding_factor(ticker: str, side: str = "long"):
    """
    Funding rate factor score (0.0 to 1.0).
    - Negative funding + long = bullish (shorts paying, squeeze potential)
    - Positive funding + long = bearish (longs crowded)
    - Vice versa for shorts
    
    Returns: (score, rate, interpretation)
    """
    rate = get_funding_rate(ticker)
    if rate is None:
        return 0.5, None, "no data"
    
    # Funding rate is typically -0.01 to +0.01 (basis points)
    # Extreme: -0.05 or +0.05
    
    if side == "long":
        # Negative funding = bullish for longs (shorts paying)
        # More negative = more bullish
        if rate < -0.001:
            score = min(1.0, 0.7 + abs(rate) * 20)  # Strongly bullish
            interp = f"BULLISH — shorts paying {rate*100:.4f}%, squeeze potential"
        elif rate < 0.001:
            score = 0.5  # Neutral
            interp = f"NEUTRAL — funding near zero ({rate*100:.4f}%)"
        else:
            score = max(0.0, 0.3 - rate * 10)  # Bearish — longs crowded
            interp = f"BEARISH — longs crowded, paying {rate*100:.4f}%"
    else:  # short
        if rate > 0.001:
            score = min(1.0, 0.7 + rate * 20)
            interp = f"BULLISH for shorts — longs paying {rate*100:.4f}%"
        elif rate > -0.001:
            score = 0.5
            interp = f"NEUTRAL — funding near zero ({rate*100:.4f}%)"
        else:
            score = max(0.0, 0.3 - abs(rate) * 10)
            interp = f"BEARISH for shorts — shorts crowded ({rate*100:.4f}%)"
    
    return round(score, 3), rate, interp


# ─── VIX Regime ───

def get_vix_price():
    """Fetch VIX from Yahoo Finance."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=2d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            meta = data["chart"]["result"][0]["meta"]
            return float(meta.get("regularMarketPrice", 0))
    except Exception as e:
        print(f"⚠️ VIX fetch failed: {e}", file=sys.stderr)
    return None


def get_vix_regime():
    """
    VIX regime classification + weight modifiers.
    Returns: (regime, vix_level, weight_modifiers)
    
    Weight modifiers adjust other factor category weights:
    - In high VIX: risk weight UP, trend weight DOWN
    - In low VIX: momentum weight UP, risk weight DOWN
    """
    vix = get_vix_price()
    if vix is None:
        return "unknown", None, {}
    
    if vix < 15:
        regime = "RISK_ON"
        modifiers = {
            "trend": 1.0, "momentum": 1.2, "volume": 1.0,
            "volatility": 0.8, "risk": 0.7, "macro": 0.8
        }
    elif vix < 20:
        regime = "NORMAL"
        modifiers = {
            "trend": 1.0, "momentum": 1.0, "volume": 1.0,
            "volatility": 1.0, "risk": 1.0, "macro": 1.0
        }
    elif vix < 25:
        regime = "CAUTIOUS"
        modifiers = {
            "trend": 0.9, "momentum": 0.8, "volume": 1.1,
            "volatility": 1.1, "risk": 1.3, "macro": 1.2
        }
    elif vix < 30:
        regime = "DEFENSIVE"
        modifiers = {
            "trend": 0.7, "momentum": 0.6, "volume": 1.2,
            "volatility": 1.2, "risk": 1.5, "macro": 1.3
        }
    else:
        regime = "CRISIS"
        modifiers = {
            "trend": 0.5, "momentum": 0.4, "volume": 1.3,
            "volatility": 1.3, "risk": 2.0, "macro": 1.5
        }
    
    return regime, round(vix, 2), modifiers


# ─── Time of Day Modifier ───

def get_time_of_day_modifier():
    """
    Time-of-day score modifier based on historical win rates.
    Returns: (modifier, period_name, description)
    
    Modifiers:
    - 9:30-11:00 AM ET: 1.0 (best window, no penalty)
    - 11:00-2:00 PM ET: 0.85 (dead zone, 15% penalty)
    - 2:00-3:00 PM ET: 0.80 (chop zone, 20% penalty)
    - 3:00-3:30 PM ET: 0.90 (power hour, slight penalty unless RVOL surge)
    - After 3:30 PM ET: 0.0 (EXIT ONLY — no new entries)
    - Pre-market (before 9:30): 0.70 (thin liquidity)
    - After-hours (after 4:00): 0.0 for equities, 1.0 for crypto (24/7)
    """
    from datetime import datetime, timezone, timedelta
    
    # Get current ET time
    et_offset = timedelta(hours=-5)  # EST (adjust for EDT if needed)
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + et_offset
    
    hour = now_et.hour
    minute = now_et.minute
    time_val = hour + minute / 60.0
    
    if time_val < 9.5:
        return 0.70, "PRE_MARKET", "Thin liquidity, reduced sizing"
    elif time_val < 11.0:
        return 1.0, "PRIME_TIME", "Best trading window — full conviction"
    elif time_val < 14.0:
        return 0.85, "DEAD_ZONE", "11AM-2PM penalty — most losers come from here"
    elif time_val < 15.0:
        return 0.80, "CHOP_ZONE", "2-3PM chop — TARS lost $3.5K here today"
    elif time_val < 15.5:
        return 0.90, "POWER_HOUR", "Only enter on RVOL >1.5x confirmation"
    elif time_val < 16.0:
        return 0.0, "EXIT_ONLY", "After 3:30 PM — exits and stops only, no new entries"
    else:
        return 0.0, "AFTER_HOURS", "Market closed for equities (crypto = 1.0)"


def get_time_modifier_crypto():
    """Crypto trades 24/7 — always return 1.0 (no time penalty)."""
    return 1.0, "24_7", "Crypto markets always open"


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="Macro Factors Module")
    parser.add_argument("--dxy", action="store_true", help="Get DXY factor")
    parser.add_argument("--funding", help="Get funding rate factor for ticker")
    parser.add_argument("--vix", action="store_true", help="Get VIX regime")
    parser.add_argument("--all", help="All macro factors for a ticker")
    parser.add_argument("--side", default="long", choices=["long", "short"])
    parser.add_argument("--asset-class", default="crypto",
                        choices=["crypto", "gold", "commodities", "tech", "equity", "international"])

    args = parser.parse_args()

    if args.dxy:
        score, direction, change = get_dxy_factor(args.side, args.asset_class)
        print(f"DXY Factor: {score:.3f} | Direction: {direction} | Change: {change:+.2f}%")
        
    elif args.funding:
        score, rate, interp = get_funding_factor(args.funding, args.side)
        rate_str = f"{rate*100:.4f}%" if rate is not None else "N/A"
        print(f"Funding Factor: {score:.3f} | Rate: {rate_str} | {interp}")
        
    elif args.vix:
        regime, level, modifiers = get_vix_regime()
        print(f"VIX Regime: {regime} | Level: {level}")
        print(f"Weight modifiers: {json.dumps(modifiers, indent=2)}")
        
    elif args.all:
        ticker = args.all
        is_crypto = args.asset_class == "crypto" or ticker.endswith("-USD")
        print(f"=== Macro Factors for {ticker} ({args.side}) ===")
        
        score, direction, change = get_dxy_factor(args.side, args.asset_class)
        print(f"DXY:     {score:.3f} ({direction}, {change:+.2f}%)")
        
        if is_crypto:
            score_f, rate, interp = get_funding_factor(ticker, args.side)
            rate_str = f"{rate*100:.4f}%" if rate is not None else "N/A"
            print(f"Funding: {score_f:.3f} ({rate_str}) — {interp}")
        
        regime, level, modifiers = get_vix_regime()
        print(f"VIX:     {regime} ({level})")
        print(f"Modifiers: trend={modifiers.get('trend',1)}, risk={modifiers.get('risk',1)}, momentum={modifiers.get('momentum',1)}")
        
        if is_crypto:
            tod_mod, period, desc = get_time_modifier_crypto()
        else:
            tod_mod, period, desc = get_time_of_day_modifier()
        print(f"Time:    {tod_mod:.2f}x ({period}) — {desc}")
        
        if tod_mod == 0.0:
            print(f"⛔ BLOCKED: {period} — no new entries allowed")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
