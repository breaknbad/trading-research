# CALLED BY: imported by log_trade.py on every BUY/SHORT
#!/usr/bin/env python3
"""
pre_trade_checker.py — Factor-based pre-trade validation gate.

Every trade MUST pass this checker before logging. Scores factors 0-10,
rejects trades below minimum conviction threshold.

Usage:
    python3 pre_trade_checker.py --ticker NVDA --action BUY --bot tars
    python3 pre_trade_checker.py --ticker GLD --action BUY --bot tars --force
    python3 pre_trade_checker.py --scan   # scan all watchlist tickers
    python3 pre_trade_checker.py --regime  # print current market regime

Outputs JSON with factor scores and GO/NO-GO decision.
"""

import argparse
import json
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
MIN_CONVICTION = 0  # Factor engine is a SIZER not a GATE (DA Round 2 consensus)
MIN_SCOUT_MAX = 4   # Below 4/10 = SCOUT only (2% max). Never blocked.
MIN_CONFIRM = 5     # 5-7 = CONFIRM tier (4-6% of portfolio)
MIN_FULL = 7        # 7+ = CONVICTION tier (6-10% of portfolio)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Market-wide factor cache (VIX/SPY/DXY/breadth don't change per-ticker)
# Saves 4 API calls per ticker during scans
_market_cache = {}
_market_cache_ts = 0
MARKET_CACHE_TTL = 120  # 2 minutes

def get_cached_market_factors():
    """Return cached market-wide factors. Refreshes every 2 min."""
    global _market_cache, _market_cache_ts
    now = time.time()
    if now - _market_cache_ts < MARKET_CACHE_TTL and _market_cache:
        return _market_cache
    _market_cache = {
        "vix": check_vix(),
        "spy_trend": check_spy_trend(),
        "dxy": check_dxy(),
        "breadth": check_breadth(),
    }
    _market_cache_ts = now
    return _market_cache

# ---------------------------------------------------------------------------
# Factor categories — each returns (score 0-2, reason string)
# Gradient scoring: no more binary 0/1. Distance from threshold matters.
# ---------------------------------------------------------------------------

def check_trend(ticker: str, data: dict) -> tuple:
    """Trend check with gradient scoring + breakout detection.
    Uses EMA alignment with gradient, not binary cross."""
    closes = data.get("closes", [])
    highs = data.get("highs", [])
    volumes = data.get("volumes", [])
    if len(closes) < 50:
        return (0, "Insufficient data for trend check")
    
    price = closes[-1]
    # Use EMA (exponential) not SMA for faster response
    def ema(series, period):
        k = 2 / (period + 1)
        e = series[0]
        for p in series[1:]:
            e = p * k + e * (1 - k)
        return e
    
    ema20 = ema(closes[-25:], 20)  # extra lookback for warmup
    ema50 = ema(closes[-55:], 50) if len(closes) >= 55 else sum(closes[-50:]) / 50
    
    # Gradient: how far above/below EMAs (as % of price)
    dist_20 = (price - ema20) / price * 100
    dist_50 = (price - ema50) / price * 100
    
    # Breakout detection: price just broke 20-day high with volume
    recent_high = max(highs[-20:]) if highs and len(highs) >= 20 else price
    avg_vol = sum(volumes[-20:]) / 20 if volumes and len(volumes) >= 20 else 1
    current_vol = volumes[-1] if volumes else 0
    rvol = current_vol / avg_vol if avg_vol > 0 else 0
    breakout = price >= recent_high * 0.99 and rvol >= 1.3
    
    if breakout:
        return (2, f"BREAKOUT: ${price:.2f} at 20d high with RVOL {rvol:.1f}x")
    elif dist_20 > 1.0 and dist_50 > 0:
        return (2, f"Strong uptrend: {dist_20:+.1f}% above EMA20, {dist_50:+.1f}% above EMA50")
    elif dist_50 > 0:
        score = min(2, max(0, round(1 + dist_50 / 2)))
        return (score, f"Above EMA50 ({dist_50:+.1f}%), {'above' if dist_20 > 0 else 'below'} EMA20 ({dist_20:+.1f}%)")
    else:
        return (0, f"Bearish: {dist_50:+.1f}% below EMA50")


