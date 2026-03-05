"""
price_sanity.py — Universal price validation gate.
Import this in ANY script that auto-executes trades.

Usage:
    from price_sanity import validate_price, sanitize_trade_price

SHIL HARDENED: No trade executes without passing these checks.
"""

# Minimum believable prices by asset class
PRICE_FLOORS = {
    "BTC-USD": 10000, "BTC": 10000,
    "ETH-USD": 100, "ETH": 100,
    "SOL-USD": 0.50, "SOL": 0.50,
    "BNB-USD": 10, "BNB": 10,
    "AVAX-USD": 0.10, "AVAX": 0.10,
    "LINK-USD": 0.10, "LINK": 0.10,
    "XRP-USD": 0.01, "XRP": 0.01,
    "ADA-USD": 0.001, "ADA": 0.001,
    "DOGE-USD": 0.001, "DOGE": 0.001,
    "DOT-USD": 0.10, "DOT": 0.10,
    "NEAR-USD": 0.05, "NEAR": 0.05,
    "ATOM-USD": 0.10, "ATOM": 0.10,
    "SUI-USD": 0.01, "SUI": 0.01,
    "APT-USD": 0.10, "APT": 0.10,
    "ARB-USD": 0.01, "ARB": 0.01,
    "RENDER-USD": 0.01, "RENDER": 0.01,
    "INJ-USD": 0.10, "INJ": 0.10,
    "FET-USD": 0.001, "FET": 0.001,
    "OP-USD": 0.01, "OP": 0.01,
    "AAVE-USD": 1.0, "AAVE": 1.0,
    # Equities
    "SQQQ": 1.0, "SH": 1.0,
    "SPY": 100, "QQQ": 100,
    "GLD": 50, "GDX": 5,
    "XLE": 10, "XLV": 20,
    "ROST": 50, "MRNA": 5,
    "COIN": 10, "MSTR": 10,
}

DEFAULT_FLOOR = 0.001  # For unknown tickers


def validate_price(ticker: str, price: float, entry_price: float = None) -> dict:
    """
    Validate a price before any auto-execution.
    
    Returns: {"valid": bool, "reason": str}
    """
    if price is None or price <= 0:
        return {"valid": False, "reason": f"Price is None or ≤0 (${price})"}
    
    # Check absolute floor
    floor = PRICE_FLOORS.get(ticker, DEFAULT_FLOOR)
    if price < floor:
        return {"valid": False, "reason": f"${price:.4f} below floor ${floor} for {ticker}"}
    
    # Check relative to entry (if provided) — reject if <10% of entry
    if entry_price and entry_price > 0:
        ratio = price / entry_price
        if ratio < 0.10:
            return {"valid": False, "reason": f"${price:.4f} is {ratio:.1%} of entry ${entry_price:.2f} — likely bad data"}
        if ratio > 10.0:
            return {"valid": False, "reason": f"${price:.4f} is {ratio:.1%} of entry ${entry_price:.2f} — likely bad data"}
    
    return {"valid": True, "reason": "OK"}


def sanitize_trade_price(ticker: str, price: float, entry_price: float = None, action: str = "SELL") -> bool:
    """
    Gate function for auto-execution. Returns True if trade should proceed.
    Prints rejection reason if blocked.
    """
    result = validate_price(ticker, price, entry_price)
    if not result["valid"]:
        print(f"  🚫 PRICE SANITY REJECTED: {action} {ticker} @ ${price} — {result['reason']}")
        return False
    return True


if __name__ == "__main__":
    # Self-test
    tests = [
        ("BTC-USD", 72000, 67000, True),
        ("BTC-USD", 32.27, 67000, False),   # The Vex bug
        ("ETH-USD", 20.20, 1973, False),     # The Vex bug
        ("ETH-USD", 2100, 1973, True),
        ("APT-USD", 0.0, 5.50, False),       # CoinGecko $0
        ("SOL-USD", 92.0, 84.7, True),
        ("BTC", 32.0, 72000, False),         # Bare ticker bug
        ("SQQQ", 72.87, 72.30, True),
    ]
    passed = 0
    for ticker, price, entry, expected in tests:
        result = validate_price(ticker, price, entry)
        ok = result["valid"] == expected
        passed += ok
        status = "✅" if ok else "❌"
        print(f"  {status} {ticker} @ ${price} (entry ${entry}): valid={result['valid']} — {result['reason']}")
    print(f"\n{passed}/{len(tests)} tests passed")
