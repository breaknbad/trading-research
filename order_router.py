#!/usr/bin/env python3
"""Smart order router — recommends order type based on spread analysis."""

import sys, os, json, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FINNHUB_KEY, CACHE_DIR

ROUTING_LOG = os.path.join(CACHE_DIR, "order_routing_log.json")


def _get_quote(ticker: str) -> dict:
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        return r.json()
    except Exception:
        return {}


def _estimate_spread(quote: dict) -> float:
    """Estimate spread using high-low as proxy. Returns spread as fraction of price."""
    h, l, c = quote.get("h", 0), quote.get("l", 0), quote.get("c", 0)
    if c <= 0 or h <= 0 or l <= 0:
        return 0.0
    # Use intraday range as spread proxy (actual spread is tighter, but this is what we have)
    return (h - l) / c


def recommend_order(ticker: str, side: str, urgency: str = "normal") -> dict:
    """Recommend order type based on market conditions.

    Args:
        ticker: Stock symbol
        side: 'buy' or 'sell'
        urgency: 'normal' or 'high' (hard exits)

    Returns:
        {order_type, limit_price, reason}
    """
    quote = _get_quote(ticker)
    current = quote.get("c", 0)
    high = quote.get("h", 0)
    low = quote.get("l", 0)

    if current <= 0:
        return {"order_type": "market", "limit_price": None, "reason": "No quote available — defaulting to market"}

    # Hard exits always market
    if urgency == "high":
        result = {"order_type": "market", "limit_price": current, "reason": "High urgency — market order for immediate fill"}
        _log_routing(ticker, side, urgency, result)
        return result

    spread_pct = _estimate_spread(quote) * 100  # as percentage
    mid = (high + low) / 2 if high > 0 and low > 0 else current

    if spread_pct < 0.1:
        result = {"order_type": "market", "limit_price": current, "reason": f"Tight spread ({spread_pct:.3f}%) — market order fine"}
    elif spread_pct <= 0.3:
        result = {"order_type": "limit", "limit_price": round(mid, 2), "reason": f"Moderate spread ({spread_pct:.3f}%) — limit at mid ${mid:.2f}"}
    else:
        # Wide spread: buy at low side, sell at high side
        if side == "buy":
            favorable = round(low + (mid - low) * 0.3, 2)
        else:
            favorable = round(mid + (high - mid) * 0.3, 2)
        result = {"order_type": "limit", "limit_price": favorable, "reason": f"Wide spread ({spread_pct:.3f}%) — limit at favorable ${favorable:.2f}"}

    _log_routing(ticker, side, urgency, result)
    return result


def _log_routing(ticker, side, urgency, result):
    """Append routing decision to log."""
    log = []
    if os.path.exists(ROUTING_LOG):
        try:
            with open(ROUTING_LOG) as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    log.append({
        "ticker": ticker,
        "side": side,
        "urgency": urgency,
        "recommendation": result,
        "timestamp": time.time(),
    })

    # Keep last 500 entries
    log = log[-500:]
    with open(ROUTING_LOG, "w") as f:
        json.dump(log, f, indent=2)


def estimate_savings(trades_today: list = None) -> dict:
    """Estimate $ saved by smart routing vs always-market.

    Args:
        trades_today: List of {ticker, side, shares, fill_price} dicts.
                      If None, reads from routing log.

    Returns:
        {total_estimated_savings, num_limit_orders, num_market_orders}
    """
    if trades_today is None:
        if not os.path.exists(ROUTING_LOG):
            return {"total_estimated_savings": 0.0, "num_limit_orders": 0, "num_market_orders": 0}
        with open(ROUTING_LOG) as f:
            log = json.load(f)
        # Filter to today
        today_start = time.time() - 86400
        trades_today = [e for e in log if e.get("timestamp", 0) > today_start]

    limit_count = 0
    market_count = 0
    estimated_savings = 0.0

    for trade in trades_today:
        rec = trade.get("recommendation", trade)
        if rec.get("order_type") == "limit":
            limit_count += 1
            # Estimate: limit orders save ~0.05% on average
            price = rec.get("limit_price", 0)
            shares = trade.get("shares", 100)  # default 100 shares
            estimated_savings += price * shares * 0.0005
        else:
            market_count += 1

    return {
        "total_estimated_savings": round(estimated_savings, 2),
        "num_limit_orders": limit_count,
        "num_market_orders": market_count,
    }


if __name__ == "__main__":
    print(recommend_order("NVDA", "buy"))
    print(recommend_order("TSLA", "sell", urgency="high"))
    print(estimate_savings())
