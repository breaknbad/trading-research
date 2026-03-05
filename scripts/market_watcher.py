#!/usr/bin/env python3
"""market_watcher.py — Unified market monitoring service (30s loop)."""

import json, os, sys, time, math, signal, logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Bot identity auto-detection
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bot_config import BOT_ID, BOT_IDS

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPTS   = WORKSPACE / "scripts"
DATA_DIR  = SCRIPTS / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

ROLLING_FILE   = DATA_DIR / "rolling_closes.json"
STATE_FILE     = WORKSPACE / "market-state.json"
ALERTS_FILE    = WORKSPACE / "alerts.json"
DRAWDOWN_FILE  = DATA_DIR / "drawdown_history.json"

# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------
from dotenv import load_dotenv
load_dotenv(WORKSPACE / ".env")
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
COINGECKO_KEY = os.getenv("COINGECKO_API_KEY", "")

HEADERS_SB = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [WATCHER] %(message)s")
log = logging.getLogger("watcher")

CRYPTO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "AVAX": "avalanche-2", "LINK": "chainlink", "DOT": "polkadot",
    "ADA": "cardano", "DOGE": "dogecoin", "SUI": "sui",
    "INJ": "injective-protocol", "RNDR": "render-token", "PENDLE": "pendle",
}
LEVERAGED_ETFS = {"TQQQ","SQQQ","SPXU","SPXL","UPRO","SDOW","UDOW","LABU","LABD",
                  "SOXL","SOXS","FNGU","FNGD","TNA","TZA","UVXY","SVXY","QLD","QID"}

RUNNING = True
def _stop(*_): global RUNNING; RUNNING = False
signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _retry(fn, retries=3):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)

def _atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(path)

def _now_et():
    from datetime import timezone as tz
    ET = timezone(timedelta(hours=-5))
    return datetime.now(ET)

def _is_market_hours():
    n = _now_et()
    if n.weekday() >= 5:
        return False
    t = n.hour * 60 + n.minute
    return 570 <= t <= 960  # 9:30-16:00

def _is_after_350():
    n = _now_et()
    return n.weekday() < 5 and (n.hour * 60 + n.minute) >= 950

# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------
def fetch_open_trades():
    try:
        r = _retry(lambda: requests.get(
            f"{SUPABASE_URL}/rest/v1/trades?status=eq.OPEN&select=*",
            headers=HEADERS_SB, timeout=10))
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"Failed fetching open trades: {e}")
        return []

def fetch_crypto_prices(ids_map):
    """ids_map: {TICKER: coingecko_id}"""
    if not ids_map:
        return {}
    ids_str = ",".join(ids_map.values())
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ids_str, "vs_currencies": "usd",
              "include_24hr_change": "true", "include_24hr_vol": "true"}
    if COINGECKO_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_KEY
    r = _retry(lambda: requests.get(url, params=params, timeout=15))
    r.raise_for_status()
    data = r.json()
    result = {}
    for ticker, cg_id in ids_map.items():
        if cg_id in data:
            d = data[cg_id]
            result[ticker] = {
                "price": d.get("usd", 0),
                "change_24h_pct": d.get("usd_24h_change", 0),
                "volume_24h": d.get("usd_24h_vol", 0),
                "asset_type": "crypto"
            }
    return result

