#!/usr/bin/env python3
"""Pre-market scanner — pulls pre-market quotes, flags gaps, checks sector heat."""

import sys, os, json, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FINNHUB_KEY, WATCHLIST, CACHE_DIR

SECTOR_ETFS = ["SPY", "QQQ", "XLK", "XLF", "XLE", "XLV", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
GAP_THRESHOLD_PCT = 2.0


def _get_quote(ticker: str) -> dict:
    """Fetch quote from Finnhub. Returns {c, h, l, o, pc, t} or empty dict."""
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        if data.get("c", 0) > 0:
            return data
    except Exception as e:
        print(f"  [warn] Quote failed for {ticker}: {e}")
    return {}


def _calc_gap_pct(current: float, prev_close: float) -> float:
    if prev_close <= 0:
        return 0.0
    return ((current - prev_close) / prev_close) * 100


def _get_earnings_tickers() -> list:
    """Try to import earnings from event_calendar if it exists."""
    try:
        from event_calendar import get_todays_earnings
        return get_todays_earnings()
    except (ImportError, AttributeError):
        return []


def run_premarket_scan() -> dict:
    """Run full pre-market scan.

    Returns:
        {gaps: list, sector_heat: dict, watchlist_scores: list}
    """
    gaps = []
    sector_heat = {}
    watchlist_scores = []
    earnings_tickers = _get_earnings_tickers()

    # Scan sector ETFs
    for etf in SECTOR_ETFS:
        q = _get_quote(etf)
        if not q:
            continue
        gap = _calc_gap_pct(q["c"], q["pc"])
        sector_heat[etf] = round(gap, 2)
        if abs(gap) >= GAP_THRESHOLD_PCT:
            gaps.append({"ticker": etf, "gap_pct": round(gap, 2), "price": q["c"], "prev_close": q["pc"], "type": "sector_etf"})
        time.sleep(0.25)  # Rate limiting

    # Scan watchlist
    for ticker in WATCHLIST:
        q = _get_quote(ticker)
        if not q:
            continue
        gap = _calc_gap_pct(q["c"], q["pc"])
        has_earnings = ticker in earnings_tickers
        score = {
            "ticker": ticker,
            "price": q["c"],
            "prev_close": q["pc"],
            "gap_pct": round(gap, 2),
            "has_earnings": has_earnings,
        }
        watchlist_scores.append(score)
        if abs(gap) >= GAP_THRESHOLD_PCT:
            gaps.append({"ticker": ticker, "gap_pct": round(gap, 2), "price": q["c"], "prev_close": q["pc"], "type": "watchlist"})
        time.sleep(0.25)

    # Sort gaps by magnitude
    gaps.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
    watchlist_scores.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)

    return {"gaps": gaps, "sector_heat": sector_heat, "watchlist_scores": watchlist_scores}


def format_premarket_report() -> str:
    """Format scan results for Discord posting."""
    data = run_premarket_scan()
    lines = ["**☀️ Pre-Market Scanner Report**", ""]

    # Sector heat
    lines.append("**Sector Heat Map:**")
    for etf, gap in sorted(data["sector_heat"].items(), key=lambda x: x[1], reverse=True):
        arrow = "🟢" if gap > 0 else "🔴" if gap < 0 else "⚪"
        lines.append(f"  {arrow} {etf}: {gap:+.2f}%")

    # Gaps
    if data["gaps"]:
        lines.append("")
        lines.append(f"**⚠️ Gaps >{GAP_THRESHOLD_PCT}%:**")
        for g in data["gaps"]:
            direction = "GAP UP" if g["gap_pct"] > 0 else "GAP DOWN"
            lines.append(f"  • **{g['ticker']}** {direction} {g['gap_pct']:+.2f}% → ${g['price']:.2f}")
    else:
        lines.append("\n*No significant gaps detected.*")

    # Watchlist highlights
    lines.append("")
    lines.append("**Watchlist Movers:**")
    for s in data["watchlist_scores"][:5]:
        earn = " 📊" if s["has_earnings"] else ""
        lines.append(f"  • {s['ticker']}: {s['gap_pct']:+.2f}% (${s['price']:.2f}){earn}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(format_premarket_report())
