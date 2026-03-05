#!/usr/bin/env python3
"""
catalyst_calendar.py - Pull upcoming market catalysts and write to JSON.

Sources:
  - FOMC meeting dates (hardcoded 2026 schedule)
  - CPI / Jobs / GDP release dates (hardcoded BLS/BEA schedule)
  - Options expiry (OPEX) - calculated from calendar math
  - Earnings dates - scraped from Yahoo Finance earnings calendar
  - Crypto token unlocks - best-effort from free sources

Output: trading/data/upcoming_catalysts.json
Only includes events in the next 14 days.

Usage:
    python3 catalyst_calendar.py
"""

import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from calendar import monthrange

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "upcoming_catalysts.json")

# ── Hardcoded schedules ──────────────────────────────────────────────────────

# 2025-2026 FOMC meeting dates (announcement days)
FOMC_DATES = [
    # 2025
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
    "2025-07-30", "2025-09-17", "2025-11-05", "2025-12-17",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-11-04", "2026-12-16",
]

# Approximate BLS/BEA release schedule for 2025-2026
# CPI: usually 2nd or 3rd week of the month
ECON_RELEASES = [
    # 2025
    {"date": "2025-01-10", "type": "jobs",  "description": "December 2024 Jobs Report (BLS)"},
    {"date": "2025-01-15", "type": "cpi",   "description": "December 2024 CPI Release"},
    {"date": "2025-01-30", "type": "gdp",   "description": "Q4 2024 GDP Advance Estimate"},
    {"date": "2025-02-07", "type": "jobs",  "description": "January 2025 Jobs Report (BLS)"},
    {"date": "2025-02-12", "type": "cpi",   "description": "January 2025 CPI Release"},
    {"date": "2025-02-27", "type": "gdp",   "description": "Q4 2024 GDP Second Estimate"},
    {"date": "2025-03-07", "type": "jobs",  "description": "February 2025 Jobs Report (BLS)"},
    {"date": "2025-03-12", "type": "cpi",   "description": "February 2025 CPI Release"},
    {"date": "2025-03-27", "type": "gdp",   "description": "Q4 2024 GDP Third Estimate"},
    {"date": "2025-04-04", "type": "jobs",  "description": "March 2025 Jobs Report (BLS)"},
    {"date": "2025-04-10", "type": "cpi",   "description": "March 2025 CPI Release"},
    {"date": "2025-04-30", "type": "gdp",   "description": "Q1 2025 GDP Advance Estimate"},
    {"date": "2025-05-02", "type": "jobs",  "description": "April 2025 Jobs Report (BLS)"},
    {"date": "2025-05-13", "type": "cpi",   "description": "April 2025 CPI Release"},
    {"date": "2025-05-29", "type": "gdp",   "description": "Q1 2025 GDP Second Estimate"},
    {"date": "2025-06-06", "type": "jobs",  "description": "May 2025 Jobs Report (BLS)"},
    {"date": "2025-06-11", "type": "cpi",   "description": "May 2025 CPI Release"},
    {"date": "2025-06-26", "type": "gdp",   "description": "Q1 2025 GDP Third Estimate"},
    {"date": "2025-07-03", "type": "jobs",  "description": "June 2025 Jobs Report (BLS)"},
    {"date": "2025-07-11", "type": "cpi",   "description": "June 2025 CPI Release"},
    {"date": "2025-07-30", "type": "gdp",   "description": "Q2 2025 GDP Advance Estimate"},
    {"date": "2025-08-01", "type": "jobs",  "description": "July 2025 Jobs Report (BLS)"},
    {"date": "2025-08-12", "type": "cpi",   "description": "July 2025 CPI Release"},
    {"date": "2025-08-28", "type": "gdp",   "description": "Q2 2025 GDP Second Estimate"},
    {"date": "2025-09-05", "type": "jobs",  "description": "August 2025 Jobs Report (BLS)"},
    {"date": "2025-09-10", "type": "cpi",   "description": "August 2025 CPI Release"},
    {"date": "2025-09-25", "type": "gdp",   "description": "Q2 2025 GDP Third Estimate"},
    {"date": "2025-10-03", "type": "jobs",  "description": "September 2025 Jobs Report (BLS)"},
    {"date": "2025-10-14", "type": "cpi",   "description": "September 2025 CPI Release"},
    {"date": "2025-10-30", "type": "gdp",   "description": "Q3 2025 GDP Advance Estimate"},
    {"date": "2025-11-07", "type": "jobs",  "description": "October 2025 Jobs Report (BLS)"},
    {"date": "2025-11-12", "type": "cpi",   "description": "October 2025 CPI Release"},
    {"date": "2025-11-26", "type": "gdp",   "description": "Q3 2025 GDP Second Estimate"},
    {"date": "2025-12-05", "type": "jobs",  "description": "November 2025 Jobs Report (BLS)"},
    {"date": "2025-12-10", "type": "cpi",   "description": "November 2025 CPI Release"},
    {"date": "2025-12-23", "type": "gdp",   "description": "Q3 2025 GDP Third Estimate"},
    # 2026
    {"date": "2026-01-09", "type": "jobs",  "description": "December 2025 Jobs Report (BLS)"},
    {"date": "2026-01-14", "type": "cpi",   "description": "December 2025 CPI Release"},
    {"date": "2026-01-29", "type": "gdp",   "description": "Q4 2025 GDP Advance Estimate"},
    {"date": "2026-02-06", "type": "jobs",  "description": "January 2026 Jobs Report (BLS)"},
    {"date": "2026-02-11", "type": "cpi",   "description": "January 2026 CPI Release"},
    {"date": "2026-02-26", "type": "gdp",   "description": "Q4 2025 GDP Second Estimate"},
    {"date": "2026-03-06", "type": "jobs",  "description": "February 2026 Jobs Report (BLS)"},
    {"date": "2026-03-11", "type": "cpi",   "description": "February 2026 CPI Release"},
    {"date": "2026-03-26", "type": "gdp",   "description": "Q4 2025 GDP Third Estimate"},
    {"date": "2026-04-03", "type": "jobs",  "description": "March 2026 Jobs Report (BLS)"},
    {"date": "2026-04-14", "type": "cpi",   "description": "March 2026 CPI Release"},
    {"date": "2026-04-29", "type": "gdp",   "description": "Q1 2026 GDP Advance Estimate"},
    {"date": "2026-05-08", "type": "jobs",  "description": "April 2026 Jobs Report (BLS)"},
    {"date": "2026-05-12", "type": "cpi",   "description": "April 2026 CPI Release"},
    {"date": "2026-05-28", "type": "gdp",   "description": "Q1 2026 GDP Second Estimate"},
    {"date": "2026-06-05", "type": "jobs",  "description": "May 2026 Jobs Report (BLS)"},
    {"date": "2026-06-10", "type": "cpi",   "description": "May 2026 CPI Release"},
    {"date": "2026-06-25", "type": "gdp",   "description": "Q1 2026 GDP Third Estimate"},
    {"date": "2026-07-02", "type": "jobs",  "description": "June 2026 Jobs Report (BLS)"},
    {"date": "2026-07-15", "type": "cpi",   "description": "June 2026 CPI Release"},
    {"date": "2026-07-30", "type": "gdp",   "description": "Q2 2026 GDP Advance Estimate"},
    {"date": "2026-08-07", "type": "jobs",  "description": "July 2026 Jobs Report (BLS)"},
    {"date": "2026-08-12", "type": "cpi",   "description": "July 2026 CPI Release"},
    {"date": "2026-08-27", "type": "gdp",   "description": "Q2 2026 GDP Second Estimate"},
    {"date": "2026-09-04", "type": "jobs",  "description": "August 2026 Jobs Report (BLS)"},
    {"date": "2026-09-16", "type": "cpi",   "description": "August 2026 CPI Release"},
    {"date": "2026-09-24", "type": "gdp",   "description": "Q2 2026 GDP Third Estimate"},
    {"date": "2026-10-02", "type": "jobs",  "description": "September 2026 Jobs Report (BLS)"},
    {"date": "2026-10-14", "type": "cpi",   "description": "September 2026 CPI Release"},
    {"date": "2026-10-29", "type": "gdp",   "description": "Q3 2026 GDP Advance Estimate"},
    {"date": "2026-11-06", "type": "jobs",  "description": "October 2026 Jobs Report (BLS)"},
    {"date": "2026-11-12", "type": "cpi",   "description": "October 2026 CPI Release"},
    {"date": "2026-11-25", "type": "gdp",   "description": "Q3 2026 GDP Second Estimate"},
    {"date": "2026-12-04", "type": "jobs",  "description": "November 2026 Jobs Report (BLS)"},
    {"date": "2026-12-09", "type": "cpi",   "description": "November 2026 CPI Release"},
    {"date": "2026-12-22", "type": "gdp",   "description": "Q3 2026 GDP Third Estimate"},
]


