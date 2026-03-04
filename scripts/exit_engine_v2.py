#!/usr/bin/env python3
"""exit_engine_v2.py — Minimum Viable Exit Engine (5 factors, alert-only).

Checks open positions against 5 exit factors:
  1. Regime Mismatch — position thesis conflicts with current market regime
  2. Relative Weakness — position underperforming its benchmark
  3. Catalyst Expiry — catalyst that justified entry has passed
  4. Concentration Drift — single ticker > 25% of portfolio
  5. Price Sanity Hard Exit — price deviates > 50% from cost basis (data error)

Outputs EXIT SIGNAL alerts. NEVER auto-executes.
"""

import json, os, sys, time, logging
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("ERROR: 'requests' required", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [EXIT] %(message)s")
log = logging.getLogger("exit_engine")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    cred_file = Path.home() / ".supabase_trading_creds"
    if cred_file.exists():
        for line in cred_file.read_text().splitlines():
            if "=" in line:
                k, v = line.strip().split("=", 1)
                if "URL" in k.upper():
                    SUPABASE_URL = v
                elif "KEY" in k.upper() or "ANON" in k.upper():
                    SUPABASE_KEY = v

HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"} if SUPABASE_KEY else {}

# Bot identity
from bot_config import BOT_ID

CRYPTO_BOT_ID = f"{BOT_ID}_crypto" if not BOT_ID.endswith("_crypto") else BOT_ID
EQUITY_BOT_ID = BOT_ID.replace("_crypto", "") if BOT_ID.endswith("_crypto") else BOT_ID
BOT_IDS = [EQUITY_BOT_ID, CRYPTO_BOT_ID]

# --- Regime definitions ---
REGIME_MAP = {
    "RISK_ON": ["momentum", "growth", "crypto", "speculative"],
    "RISK_OFF": ["defensive", "hedge", "gold", "bonds"],
    "NEUTRAL": [],  # no conflicts
}

# Thesis tags for known tickers (expand over time)
THESIS_TAGS = {
    "GDX": "defensive", "GLD": "defensive", "SLV": "defensive", "GDXJ": "defensive",
    "XLE": "defensive", "TLT": "defensive", "SH": "hedge", "SQQQ": "hedge",
    "BTC-USD": "crypto", "ETH-USD": "crypto", "SOL-USD": "crypto",
    "LINK-USD": "crypto", "RENDER-USD": "speculative",
    "COIN": "crypto", "MARA": "crypto", "RIOT": "crypto", "CLSK": "crypto",
    "NVDA": "growth", "AMD": "growth", "AVGO": "growth",
    "ROST": "momentum", "HOOD": "speculative",
}


def get_market_regime():
    """Read regime from market-state.json."""
    state_file = WORKSPACE / "scripts" / "data" / "market-state.json"
    if not state_file.exists():
        state_file = WORKSPACE / "scripts" / "market-state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            regime = data.get("regime", "NEUTRAL").upper()
            return regime
        except Exception:
            pass
    return "NEUTRAL"


def get_positions():
    """Fetch open positions from Supabase."""
    positions = []
    for bid in BOT_IDS:
        url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bid}&status=eq.OPEN&select=*"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.ok:
                positions.extend(r.json())
        except Exception as e:
            log.warning(f"Failed to fetch positions for {bid}: {e}")
    return positions


