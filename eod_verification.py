"""
eod_verification.py — End-of-day sweep verification for inverse/leveraged ETFs.
Runs at 3:55 PM (pre-close check) and 4:01 PM (post-close verification).
"""
import sys, os, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY

LEVERAGED_ETFS = [
    "SQQQ", "TQQQ", "SPXU", "SPXS", "UVXY", "SDOW", "QID", "SDS",
    "SOXS", "SOXL", "LABU", "LABD", "FNGU", "FNGD", "TZA", "TNA",
    "SPXL", "UPRO", "UDOW", "DRV", "ERX", "ERY", "NUGT", "DUST",
    "JNUG", "JDST", "FAZ", "FAS", "TECL", "TECS", "YANG", "YINN",
]


def get_leveraged_etf_list() -> list:
    """Return the list of known inverse/leveraged ETF tickers."""
    return list(LEVERAGED_ETFS)


def verify_eod_sweep() -> dict:
    """
    Query Supabase for any open positions in leveraged/inverse ETFs.
    Returns {clean: bool, stuck_positions: list}.
    """
    stuck = []
    try:
        # Query open positions matching leveraged ETF tickers
        tickers_filter = ",".join(LEVERAGED_ETFS)
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/positions",
            headers=SUPABASE_HEADERS,
            params={
                "select": "ticker,quantity,entry_price,opened_at",
                "ticker": f"in.({tickers_filter})",
                "status": "eq.OPEN",
                "bot_id": f"eq.{BOT_ID}",
            },
            timeout=10,
        )
        resp.raise_for_status()
        positions = resp.json()

        for pos in positions:
            stuck.append({
                "ticker": pos["ticker"],
                "quantity": pos.get("quantity"),
                "entry_price": pos.get("entry_price"),
                "opened_at": pos.get("opened_at"),
            })

        if stuck:
            _log_critical(stuck)
            print(f"[EOD] CRITICAL: {len(stuck)} stuck leveraged ETF positions: {[p['ticker'] for p in stuck]}")
        else:
            print("[EOD] Clean — no stuck leveraged ETF positions.")

    except Exception as e:
        print(f"[EOD] Error querying positions: {e}")
        # If we can't verify, treat as dirty
        return {"clean": False, "stuck_positions": [], "error": str(e)}

    return {"clean": len(stuck) == 0, "stuck_positions": stuck}


def _log_critical(stuck_positions: list):
    """Log critical stuck position alert to Supabase."""
    payload = {
        "bot_id": BOT_ID,
        "event": "EOD_STUCK_POSITIONS",
        "severity": "CRITICAL",
        "details": {
            "stuck_count": len(stuck_positions),
            "tickers": [p["ticker"] for p in stuck_positions],
            "positions": stuck_positions,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/system_alerts",
            headers=SUPABASE_HEADERS,
            json=payload,
            timeout=5,
        )
    except Exception as e:
        print(f"[EOD] Failed to log critical alert: {e}")


if __name__ == "__main__":
    print("Leveraged ETFs monitored:", len(get_leveraged_etf_list()))
    result = verify_eod_sweep()
    print("Result:", result)
