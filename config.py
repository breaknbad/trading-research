#!/usr/bin/env python3
"""Central configuration for Alfred's automated trading system."""

import os

# === Identity ===
BOT_ID = "alfred"

# === API Keys ===
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "d6dloapr01qm89pk26t0d6dloapr01qm89pk26tg")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "3RHX3MXAXDLM0NAJ")

# === Supabase ===
SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# === Watchlist ===
WATCHLIST = ["NVDA", "GOOGL", "TSLA", "MSFT", "PLTR", "AAPL", "AMD", "AMZN", "SQQQ", "CRM", "META"]

# === Trigger Thresholds (Velocity/Volume Protocol) ===
TIERS = {
    "SCOUT": {
        "pct_move": 1.5,
        "rvol_min": 1.5,
        "size_min_pct": 2.0,
        "size_max_pct": 6.0,
    },
    "CONFIRM": {
        "pct_move": 3.0,
        "rvol_min": 2.0,
        "size_min_pct": 6.0,  # add equal to existing
        "size_max_pct": 10.0,
        "stop_to_breakeven": True,
    },
    "CONVICTION": {
        "pct_move": 5.0,
        "rvol_min": 3.0,
        "size_max_pct": 12.0,
        "trail_stop_pct": 1.5,
        "requires_sector_confirm": True,
    },
}

# === Risk Parameters ===
STOP_LOSS_PCT = 2.0          # Default stop loss %
MAX_POSITION_PCT = 10.0      # Max single position as % of portfolio
DAILY_CIRCUIT_BREAKER_PCT = 5.0  # Max daily loss % before halting
COOLDOWN_SECONDS = 600       # 10-min same-ticker cooldown (v1.2 — no trade caps)
SECTOR_CAP_PCT = 30.0        # Max sector exposure %
MARKET_CAP_FLOOR = 500_000_000  # $500M minimum
STARTING_CAPITAL = 25000.0

# === Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DASHBOARD_DIR = os.path.join(BASE_DIR, "dashboard", "data")
RVOL_CACHE_FILE = os.path.join(CACHE_DIR, "avg_volumes.json")
TRADE_TIMESTAMPS_FILE = os.path.join(CACHE_DIR, "trade_timestamps.json")

# Ensure dirs exist
for d in [CACHE_DIR, LOGS_DIR]:
    os.makedirs(d, exist_ok=True)

# === Scout Cutoff ===
SCOUT_CUTOFF_HOUR = 15   # 3:00 PM ET — no new scouts after this
SCOUT_CUTOFF_MINUTE = 0

# === Finnhub Rate Limit ===
FINNHUB_CALLS_PER_MIN = 60
ALPHA_VANTAGE_CALLS_PER_DAY = 25

if __name__ == "__main__":
    print("=== Alfred Trading Config ===")
    print(f"Bot ID: {BOT_ID}")
    print(f"Watchlist: {WATCHLIST}")
    print(f"Tiers: {list(TIERS.keys())}")
    print(f"Stop Loss: {STOP_LOSS_PCT}%")
    print(f"Max Position: {MAX_POSITION_PCT}%")
    print(f"Circuit Breaker: {DAILY_CIRCUIT_BREAKER_PCT}%")
    print(f"Cache dir: {CACHE_DIR}")