def check_volume(ticker: str, data: dict) -> tuple:
    """RVOL — our best predictor. HARD GATE: RVOL <0.8 = automatic 0."""
    volumes = data.get("volumes", [])
    if len(volumes) < 20:
        return (0, "Insufficient volume data")
    
    avg_vol = sum(volumes[-20:]) / 20
    current_vol = volumes[-1] if volumes[-1] else 0
    
    if avg_vol == 0:
        return (0, "Zero average volume")
    
    rvol = current_vol / avg_vol
    
    if rvol >= 2.0:
        return (2, f"Surge volume: RVOL {rvol:.1f}x (institutional conviction)")
    elif rvol >= 1.5:
        return (2, f"High volume: RVOL {rvol:.1f}x (strong interest)")
    elif rvol >= 1.0:
        return (1, f"Normal volume: RVOL {rvol:.1f}x")
    elif rvol >= 0.8:
        return (1, f"Below-average volume: RVOL {rvol:.1f}x (weak)")
    else:
        return (0, f"Dead volume: RVOL {rvol:.1f}x — NO TRADE without volume")


def check_momentum(ticker: str, data: dict, action: str = "BUY") -> tuple:
    """RSI reworked per DA consensus:
    - For LONGS: RSI <40 = HIGH (oversold bounce), RSI 40-65 = good, RSI >80 = too hot
    - For SHORTS: inverted
    - RSI 65-80 = momentum play (score 2 if trend confirms)"""
    closes = data.get("closes", [])
    if len(closes) < 15:
        return (0, "Insufficient data for RSI")
    
    changes = [closes[i] - closes[i-1] for i in range(-14, 0)]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    
    avg_gain = sum(gains) / 14 if gains else 0.001
    avg_loss = sum(losses) / 14 if losses else 0.001
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    if action.upper() in ("BUY",):
        if rsi < 30:
            return (2, f"RSI {rsi:.0f} — deeply oversold, high bounce probability")
        elif rsi < 40:
            return (2, f"RSI {rsi:.0f} — oversold, good long entry zone")
        elif rsi <= 65:
            return (2, f"RSI {rsi:.0f} — healthy momentum range")
        elif rsi <= 80:
            return (1, f"RSI {rsi:.0f} — strong momentum, watch for exhaustion")
        else:
            return (0, f"RSI {rsi:.0f} — extreme overbought, high reversal risk")
    else:  # SHORT
        if rsi > 80:
            return (2, f"RSI {rsi:.0f} — extreme overbought, ideal short")
        elif rsi > 70:
            return (2, f"RSI {rsi:.0f} — overbought, good short entry")
        elif rsi >= 50:
            return (1, f"RSI {rsi:.0f} — neutral, weak short setup")
        else:
            return (0, f"RSI {rsi:.0f} — oversold, DON'T short into weakness")


def check_intraday_structure(ticker: str, data: dict) -> tuple:
    """NEW: Intraday price structure — higher lows (bull) or lower highs (bear).
    The single best 2-hour signal per fleet consensus."""
    closes = data.get("closes", [])
    lows = data.get("lows", [])
    highs = data.get("highs", [])
    
    if len(closes) < 5:
        return (1, "Insufficient data for structure check")
    
    # Check last 5 candles for pattern
    recent_lows = lows[-5:] if len(lows) >= 5 else lows
    recent_highs = highs[-5:] if len(highs) >= 5 else highs
    
    higher_lows = all(recent_lows[i] >= recent_lows[i-1] for i in range(1, len(recent_lows)))
    lower_highs = all(recent_highs[i] <= recent_highs[i-1] for i in range(1, len(recent_highs)))
    
    if higher_lows and not lower_highs:
        return (2, "Higher lows pattern — bullish structure confirmed")
    elif lower_highs and not higher_lows:
        return (0, "Lower highs pattern — bearish structure, avoid longs")
    elif higher_lows and lower_highs:
        return (1, "Converging pattern (triangle) — breakout pending")
    else:
        return (1, "No clear structure — neutral")