def get_fomc_events(today, horizon):
    """Return FOMC events within the date window."""
    events = []
    for d in FOMC_DATES:
        dt = date.fromisoformat(d)
        if today <= dt <= horizon:
            events.append({
                "date": d,
                "type": "fomc",
                "ticker": None,
                "description": f"FOMC Interest Rate Decision",
            })
    return events


def get_econ_events(today, horizon):
    """Return CPI/Jobs/GDP events within the date window."""
    events = []
    for entry in ECON_RELEASES:
        dt = date.fromisoformat(entry["date"])
        if today <= dt <= horizon:
            events.append({
                "date": entry["date"],
                "type": entry["type"],
                "ticker": None,
                "description": entry["description"],
            })
    return events


def get_opex_dates(today, horizon):
    """Calculate options expiry dates (monthly = 3rd Friday, weekly = every Friday)."""
    events = []
    d = today
    while d <= horizon:
        if d.weekday() == 4:  # Friday
            # Check if it's the 3rd Friday of the month
            first_day = date(d.year, d.month, 1)
            # Find first Friday
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            third_friday = first_friday + timedelta(weeks=2)
            if d == third_friday:
                label = "Monthly OPEX (3rd Friday)"
            else:
                label = "Weekly Options Expiry"
            events.append({
                "date": d.isoformat(),
                "type": "opex",
                "ticker": None,
                "description": label,
            })
        d += timedelta(days=1)
    return events


