"""Event Calendar - Earnings date checks and event risk gating via Finnhub."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID
try:
    from config import FINNHUB_KEY
except ImportError:
    FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

import requests
import json
import time
from datetime import datetime, timedelta, timezone

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".event_cache.json")
CACHE_TTL = 6 * 3600  # 6 hours


def _load_cache():
    try:
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
        if time.time() - cache.get("ts", 0) < CACHE_TTL:
            return cache.get("data", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def _save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump({"ts": time.time(), "data": data}, f)


def _fetch_earnings(from_date, to_date):
    """Fetch earnings calendar from Finnhub, with caching."""
    cache_key = f"{from_date}_{to_date}"
    cached = _load_cache()
    if cached and cache_key in cached:
        return cached[cache_key]

    url = f"https://finnhub.io/api/v1/calendar/earnings?from={from_date}&to={to_date}&token={FINNHUB_KEY}"
    r = requests.get(url)
    events = []
    if r.status_code == 200:
        data = r.json()
        events = data.get("earningsCalendar", [])

    # Update cache
    cache = cached or {}
    cache[cache_key] = events
    _save_cache(cache)
    return events


def check_event_risk(ticker):
    """Check if a ticker has earnings within 24 hours."""
    today = datetime.now(timezone.utc).date()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")

    events = _fetch_earnings(from_date, to_date)

    for event in events:
        if event.get("symbol", "").upper() == ticker.upper():
            event_date_str = event.get("date", "")
            try:
                event_date = datetime.strptime(event_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                hours_until = (event_date - now).total_seconds() / 3600
                if -12 <= hours_until <= 24:
                    return {
                        "blocked": True,
                        "event": "earnings",
                        "event_date": event_date_str,
                        "hours_until": round(hours_until, 1),
                        "ticker": ticker.upper(),
                    }
            except ValueError:
                pass

    return {"blocked": False, "event": "", "event_date": "", "ticker": ticker.upper()}


def upcoming_events(days=7):
    """Return all earnings events for the next N days."""
    today = datetime.now(timezone.utc).date()
    from_date = today.strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=days)).strftime("%Y-%m-%d")

    events = _fetch_earnings(from_date, to_date)

    return [
        {
            "ticker": e.get("symbol", ""),
            "date": e.get("date", ""),
            "hour": e.get("hour", ""),
            "eps_estimate": e.get("epsEstimate"),
            "revenue_estimate": e.get("revenueEstimate"),
        }
        for e in events
    ]


if __name__ == "__main__":
    print("=== Event Calendar Test ===")
    risk = check_event_risk("AAPL")
    print(f"AAPL event risk: {risk}")
    events = upcoming_events(days=7)
    print(f"Upcoming events (first 5): {events[:5]}")
