#!/usr/bin/env python3
"""
Fleet-Wide Value at Risk (VaR) for Crypto.

Calculates portfolio VaR across all 4 bots using historical volatility method.
"If the worst 5% scenario hits right now, how much do we lose?"

If fleet VaR > $5K (5% of $100K capital), we're overleveraged.

Usage:
  from crypto_fleet_var import FleetVaR
  fv = FleetVaR()
  var = fv.calculate()
  fv.check_limit()  # Returns True if within limits
"""

import json
import math
import os
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if not SUPABASE_KEY:
    key_path = os.path.expanduser("~/.supabase_service_key")
    if os.path.exists(key_path):
        SUPABASE_KEY = open(key_path).read().strip()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOTS = ["alfred", "tars", "vex", "eddie_v"]
FLEET_CAPITAL = 100_000.0
VAR_LIMIT_PCT = 5.0  # 5% of fleet capital
VAR_LIMIT_DOLLARS = FLEET_CAPITAL * (VAR_LIMIT_PCT / 100)
CONFIDENCE = 1.645  # 95% confidence (1-tail normal)

# Historical daily volatilities for crypto assets (annualized → daily)
# Updated periodically from actual data
DAILY_VOL = {
    "BTC": 0.035,   # ~3.5% daily vol
    "ETH": 0.045,   # ~4.5%
    "SOL": 0.065,   # ~6.5%
    "AVAX": 0.060,
    "ADA": 0.055,
    "DOT": 0.055,
    "LINK": 0.055,
    "DOGE": 0.070,
    "SHIB": 0.080,
    "PEPE": 0.090,
    "BONK": 0.085,
    "UNI": 0.055,
    "AAVE": 0.055,
    "MKR": 0.050,
    "XRP": 0.050,
    "DEFAULT": 0.060,
}

# Correlation assumptions (simplified)
AVG_CRYPTO_CORRELATION = 0.65  # Crypto assets are highly correlated


def get_all_positions() -> list:
    """Fetch all open positions across fleet."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/crypto_positions",
            params={"status": "eq.OPEN", "select": "*"},
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_crypto_prices() -> dict:
    """Fetch current prices."""
    try:
        ids = "bitcoin,ethereum,solana,avalanche-2,cardano,polkadot,chainlink,dogecoin,shiba-inu,uniswap,aave,maker"
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd",
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            mapping = {
                "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
                "avalanche-2": "AVAX", "cardano": "ADA", "polkadot": "DOT",
                "chainlink": "LINK", "dogecoin": "DOGE", "shiba-inu": "SHIB",
                "uniswap": "UNI", "aave": "AAVE", "maker": "MKR",
            }
            return {mapping[k]: v["usd"] for k, v in data.items() if k in mapping}
    except Exception:
        pass
    return {}


class FleetVaR:
    def __init__(self):
        self.positions = get_all_positions()
        self.prices = get_crypto_prices()

    def calculate(self) -> dict:
        """Calculate fleet-wide VaR."""
        position_vars = []
        total_notional = 0.0

        for pos in self.positions:
            ticker = pos.get("ticker", "").upper().replace("USDT", "").replace("USD", "")
            qty = float(pos.get("quantity", 0))
            price = self.prices.get(ticker, 0)
            notional = qty * price
            total_notional += notional

            vol = DAILY_VOL.get(ticker, DAILY_VOL["DEFAULT"])
            individual_var = notional * vol * CONFIDENCE
            position_vars.append({
                "bot": pos.get("bot_id"),
                "ticker": ticker,
                "notional": round(notional, 2),
                "vol": vol,
                "individual_var": round(individual_var, 2),
            })

        # Portfolio VaR with correlation adjustment
        # Simplified: VaR_portfolio = sqrt(sum(VaR_i^2) + 2*rho*sum(VaR_i*VaR_j))
        sum_var_sq = sum(p["individual_var"] ** 2 for p in position_vars)
        cross_term = 0.0
        for i, p1 in enumerate(position_vars):
            for p2 in position_vars[i + 1:]:
                cross_term += 2 * AVG_CRYPTO_CORRELATION * p1["individual_var"] * p2["individual_var"]

        portfolio_var = math.sqrt(sum_var_sq + cross_term) if (sum_var_sq + cross_term) > 0 else 0

        return {
            "portfolio_var_95": round(portfolio_var, 2),
            "var_limit": VAR_LIMIT_DOLLARS,
            "var_pct_of_capital": round((portfolio_var / FLEET_CAPITAL) * 100, 2),
            "within_limit": portfolio_var <= VAR_LIMIT_DOLLARS,
            "total_notional": round(total_notional, 2),
            "position_count": len(position_vars),
            "positions": position_vars,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def check_limit(self) -> bool:
        result = self.calculate()
        return result["within_limit"]


if __name__ == "__main__":
    fv = FleetVaR()
    result = fv.calculate()
    status = "✅ WITHIN LIMITS" if result["within_limit"] else "🚨 VAR EXCEEDED"
    print(f"{status}: ${result['portfolio_var_95']:,.2f} VaR (limit: ${result['var_limit']:,.2f})")
    print(json.dumps(result, indent=2))
