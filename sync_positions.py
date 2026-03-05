#!/usr/bin/env python3
"""Sync open positions from Supabase to trading-state.json with live prices and fleet signals."""
import json, os, sys, urllib.request, urllib.error, time
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc")

# Load .env from workspace
def load_dotenv():
    workspace = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
    envfile = os.path.join(workspace, ".env")
    if os.path.exists(envfile):
        with open(envfile) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_dotenv()

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Crypto ticker -> CoinGecko ID mapping
CRYPTO_MAP = {
    "BTC-USD": "bitcoin", "BTC": "bitcoin",
    "ETH-USD": "ethereum", "ETH": "ethereum",
    "SOL-USD": "solana", "SOL": "solana",
    "DOGE-USD": "dogecoin", "DOGE": "dogecoin",
    "ADA-USD": "cardano", "ADA": "cardano",
    "BNB-USD": "binancecoin", "BNB": "binancecoin",
    "DOT-USD": "polkadot", "DOT": "polkadot",
    "RNDR-USD": "render-token", "RNDR": "render-token",
    "PENDLE-USD": "pendle", "PENDLE": "pendle",
    "UNI-USD": "uniswap", "UNI": "uniswap",
    "INJ-USD": "injective-protocol", "INJ": "injective-protocol",
    "SUI-USD": "sui", "SUI": "sui",
    "ARB-USD": "arbitrum", "ARB": "arbitrum",
    "AVAX-USD": "avalanche-2", "AVAX": "avalanche-2",
    "LINK-USD": "chainlink", "LINK": "chainlink",
    "XRP-USD": "ripple", "XRP": "ripple",
    "AAVE-USD": "aave", "AAVE": "aave",
    "NEAR-USD": "near", "NEAR": "near",
    "MATIC-USD": "matic-network", "MATIC": "matic-network",
    "ATOM-USD": "cosmos", "ATOM": "cosmos",
    "FTM-USD": "fantom", "FTM": "fantom",
    "OP-USD": "optimism", "OP": "optimism",
}

BOT_IDS = sys.argv[1:] if len(sys.argv) > 1 else []

def fetch_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  fetch error {url[:80]}: {e}", file=sys.stderr)
        return None

