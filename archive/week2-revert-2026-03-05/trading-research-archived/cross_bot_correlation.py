"""Cross-Bot Correlation - Team-wide exposure and overlap checks."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

import requests
from collections import defaultdict

ALL_BOTS = ["alfred", "tars", "vex", "eddie"]
MAX_SECTOR_PCT = 40.0
MAX_TICKER_OVERLAP = 3


def _fetch_all_positions():
    """Fetch open positions for all 4 bots."""
    bots_csv = ",".join(f'"{b}"' for b in ALL_BOTS)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades?bot_id=in.({bots_csv})&status=eq.open&select=*",
        headers=SUPABASE_HEADERS,
    )
    return r.json() if r.status_code == 200 else []


def team_positions_summary():
    """Return all bots' holdings grouped by sector."""
    positions = _fetch_all_positions()

    by_bot = defaultdict(lambda: defaultdict(list))
    by_sector = defaultdict(float)
    total_value = 0.0

    for p in positions:
        bot = p.get("bot_id", "unknown")
        sector = p.get("sector", "unknown")
        ticker = p.get("ticker", "???")
        value = abs(float(p.get("market_value", 0) or 0))

        by_bot[bot][sector].append({"ticker": ticker, "value": value})
        by_sector[sector] += value
        total_value += value

    sector_pcts = {}
    if total_value > 0:
        sector_pcts = {s: round(v / total_value * 100, 2) for s, v in by_sector.items()}

    return {
        "by_bot": dict(by_bot),
        "sector_totals": dict(by_sector),
        "sector_pcts": sector_pcts,
        "total_team_value": total_value,
    }


def check_team_exposure(ticker, sector):
    """Check if adding a position is allowed given team-wide limits."""
    positions = _fetch_all_positions()

    # Check ticker overlap
    bots_holding = set()
    for p in positions:
        if p.get("ticker", "").upper() == ticker.upper():
            bots_holding.add(p.get("bot_id"))

    if len(bots_holding) >= MAX_TICKER_OVERLAP:
        return {
            "allowed": False,
            "reason": f"{ticker} already held by {len(bots_holding)} bots ({', '.join(bots_holding)}). Max overlap is {MAX_TICKER_OVERLAP}.",
        }

    # Check sector exposure
    total_value = 0.0
    sector_value = 0.0
    for p in positions:
        value = abs(float(p.get("market_value", 0) or 0))
        total_value += value
        if p.get("sector", "").lower() == sector.lower():
            sector_value += value

    if total_value > 0:
        sector_pct = sector_value / total_value * 100
        if sector_pct >= MAX_SECTOR_PCT:
            return {
                "allowed": False,
                "reason": f"Sector '{sector}' at {sector_pct:.1f}% of team portfolio (limit {MAX_SECTOR_PCT}%).",
            }

    return {"allowed": True, "reason": "Within limits."}


if __name__ == "__main__":
    print("=== Cross-Bot Correlation Test ===")
    summary = team_positions_summary()
    print(f"Team summary: {summary}")
    check = check_team_exposure("AAPL", "Technology")
    print(f"Exposure check AAPL/Tech: {check}")
