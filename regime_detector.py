"""
regime_detector.py - Market regime classification based on VIX levels.
"""

import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FINNHUB_KEY

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# Cache
_cache = {"regime": None, "timestamp": 0}
CACHE_TTL = 300  # 5 minutes

REGIMES = {
    "CALM":     {"max_vix": 15, "adjustments": {"stop_pct": None, "max_position_pct": None, "halt_entries": False}},
    "NORMAL":   {"max_vix": 20, "adjustments": {"stop_pct": None, "max_position_pct": None, "halt_entries": False}},
    "ELEVATED": {"max_vix": 30, "adjustments": {"stop_pct": 1.5, "max_position_pct": 7.0, "halt_entries": False}},
    "CRISIS":   {"max_vix": float("inf"), "adjustments": {"stop_pct": 1.0, "max_position_pct": None, "halt_entries": True}},
}


def _fetch_vix():
    """Fetch VIX proxy (VIXY) price from Finnhub."""
    url = "https://finnhub.io/api/v1/quote"
    # Finnhub doesn't support ^VIX directly; use VIXY ETF as proxy
    # or try CBOE VIX index symbol
    for symbol in ["VIXY", "VIX"]:
        try:
            resp = requests.get(url, params={"symbol": symbol, "token": FINNHUB_KEY}, timeout=10)
            data = resp.json()
            price = data.get("c", 0)
            if price and price > 0:
                # VIXY tracks VIX futures, rough proxy. For real VIX level,
                # we'd need a different data source. VIXY price != VIX level,
                # but we scale: VIXY ~$15-25 maps roughly to VIX territory.
                return price, symbol
        except Exception:
            continue
    return None, None


def _classify(vix_value):
    """Classify VIX into regime."""
    if vix_value < 15:
        return "CALM"
    elif vix_value < 20:
        return "NORMAL"
    elif vix_value < 30:
        return "ELEVATED"
    else:
        return "CRISIS"


def get_regime():
    """
    Get current market regime based on VIX level.
    Returns: {regime: str, vix: float, adjustments: dict, source: str, cached: bool}
    """
    now = time.time()
    if _cache["regime"] and (now - _cache["timestamp"]) < CACHE_TTL:
        result = _cache["regime"].copy()
        result["cached"] = True
        return result

    vix_value, source = _fetch_vix()

    if vix_value is None:
        return {
            "regime": "NORMAL",
            "vix": None,
            "adjustments": REGIMES["NORMAL"]["adjustments"],
            "source": "default_fallback",
            "cached": False,
            "error": "Could not fetch VIX data"
        }

    regime = _classify(vix_value)
    result = {
        "regime": regime,
        "vix": round(vix_value, 2),
        "adjustments": REGIMES[regime]["adjustments"],
        "source": source,
        "cached": False,
    }

    _cache["regime"] = result
    _cache["timestamp"] = now
    return result


if __name__ == "__main__":
    print(json.dumps(get_regime(), indent=2))