def get_live_price(ticker):
    """Get live price via Yahoo Finance (with CoinGecko fallback for crypto)."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("last_price")
        if price and price > 0.01:
            return float(price)
    except Exception:
        pass

    # CoinGecko fallback for crypto
    COINGECKO_MAP = {
        "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
        "LINK-USD": "chainlink", "RENDER-USD": "render-token",
        "SUI-USD": "sui", "AVAX-USD": "avalanche-2", "DOT-USD": "polkadot",
        "ADA-USD": "cardano", "DOGE-USD": "dogecoin", "XRP-USD": "ripple",
        "APT-USD": "aptos", "NEAR-USD": "near", "MATIC-USD": "matic-network",
    }
    cg_id = COINGECKO_MAP.get(ticker)
    if cg_id:
        try:
            r = requests.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd",
                timeout=5,
            )
            if r.ok:
                data = r.json()
                return float(data[cg_id]["usd"])
        except Exception:
            pass
    return None


def normalize_ticker(ticker):
    """Normalize ticker to standard format."""
    if not ticker:
        return ticker
    ticker = ticker.upper().strip()
    # Bare crypto → XXX-USD
    crypto_bare = {"BTC", "ETH", "SOL", "LINK", "RENDER", "SUI", "AVAX", "DOT", "ADA", "DOGE", "XRP", "APT", "NEAR", "MATIC"}
    if ticker in crypto_bare:
        return f"{ticker}-USD"
    return ticker


# ===== EXIT FACTORS =====

def check_regime_mismatch(position, regime):
    """Factor 1: Position thesis conflicts with current regime."""
    ticker = normalize_ticker(position.get("ticker", ""))
    thesis = THESIS_TAGS.get(ticker, "unknown")

    if regime == "RISK_ON" and thesis in ["defensive", "hedge", "gold", "bonds"]:
        return {
            "factor": "REGIME_MISMATCH",
            "score": 80,
            "detail": f"{ticker} thesis={thesis} conflicts with RISK_ON regime",
        }
    if regime == "RISK_OFF" and thesis in ["speculative", "growth", "momentum"]:
        return {
            "factor": "REGIME_MISMATCH",
            "score": 70,
            "detail": f"{ticker} thesis={thesis} conflicts with RISK_OFF regime",
        }
    return {"factor": "REGIME_MISMATCH", "score": 0, "detail": "OK"}


def check_relative_weakness(position, live_price):
    """Factor 2: Position underperforming benchmark."""
    ticker = normalize_ticker(position.get("ticker", ""))
    entry_price = float(position.get("price_usd") or position.get("entry_price") or 0)
    if not entry_price or not live_price:
        return {"factor": "RELATIVE_WEAKNESS", "score": 0, "detail": "No price data"}

    change_pct = ((live_price - entry_price) / entry_price) * 100

    # For crypto: BTC is benchmark. If BTC is up 5%+ and this alt is flat/down = weak
    # Simplified: flag if position is down > 3% while market is up
    regime = get_market_regime()
    if regime == "RISK_ON" and change_pct < -3:
        return {
            "factor": "RELATIVE_WEAKNESS",
            "score": 65,
            "detail": f"{ticker} down {change_pct:.1f}% in RISK_ON regime",
        }
    if change_pct < -8:
        return {
            "factor": "RELATIVE_WEAKNESS",
            "score": 75,
            "detail": f"{ticker} down {change_pct:.1f}% — significant underperformance",
        }
    return {"factor": "RELATIVE_WEAKNESS", "score": 0, "detail": f"OK ({change_pct:+.1f}%)"}


def check_catalyst_expiry(position):
    """Factor 3: Catalyst that justified entry has passed."""
    # For now: flag positions held > 5 days with no updated catalyst
    created = position.get("created_at") or position.get("timestamp")
    if not created:
        return {"factor": "CATALYST_EXPIRY", "score": 0, "detail": "No timestamp"}

    try:
        if isinstance(created, str):
            # Handle ISO format
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            created_dt = created
        age_days = (datetime.now(timezone.utc) - created_dt).total_seconds() / 86400
        if age_days > 5:
            return {
                "factor": "CATALYST_EXPIRY",
                "score": 50,
                "detail": f"Position {age_days:.0f} days old — review catalyst validity",
            }
    except Exception:
        pass
    return {"factor": "CATALYST_EXPIRY", "score": 0, "detail": "OK"}


def check_concentration(position, all_positions, prices):
    """Factor 4: Single ticker > 25% of portfolio."""
    ticker = normalize_ticker(position.get("ticker", ""))
    base_ticker = ticker.replace("-USD", "")

    # Calculate total portfolio value
    total_value = 0
    ticker_value = 0
    for p in all_positions:
        t = normalize_ticker(p.get("ticker", ""))
        qty = float(p.get("quantity") or p.get("shares") or 0)
        price = prices.get(t, float(p.get("price_usd") or p.get("entry_price") or 0))
        val = abs(qty * price)
        total_value += val
        if t.replace("-USD", "") == base_ticker:
            ticker_value += val

    if total_value <= 0:
        return {"factor": "CONCENTRATION", "score": 0, "detail": "No portfolio value"}

    concentration_pct = (ticker_value / total_value) * 100
    if concentration_pct > 35:
        return {
            "factor": "CONCENTRATION",
            "score": 90,
            "detail": f"{base_ticker} at {concentration_pct:.1f}% — CRITICAL concentration (>35%)",
        }
    if concentration_pct > 25:
        return {
            "factor": "CONCENTRATION",
            "score": 70,
            "detail": f"{base_ticker} at {concentration_pct:.1f}% — over 25% limit, trim recommended",
        }
    return {"factor": "CONCENTRATION", "score": 0, "detail": f"OK ({concentration_pct:.1f}%)"}


def check_price_sanity(position, live_price):
    """Factor 5: Price deviates > 50% from cost basis (likely data error)."""
    ticker = normalize_ticker(position.get("ticker", ""))
    entry_price = float(position.get("price_usd") or position.get("entry_price") or 0)
    if not entry_price or not live_price:
        return {"factor": "PRICE_SANITY", "score": 0, "detail": "No price data"}

    deviation_pct = abs((live_price - entry_price) / entry_price) * 100
    if deviation_pct > 50:
        return {
            "factor": "PRICE_SANITY",
            "score": 95,
            "detail": f"{ticker} price ${live_price:.2f} vs entry ${entry_price:.2f} — {deviation_pct:.0f}% deviation, likely data error",
        }
    return {"factor": "PRICE_SANITY", "score": 0, "detail": "OK"}


def run_exit_scan():
    """Run all 5 exit factors on all positions."""
    positions = get_positions()
    if not positions:
        log.info("No open positions found.")
        return []

    regime = get_market_regime()
    log.info(f"Regime: {regime} | Positions: {len(positions)}")

    # Get live prices
    prices = {}
    tickers = set(normalize_ticker(p.get("ticker", "")) for p in positions)
    for t in tickers:
        price = get_live_price(t)
        if price:
            prices[t] = price
            log.info(f"  {t}: ${price:.2f}")

    # Aggregate positions by base ticker to avoid duplicate alerts
    from collections import defaultdict
    grouped = defaultdict(list)
    for pos in positions:
        ticker = normalize_ticker(pos.get("ticker", ""))
        base = ticker.replace("-USD", "")
        grouped[base].append(pos)

    alerts = []
    seen_tickers = set()
    for base, group in grouped.items():
        # Use first position as representative, sum quantity
        pos = group[0]
        ticker = normalize_ticker(pos.get("ticker", ""))
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)
        live_price = prices.get(ticker)
        total_qty = sum(float(p.get("quantity") or p.get("shares") or 0) for p in group)

        results = [
            check_regime_mismatch(pos, regime),
            check_relative_weakness(pos, live_price),
            check_catalyst_expiry(pos),
            check_concentration(pos, positions, prices),
            check_price_sanity(pos, live_price),
        ]

        # Aggregate: any factor > 65 = alert
        flagged = [r for r in results if r["score"] >= 65]
        if flagged:
            avg_score = sum(r["score"] for r in flagged) / len(flagged)
            alert = {
                "ticker": ticker,
                "quantity": total_qty,
                "live_price": live_price,
                "flags": flagged,
                "avg_score": avg_score,
            }
            alerts.append(alert)
            log.warning(f"🚨 EXIT SIGNAL: {ticker} — {len(flagged)} factors flagged (avg {avg_score:.0f})")
            for f in flagged:
                log.warning(f"   [{f['factor']}] score={f['score']} — {f['detail']}")
        else:
            log.info(f"  ✅ {ticker} — all factors clear")

    return alerts


def format_discord_alert(alerts):
    """Format alerts for Discord posting."""
    if not alerts:
        return None
    lines = ["🚨 **EXIT ENGINE SCAN**\n"]
    for a in sorted(alerts, key=lambda x: -x["avg_score"]):
        lines.append(f"**{a['ticker']}** — {len(a['flags'])} flags, avg score {a['avg_score']:.0f}")
        for f in a["flags"]:
            lines.append(f"  • [{f['factor']}] {f['detail']}")
    lines.append("\n*Alert only — no auto-execution.*")
    return "\n".join(lines)


if __name__ == "__main__":
    alerts = run_exit_scan()
    msg = format_discord_alert(alerts)
    if msg:
        print(msg)
        # Write to file for heartbeat pickup
        alert_file = WORKSPACE / "scripts" / "data" / "exit_alerts.json"
        alert_file.parent.mkdir(exist_ok=True)
        alert_file.write_text(json.dumps(alerts, default=str, indent=2))
    else:
        print("✅ All positions clear — no exit signals.")
