#!/usr/bin/env python3
"""
Sector Weakness Detector — finds sectors bleeding and flags weakest names for shorts.

Scans all 11 GICS sector ETFs for 3-day declining momentum.
When a sector is weak, identifies the worst-performing individual stocks
within that sector as short candidates.

Usage:
  python3 sector_weakness.py              # Full scan
  python3 sector_weakness.py --sector XLK  # Single sector
  python3 sector_weakness.py --write       # Write signals to Supabase

Runs daily at 8 PM ET as part of overnight prep.
"""

import argparse
import json
import sys
import requests
from datetime import datetime, timezone

# Sector ETFs → top holdings (simplified universe)
SECTORS = {
    "XLK": {"name": "Technology", "holdings": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "AMD", "ADBE", "ORCL", "CSCO", "ACN", "INTC", "QCOM", "TXN", "NOW", "INTU", "AMAT", "MU", "LRCX", "KLAC", "MRVL", "SNPS", "CDNS", "FTNT", "PANW", "CRWD"]},
    "XLF": {"name": "Financials", "holdings": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "BLK", "C", "AXP", "SCHW", "CB", "MMC", "PGR", "CME", "ICE", "AON", "MET"]},
    "XLV": {"name": "Healthcare", "holdings": ["UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN", "BMY", "MDT", "SYK", "ISRG", "GILD", "VRTX", "CI", "ELV", "REGN", "ZTS"]},
    "XLY": {"name": "Consumer Disc.", "holdings": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "BKNG", "SBUX", "TJX", "CMG", "ORLY", "AZO", "ROST", "DHI", "LEN", "MAR", "HLT", "GM", "F", "LULU"]},
    "XLP": {"name": "Consumer Staples", "holdings": ["PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "CL", "KMB", "GIS", "K", "SJM", "HSY", "STZ", "TSN", "KHC", "CAG", "HRL", "MKC"]},
    "XLE": {"name": "Energy", "holdings": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "PXD", "OXY", "HES", "DVN", "WMB", "KMI", "HAL", "FANG", "BKR", "TRGP", "OKE", "CTRA"]},
    "XLI": {"name": "Industrials", "holdings": ["GE", "CAT", "UNP", "HON", "UPS", "RTX", "BA", "DE", "LMT", "MMM", "GD", "NOC", "ITW", "EMR", "WM", "RSG", "FDX", "CSX", "NSC", "ETN"]},
    "XLB": {"name": "Materials", "holdings": ["LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "PPG", "VMC", "MLM", "CF", "MOS", "IFF", "CE", "ALB", "CTVA", "FMC", "BALL"]},
    "XLRE": {"name": "Real Estate", "holdings": ["PLD", "AMT", "CCI", "EQIX", "PSA", "SPG", "O", "DLR", "WELL", "AVB", "EQR", "VTR", "ARE", "MAA", "UDR", "ESS", "HST", "KIM", "REG", "FRT"]},
    "XLU": {"name": "Utilities", "holdings": ["NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "PEG", "ED", "WEC", "ES", "AWK", "DTE", "AEE", "CMS", "CNP", "FE", "EVRG", "ATO"]},
    "XLC": {"name": "Communication", "holdings": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "ATVI", "TTWO", "WBD", "PARA", "FOX", "FOXA", "OMC", "IPG", "MTCH"]},
}


def get_price_data(ticker, period="5d"):
    """Get recent price data from Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            meta = result.get("meta", {})
            current = float(meta.get("regularMarketPrice", 0))
            return {"closes": [c for c in closes if c], "current": current}
    except Exception:
        pass
    return None


def calculate_momentum(closes):
    """Calculate 3-day momentum (% change over last 3 closes)."""
    if len(closes) < 3:
        return 0
    return ((closes[-1] - closes[-3]) / closes[-3]) * 100


def scan_sectors():
    """Scan all sector ETFs for weakness."""
    weak_sectors = []
    
    print("📊 SECTOR WEAKNESS SCAN")
    print("=" * 60)
    
    for etf, info in SECTORS.items():
        data = get_price_data(etf)
        if not data or not data["closes"]:
            print(f"  ⚠️  {etf} ({info['name']}): No data")
            continue
        
        momentum = calculate_momentum(data["closes"])
        current = data["current"]
        
        status = "🔴" if momentum < -1.0 else ("🟡" if momentum < 0 else "🟢")
        print(f"  {status} {etf} ({info['name']}): {momentum:+.2f}% (3-day) @ ${current:.2f}")
        
        if momentum < -1.0:  # Sector declining >1% over 3 days
            weak_sectors.append({
                "etf": etf,
                "name": info["name"],
                "momentum": momentum,
                "holdings": info["holdings"],
            })
    
    return weak_sectors


def find_weakest_names(sector):
    """Find the weakest individual stocks in a weak sector."""
    print(f"\n🔍 Scanning {sector['name']} ({sector['etf']}) — weakest names:")
    
    weak_names = []
    for ticker in sector["holdings"][:15]:  # Top 15 holdings
        data = get_price_data(ticker, "5d")
        if not data or not data["closes"]:
            continue
        
        momentum = calculate_momentum(data["closes"])
        current = data["current"]
        
        if momentum < -2.0:  # Individual stock down >2% in 3 days
            weak_names.append({
                "ticker": ticker,
                "momentum": momentum,
                "price": current,
                "sector": sector["name"],
            })
            print(f"  🔴 {ticker}: {momentum:+.2f}% (3-day) @ ${current:.2f}")
    
    weak_names.sort(key=lambda x: x["momentum"])
    return weak_names


def write_signals(weak_names):
    """Write short candidates to Supabase shared_signals."""
    SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
    HEADERS = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    
    for name in weak_names[:5]:  # Top 5 weakest
        signal = {
            "ticker": name["ticker"],
            "price": name["price"],
            "change_pct": name["momentum"],
            "signal_type": "SECTOR_WEAK_SHORT",
            "source_bot": "alfred",
            "reason": f"Sector weakness: {name['sector']} declining. {name['ticker']} down {name['momentum']:.1f}% (3-day). Short candidate.",
            "status": "OPEN",
        }
        try:
            r = requests.post(f"{SUPABASE_URL}/rest/v1/shared_signals", headers=HEADERS, json=signal)
            if r.status_code in (200, 201):
                print(f"  📡 Signal posted: SHORT {name['ticker']}")
            else:
                print(f"  ⚠️  Signal post failed: {r.status_code}")
        except Exception as e:
            print(f"  ⚠️  Signal post error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sector Weakness Detector")
    parser.add_argument("--sector", help="Scan single sector ETF")
    parser.add_argument("--write", action="store_true", help="Write signals to Supabase")
    args = parser.parse_args()
    
    weak_sectors = scan_sectors()
    
    if not weak_sectors:
        print("\n✅ No sectors in significant decline (>1% 3-day). No short candidates.")
    else:
        print(f"\n🔴 {len(weak_sectors)} weak sector(s) found. Scanning for short candidates...")
        all_weak = []
        for sector in weak_sectors:
            weak_names = find_weakest_names(sector)
            all_weak.extend(weak_names)
        
        if all_weak:
            all_weak.sort(key=lambda x: x["momentum"])
            print(f"\n📋 TOP SHORT CANDIDATES:")
            for i, name in enumerate(all_weak[:10], 1):
                print(f"  {i}. {name['ticker']} ({name['sector']}): {name['momentum']:+.2f}% @ ${name['price']:.2f}")
            
            if args.write:
                write_signals(all_weak)
        else:
            print("\n⚠️  Weak sectors found but no individual stocks down >2%. Watch list only.")
