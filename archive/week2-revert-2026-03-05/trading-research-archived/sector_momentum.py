#!/usr/bin/env python3
"""Sector momentum — ranks GICS sectors by 5-day relative strength."""

import sys, os, json, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FINNHUB_KEY, CACHE_DIR

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
}

# Top 100 stocks → sector mapping
TICKER_SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology", "GOOGL": "Communication Services",
    "GOOG": "Communication Services", "AMZN": "Consumer Discretionary", "META": "Communication Services",
    "TSLA": "Consumer Discretionary", "BRK.B": "Financials", "JPM": "Financials",
    "V": "Financials", "UNH": "Health Care", "MA": "Financials", "JNJ": "Health Care",
    "XOM": "Energy", "PG": "Consumer Staples", "HD": "Consumer Discretionary", "CVX": "Energy",
    "AVGO": "Technology", "LLY": "Health Care", "MRK": "Health Care", "ABBV": "Health Care",
    "KO": "Consumer Staples", "PEP": "Consumer Staples", "COST": "Consumer Staples",
    "WMT": "Consumer Staples", "TMO": "Health Care", "MCD": "Consumer Discretionary",
    "CSCO": "Technology", "ACN": "Technology", "ABT": "Health Care", "DHR": "Health Care",
    "NEE": "Utilities", "LIN": "Materials", "ADBE": "Technology", "TXN": "Technology",
    "AMD": "Technology", "CRM": "Technology", "NFLX": "Communication Services",
    "INTC": "Technology", "WFC": "Financials", "BAC": "Financials", "CMCSA": "Communication Services",
    "ORCL": "Technology", "PM": "Consumer Staples", "NKE": "Consumer Discretionary",
    "COP": "Energy", "RTX": "Industrials", "UPS": "Industrials", "HON": "Industrials",
    "LOW": "Consumer Discretionary", "QCOM": "Technology", "IBM": "Technology",
    "CAT": "Industrials", "GE": "Industrials", "BA": "Industrials", "DE": "Industrials",
    "SPGI": "Financials", "AMAT": "Technology", "GS": "Financials", "MS": "Financials",
    "BLK": "Financials", "PLTR": "Technology", "SQQQ": "Technology",
    "AXP": "Financials", "MDLZ": "Consumer Staples", "SYK": "Health Care",
    "ISRG": "Health Care", "GILD": "Health Care", "BKNG": "Consumer Discretionary",
    "ADI": "Technology", "VRTX": "Health Care", "REGN": "Health Care",
    "LRCX": "Technology", "KLAC": "Technology", "PANW": "Technology", "SNPS": "Technology",
    "CDNS": "Technology", "MRVL": "Technology", "FTNT": "Technology",
    "SLB": "Energy", "EOG": "Energy", "PSX": "Energy", "MPC": "Energy", "VLO": "Energy",
    "SO": "Utilities", "DUK": "Utilities", "D": "Utilities", "AEP": "Utilities",
    "AMT": "Real Estate", "PLD": "Real Estate", "CCI": "Real Estate",
    "DIS": "Communication Services", "T": "Communication Services", "VZ": "Communication Services",
    "TMUS": "Communication Services",
    "MMM": "Industrials", "LMT": "Industrials", "GD": "Industrials", "NOC": "Industrials",
    "FDX": "Industrials",
    "APD": "Materials", "ECL": "Materials", "SHW": "Materials", "NEM": "Materials", "FCX": "Materials",
}

MOMENTUM_CACHE_FILE = os.path.join(CACHE_DIR, "sector_momentum_cache.json")
CACHE_TTL = 3600  # 1 hour


def _load_cache():
    if os.path.exists(MOMENTUM_CACHE_FILE):
        with open(MOMENTUM_CACHE_FILE) as f:
            data = json.load(f)
        if time.time() - data.get("timestamp", 0) < CACHE_TTL:
            return data.get("rankings")
    return None


def _save_cache(rankings):
    with open(MOMENTUM_CACHE_FILE, "w") as f:
        json.dump({"timestamp": time.time(), "rankings": rankings}, f, indent=2)


def _get_5d_momentum(ticker: str) -> float:
    """Get 5-day momentum using Finnhub candles."""
    now = int(time.time())
    five_days_ago = now - (5 * 86400 + 172800)  # extra 2 days for weekends
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={"symbol": ticker, "resolution": "D", "from": five_days_ago, "to": now, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        if data.get("s") == "ok" and len(data.get("c", [])) >= 2:
            closes = data["c"]
            return ((closes[-1] - closes[0]) / closes[0]) * 100
    except Exception as e:
        print(f"  [warn] Candles failed for {ticker}: {e}")
    return 0.0


def get_sector_rankings() -> list:
    """Rank sectors by 5-day momentum.

    Returns sorted list of {sector, etf, momentum_5d, rank}
    """
    cached = _load_cache()
    if cached:
        return cached

    rankings = []
    for etf, sector in SECTOR_ETFS.items():
        mom = _get_5d_momentum(etf)
        rankings.append({"sector": sector, "etf": etf, "momentum_5d": round(mom, 2)})
        time.sleep(0.3)

    rankings.sort(key=lambda x: x["momentum_5d"], reverse=True)
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    _save_cache(rankings)
    return rankings


def get_sector_for_ticker(ticker: str) -> str:
    """Return sector for a ticker (hardcoded mapping)."""
    return TICKER_SECTOR_MAP.get(ticker.upper(), "Unknown")


def is_sector_aligned(ticker: str) -> dict:
    """Check if a ticker's sector is in the top half of momentum rankings.

    Returns {aligned, sector_rank, momentum}
    """
    sector = get_sector_for_ticker(ticker)
    if sector == "Unknown":
        return {"aligned": False, "sector_rank": -1, "momentum": 0.0}

    rankings = get_sector_rankings()
    for r in rankings:
        if r["sector"] == sector:
            return {
                "aligned": r["rank"] <= len(rankings) // 2,
                "sector_rank": r["rank"],
                "momentum": r["momentum_5d"],
            }

    return {"aligned": False, "sector_rank": -1, "momentum": 0.0}


if __name__ == "__main__":
    for r in get_sector_rankings():
        print(f"  #{r['rank']} {r['etf']:5s} {r['sector']:25s} {r['momentum_5d']:+.2f}%")
    print()
    print("NVDA aligned?", is_sector_aligned("NVDA"))
    print("XOM aligned?", is_sector_aligned("XOM"))
