#!/usr/bin/env python3
"""
Technical Scanner — Eddie V's dumb loop
Runs every 60s via launchd. Zero AI. Pure math.
Calculates RSI, MACD, volume spikes, support/resistance proximity.
Writes alerts to alerts.json and signals to fleet_signals table.
"""
import json, os, sys, time, urllib.request, urllib.error, math
from datetime import datetime, timezone, timedelta
import sys as _sys; _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

# Config
WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALERTS_PATH = os.path.join(WORKSPACE, "alerts.json")
LOG_PATH = os.path.join(WORKSPACE, "logs", "technical_scanner.log")

# Ensure dirs exist
os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass

def fetch_json(url, headers=None):
    """Fetch JSON from URL with error handling."""
    hdrs = {"User-Agent": "TechnicalScanner/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        log(f"Fetch error {url}: {e}")
        return None

def get_open_positions():
    """Read positions from trading-state.json."""
    state_path = os.path.join(WORKSPACE, "trading-state.json")
    try:
        with open(state_path) as f:
            state = json.load(f)
        return state.get("positions", [])
    except:
        return []

def fetch_candles_finnhub(symbol, resolution="D", count=50):
    """Fetch OHLCV candles from Finnhub."""
    if not FINNHUB_KEY:
        return None
    now = int(time.time())
    start = now - (count * 86400 * 2)  # Extra buffer for weekends
    url = f"https://finnhub.io/api/v1/stock/candle?symbol={symbol}&resolution={resolution}&from={start}&to={now}&token={FINNHUB_KEY}"
    data = fetch_json(url)
    if not data or data.get("s") != "ok":
        return None
    candles = []
    for i in range(len(data.get("c", []))):
        candles.append({
            "open": data["o"][i],
            "high": data["h"][i],
            "low": data["l"][i],
            "close": data["c"][i],
            "volume": data["v"][i],
            "timestamp": data["t"][i]
        })
    return candles[-count:] if len(candles) > count else candles


def fetch_candles_yahoo(symbol, count=50):
    """Fallback: fetch OHLCV candles from Yahoo Finance (free, no key)."""
    try:
        # Convert crypto tickers: BTC-USD stays, NEAR-USD stays, stocks stay
        yahoo_symbol = symbol.replace("-USD", "-USD")  # Already correct format
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=3mo"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = fetch_json(url, headers=headers)
        if not resp:
            return None
        result = resp.get("chart", {}).get("result", [{}])[0]
        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        if not timestamps or not quote.get("close"):
            return None
        candles = []
        for i in range(len(timestamps)):
            c = quote["close"][i]
            if c is None:
                continue
            candles.append({
                "open": quote["open"][i] or c,
                "high": quote["high"][i] or c,
                "low": quote["low"][i] or c,
                "close": c,
                "volume": quote["volume"][i] or 0,
                "timestamp": timestamps[i]
            })
        return candles[-count:] if len(candles) > count else candles
    except Exception as e:
        log(f"Yahoo fallback failed for {symbol}: {e}")
        return None


def fetch_candles(symbol, resolution="D", count=50):
    """Fetch candles with Finnhub primary, Yahoo fallback."""
    candles = fetch_candles_finnhub(symbol, resolution, count)
    if candles:
        return candles
    # Finnhub failed — try Yahoo
    candles = fetch_candles_yahoo(symbol, count)
    if candles:
        log(f"Using Yahoo fallback for {symbol}")
    return candles


def calc_rsi(closes, period=14):
    """Calculate RSI from close prices."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calc_ema(values, period):
    """Calculate EMA."""
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * multiplier + ema
    return round(ema, 4)

def calc_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD line, signal line, histogram."""
    if len(closes) < slow + signal:
        return None
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    if ema_fast is None or ema_slow is None:
        return None
    
    # Build MACD series for signal line
    macd_series = []
    for i in range(slow - 1, len(closes)):
        subset = closes[:i+1]
        ef = calc_ema(subset, fast)
        es = calc_ema(subset, slow)
        if ef is not None and es is not None:
            macd_series.append(ef - es)
    
    if len(macd_series) < signal:
        return None
    
    macd_line = macd_series[-1]
    signal_line = calc_ema(macd_series, signal)
    if signal_line is None:
        return None
    histogram = round(macd_line - signal_line, 4)
    
    # Check for crossover
    if len(macd_series) >= 2:
        prev_macd = macd_series[-2]
        prev_signal = calc_ema(macd_series[:-1], signal)
        if prev_signal is not None:
            if prev_macd <= prev_signal and macd_line > signal_line:
                crossover = "bullish"
            elif prev_macd >= prev_signal and macd_line < signal_line:
                crossover = "bearish"
            else:
                crossover = None
        else:
            crossover = None
    else:
        crossover = None
    
    return {
        "macd": round(macd_line, 4),
        "signal": round(signal_line, 4),
        "histogram": histogram,
        "crossover": crossover
    }

def detect_volume_spike(volumes, threshold=2.0):
    """Check if latest volume is >threshold x 20d average."""
    if len(volumes) < 21:
        return None
    avg_20d = sum(volumes[-21:-1]) / 20
    if avg_20d == 0:
        return None
    ratio = volumes[-1] / avg_20d
    return {
        "current": volumes[-1],
        "avg_20d": round(avg_20d, 0),
        "ratio": round(ratio, 2),
        "spike": ratio >= threshold
    }

def detect_support_resistance(candles, current_price):
    """Simple support/resistance based on recent highs/lows."""
    if not candles or len(candles) < 10:
        return None
    highs = [c["high"] for c in candles[-20:]]
    lows = [c["low"] for c in candles[-20:]]
    
    resistance = max(highs)
    support = min(lows)
    
    pct_to_resistance = ((resistance - current_price) / current_price * 100) if current_price else None
    pct_to_support = ((current_price - support) / current_price * 100) if current_price else None
    
    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "pct_to_support": round(pct_to_support, 2) if pct_to_support else None,
        "pct_to_resistance": round(pct_to_resistance, 2) if pct_to_resistance else None,
        "near_support": pct_to_support is not None and pct_to_support < 2.0,
        "near_resistance": pct_to_resistance is not None and pct_to_resistance < 2.0
    }