def fetch_positions(bot_ids):
    positions = []
    for bid in bot_ids:
        url = f"{SUPABASE_URL}/rest/v1/trades?select=*&status=eq.OPEN&bot_id=eq.{bid}&order=timestamp.desc"
        data = fetch_json(url, {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        if data:
            for t in data:
                positions.append({
                    "trade_id": t.get("trade_id"),
                    "bot_id": t.get("bot_id"),
                    "ticker": t.get("ticker"),
                    "side": t.get("action", "BUY"),
                    "quantity": t.get("quantity"),
                    "entry_price": t.get("price_usd"),
                    "market": t.get("market", "UNKNOWN"),
                    "status": "OPEN"
                })
        else:
            print(f"Error fetching positions for {bid}", file=sys.stderr)
    return positions

def is_crypto(ticker, market):
    return ticker in CRYPTO_MAP or market in ("CRYPTO",)

def fetch_crypto_prices(tickers):
    """Batch fetch crypto prices from CoinGecko."""
    ids = set()
    ticker_to_id = {}
    for t in tickers:
        cg_id = CRYPTO_MAP.get(t)
        if cg_id:
            ids.add(cg_id)
            ticker_to_id[t] = cg_id
    if not ids:
        return {}
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies=usd"
    data = fetch_json(url)
    if not data:
        return {}
    result = {}
    for ticker, cg_id in ticker_to_id.items():
        if cg_id in data and "usd" in data[cg_id]:
            result[ticker] = data[cg_id]["usd"]
    return result

def fetch_stock_price(ticker):
    """Fetch a single stock price from Finnhub."""
    if not FINNHUB_KEY:
        return None
    # Strip -USD suffix for stock lookups
    symbol = ticker.replace("-USD", "")
    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
    data = fetch_json(url)
    if data and data.get("c") and data["c"] > 0:
        return data["c"]
    return None

def enrich_with_prices(positions):
    """Add current_price, unrealized_pl, unrealized_pl_pct to each position."""
    # Separate crypto and stock tickers
    crypto_tickers = set()
    stock_tickers = set()
    for p in positions:
        ticker = p["ticker"]
        if is_crypto(ticker, p.get("market", "")):
            crypto_tickers.add(ticker)
        else:
            stock_tickers.add(ticker)

    # Batch fetch crypto
    crypto_prices = fetch_crypto_prices(crypto_tickers) if crypto_tickers else {}

    # Fetch stocks one by one (Finnhub rate limit: ~60/min)
    stock_prices = {}
    for ticker in stock_tickers:
        price = fetch_stock_price(ticker)
        if price is not None:
            stock_prices[ticker] = price
        time.sleep(0.2)  # Rate limit protection

    # Enrich positions
    for p in positions:
        ticker = p["ticker"]
        if ticker in crypto_prices:
            p["current_price"] = crypto_prices[ticker]
        elif ticker in stock_prices:
            p["current_price"] = stock_prices[ticker]
        else:
            # Try crypto mapping for tickers like "ETH" that might be crypto
            cg_id = CRYPTO_MAP.get(ticker)
            if cg_id and ticker in crypto_prices:
                p["current_price"] = crypto_prices[ticker]
            else:
                p["current_price"] = None
                p["price_status"] = "stale"

        # Calculate unrealized P&L
        entry = p.get("entry_price")
        current = p.get("current_price")
        qty = p.get("quantity", 0)
        side = p.get("side", "BUY").upper()

        if entry and current and qty:
            if side in ("BUY", "LONG"):
                p["unrealized_pl"] = round((current - entry) * qty, 2)
            elif side in ("SELL", "SHORT"):
                p["unrealized_pl"] = round((entry - current) * qty, 2)
            else:
                p["unrealized_pl"] = round((current - entry) * qty, 2)

            if entry != 0:
                if side in ("SELL", "SHORT"):
                    p["unrealized_pl_pct"] = round(((entry - current) / entry) * 100, 2)
                else:
                    p["unrealized_pl_pct"] = round(((current - entry) / entry) * 100, 2)
            else:
                p["unrealized_pl_pct"] = None
        else:
            p["unrealized_pl"] = None
            p["unrealized_pl_pct"] = None

    return positions

def fetch_fleet_signals():
    """Fetch fleet_signals from last 30 minutes."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    url = f"{SUPABASE_URL}/rest/v1/fleet_signals?select=*&created_at=gte.{since}&order=created_at.desc&limit=50"
    data = fetch_json(url, {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
    return data if data else []

# Main
positions = fetch_positions(BOT_IDS)
print(f"Fetched {len(positions)} positions, enriching with live prices...")
positions = enrich_with_prices(positions)

# Fetch signals (gracefully handle if table doesn't exist yet)
signals = []
try:
    signals = fetch_fleet_signals()
except Exception as e:
    print(f"Could not fetch fleet_signals: {e}", file=sys.stderr)

# Summary
total_pl = sum(p.get("unrealized_pl", 0) or 0 for p in positions)
priced = sum(1 for p in positions if p.get("current_price") is not None)
stale = sum(1 for p in positions if p.get("price_status") == "stale")

state = {
    "lastUpdated": datetime.now(timezone.utc).isoformat(),
    "positions": positions,
    "signals": signals,
    "pendingOrders": [],
    "cashBalance": None,
    "summary": {
        "total_positions": len(positions),
        "priced": priced,
        "stale": stale,
        "total_unrealized_pl": round(total_pl, 2)
    },
    "notes": f"Synced {len(positions)} positions ({priced} priced, {stale} stale). Total unrealized P&L: ${total_pl:+,.2f}"
}

workspace = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
outpath = os.path.join(workspace, "trading-state.json")
with open(outpath, "w") as f:
    json.dump(state, f, indent=2)
print(f"✅ {state['notes']}")
print(f"   Signals: {len(signals)} in last 30min")
print(f"   Written to {outpath}")
