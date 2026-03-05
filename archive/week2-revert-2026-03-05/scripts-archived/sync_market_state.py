#!/usr/bin/env python3
"""sync_market_state.py — Pull market-state from Supabase and write local file. 
Run on bots that don't run market_watcher themselves."""

import os, json, sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
STATE_FILE = WORKSPACE / "market-state.json"

def main():
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/market_state?id=eq.latest&select=state_json",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=10
    )
    if resp.status_code != 200 or not resp.json():
        print(f"Error: {resp.status_code}")
        return
    
    state = json.loads(resp.json()[0]["state_json"])
    
    # Atomic write
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(STATE_FILE)
    print(f"Synced {len(state.get('tickers', {}))} tickers")

if __name__ == "__main__":
    main()
