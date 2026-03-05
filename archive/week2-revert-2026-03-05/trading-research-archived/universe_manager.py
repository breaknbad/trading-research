"""
universe_manager.py - Tradeable universe definition and management.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID

# Sector mapping: ticker → sector
UNIVERSE = {
    # Technology
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "GOOG": "Technology",
    "META": "Technology", "NVDA": "Technology", "AVGO": "Technology", "ADBE": "Technology",
    "CRM": "Technology", "CSCO": "Technology", "ORCL": "Technology", "ACN": "Technology",
    "TXN": "Technology", "QCOM": "Technology", "INTC": "Technology", "AMD": "Technology",
    "AMAT": "Technology", "NOW": "Technology", "INTU": "Technology", "IBM": "Technology",
    "MU": "Technology", "LRCX": "Technology", "ADI": "Technology", "KLAC": "Technology",
    "SNPS": "Technology", "CDNS": "Technology", "MRVL": "Technology", "MSI": "Technology",
    "FTNT": "Technology", "PANW": "Technology", "CRWD": "Technology", "PLTR": "Technology",
    "DELL": "Technology", "HPQ": "Technology", "HPE": "Technology", "MCHP": "Technology",
    "ON": "Technology", "NXPI": "Technology", "SWKS": "Technology", "KEYS": "Technology",

    # Healthcare
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare", "ABBV": "Healthcare",
    "MRK": "Healthcare", "PFE": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "DHR": "Healthcare", "AMGN": "Healthcare", "BMY": "Healthcare", "MDT": "Healthcare",
    "GILD": "Healthcare", "ISRG": "Healthcare", "VRTX": "Healthcare", "SYK": "Healthcare",
    "BSX": "Healthcare", "REGN": "Healthcare", "ZTS": "Healthcare", "BDX": "Healthcare",
    "EW": "Healthcare", "HCA": "Healthcare", "CI": "Healthcare", "ELV": "Healthcare",
    "IDXX": "Healthcare", "DXCM": "Healthcare", "IQV": "Healthcare", "MOH": "Healthcare",

    # Financials
    "JPM": "Financials", "V": "Financials", "MA": "Financials", "BAC": "Financials",
    "WFC": "Financials", "GS": "Financials", "MS": "Financials", "BLK": "Financials",
    "SCHW": "Financials", "C": "Financials", "AXP": "Financials", "USB": "Financials",
    "PNC": "Financials", "TFC": "Financials", "CME": "Financials", "ICE": "Financials",
    "CB": "Financials", "MMC": "Financials", "AON": "Financials", "SPGI": "Financials",
    "MCO": "Financials", "MET": "Financials", "AIG": "Financials", "PRU": "Financials",
    "PYPL": "Financials", "FIS": "Financials", "FISV": "Financials", "COF": "Financials",

    # Consumer Discretionary
    "AMZN": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "HD": "Consumer Discretionary",
    "MCD": "Consumer Discretionary", "NKE": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "TJX": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    "CMG": "Consumer Discretionary", "MAR": "Consumer Discretionary", "HLT": "Consumer Discretionary",
    "ORLY": "Consumer Discretionary", "AZO": "Consumer Discretionary", "ROST": "Consumer Discretionary",
    "DHI": "Consumer Discretionary", "LEN": "Consumer Discretionary", "GM": "Consumer Discretionary",
    "F": "Consumer Discretionary", "ABNB": "Consumer Discretionary", "YUM": "Consumer Discretionary",
    "DPZ": "Consumer Discretionary", "LULU": "Consumer Discretionary", "DECK": "Consumer Discretionary",

    # Consumer Staples
    "PG": "Consumer Staples", "KO": "Consumer Staples", "PEP": "Consumer Staples",
    "COST": "Consumer Staples", "WMT": "Consumer Staples", "PM": "Consumer Staples",
    "MO": "Consumer Staples", "MDLZ": "Consumer Staples", "CL": "Consumer Staples",
    "KMB": "Consumer Staples", "GIS": "Consumer Staples", "SYY": "Consumer Staples",
    "HSY": "Consumer Staples", "STZ": "Consumer Staples", "KHC": "Consumer Staples",
    "KR": "Consumer Staples", "TGT": "Consumer Staples", "DG": "Consumer Staples",
    "DLTR": "Consumer Staples", "EL": "Consumer Staples",

    # Industrials
    "CAT": "Industrials", "DE": "Industrials", "UNP": "Industrials", "HON": "Industrials",
    "UPS": "Industrials", "RTX": "Industrials", "BA": "Industrials", "LMT": "Industrials",
    "GE": "Industrials", "MMM": "Industrials", "GD": "Industrials", "NOC": "Industrials",
    "WM": "Industrials", "RSG": "Industrials", "EMR": "Industrials", "ITW": "Industrials",
    "ETN": "Industrials", "PH": "Industrials", "CTAS": "Industrials", "FAST": "Industrials",
    "CARR": "Industrials", "OTIS": "Industrials", "FDX": "Industrials", "CSX": "Industrials",
    "NSC": "Industrials", "PCAR": "Industrials", "IR": "Industrials", "TT": "Industrials",

    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy",
    "EOG": "Energy", "MPC": "Energy", "PSX": "Energy", "VLO": "Energy",
    "OXY": "Energy", "PXD": "Energy", "DVN": "Energy", "HAL": "Energy",
    "WMB": "Energy", "KMI": "Energy", "OKE": "Energy", "FANG": "Energy",

    # Communication Services
    "NFLX": "Communication Services", "DIS": "Communication Services", "CMCSA": "Communication Services",
    "T": "Communication Services", "VZ": "Communication Services", "TMUS": "Communication Services",
    "CHTR": "Communication Services", "EA": "Communication Services", "TTWO": "Communication Services",
    "MTCH": "Communication Services", "WBD": "Communication Services", "PARA": "Communication Services",
    "OMC": "Communication Services", "IPG": "Communication Services",

    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities", "D": "Utilities",
    "AEP": "Utilities", "SRE": "Utilities", "EXC": "Utilities", "XEL": "Utilities",
    "ED": "Utilities", "WEC": "Utilities", "ES": "Utilities", "AWK": "Utilities",

    # Real Estate
    "PLD": "Real Estate", "AMT": "Real Estate", "CCI": "Real Estate", "EQIX": "Real Estate",
    "PSA": "Real Estate", "O": "Real Estate", "SPG": "Real Estate", "WELL": "Real Estate",
    "DLR": "Real Estate", "AVB": "Real Estate", "EQR": "Real Estate", "VICI": "Real Estate",

    # Materials
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials", "ECL": "Materials",
    "NEM": "Materials", "FCX": "Materials", "NUE": "Materials", "DOW": "Materials",
    "DD": "Materials", "PPG": "Materials", "VMC": "Materials", "MLM": "Materials",
}


def get_universe():
    """Return sorted list of all tickers in the tradeable universe."""
    return sorted(UNIVERSE.keys())


def is_tradeable(ticker):
    """
    Check if a ticker is in the tradeable universe.
    Returns: {tradeable: bool, reason: str, sector: str|None}
    """
    t = ticker.upper().strip()
    if t in UNIVERSE:
        return {"tradeable": True, "reason": "In universe", "sector": UNIVERSE[t]}
    return {"tradeable": False, "reason": "Not in tradeable universe (may be OTC, too small, or unlisted)", "sector": None}


def get_sector(ticker):
    """Return sector for a ticker, or None."""
    return UNIVERSE.get(ticker.upper().strip())


def get_by_sector(sector):
    """Return all tickers in a given sector."""
    return sorted([t for t, s in UNIVERSE.items() if s == sector])


def get_sectors():
    """Return dict of sector → ticker count."""
    sectors = {}
    for s in UNIVERSE.values():
        sectors[s] = sectors.get(s, 0) + 1
    return sectors


def refresh_universe():
    """Placeholder for future API-based universe refresh."""
    # TODO: Pull from Finnhub or other screener API
    # Filter: market cap > $500M, US-listed, not OTC
    return {"status": "not_implemented", "message": "Future: will refresh from API screener"}


if __name__ == "__main__":
    tickers = get_universe()
    print(f"Universe: {len(tickers)} tickers")
    print(json.dumps(get_sectors(), indent=2))
    print(json.dumps(is_tradeable("AAPL"), indent=2))
    print(json.dumps(is_tradeable("PENNY"), indent=2))