def get_yahoo_earnings(today, horizon):
    """Fetch earnings dates from Yahoo Finance earnings calendar."""
    events = []
    d = today
    while d <= horizon:
        url = f"https://finance.yahoo.com/calendar/earnings?day={d.isoformat()}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            # Try to extract ticker symbols from the HTML table
            # Yahoo earnings calendar has rows with ticker links
            tickers = re.findall(r'/quote/([A-Z]{1,5})\?', html)
            seen = set()
            for t in tickers:
                if t not in seen and len(seen) < 20:
                    seen.add(t)
                    events.append({
                        "date": d.isoformat(),
                        "type": "earnings",
                        "ticker": t,
                        "description": f"{t} earnings report",
                    })
        except Exception:
            pass  # Best effort - earnings scraping may fail
        d += timedelta(days=1)
    return events


def get_crypto_unlocks(today, horizon):
    """Best-effort crypto token unlock data from CoinGecko status page or similar."""
    # CoinGecko doesn't have a free unlock calendar API.
    # This is a placeholder that returns empty - can be extended with specific sources.
    # Major known unlock schedules could be hardcoded here if desired.
    return []


def build_calendar():
    """Build the full catalyst calendar for the next 14 days."""
    today = date.today()
    horizon = today + timedelta(days=14)

    events = []
    print(f"Collecting catalysts from {today} to {horizon}...")

    # Deterministic sources first
    events.extend(get_fomc_events(today, horizon))
    events.extend(get_econ_events(today, horizon))
    events.extend(get_opex_dates(today, horizon))

    # Network sources (best effort)
    print("Fetching Yahoo Finance earnings calendar...")
    events.extend(get_yahoo_earnings(today, horizon))

    print("Checking crypto unlock sources...")
    events.extend(get_crypto_unlocks(today, horizon))

    # Sort by date
    events.sort(key=lambda e: e["date"])

    output = {
        "last_updated": datetime.now().isoformat(),
        "window": {"start": today.isoformat(), "end": horizon.isoformat()},
        "events": events,
    }
    return output


def main():
    """Entry point: build calendar and write to disk."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    output = build_calendar()
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {len(output['events'])} events to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
