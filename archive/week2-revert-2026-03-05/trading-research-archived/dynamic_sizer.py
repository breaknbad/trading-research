"""
dynamic_sizer.py - Maps pretrade factor score to position size.
"""

import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

# Score → size bands (midpoints used for interpolation)
SIZE_BANDS = [
    # (min_score, max_score, min_pct, max_pct)
    (80, 100, 8.0, 10.0),
    (60, 79,  5.0, 7.0),
    (40, 59,  3.0, 4.0),
]
MINIMUM_SCORE = 40

# Regime caps
REGIME_CAPS = {
    "CALM":     {"max_position_pct": 10.0},
    "NORMAL":   {"max_position_pct": 10.0},
    "ELEVATED": {"max_position_pct": 7.0},
    "CRISIS":   {"max_position_pct": 0.0},  # halt new entries
}


def _score_to_pct(factor_score):
    """Map factor score to position size percentage."""
    if factor_score < MINIMUM_SCORE:
        return 0.0, "Score below minimum threshold"

    for min_s, max_s, min_pct, max_pct in SIZE_BANDS:
        if min_s <= factor_score <= max_s:
            ratio = (factor_score - min_s) / max(max_s - min_s, 1)
            pct = min_pct + ratio * (max_pct - min_pct)
            return round(pct, 2), f"Score {factor_score} → {round(pct, 2)}%"

    # Score > 100 edge case
    return 10.0, f"Score {factor_score} capped at 10%"


def calculate_size(factor_score, portfolio_value, regime="NORMAL"):
    """
    Calculate position size based on factor score and regime.

    Returns: {size_pct, size_dollars, reason}
    """
    pct, reason = _score_to_pct(factor_score)

    if regime == "CRISIS":
        return {
            "size_pct": 0.0,
            "size_dollars": 0.0,
            "shares": 0,
            "reason": "CRISIS regime — no new entries",
        }

    cap = REGIME_CAPS.get(regime, {}).get("max_position_pct", 10.0)
    if pct > cap:
        pct = cap
        reason += f" (capped by {regime} regime to {cap}%)"

    dollars = round(portfolio_value * (pct / 100), 2)

    return {
        "size_pct": pct,
        "size_dollars": dollars,
        "shares": 0,  # no price info
        "reason": reason,
    }


def size_with_price(factor_score, portfolio_value, price, regime="NORMAL"):
    """
    Calculate position size including share count.

    Returns: {size_pct, size_dollars, shares, reason}
    """
    result = calculate_size(factor_score, portfolio_value, regime)

    if price and price > 0 and result["size_dollars"] > 0:
        result["shares"] = math.floor(result["size_dollars"] / price)
        result["size_dollars"] = round(result["shares"] * price, 2)
        result["size_pct"] = round((result["size_dollars"] / portfolio_value) * 100, 2)

    return result


if __name__ == "__main__":
    print(json.dumps(size_with_price(75, 100000, 150.0, "NORMAL"), indent=2))
    print(json.dumps(size_with_price(85, 100000, 150.0, "ELEVATED"), indent=2))
    print(json.dumps(calculate_size(30, 100000), indent=2))
