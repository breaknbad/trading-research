#!/usr/bin/env python3
"""
extension_filter.py — Gap-chase prevention for Mi AI trading bots.

Returns the minimum conviction score required to enter a position based on
how extended a ticker already is intraday. Prevents chasing parabolic moves.

Thresholds:
  0-5% gain:   min 2/10 (standard scout)
  5-15% gain:  min 4/10
  15-25% gain: min 7/10
  >25% gain:   min 9/10 (almost never chase)

Usage:
  python3 extension_filter.py --pct 12.5
  python3 extension_filter.py --pct 30 --conviction 8  # check if trade passes

Import:
  from extension_filter import min_conviction_for_gain, check_entry_allowed
"""

import argparse
import sys


def min_conviction_for_gain(pct_gain: float) -> int:
    """
    Given a ticker's intraday gain %, return the minimum conviction score (1-10)
    required to enter the position.

    Args:
        pct_gain: Absolute intraday percentage gain (e.g., 12.5 for +12.5%)

    Returns:
        Minimum conviction score (2, 4, 7, or 9)
    """
    pct = abs(pct_gain)
    if pct <= 5:
        return 2
    elif pct <= 15:
        return 4
    elif pct <= 25:
        return 7
    else:
        return 9


def check_entry_allowed(ticker: str, pct_gain: float, conviction_score: int) -> dict:
    """
    Check if entry is allowed for a given ticker based on extension and conviction.

    Args:
        ticker: Stock ticker
        pct_gain: Intraday gain percentage
        conviction_score: Bot's conviction score for this trade (1-10)

    Returns:
        Dict with 'allowed' (bool), 'min_required' (int), 'reason' (str)
    """
    min_required = min_conviction_for_gain(pct_gain)
    allowed = conviction_score >= min_required

    if allowed:
        reason = f"{ticker} +{pct_gain:.1f}% — conviction {conviction_score}/10 >= {min_required}/10 required. PASS."
    else:
        reason = (
            f"{ticker} +{pct_gain:.1f}% — conviction {conviction_score}/10 < {min_required}/10 required. "
            f"BLOCKED: too extended for this conviction level."
        )

    return {
        "allowed": allowed,
        "min_required": min_required,
        "conviction_score": conviction_score,
        "pct_gain": pct_gain,
        "ticker": ticker,
        "reason": reason,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gap-chase prevention filter")
    parser.add_argument("--pct", required=True, type=float, help="Intraday gain percentage")
    parser.add_argument("--conviction", type=int, help="Your conviction score (1-10) to check against")
    parser.add_argument("--ticker", type=str, default="???", help="Ticker symbol")

    args = parser.parse_args()

    min_req = min_conviction_for_gain(args.pct)
    print(f"\n📊 Extension Filter: +{args.pct:.1f}% gain → minimum conviction: {min_req}/10")

    if args.conviction is not None:
        result = check_entry_allowed(args.ticker, args.pct, args.conviction)
        if result["allowed"]:
            print(f"✅ {result['reason']}")
        else:
            print(f"🚫 {result['reason']}")
        sys.exit(0 if result["allowed"] else 1)
