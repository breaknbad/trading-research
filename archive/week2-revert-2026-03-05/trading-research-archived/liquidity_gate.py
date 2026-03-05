"""Liquidity Gate - Pre-trade liquidity check using Finnhub quote data."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID
try:
    from config import FINNHUB_KEY
except ImportError:
    FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

import requests

MIN_DAILY_DOLLAR_VOL = 5_000_000  # $5M minimum
MAX_VOL_PCT = 0.01  # 1% of avg daily volume


def check_liquidity(ticker):
    """Check if a ticker has sufficient liquidity for trading."""
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker.upper()}&token={FINNHUB_KEY}"
    r = requests.get(url)

    if r.status_code != 200:
        return {"pass": False, "daily_dollar_vol": 0, "max_position_dollars": 0,
                "reason": f"Finnhub API error: {r.status_code}"}

    data = r.json()
    current_price = data.get("c", 0)  # current price
    prev_close = data.get("pc", 0)    # previous close

    # Finnhub quote doesn't give volume directly in this endpoint,
    # but we can estimate from the data available.
    # For a more accurate check, we'd use /stock/candle, but quote is simpler.
    # Using a heuristic: if the stock has a price, we check it.
    # In production, pair with /stock/candle for actual volume.

    if current_price <= 0:
        return {"pass": False, "daily_dollar_vol": 0, "max_position_dollars": 0,
                "reason": f"No valid price for {ticker}"}

    # Fetch actual volume from candle data (last trading day)
    from datetime import datetime, timedelta
    import time
    now = int(time.time())
    candle_url = (f"https://finnhub.io/api/v1/stock/candle"
                  f"?symbol={ticker.upper()}&resolution=D&from={now - 86400 * 5}&to={now}&token={FINNHUB_KEY}")
    cr = requests.get(candle_url)
    avg_volume = 0

    if cr.status_code == 200:
        cdata = cr.json()
        volumes = cdata.get("v", [])
        if volumes:
            avg_volume = sum(volumes) / len(volumes)

    daily_dollar_vol = avg_volume * current_price
    max_position_dollars = daily_dollar_vol * MAX_VOL_PCT

    passed = daily_dollar_vol >= MIN_DAILY_DOLLAR_VOL

    return {
        "pass": passed,
        "ticker": ticker.upper(),
        "current_price": current_price,
        "avg_daily_volume": avg_volume,
        "daily_dollar_vol": round(daily_dollar_vol, 2),
        "max_position_dollars": round(max_position_dollars, 2),
        "reason": "OK" if passed else f"Daily dollar volume ${daily_dollar_vol:,.0f} below ${MIN_DAILY_DOLLAR_VOL:,.0f} minimum",
    }


if __name__ == "__main__":
    print("=== Liquidity Gate Test ===")
    result = check_liquidity("AAPL")
    print(f"AAPL liquidity: {result}")
    result2 = check_liquidity("AAPL")
    print(f"Check: {result2}")