def check_catalyst() -> tuple:
    """NEW: Check if there's a known catalyst driving action.
    Reads from Vex's sentiment_state.json if available."""
    try:
        import os
        sentiment_file = os.path.expanduser("~/.openclaw/workspace/sentiment_state.json")
        if os.path.exists(sentiment_file):
            with open(sentiment_file, "r") as f:
                sentiment = json.load(f)
            ts = sentiment.get("timestamp", "")
            if ts:
                return (2, f"Catalyst data available: {len(sentiment.get('signals', []))} active signals")
        return (1, "No catalyst data — proceed with caution, tighter stops")
    except Exception:
        return (1, "Catalyst check unavailable — neutral")


def check_cross_bot_convergence(ticker: str) -> tuple:
    """NEW: Cross-bot convergence — 2+ bots flag same ticker = signal multiplier.
    Reads from shared_signals Supabase table."""
    try:
        import os
        sb_url = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
        sb_key = os.environ.get("SUPABASE_KEY", "")
        if not sb_key:
            # Try .env file
            env_path = os.path.expanduser("~/.openclaw/workspace/.env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("SUPABASE_KEY="):
                            sb_key = line.strip().split("=", 1)[1]
        if not sb_key:
            return (1, "No Supabase key — convergence check skipped")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"{sb_url}/rest/v1/shared_signals?ticker=eq.{ticker.upper()}&created_at=gte.{today}T00:00:00Z&select=source_bot,signal_type"
        headers_sb = {"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
        r = requests.get(url, headers=headers_sb, timeout=10)

        if r.status_code == 200:
            signals = r.json()
            unique_bots = set(s.get("source_bot", "") for s in signals)
            if len(unique_bots) >= 3:
                return (2, f"STRONG convergence: {len(unique_bots)} bots flagged {ticker} today")
            elif len(unique_bots) >= 2:
                return (2, f"Convergence: {len(unique_bots)} bots flagged {ticker} — signal multiplier")
            elif len(unique_bots) == 1:
                return (1, f"Single bot flagged {ticker} — no convergence yet")
            else:
                return (1, f"No fleet signals for {ticker} today")
        return (1, "Convergence check failed — Supabase error")
    except Exception as e:
        return (1, f"Convergence check failed: {e}")


def get_time_of_day_modifier() -> float:
    """Time-of-day modifier — ACTIVITY-BASED, not clock-based (DA Round 2 consensus Mar 3).
    
    REMOVED: 11-2 PM dead zone penalty (0.85x) — replaced by RVOL regime detection
    REMOVED: 3:30 PM hard block (0.0) — Mark explicitly allows ALL market hours
    KEPT: Slight pre/post market discount (0.95x) for equity spread risk
    
    The volume_monitor.py regime system now handles activity-based gating.
    This modifier only handles the edges (pre-market, post-market).
    """
    now_et = datetime.now(timezone(timedelta(hours=-5)))  # EST approximation
    hour = now_et.hour
    minute = now_et.minute
    t = hour + minute / 60.0

    # Weekday check
    if now_et.weekday() >= 5:  # Weekend = crypto only, no penalty
        return 1.0

    if 9.5 <= t < 16.0:
        return 1.0   # Full market hours — ALL of them. No clock penalties.
    else:
        return 0.95   # Pre/post market — slight discount for wider spreads


def check_funding_rate(ticker: str) -> tuple:
    """NEW: Crypto funding rate from Bitget (free, no API key).
    Negative = shorts paying = squeeze setup. Positive >0.05% = crowded longs."""
    if not ticker.endswith("-USD") and not ticker.endswith("USD"):
        return (1, "Not crypto — funding rate N/A")
    
    # Map ticker to Bitget format
    symbol = ticker.replace("-USD", "").replace("USD", "") + "USDT"
    
    try:
        url = f"https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol={symbol}&productType=USDT-FUTURES"
        r = requests.get(url, timeout=10)
        data = r.json()
        
        if data.get("code") == "00000" and data.get("data"):
            rate = float(data["data"][0]["fundingRate"])
            rate_pct = rate * 100
            
            if rate_pct < -0.01:
                return (2, f"Funding {rate_pct:+.3f}% — shorts paying, squeeze potential")
            elif rate_pct < 0.03:
                return (1, f"Funding {rate_pct:+.3f}% — neutral, no crowd")
            else:
                return (0, f"Funding {rate_pct:+.3f}% — crowded longs, reversal risk")
        return (1, "Funding rate data unavailable")
    except Exception as e:
        return (1, f"Funding rate check failed: {e}")


# ---------------------------------------------------------------------------
# Market regime factors (apply to all trades)
# ---------------------------------------------------------------------------

def check_vix() -> tuple:
    """VIX level check — market fear gauge."""
    try:
        url = f"{YAHOO_BASE}/^VIX?interval=1d&range=5d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        vix = result["indicators"]["quote"][0]["close"][-1]
        
        if vix is None:
            return (1, "VIX data unavailable")
        
        if vix < 15:
            return (2, f"VIX {vix:.1f} — low fear, risk-on")
        elif vix < 25:
            return (1, f"VIX {vix:.1f} — moderate, selective entries")
        else:
            return (0, f"VIX {vix:.1f} — HIGH FEAR, reduce size or go defensive")
    except Exception as e:
        return (1, f"VIX check failed: {e}")


def check_spy_trend() -> tuple:
    """S&P 500 trend — broad market direction."""
    try:
        url = f"{YAHOO_BASE}/SPY?interval=1d&range=3mo"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
        
        if len(closes) < 50:
            return (1, "Insufficient SPY data")
        
        price = closes[-1]
        ma20 = sum(closes[-20:]) / 20
        ma50 = sum(closes[-50:]) / 50
        
        if price > ma20 > ma50:
            return (2, f"SPY bullish: ${price:.0f} > MA20 > MA50")
        elif price > ma50:
            return (1, f"SPY mixed: above MA50, below MA20")
        else:
            return (0, f"SPY bearish: below MA50 — reduce long exposure")
    except Exception as e:
        return (1, f"SPY check failed: {e}")


def check_dxy() -> tuple:
    """Dollar strength — strong dollar = headwind for risk assets."""
    try:
        url = f"{YAHOO_BASE}/DX-Y.NYB?interval=1d&range=1mo"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
        
        if len(closes) < 5:
            return (1, "Insufficient DXY data")
        
        dxy = closes[-1]
        dxy_5d = closes[-5]
        change = ((dxy - dxy_5d) / dxy_5d) * 100
        
        if change < -0.5:
            return (2, f"DXY weakening ({change:+.1f}%) — tailwind for risk assets")
        elif change < 0.5:
            return (1, f"DXY flat ({change:+.1f}%) — neutral")
        else:
            return (0, f"DXY strengthening ({change:+.1f}%) — headwind for equities")
    except Exception as e:
        return (1, f"DXY check failed: {e}")


def check_breadth() -> tuple:
    """Market breadth via advancing vs declining issues."""
    # Use RSP (equal-weight S&P) vs SPY as breadth proxy
    try:
        for sym in ["RSP", "SPY"]:
            url = f"{YAHOO_BASE}/{sym}?interval=1d&range=5d"
            r = requests.get(url, headers=HEADERS, timeout=10)
            result = r.json()["chart"]["result"][0]
            closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
            if sym == "RSP":
                rsp_chg = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
            else:
                spy_chg = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
        
        diff = rsp_chg - spy_chg
        if diff > 0.3:
            return (2, f"Breadth strong: RSP {rsp_chg:+.1f}% vs SPY {spy_chg:+.1f}% — broad participation")
        elif diff > -0.3:
            return (1, f"Breadth neutral: RSP {rsp_chg:+.1f}% vs SPY {spy_chg:+.1f}%")
        else:
            return (0, f"Breadth weak: RSP {rsp_chg:+.1f}% vs SPY {spy_chg:+.1f}% — narrow leadership")
    except Exception as e:
        return (1, f"Breadth check failed: {e}")


def check_sector_rotation(ticker: str) -> tuple:
    """Check if the ticker's sector is in favor."""
    # Sector ETF mapping
    sector_map = {
        "XLK": ["AAPL", "MSFT", "NVDA", "AMD", "AVGO", "CRM", "PLTR", "INTC", "QCOM"],
        "XLF": ["JPM", "BAC", "GS", "MS", "WFC"],
        "XLE": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "XLV": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "INSP", "BFLY"],
        "XLI": ["CAT", "GE", "HON", "BA", "RTX", "DRS"],
        "XLP": ["PG", "KO", "PEP", "COST", "WMT"],
        "XLU": ["NEE", "DUK", "SO", "AEP"],
        "GLD": ["GLD", "GDX", "GDXJ", "SLV"],
        "XLRE": ["AMT", "PLD", "EQIX"],
    }
    
    sector_etf = None
    for etf, tickers in sector_map.items():
        if ticker.upper() in tickers or ticker.upper() == etf:
            sector_etf = etf
            break
    
    if not sector_etf:
        return (1, f"No sector mapping for {ticker}")
    
    try:
        url = f"{YAHOO_BASE}/{sector_etf}?interval=1d&range=5d"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
        
        if len(closes) < 5:
            return (1, "Insufficient sector data")
        
        chg_1d = (closes[-1] - closes[-2]) / closes[-2] * 100
        chg_5d = (closes[-1] - closes[0]) / closes[0] * 100
        
        if chg_5d > 1:
            return (2, f"Sector {sector_etf} strong: {chg_5d:+.1f}% 5d — tailwind")
        elif chg_5d > -1:
            return (1, f"Sector {sector_etf} flat: {chg_5d:+.1f}% 5d")
        else:
            return (0, f"Sector {sector_etf} weak: {chg_5d:+.1f}% 5d — headwind")
    except Exception as e:
        return (1, f"Sector check failed: {e}")


# ---------------------------------------------------------------------------
# Yahoo data fetcher
# ---------------------------------------------------------------------------

def fetch_ticker_data(ticker: str) -> dict:
    """Fetch OHLCV data from Yahoo Finance."""
    try:
        url = f"{YAHOO_BASE}/{ticker}?interval=1d&range=3mo"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        
        return {
            "closes": [c for c in quote["close"] if c is not None],
            "highs": [h for h in quote["high"] if h is not None],
            "lows": [l for l in quote["low"] if l is not None],
            "volumes": [v for v in quote["volume"] if v is not None],
        }
    except Exception as e:
        return {"error": str(e), "closes": [], "highs": [], "lows": [], "volumes": []}


# ---------------------------------------------------------------------------
# Main scoring engine
# ---------------------------------------------------------------------------

STOP_HISTORY_FILE = "/tmp/stop_history.json"
DEAD_SIGNALS_FILE = "/tmp/dead_signals.json"

def check_cooldown(ticker: str, bot_id: str) -> tuple:
    """Check if ticker is in cooldown (2+ consecutive stops = dead for session)."""
    try:
        with open(STOP_HISTORY_FILE, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return True, ""
    
    key = f"{bot_id}:{ticker}"
    stops = history.get(key, [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_stops = [s for s in stops if s.startswith(today)]
    
    if len(today_stops) >= 2:
        return False, f"COOLDOWN: {ticker} stopped out {len(today_stops)}x today — dead for session"
    return True, ""

def record_stop(ticker: str, bot_id: str):
    """Record a stop-loss hit for cooldown tracking."""
    try:
        with open(STOP_HISTORY_FILE, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = {}
    
    key = f"{bot_id}:{ticker}"
    if key not in history:
        history[key] = []
    history[key].append(datetime.now(timezone.utc).isoformat())
    
    with open(STOP_HISTORY_FILE, "w") as f:
        json.dump(history, f)

def check_signal_dead(ticker: str) -> tuple:
    """Check if 3+ bots have PASSed on this ticker today."""
    try:
        with open(DEAD_SIGNALS_FILE, "r") as f:
            dead = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return True, ""
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{today}:{ticker}"
    passes = dead.get(key, [])
    
    if len(set(passes)) >= 3:
        return False, f"DEAD SIGNAL: {ticker} rejected by {len(set(passes))} bots today"
    return True, ""

def record_pass(ticker: str, bot_id: str):
    """Record a PASS vote on a ticker."""
    try:
        with open(DEAD_SIGNALS_FILE, "r") as f:
            dead = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        dead = {}
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{today}:{ticker}"
    if key not in dead:
        dead[key] = []
    if bot_id not in dead[key]:
        dead[key].append(bot_id)
    
    with open(DEAD_SIGNALS_FILE, "w") as f:
        json.dump(dead, f)


def score_trade(ticker: str, action: str, bot_id: str) -> dict:
    """Score a potential trade across all factors. Returns dict with GO/NO-GO."""
    
    # Check cooldown (2 consecutive stops = dead)
    cooldown_ok, cooldown_reason = check_cooldown(ticker, bot_id)
    if not cooldown_ok:
        return {
            "ticker": ticker, "action": action, "bot_id": bot_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": 0, "max_possible": 10, "tier": "REJECT",
            "sizing": "BLOCKED — cooldown active",
            "go": False, "block_reason": cooldown_reason, "factors": {},
        }
    
    # Check dead signal (3+ PASS votes)
    signal_ok, signal_reason = check_signal_dead(ticker)
    if not signal_ok:
        return {
            "ticker": ticker, "action": action, "bot_id": bot_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": 0, "max_possible": 10, "tier": "REJECT",
            "sizing": "BLOCKED — dead signal",
            "go": False, "block_reason": signal_reason, "factors": {},
        }
    
    data = fetch_ticker_data(ticker)
    
    # Ticker-specific factors (weighted)
    ticker_factors = {
        "trend": check_trend(ticker, data),
        "volume": check_volume(ticker, data),
        "momentum": check_momentum(ticker, data, action),
        "intraday_structure": check_intraday_structure(ticker, data),
        "sector_rotation": check_sector_rotation(ticker),
        "catalyst": check_catalyst(),
        "funding_rate": check_funding_rate(ticker),
        "convergence": check_cross_bot_convergence(ticker),
    }
    
    # Market-wide factors (cached — saves 4 API calls per ticker)
    market_factors = get_cached_market_factors().copy()
    
    # Weights per DA consensus + Mark's directive (total = 100%)
    # Volume boosted to 18% (Alfred), structure cut to 7% (unproven)
    weights = {
        "volume": 0.18,       # Best predictor — HIGHEST weight (Alfred's amendment)
        "vix": 0.12,          # Essential regime gate
        "trend": 0.12,        # Core but reduced from old 30%
        "momentum": 0.10,     # Reworked RSI
        "spy_trend": 0.08,    # Broad market direction
        "sector_rotation": 0.08,  # Sector relative strength
        "catalyst": 0.07,     # NEW — news-driven or not
        "intraday_structure": 0.07,  # NEW — higher lows / lower highs (cut from 10%)
        "convergence": 0.05,  # NEW — cross-bot signal multiplier
        "funding_rate": 0.05, # NEW — crypto funding rate
        "breadth": 0.04,      # Market participation
        "dxy": 0.04,          # Dollar strength (lane-variable)
    }
    
    # Adjust DXY weight by lane — higher for gold/commodities
    gold_tickers = {"GLD", "GDX", "GDXJ", "SLV", "GOLD", "NEM", "AEM"}
    if ticker.upper() in gold_tickers:
        weights["dxy"] = 0.10
        weights["breadth"] = 0.00  # Gold doesn't care about equity breadth
    
    # For crypto, zero out irrelevant equity factors
    is_crypto = ticker.endswith("-USD") or ticker.endswith("USD")
    if is_crypto:
        weights["sector_rotation"] = 0.00
        weights["spy_trend"] = 0.03  # Reduced but not zero (correlation exists)
        weights["funding_rate"] = 0.12  # Boost funding rate for crypto
        weights["breadth"] = 0.00
    
    # Flip scores for SHORT/SELL actions (bearish = good for shorts)
    if action.upper() in ("SHORT", "SELL"):
        for key in ["trend", "spy_trend", "intraday_structure"]:
            if key in ticker_factors:
                score, reason = ticker_factors[key]
                ticker_factors[key] = (2 - score, f"[INVERSE for {action}] {reason}")
            elif key in market_factors:
                score, reason = market_factors[key]
                market_factors[key] = (2 - score, f"[INVERSE for {action}] {reason}")
    
    all_factors = {**ticker_factors, **market_factors}
    
    # Weighted scoring (not equal weight anymore)
    weighted_total = 0
    weight_sum = 0
    for key, (score, reason) in all_factors.items():
        w = weights.get(key, 0.05)
        weighted_total += score * w
        weight_sum += 2 * w  # max possible per factor is 2
    
    normalized = round((weighted_total / weight_sum) * 10, 1) if weight_sum > 0 else 0
    
    # TIME-OF-DAY MODIFIER (simplified — clock penalties removed per DA Round 2)
    tod_modifier = get_time_of_day_modifier()
    tod_note = ""
    if tod_modifier < 1.0:
        normalized = round(normalized * tod_modifier, 1)
        tod_note = f" (pre/post market: {tod_modifier}x)"
    
    # HARD GATES: These override the score
    vol_score = all_factors.get("volume", (1, ""))[0]
    vix_score = all_factors.get("vix", (1, ""))[0]
    if vol_score == 0 and not is_crypto:  # Dead volume = no trade (stocks only)
        normalized = min(normalized, 1.9)  # Force below minimum
    
    # Sizing recommendation — SIZER NOT GATE (DA Round 2 consensus)
    # Factor engine NEVER blocks. It sizes. Contrarian trades need a path.
    if normalized >= MIN_FULL:
        sizing = "CONVICTION (6-10% of portfolio)"
        tier = "CONVICTION"
    elif normalized >= MIN_CONFIRM:
        sizing = "CONFIRM (4-6% of portfolio)"
        tier = "CONFIRM"
    elif normalized >= MIN_SCOUT_MAX:
        sizing = "SCOUT (2-4% of portfolio)"
        tier = "SCOUT"
    else:
        sizing = "SCOUT-MIN (2% max — low conviction, contrarian OK)"
        tier = "SCOUT"  # Still SCOUT, just capped at 2%
    
    return {
        "ticker": ticker,
        "action": action,
        "bot_id": bot_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": normalized,
        "max_possible": 10,
        "tier": tier,
        "sizing": sizing + tod_note,
        "go": True,  # ALWAYS go — factor engine sizes, doesn't block
        "time_modifier": tod_modifier,
        "factors": {k: {"score": s, "reason": r} for k, (s, r) in all_factors.items()},
    }


def print_report(result: dict):
    """Pretty print the factor report."""
    go = "✅ GO" if result["go"] else "❌ NO-GO"
    print(f"\n{'='*60}")
    print(f"  {result['ticker']} {result['action']} — {go} ({result['score']}/10)")
    print(f"  Tier: {result['tier']} | {result['sizing']}")
    print(f"{'='*60}")
    
    for name, info in result["factors"].items():
        icon = "🟢" if info["score"] == 2 else "🟡" if info["score"] == 1 else "🔴"
        print(f"  {icon} {name}: {info['score']}/2 — {info['reason']}")
    
    print(f"\n  TOTAL: {result['score']}/10")
    if not result["go"]:
        print(f"  ⛔ TRADE REJECTED — score below minimum {MIN_CONVICTION}/10")
    print()


def scan_watchlist():
    """Scan all tickers on the watchlist."""
    watchlist = [
        "SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA",
        "AMD", "CRM", "PLTR", "INTC", "AVGO", "QCOM",
        "GLD", "GDX", "GDXJ", "SLV",
        "XLE", "XLV", "XLP", "XLI", "XLF",
        "BTC-USD", "ETH-USD",
        "TLT", "HYG", "LQD",
        "EFA", "EWC", "EEM",
    ]
    
    results = []
    for ticker in watchlist:
        try:
            result = score_trade(ticker, "BUY", "scan")
            results.append(result)
            time.sleep(0.5)  # Rate limit
        except Exception as e:
            print(f"  ⚠️ {ticker}: {e}")
    
    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    print(f"\n{'='*60}")
    print(f"  WATCHLIST SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'='*60}")
    
    for r in results:
        icon = "🟢" if r["score"] >= MIN_FULL else "🟡" if r["score"] >= MIN_CONFIRM else "🔴"
        print(f"  {icon} {r['ticker']:8s} {r['score']:4.1f}/10  {r['tier']:10s}")
    
    # Top picks
    top = [r for r in results if r["score"] >= MIN_CONFIRM]
    print(f"\n  TOP PICKS ({len(top)} above confirm threshold):")
    for r in top:
        print(f"    {r['ticker']} — {r['score']}/10 — {r['sizing']}")


def print_regime():
    """Print current market regime summary."""
    vix_score, vix_reason = check_vix()
    spy_score, spy_reason = check_spy_trend()
    dxy_score, dxy_reason = check_dxy()
    breadth_score, breadth_reason = check_breadth()
    
    total = vix_score + spy_score + dxy_score + breadth_score
    
    if total >= 6:
        regime = "🟢 RISK-ON"
    elif total >= 4:
        regime = "🟡 NEUTRAL"
    else:
        regime = "🔴 RISK-OFF"
    
    print(f"\n{'='*60}")
    print(f"  MARKET REGIME: {regime} ({total}/8)")
    print(f"{'='*60}")
    print(f"  {vix_reason}")
    print(f"  {spy_reason}")
    print(f"  {dxy_reason}")
    print(f"  {breadth_reason}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-trade factor checker")
    parser.add_argument("--ticker", help="Ticker to check")
    parser.add_argument("--action", default="BUY", help="BUY/SELL/SHORT/COVER")
    parser.add_argument("--bot", default="tars", help="Bot ID")
    parser.add_argument("--scan", action="store_true", help="Scan full watchlist")
    parser.add_argument("--regime", action="store_true", help="Print market regime")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--force", action="store_true", help="Skip minimum conviction check")
    
    args = parser.parse_args()
    
    if args.regime:
        print_regime()
    elif args.scan:
        scan_watchlist()
    elif args.ticker:
        result = score_trade(args.ticker, args.action, args.bot)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_report(result)
        
        if not result["go"] and not args.force:
            sys.exit(1)
    else:
        parser.print_help()
