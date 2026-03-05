#!/usr/bin/env python3
"""
Outlier Catcher — Finds green outliers on red days.
When market breadth <20% green AND a ticker is +5% with RVOL >1.5x,
flags it for a 2% SCOUT position.

Usage:
  python3 outlier_catcher.py --scan                    # Scan signal bus for outliers
  python3 outlier_catcher.py --evaluate TICKER CHANGE RVOL  # Evaluate single ticker
  python3 outlier_catcher.py --set-breadth 0.10        # Set current market breadth (0-1)

Designed to be called from heartbeat/scan loops.
Reads from signal_bus.json (TARS output) if available.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
STATE_FILE = WORKSPACE / "outlier_state.json"
SIGNAL_BUS_FILE = WORKSPACE / "signal_bus.json"

# Thresholds
MIN_CHANGE_PCT = 5.0       # Ticker must be +5%
MIN_RVOL = 1.5             # Relative volume must be >1.5x
MAX_BREADTH = 0.20          # Market breadth must be <20% green
MIN_CASH_PCT = 0.20         # Bot must have >20% cash
SCOUT_SIZE_PCT = 0.02       # 2% position size


def load_state():
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "breadth": None,
        "outliers_found": [],
        "outliers_acted": [],
    }


def save_state(data):
    STATE_FILE.write_text(json.dumps(data, indent=2))


def evaluate_ticker(ticker: str, change_pct: float, rvol: float, breadth: float):
    """Evaluate if a ticker qualifies as an outlier catch."""
    result = {
        "ticker": ticker.upper(),
        "change_pct": change_pct,
        "rvol": rvol,
        "breadth": breadth,
        "qualifies": False,
        "reasons": [],
    }

    if change_pct < MIN_CHANGE_PCT:
        result["reasons"].append(f"Change {change_pct:.1f}% < {MIN_CHANGE_PCT}% minimum")
    if rvol < MIN_RVOL:
        result["reasons"].append(f"RVOL {rvol:.2f}x < {MIN_RVOL}x minimum")
    if breadth > MAX_BREADTH:
        result["reasons"].append(f"Breadth {breadth:.0%} > {MAX_BREADTH:.0%} max (not red enough)")

    if not result["reasons"]:
        result["qualifies"] = True
        result["reasons"].append(f"✅ OUTLIER CATCH: {ticker} +{change_pct:.1f}% on {rvol:.1f}x RVOL, breadth {breadth:.0%}")

    return result


def scan_signal_bus(breadth: float):
    """Scan TARS signal bus output for outlier candidates."""
    if not SIGNAL_BUS_FILE.exists():
        print("⚠️  No signal_bus.json found. Provide signals manually or wait for TARS scan.")
        return []

    try:
        signals = json.loads(SIGNAL_BUS_FILE.read_text())
    except json.JSONDecodeError:
        print("⚠️  signal_bus.json corrupted.")
        return []

    state = load_state()
    outliers = []

    for sig in signals:
        ticker = sig.get("ticker", "")
        change = sig.get("change_pct", 0)
        rvol = sig.get("rvol", 0)

        if change <= 0:
            continue  # Only green outliers

        result = evaluate_ticker(ticker, change, rvol, breadth)
        if result["qualifies"]:
            # Check if already acted on today
            if ticker not in state["outliers_acted"]:
                outliers.append(result)
                if ticker not in [o["ticker"] for o in state["outliers_found"]]:
                    state["outliers_found"].append({
                        "ticker": ticker,
                        "change_pct": change,
                        "rvol": rvol,
                        "found_at": datetime.now(timezone.utc).isoformat()
                    })

    state["breadth"] = breadth
    save_state(state)
    return outliers


def main():
    parser = argparse.ArgumentParser(description="Outlier Catcher")
    parser.add_argument("--scan", action="store_true", help="Scan signal bus for outliers")
    parser.add_argument("--evaluate", nargs=3, metavar=("TICKER", "CHANGE", "RVOL"),
                        help="Evaluate single ticker")
    parser.add_argument("--set-breadth", type=float, help="Set current market breadth (0-1)")
    parser.add_argument("--breadth", type=float, default=0.10,
                        help="Market breadth for scan (default 0.10 = 10%% green)")
    parser.add_argument("--mark-acted", help="Mark a ticker as acted on (no re-catch)")

    args = parser.parse_args()

    if args.scan:
        outliers = scan_signal_bus(args.breadth)
        if outliers:
            print(f"🎯 {len(outliers)} OUTLIER(S) FOUND:")
            for o in outliers:
                print(f"  {o['ticker']} +{o['change_pct']:.1f}% | RVOL {o['rvol']:.1f}x")
                print(f"  → SCOUT 2% position recommended")
        else:
            print("No qualifying outliers on current scan.")

    elif args.evaluate:
        ticker, change, rvol = args.evaluate
        result = evaluate_ticker(ticker, float(change), float(rvol), args.breadth)
        if result["qualifies"]:
            print(f"🎯 {result['reasons'][0]}")
        else:
            print(f"❌ {ticker} does not qualify:")
            for r in result["reasons"]:
                print(f"  - {r}")

    elif args.set_breadth is not None:
        state = load_state()
        state["breadth"] = args.set_breadth
        save_state(state)
        print(f"Breadth set to {args.set_breadth:.0%}")

    elif args.mark_acted:
        state = load_state()
        ticker = args.mark_acted.upper()
        if ticker not in state["outliers_acted"]:
            state["outliers_acted"].append(ticker)
        save_state(state)
        print(f"✅ {ticker} marked as acted on. Won't re-catch today.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
