#!/usr/bin/env python3
"""
Portfolio Correlation Monitor — EOD check for concentrated risk.
Flags when >3 positions have >0.7 pairwise correlation.

Usage:
  python3 correlation_check.py              # Check all bots
  python3 correlation_check.py --bot alfred  # Check one bot
"""

import argparse
import requests
import json
from collections import defaultdict

SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]

# Sector mapping for correlation proxy (no API needed)
SECTOR_MAP = {
    # Tech / Semis (highly correlated)
    "NVDA": "TECH_SEMI", "AMD": "TECH_SEMI", "AVGO": "TECH_SEMI", "INTC": "TECH_SEMI", "QCOM": "TECH_SEMI",
    "AAPL": "TECH_MEGA", "MSFT": "TECH_MEGA", "GOOGL": "TECH_MEGA", "META": "TECH_MEGA", "AMZN": "TECH_MEGA",
    "TSLA": "TECH_EV",
    # Software
    "PLTR": "TECH_SW", "CRM": "TECH_SW", "BBAI": "TECH_SW",
    # Gold / Miners
    "GLD": "GOLD", "GDX": "GOLD", "GDXJ": "GOLD", "SLV": "PRECIOUS",
    # Energy
    "XLE": "ENERGY", "XOP": "ENERGY",
    # Defensive
    "XLP": "DEFENSIVE", "XLU": "DEFENSIVE",
    # Crypto
    "BTC": "CRYPTO", "BTC-USD": "CRYPTO", "ETH": "CRYPTO", "ETH-USD": "CRYPTO",
    "SOL": "CRYPTO_ALT", "SOL-USD": "CRYPTO_ALT",
    # Inverse / Leveraged
    "SQQQ": "TECH_INVERSE", "QQQ": "TECH_LONG",
}


def check_correlation(bot_id=None):
    """Check portfolio for concentrated sector exposure."""
    bots_to_check = [bot_id] if bot_id else BOTS

    for bot in bots_to_check:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
            params={"bot_id": f"eq.{bot}", "select": "open_positions"},
            headers=HEADERS,
        )
        if r.status_code != 200 or not r.json():
            continue

        positions = r.json()[0].get("open_positions", []) or []
        if not positions:
            continue

        # Group positions by sector
        sector_positions = defaultdict(list)
        for pos in positions:
            ticker = pos.get("ticker", "").upper()
            sector = SECTOR_MAP.get(ticker, "UNKNOWN")
            sector_positions[sector].append({
                "ticker": ticker,
                "side": pos.get("side", "LONG"),
                "qty": float(pos.get("quantity", 0)),
                "entry": float(pos.get("avg_entry", 0)),
            })

        # Flag sectors with >3 correlated positions
        print(f"\n📊 Correlation Check: {bot}")
        alerts = 0
        for sector, positions_in_sector in sector_positions.items():
            # Count same-direction positions (same side = correlated risk)
            longs = [p for p in positions_in_sector if p["side"] == "LONG"]
            shorts = [p for p in positions_in_sector if p["side"] == "SHORT"]

            if len(longs) > 3:
                tickers = ", ".join(p["ticker"] for p in longs)
                print(f"   🔴 CORRELATION ALERT: {len(longs)} LONG positions in {sector}: {tickers}")
                alerts += 1
            elif len(longs) > 2:
                tickers = ", ".join(p["ticker"] for p in longs)
                print(f"   🟡 CORRELATION WARNING: {len(longs)} LONG positions in {sector}: {tickers}")

            if len(shorts) > 3:
                tickers = ", ".join(p["ticker"] for p in shorts)
                print(f"   🔴 CORRELATION ALERT: {len(shorts)} SHORT positions in {sector}: {tickers}")
                alerts += 1
            elif len(shorts) > 2:
                tickers = ", ".join(p["ticker"] for p in shorts)
                print(f"   🟡 CORRELATION WARNING: {len(shorts)} SHORT positions in {sector}: {tickers}")

        if alerts == 0:
            print(f"   ✅ No correlation breaches (≤3 same-direction positions per sector)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Portfolio correlation monitor")
    parser.add_argument("--bot", choices=BOTS)
    args = parser.parse_args()
    check_correlation(args.bot)