def write_signal(bot_id, signal_type, ticker, direction, score, message, metadata=None):
    """Write a signal to fleet_signals table."""
    payload = json.dumps({
        "bot_id": bot_id,
        "signal_type": signal_type,
        "ticker": ticker,
        "direction": direction,
        "score": score,
        "message": message,
        "metadata": metadata or {},
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    }).encode()
    
    url = f"{SUPABASE_URL}/rest/v1/fleet_signals"
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    })
    try:
        urllib.request.urlopen(req, timeout=10)
        log(f"Signal written: {signal_type} {ticker} {direction} score={score}")
    except Exception as e:
        log(f"Signal write error: {e}")

def scan_ticker(ticker, is_crypto=False):
    """Run full technical scan on a single ticker."""
    if is_crypto:
        # Skip crypto for now — Finnhub doesn't have crypto candles on free tier
        return None
    
    candles = fetch_candles(ticker)
    if not candles or len(candles) < 26:
        return None
    
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    current = closes[-1]
    
    result = {"ticker": ticker, "price": current, "alerts": []}
    
    # RSI
    rsi = calc_rsi(closes)
    result["rsi"] = rsi
    if rsi is not None:
        if rsi < 30:
            result["alerts"].append({"type": "rsi_oversold", "value": rsi})
        elif rsi > 70:
            result["alerts"].append({"type": "rsi_overbought", "value": rsi})
    
    # MACD
    macd = calc_macd(closes)
    result["macd"] = macd
    if macd and macd.get("crossover"):
        result["alerts"].append({"type": f"macd_{macd['crossover']}_crossover", "value": macd["histogram"]})
    
    # Volume
    vol = detect_volume_spike(volumes)
    result["volume"] = vol
    if vol and vol.get("spike"):
        result["alerts"].append({"type": "volume_spike", "value": vol["ratio"]})
    
    # Support/Resistance
    sr = detect_support_resistance(candles, current)
    result["support_resistance"] = sr
    if sr:
        if sr.get("near_support"):
            result["alerts"].append({"type": "near_support", "value": sr["pct_to_support"]})
        if sr.get("near_resistance"):
            result["alerts"].append({"type": "near_resistance", "value": sr["pct_to_resistance"]})
    
    return result

def run_scan():
    """Main scan loop."""
    positions = get_open_positions()
    
    # Get unique stock tickers (skip crypto for now)
    stock_tickers = set()
    for p in positions:
        ticker = p.get("ticker", "")
        market = p.get("market", "").upper()
        if market not in ("CRYPTO", "CRYPTOCURRENCY") and "-USD" not in ticker:
            stock_tickers.add(ticker.upper())
    
    if not stock_tickers:
        log("No stock positions to scan")
        # Still write empty alerts
        with open(ALERTS_PATH, "w") as f:
            json.dump({"lastScan": datetime.now(timezone.utc).isoformat(), "alerts": [], "scanned": 0}, f, indent=2)
        return
    
    log(f"Scanning {len(stock_tickers)} tickers: {', '.join(stock_tickers)}")
    
    all_alerts = []
    for ticker in stock_tickers:
        result = scan_ticker(ticker)
        if result and result.get("alerts"):
            for alert in result["alerts"]:
                alert_entry = {
                    "ticker": ticker,
                    "type": alert["type"],
                    "value": alert["value"],
                    "price": result.get("price"),
                    "rsi": result.get("rsi"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                all_alerts.append(alert_entry)
                
                # Write significant alerts to fleet_signals
                if alert["type"] in ("rsi_oversold", "rsi_overbought", "macd_bullish_crossover", "macd_bearish_crossover", "volume_spike"):
                    direction = "bearish" if "overbought" in alert["type"] or "bearish" in alert["type"] else "bullish"
                    write_signal(
                        BOT_ID, "opportunity", ticker, direction,
                        alert["value"],
                        f"{alert['type']}: {ticker} @ ${result.get('price', '?')}"
                    )
        
        time.sleep(0.5)  # Rate limit courtesy
    
    # Write alerts.json
    alerts_data = {
        "lastScan": datetime.now(timezone.utc).isoformat(),
        "alerts": all_alerts,
        "scanned": len(stock_tickers),
        "alertCount": len(all_alerts)
    }
    with open(ALERTS_PATH, "w") as f:
        json.dump(alerts_data, f, indent=2)
    
    log(f"Scan complete: {len(stock_tickers)} tickers, {len(all_alerts)} alerts")

if __name__ == "__main__":
    log("Technical scanner starting...")
    
    if "--once" in sys.argv:
        run_scan()
    else:
        # Continuous loop
        while True:
            try:
                run_scan()
            except Exception as e:
                log(f"Scan error: {e}")
            time.sleep(60)
