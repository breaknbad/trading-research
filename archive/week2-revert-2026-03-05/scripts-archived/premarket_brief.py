#!/usr/bin/env python3
"""premarket_brief.py — Pre-market research brief (run ~8:55 AM ET)."""

import json, os, sys, time, logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
from dotenv import load_dotenv
load_dotenv(WORKSPACE / ".env")
import requests

COINGECKO_KEY = os.getenv("COINGECKO_API_KEY", "")
STATE_FILE = WORKSPACE / "market-state.json"
CATALYSTS_FILE = WORKSPACE / "upcoming_catalysts.json"
BRIEF_FILE = WORKSPACE / "premarket-brief.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [PREMARKET] %(message)s")
log = logging.getLogger("premarket")

def _retry(fn, retries=3):
    for i in range(retries):
        try:
            return fn()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)

def fetch_yahoo_quote(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"interval": "1d", "range": "1d"}
    r = _retry(lambda: requests.get(url, params=params,
               headers={"User-Agent": "Mozilla/5.0"}, timeout=10))
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice", 0)
    prev = meta.get("chartPreviousClose", meta.get("previousClose", price))
    change = ((price - prev) / prev * 100) if prev else 0
    return {"price": round(price, 2), "change_pct": round(change, 2)}

def fetch_futures():
    futures = {}
    tickers = {"ES=F": "S&P 500", "NQ=F": "Nasdaq", "YM=F": "Dow", "^VIX": "VIX"}
    for sym, name in tickers.items():
        try:
            futures[name] = fetch_yahoo_quote(sym)
            time.sleep(0.3)
        except Exception as e:
            log.error(f"Failed {name}: {e}")
            futures[name] = {"price": None, "change_pct": None}
    return futures

def fetch_crypto_overnight():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd",
              "include_24hr_change": "true"}
    if COINGECKO_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_KEY
    try:
        r = _retry(lambda: requests.get(url, params=params, timeout=15))
        r.raise_for_status()
        data = r.json()
        return {
            "BTC": {"price": data["bitcoin"]["usd"], "change_pct": round(data["bitcoin"].get("usd_24h_change", 0), 2)},
            "ETH": {"price": data["ethereum"]["usd"], "change_pct": round(data["ethereum"].get("usd_24h_change", 0), 2)},
            "SOL": {"price": data["solana"]["usd"], "change_pct": round(data["solana"].get("usd_24h_change", 0), 2)},
        }
    except Exception as e:
        log.error(f"Crypto fetch failed: {e}")
        return {}

def load_catalysts():
    if CATALYSTS_FILE.exists():
        try:
            return json.loads(CATALYSTS_FILE.read_text())
        except:
            pass
    return []

def load_overnight_alerts():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            alerts_file = WORKSPACE / "alerts.json"
            if alerts_file.exists():
                return json.loads(alerts_file.read_text()).get("alerts", [])
        except:
            pass
    return []

def format_brief(futures, crypto, catalysts, alerts):
    lines = []
    lines.append("📊 **PRE-MARKET BRIEF**")
    now_et = datetime.now(timezone(timedelta(hours=-5)))
    lines.append(f"_{now_et.strftime('%A, %B %d %Y — %I:%M %p ET')}_\n")

    lines.append("**🔮 Futures**")
    for name, d in futures.items():
        if d["price"] is not None:
            arrow = "🟢" if d["change_pct"] >= 0 else "🔴"
            lines.append(f"  {arrow} {name}: {d['price']:,.2f} ({d['change_pct']:+.2f}%)")
        else:
            lines.append(f"  ⚪ {name}: unavailable")

    lines.append("\n**₿ Crypto Overnight**")
    for tk, d in crypto.items():
        arrow = "🟢" if d["change_pct"] >= 0 else "🔴"
        lines.append(f"  {arrow} {tk}: ${d['price']:,.2f} ({d['change_pct']:+.2f}%)")

    if catalysts:
        lines.append("\n**📅 Catalysts Today**")
        for c in catalysts[:10]:
            if isinstance(c, dict):
                lines.append(f"  • {c.get('event', c.get('description', str(c)))}")
            else:
                lines.append(f"  • {c}")

    if alerts:
        lines.append("\n**⚠️ Active Alerts**")
        for a in alerts[:10]:
            sev = a.get("severity", "HIGH")
            icon = "🚨" if sev == "CRITICAL" else "⚠️"
            lines.append(f"  {icon} {a.get('message', a.get('type', ''))}")

    if not catalysts and not alerts:
        lines.append("\n_No catalysts or alerts overnight._")

    return "\n".join(lines)

def main():
    log.info("Generating pre-market brief...")
    futures = fetch_futures()
    crypto = fetch_crypto_overnight()
    catalysts = load_catalysts()
    alerts = load_overnight_alerts()

    text = format_brief(futures, crypto, catalysts, alerts)
    brief_data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "futures": futures,
        "crypto": crypto,
        "catalysts": catalysts,
        "alerts": alerts,
        "formatted": text
    }

    tmp = BRIEF_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(brief_data, indent=2, default=str))
    tmp.rename(BRIEF_FILE)

    print(text)
    log.info("Brief written to premarket-brief.json")

if __name__ == "__main__":
    main()
