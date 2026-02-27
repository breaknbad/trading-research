"""
trade_grader.py — EOD analysis: scores each closed trade on timing, efficiency, and PnL.
"""
import sys, os, requests
from datetime import datetime, date, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY


def grade_trades(target_date: str = None) -> list:
    """
    Grade all closed trades for a given date (default: today).
    Returns list of graded trade dicts.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    # Fetch closed trades (SELL / COVER)
    exits = _fetch_trades(target_date, actions=["SELL", "COVER"])
    if not exits:
        print(f"[GRADER] No closed trades found for {target_date}")
        return []

    graded = []
    for exit_trade in exits:
        ticker = exit_trade["ticker"]
        # Find matching entry
        entry = _find_entry(ticker, exit_trade)
        if not entry:
            print(f"[GRADER] No entry found for {ticker}, skipping")
            continue

        grade = _compute_grade(entry, exit_trade, ticker)
        graded.append(grade)
        _write_grade(grade)

    print(f"[GRADER] Graded {len(graded)} trades for {target_date}")
    return graded


def factor_performance_summary() -> dict:
    """Analyze which factors appeared in winners vs losers from trade_grades."""
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/trade_grades",
            headers=SUPABASE_HEADERS,
            params={
                "select": "ticker,pnl_pct,factors,grade",
                "bot_id": f"eq.{BOT_ID}",
                "order": "graded_at.desc",
                "limit": "200",
            },
            timeout=10,
        )
        resp.raise_for_status()
        grades = resp.json()
    except Exception as e:
        print(f"[GRADER] Failed to fetch grades: {e}")
        return {}

    winners = {}
    losers = {}

    for g in grades:
        factors = g.get("factors") or []
        bucket = winners if (g.get("pnl_pct") or 0) > 0 else losers
        for f in factors:
            bucket[f] = bucket.get(f, 0) + 1

    return {"winner_factors": winners, "loser_factors": losers}


def _fetch_trades(target_date: str, actions: list) -> list:
    """Fetch trades from Supabase for a given date and action types."""
    try:
        action_filter = ",".join(actions)
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers=SUPABASE_HEADERS,
            params={
                "select": "*",
                "bot_id": f"eq.{BOT_ID}",
                "action": f"in.({action_filter})",
                "traded_at": f"gte.{target_date}T00:00:00",
                "order": "traded_at.asc",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[GRADER] Error fetching trades: {e}")
        return []


def _find_entry(ticker: str, exit_trade: dict) -> dict | None:
    """Find the matching entry trade for a given exit."""
    try:
        exit_time = exit_trade.get("traded_at", "")
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers=SUPABASE_HEADERS,
            params={
                "select": "*",
                "bot_id": f"eq.{BOT_ID}",
                "ticker": f"eq.{ticker}",
                "action": "in.(BUY,SHORT)",
                "traded_at": f"lt.{exit_time}",
                "order": "traded_at.desc",
                "limit": "1",
            },
            timeout=10,
        )
        resp.raise_for_status()
        entries = resp.json()
        return entries[0] if entries else None
    except Exception as e:
        print(f"[GRADER] Error finding entry for {ticker}: {e}")
        return None


def _compute_grade(entry: dict, exit_trade: dict, ticker: str) -> dict:
    """Compute grade metrics for a trade lifecycle."""
    entry_price = float(entry.get("price", 0))
    exit_price = float(exit_trade.get("price", 0))
    entry_time = entry.get("traded_at", "")
    exit_time = exit_trade.get("traded_at", "")

    # PnL %
    if entry_price > 0:
        if exit_trade.get("action") == "COVER":
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        else:
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
    else:
        pnl_pct = 0.0

    # Holding period (seconds)
    holding_period = 0
    try:
        t1 = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
        holding_period = (t2 - t1).total_seconds()
    except Exception:
        pass

    # Entry timing: where in day's range (uses Finnhub day candle)
    entry_timing = _calc_entry_timing(ticker, entry_price)

    # Exit efficiency: did price continue in our direction after exit?
    exit_efficiency = _calc_exit_efficiency(ticker, exit_price, exit_trade.get("action"))

    # Letter grade
    score = (entry_timing * 0.3) + (exit_efficiency * 0.3) + (min(max(pnl_pct * 10 + 50, 0), 100) * 0.4)
    if score >= 80:
        letter = "A"
    elif score >= 65:
        letter = "B"
    elif score >= 50:
        letter = "C"
    elif score >= 35:
        letter = "D"
    else:
        letter = "F"

    return {
        "bot_id": BOT_ID,
        "ticker": ticker,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl_pct": round(pnl_pct, 4),
        "entry_timing": round(entry_timing, 2),
        "exit_efficiency": round(exit_efficiency, 2),
        "holding_period_sec": int(holding_period),
        "grade": letter,
        "score": round(score, 2),
        "factors": entry.get("factors") or exit_trade.get("factors") or [],
        "entry_action": entry.get("action"),
        "exit_action": exit_trade.get("action"),
        "graded_at": datetime.now(timezone.utc).isoformat(),
    }


def _calc_entry_timing(ticker: str, entry_price: float) -> float:
    """Score 0-100: how close to the day's low (for BUY) we entered. 100 = perfect bottom."""
    try:
        resp = requests.get(
            f"https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        q = resp.json()
        high, low = q.get("h", 0), q.get("l", 0)
        if high == low:
            return 50.0
        # 100 = entered at low, 0 = entered at high
        return max(0, min(100, (1 - (entry_price - low) / (high - low)) * 100))
    except Exception:
        return 50.0  # neutral if we can't determine


def _calc_exit_efficiency(ticker: str, exit_price: float, action: str) -> float:
    """Score 0-100: did price move against us after exit? 100 = perfect exit."""
    try:
        resp = requests.get(
            f"https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=5,
        )
        resp.raise_for_status()
        q = resp.json()
        current = q.get("c", exit_price)
        high, low = q.get("h", exit_price), q.get("l", exit_price)

        if action == "COVER":
            # Short: good exit if price went up after we covered
            if high == low:
                return 50.0
            return max(0, min(100, ((current - exit_price) / (high - low)) * 100 + 50))
        else:
            # Long: good exit if price went down after we sold
            if high == low:
                return 50.0
            return max(0, min(100, ((exit_price - current) / (high - low)) * 100 + 50))
    except Exception:
        return 50.0


def _write_grade(grade: dict):
    """Write a single grade to Supabase trade_grades table."""
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/trade_grades",
            headers=SUPABASE_HEADERS,
            json=grade,
            timeout=5,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[GRADER] Failed to write grade for {grade['ticker']}: {e}")


if __name__ == "__main__":
    grades = grade_trades()
    for g in grades:
        print(f"  {g['ticker']}: {g['grade']} (score={g['score']}, pnl={g['pnl_pct']}%)")
    print("\nFactor summary:", factor_performance_summary())
