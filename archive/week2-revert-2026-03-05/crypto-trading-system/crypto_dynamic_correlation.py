#!/usr/bin/env python3
"""
Dynamic Correlation Regime for Crypto.

Replaces static correlation groups with rolling 24h calculated correlations.
During panic, ALL crypto correlates to 1.0 — what looks like diversification
is actually concentrated exposure.

Dynamically adjusts correlation groups based on actual price behavior.

Usage:
  from crypto_dynamic_correlation import DynamicCorrelation
  dc = DynamicCorrelation()
  groups = dc.get_current_groups()  # Dynamic groups based on rolling correlation
  is_safe = dc.check_diversification(positions)  # True if actually diversified
"""

import json
import os
import math
import requests
from datetime import datetime, timezone
from collections import defaultdict

CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "correlation_cache.json")
CORRELATION_THRESHOLD = 0.80  # Assets with corr > 0.80 are in same group
MAX_GROUP_PCT = 30.0  # Max fleet exposure per correlated group
FLEET_CAPITAL = 100_000.0

TRACKED_COINS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
    "avalanche-2": "AVAX", "cardano": "ADA", "polkadot": "DOT",
    "chainlink": "LINK", "dogecoin": "DOGE",
}


class DynamicCorrelation:
    def __init__(self):
        self.prices = self._load_cache()

    def _load_cache(self) -> dict:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self, data: dict):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def fetch_price_history(self, days: int = 7) -> dict:
        """Fetch daily price data for correlation calculation."""
        result = {}
        for cg_id, ticker in TRACKED_COINS.items():
            try:
                r = requests.get(
                    f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart",
                    params={"vs_currency": "usd", "days": days, "interval": "daily"},
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    prices = [p[1] for p in data.get("prices", [])]
                    if len(prices) > 1:
                        # Calculate daily returns
                        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
                        result[ticker] = returns
            except Exception:
                continue

        self._save_cache({"prices": result, "updated_at": datetime.now(timezone.utc).isoformat()})
        return result

    def calculate_correlations(self, returns: dict = None) -> dict:
        """Calculate pairwise correlations from returns."""
        if returns is None:
            returns = self.fetch_price_history()

        tickers = list(returns.keys())
        correlations = {}

        for i, t1 in enumerate(tickers):
            for t2 in tickers[i+1:]:
                r1 = returns[t1]
                r2 = returns[t2]
                min_len = min(len(r1), len(r2))
                if min_len < 3:
                    continue
                r1 = r1[:min_len]
                r2 = r2[:min_len]

                # Pearson correlation
                mean1 = sum(r1) / len(r1)
                mean2 = sum(r2) / len(r2)
                cov = sum((a - mean1) * (b - mean2) for a, b in zip(r1, r2)) / len(r1)
                std1 = math.sqrt(sum((x - mean1) ** 2 for x in r1) / len(r1))
                std2 = math.sqrt(sum((x - mean2) ** 2 for x in r2) / len(r2))

                if std1 > 0 and std2 > 0:
                    corr = cov / (std1 * std2)
                    correlations[f"{t1}-{t2}"] = round(corr, 3)

        return correlations

    def get_current_groups(self) -> dict:
        """Build dynamic correlation groups based on rolling data."""
        returns = self.fetch_price_history()
        correlations = self.calculate_correlations(returns)

        # Union-Find to cluster correlated assets
        parent = {}
        tickers = set()
        for pair in correlations:
            t1, t2 = pair.split("-")
            tickers.add(t1)
            tickers.add(t2)

        for t in tickers:
            parent[t] = t

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for pair, corr in correlations.items():
            if corr >= CORRELATION_THRESHOLD:
                t1, t2 = pair.split("-")
                union(t1, t2)

        groups = defaultdict(list)
        for t in tickers:
            groups[find(t)].append(t)

        # Name groups by largest member
        named_groups = {}
        for root, members in groups.items():
            name = f"cluster_{root.lower()}"
            named_groups[name] = sorted(members)

        return {
            "groups": named_groups,
            "correlations": correlations,
            "threshold": CORRELATION_THRESHOLD,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_diversification(self, positions: list) -> dict:
        """Check if fleet positions are actually diversified using dynamic groups."""
        groups_data = self.get_current_groups()
        groups = groups_data["groups"]

        # Calculate exposure per group
        group_exposure = defaultdict(float)
        for pos in positions:
            ticker = pos.get("ticker", "").upper()
            notional = float(pos.get("notional", 0))
            for group_name, members in groups.items():
                if ticker in members:
                    group_exposure[group_name] += notional
                    break

        violations = []
        for group_name, exposure in group_exposure.items():
            pct = (exposure / FLEET_CAPITAL) * 100
            if pct > MAX_GROUP_PCT:
                violations.append({
                    "group": group_name,
                    "members": groups[group_name],
                    "exposure_pct": round(pct, 1),
                    "limit": MAX_GROUP_PCT,
                    "excess": round(pct - MAX_GROUP_PCT, 1),
                })

        return {
            "diversified": len(violations) == 0,
            "violations": violations,
            "group_exposures": {k: round((v / FLEET_CAPITAL) * 100, 1) for k, v in group_exposure.items()},
        }


if __name__ == "__main__":
    dc = DynamicCorrelation()
    groups = dc.get_current_groups()
    print("Dynamic Correlation Groups:")
    print(json.dumps(groups, indent=2))