def fetch_stock_price(ticker):
    """Fetch stock quote via Yahoo Finance v8 API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": "1d"}
    headers = {"User-Agent": "Mozilla/5.0"}
    r = _retry(lambda: requests.get(url, params=params, headers=headers, timeout=10))
    r.raise_for_status()
    data = r.json()
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev = meta.get("chartPreviousClose", meta.get("previousClose", price))
    change_pct = ((price - prev) / prev * 100) if prev else 0
    vol = 0
    indicators = data["chart"]["result"][0].get("indicators", {})
    if indicators.get("quote") and indicators["quote"][0].get("volume"):
        vols = [v for v in indicators["quote"][0]["volume"] if v is not None]
        vol = vols[-1] if vols else 0
    return {
        "price": price,
        "change_24h_pct": change_pct,
        "volume_24h": vol,
        "asset_type": "stock"
    }

# ---------------------------------------------------------------------------
# Technicals — pure math
# ---------------------------------------------------------------------------
def load_rolling():
    if ROLLING_FILE.exists():
        return json.loads(ROLLING_FILE.read_text())
    return {}

def save_rolling(data):
    _atomic_write(ROLLING_FILE, data)

def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 4)

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)

def calc_macd(prices):
    ema12 = calc_ema(prices, 12)
    ema26 = calc_ema(prices, 26)
    if ema12 is None or ema26 is None:
        return None, None, None
    macd_line = round(ema12 - ema26, 4)
    # signal needs 9 periods of MACD — approximate with single value
    signal = None
    histogram = None
    return macd_line, signal, histogram

def compute_technicals(ticker, price, rolling):
    closes = rolling.get(ticker, [])
    closes.append(price)
    closes = closes[-30:]  # keep 30 for 20-day avg + technicals
    rolling[ticker] = closes

    rsi = calc_rsi(closes)
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    macd_line, macd_signal, macd_hist = calc_macd(closes)

    ema_cross = None
    if ema9 is not None and ema21 is not None and len(closes) >= 2:
        prev_closes = closes[:-1]
        prev_ema9 = calc_ema(prev_closes, 9)
        prev_ema21 = calc_ema(prev_closes, 21)
        if prev_ema9 is not None and prev_ema21 is not None:
            if prev_ema9 < prev_ema21 and ema9 > ema21:
                ema_cross = "bullish"
            elif prev_ema9 > prev_ema21 and ema9 < ema21:
                ema_cross = "bearish"

    return {
        "rsi": rsi, "ema9": ema9, "ema21": ema21,
        "macd": macd_line, "macd_signal": macd_signal,
        "macd_histogram": macd_hist, "ema_cross": ema_cross
    }

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
def detect_alerts(ticker, info, technicals, trades):
    alerts = []
    asset = info.get("asset_type", "stock")
    change = abs(info.get("change_24h_pct", 0))

    # Big moves
    if asset == "crypto":
        if change >= 8:
            alerts.append({"type": "BIG_MOVE", "ticker": ticker, "value": change,
                           "message": f"{ticker} moved {change:.1f}% (crypto CRITICAL)", "source": "watcher", "severity": "CRITICAL"})
        elif change >= 5:
            alerts.append({"type": "BIG_MOVE", "ticker": ticker, "value": change,
                           "message": f"{ticker} moved {change:.1f}% (crypto HIGH)", "source": "watcher", "severity": "HIGH"})
    else:
        if change >= 5:
            alerts.append({"type": "BIG_MOVE", "ticker": ticker, "value": change,
                           "message": f"{ticker} moved {change:.1f}% (stock CRITICAL)", "source": "watcher", "severity": "CRITICAL"})
        elif change >= 3:
            alerts.append({"type": "BIG_MOVE", "ticker": ticker, "value": change,
                           "message": f"{ticker} moved {change:.1f}% (stock HIGH)", "source": "watcher", "severity": "HIGH"})

    # RSI
    rsi = technicals.get("rsi")
    if rsi is not None:
        if rsi > 70:
            alerts.append({"type": "RSI_OVERBOUGHT", "ticker": ticker, "value": rsi,
                           "message": f"{ticker} RSI={rsi} overbought", "source": "watcher", "severity": "HIGH"})
        elif rsi < 30:
            alerts.append({"type": "RSI_OVERSOLD", "ticker": ticker, "value": rsi,
                           "message": f"{ticker} RSI={rsi} oversold", "source": "watcher", "severity": "HIGH"})

    # EMA crossover
    if technicals.get("ema_cross"):
        alerts.append({"type": "EMA_CROSS", "ticker": ticker, "value": technicals["ema_cross"],
                       "message": f"{ticker} EMA 9/21 {technicals['ema_cross']} crossover", "source": "watcher", "severity": "HIGH"})

    # Leveraged ETF after 3:50
    if ticker.upper() in LEVERAGED_ETFS and _is_after_350():
        alerts.append({"type": "LEVERAGED_ETF_CLOSE", "ticker": ticker, "value": None,
                       "message": f"{ticker} leveraged/inverse ETF still held after 3:50 PM ET", "source": "watcher", "severity": "CRITICAL"})

    # Stop enforcement
    price = info.get("price", 0)
    for t in trades:
        if t.get("ticker", "").upper() == ticker.upper() and t.get("stop_price"):
            stop = float(t["stop_price"])
            side = t.get("side", "long")
            breached = (side == "long" and price <= stop) or (side == "short" and price >= stop)
            if breached:
                alerts.append({"type": "STOP_BREACH", "ticker": ticker, "value": price,
                               "message": f"{ticker} breached stop @ {stop} (price={price})", "source": "watcher", "severity": "CRITICAL"})

    return alerts

def detect_correlation(market_state):
    """3+ positions moving >3% same direction."""
    up, down = [], []
    for ticker, info in market_state.items():
        ch = info.get("change_24h_pct", 0)
        if ch > 3:
            up.append(ticker)
        elif ch < -3:
            down.append(ticker)
    alerts = []
    if len(up) >= 3:
        alerts.append({"type": "CORRELATION", "ticker": ",".join(up), "value": len(up),
                       "message": f"Correlation alert: {len(up)} positions up >3%: {', '.join(up)}", "source": "watcher", "severity": "HIGH"})
    if len(down) >= 3:
        alerts.append({"type": "CORRELATION", "ticker": ",".join(down), "value": len(down),
                       "message": f"Correlation alert: {len(down)} positions down >3%: {', '.join(down)}", "source": "watcher", "severity": "CRITICAL"})
    return alerts

# ---------------------------------------------------------------------------
# Drawdown velocity
# ---------------------------------------------------------------------------
def track_drawdown(trades, market_state):
    history = {}
    if DRAWDOWN_FILE.exists():
        try:
            history = json.loads(DRAWDOWN_FILE.read_text())
        except:
            pass

    now_ts = time.time()
    total_pnl = 0
    for t in trades:
        tk = t.get("ticker", "").upper()
        if tk in market_state:
            entry = float(t.get("entry_price", 0))
            price = market_state[tk].get("price", 0)
            qty = float(t.get("quantity", 0))
            side = t.get("side", "long")
            if side == "long":
                total_pnl += (price - entry) * qty
            else:
                total_pnl += (entry - price) * qty

    snapshots = history.get("snapshots", [])
    snapshots.append({"ts": now_ts, "pnl": total_pnl})
    cutoff = now_ts - 1800  # 30 min
    snapshots = [s for s in snapshots if s["ts"] >= cutoff]
    history["snapshots"] = snapshots

    alerts = []
    if len(snapshots) >= 2:
        start_pnl = snapshots[0]["pnl"]
        delta = total_pnl - start_pnl
        if delta < -500:  # losing >$500 in 30min
            alerts.append({"type": "DRAWDOWN_VELOCITY", "ticker": "PORTFOLIO", "value": delta,
                           "message": f"Portfolio losing ${abs(delta):.0f} in last 30min", "source": "watcher", "severity": "CRITICAL"})

    _atomic_write(DRAWDOWN_FILE, history)
    return alerts

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run_cycle():
    trades = fetch_open_trades()
    rolling = load_rolling()

    # Build ticker set
    crypto_map = dict(CRYPTO_IDS)  # always watch BTC/ETH/SOL
    stock_tickers = set()
    for t in trades:
        tk = t.get("ticker", "").upper()
        # Strip -USD suffix for crypto matching
        base = tk.replace("-USD", "")
        if base in CRYPTO_IDS:
            crypto_map[base] = CRYPTO_IDS[base]
        elif tk.endswith("-USD"):
            # Unknown crypto pair — skip (not a stock ticker)
            log.info(f"Skipping unknown crypto pair: {tk}")
        elif tk:
            stock_tickers.add(tk)

    market_state = {}
    all_alerts = []

    # Crypto
    try:
        crypto_data = fetch_crypto_prices(crypto_map)
        for ticker, info in crypto_data.items():
            techs = compute_technicals(ticker, info["price"], rolling)
            info["technicals"] = techs
            market_state[ticker] = info
            all_alerts.extend(detect_alerts(ticker, info, techs, trades))
    except Exception as e:
        log.error(f"Crypto fetch failed: {e}")

    # Stocks
    mh = _is_market_hours()
    for ticker in stock_tickers:
        try:
            info = fetch_stock_price(ticker)
            if mh:
                techs = compute_technicals(ticker, info["price"], rolling)
                info["technicals"] = techs
            else:
                info["technicals"] = {}
            market_state[ticker] = info
            all_alerts.extend(detect_alerts(ticker, info, info.get("technicals", {}), trades))
            time.sleep(0.3)  # stagger
        except Exception as e:
            log.error(f"Stock fetch failed for {ticker}: {e}")

    # Correlation
    all_alerts.extend(detect_correlation(market_state))

    # Drawdown velocity
    all_alerts.extend(track_drawdown(trades, market_state))

    # Heat cap (total position change > 6%)
    total_exposure = 0
    total_change = 0
    for t in trades:
        tk = t.get("ticker", "").upper()
        if tk in market_state:
            qty = float(t.get("quantity", 0))
            price = market_state[tk]["price"]
            change_pct = market_state[tk].get("change_24h_pct", 0)
            exposure = qty * price
            total_exposure += exposure
            total_change += exposure * change_pct / 100
    if total_exposure > 0:
        heat = abs(total_change / total_exposure * 100)
        if heat > 6:
            all_alerts.append({"type": "HEAT_CAP", "ticker": "PORTFOLIO", "value": round(heat, 2),
                               "message": f"Portfolio heat cap {heat:.1f}% exceeds 6%", "source": "watcher", "severity": "CRITICAL"})

    save_rolling(rolling)

    now = datetime.now(timezone.utc).isoformat()
    state_out = {"updated": now, "stale_after": 90, "tickers": market_state}
    alerts_out = {"updated": now, "alerts": all_alerts}

    _atomic_write(STATE_FILE, state_out)
    _atomic_write(ALERTS_FILE, alerts_out)

    # Push to Supabase so all bots can read market state
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            row = {
                "id": "latest",
                "updated_at": now,
                "state_json": json.dumps(state_out),
                "alerts_json": json.dumps(alerts_out),
            }
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/market_state",
                headers={**HEADERS_SB, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"},
                json=row, timeout=5
            )
            if resp.status_code in (200, 201):
                log.info("Pushed market state to Supabase")
            else:
                log.warning(f"Supabase push failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Supabase push error: {e}")

    # Push alerts as fleet signals
    if SUPABASE_URL and SUPABASE_KEY and all_alerts:
        try:
            signals = []
            for alert in all_alerts:
                signals.append({
                    "bot_id": BOT_ID.upper(),
                    "signal_type": alert.get("type", "UNKNOWN"),
                    "ticker": alert.get("ticker", ""),
                    "severity": alert.get("severity", "INFO"),
                    "message": alert.get("message", ""),
                    "source": "market_watcher",
                    "created_at": now,
                })
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/fleet_signals",
                headers={**HEADERS_SB, "Content-Type": "application/json"},
                json=signals, timeout=5
            )
            if resp.status_code in (200, 201):
                log.info(f"Pushed {len(signals)} fleet signals to Supabase")
            else:
                log.warning(f"Fleet signals push failed: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Fleet signals push error: {e}")

    log.info(f"Cycle done — {len(market_state)} tickers, {len(all_alerts)} alerts")

def main():
    log.info("Market watcher starting (30s loop)")
    while RUNNING:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}")
        for _ in range(30):
            if not RUNNING:
                break
            time.sleep(1)
    log.info("Market watcher stopped")

if __name__ == "__main__":
    main()
