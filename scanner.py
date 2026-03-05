#!/usr/bin/env python3
"""Market scanner: pulls quotes, calculates RVOL, detects trigger tiers."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

import config


def _finnhub_quote(ticker):
    """Get quote from Finnhub. Returns dict with c, o, h, l, v, t or None."""
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": config.FINNHUB_KEY},
            timeout=10,
        )
        if r.status_code == 429:
            print(f"  [RATE LIMIT] Finnhub - sleeping 2s")
            time.sleep(2)
            return None
        if r.status_code != 200:
            print(f"  [WARN] Finnhub {ticker}: {r.status_code}")
            return None
        data = r.json()
        if data.get("c", 0) == 0:
            return None
        return data
    except Exception as e:
        print(f"  [ERR] Finnhub {ticker}: {e}")
        return None


def _load_avg_volumes():
    """Load cached average daily volumes."""
    if os.path.exists(config.RVOL_CACHE_FILE):
        try:
            with open(config.RVOL_CACHE_FILE) as f:
                data = json.load(f)
            # Check if cache is from today
            cached_date = data.get("_date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if cached_date == today:
                return data
        except Exception:
            pass
    return {}


def _save_avg_volumes(data):
    data["_date"] = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(config.RVOL_CACHE_FILE), exist_ok=True)
    with open(config.RVOL_CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _fetch_avg_volume_av(ticker, cache):
    """Fetch 20-day avg volume from Alpha Vantage. Caches results."""
    if ticker in cache and ticker != "_date":
        return cache[ticker]

    try:
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker,
                "apikey": config.ALPHA_VANTAGE_KEY,
                "outputsize": "compact",
            },
            timeout=15,
        )
        data = r.json()
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            note = data.get("Note", data.get("Information", ""))
            if note:
                print(f"  [AV LIMIT] {ticker}: {note[:80]}")
            return None

        volumes = []
        for date_str in sorted(ts.keys(), reverse=True)[:20]:
            volumes.append(int(ts[date_str]["5. volume"]))

        if not volumes:
            return None

        avg = sum(volumes) / len(volumes)
        cache[ticker] = avg
        _save_avg_volumes(cache)
        return avg
    except Exception as e:
        print(f"  [ERR] Alpha Vantage {ticker}: {e}")
        return None


def scan(tickers=None, verbose=True):
    """
    Scan watchlist for trigger signals.
    Returns list of dicts: {ticker, tier, direction, pct_change, rvol, price, volume, score}
    """
    if tickers is None:
        tickers = config.WATCHLIST

    if verbose:
        print(f"[SCANNER] Scanning {len(tickers)} tickers...")

    avg_vol_cache = _load_avg_volumes()
    signals = []
    quotes = {}

    # Fetch all quotes from Finnhub
    for i, ticker in enumerate(tickers):
        if i > 0 and i % 30 == 0:
            time.sleep(1)  # Rate limit: ~30 calls then pause
        q = _finnhub_quote(ticker)
        if q:
            quotes[ticker] = q

    if verbose:
        print(f"  Got quotes for {len(quotes)}/{len(tickers)} tickers")

    # Analyze each
    for ticker, q in quotes.items():
        current = q.get("c", 0)
        open_price = q.get("o", 0)
        volume = q.get("v", 0)  # This is actually the volume field from Finnhub

        if not open_price or not current:
            continue

        pct_change = ((current - open_price) / open_price) * 100
        abs_pct = abs(pct_change)
        direction = "LONG" if pct_change > 0 else "SHORT"

        # Calculate RVOL
        avg_vol = _fetch_avg_volume_av(ticker, avg_vol_cache)
        if avg_vol and avg_vol > 0 and volume:
            # Normalize: Finnhub 'v' is sometimes cumulative intraday
            rvol = volume / avg_vol
        else:
            rvol = None

        # Check tiers (highest first)
        # If RVOL available, require both price + volume.
        # If RVOL unavailable, use price-only with higher threshold (1.5x).
        tier = None
        for tier_name in ["CONVICTION", "CONFIRM", "SCOUT"]:
            t = config.TIERS[tier_name]
            if rvol is not None:
                # Full confirmation: price + volume
                if abs_pct >= t["pct_move"] and rvol >= t["rvol_min"]:
                    tier = tier_name
                    break
            else:
                # Price-only mode: require 1.5x the normal price threshold
                if abs_pct >= t["pct_move"] * 1.5:
                    tier = tier_name
                    break

        if tier:
            # Score: weighted combo of price move and rvol
            score = abs_pct * 10
            if rvol:
                score += rvol * 20
            signal = {
                "ticker": ticker,
                "tier": tier,
                "direction": direction,
                "pct_change": round(pct_change, 2),
                "rvol": round(rvol, 2) if rvol else None,
                "price": current,
                "volume": volume,
                "score": round(score, 1),
            }
            signals.append(signal)
            if verbose:
                rvol_str = f"{rvol:.1f}x" if rvol else "N/A"
                print(f"  🔔 {tier} {direction} {ticker}: {pct_change:+.2f}% RVOL={rvol_str} @ ${current}")

    # Sort by score descending
    signals.sort(key=lambda s: s["score"], reverse=True)

    if verbose and not signals:
        print("  No triggers detected.")

    return signals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scan watchlist for trading signals")
    parser.add_argument("--tickers", nargs="+", help="Override watchlist")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    results = scan(tickers=args.tickers, verbose=not args.quiet)
    if results:
        print(f"\n=== {len(results)} Signal(s) ===")
        for s in results:
            print(f"  {s['tier']:10s} {s['direction']:5s} {s['ticker']:5s} "
                  f"{s['pct_change']:+6.2f}%  RVOL={s['rvol'] or 'N/A'}  Score={s['score']}")
