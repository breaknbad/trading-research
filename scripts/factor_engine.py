#!/usr/bin/env python3
"""
Factor Engine v2 — Gradient-scored, 6-category pre-trade validation

Categories & weights:
  Trend 15% | Momentum 20% | Volume 25% | Volatility 10% | Risk 20% | Macro 10%

All factors score 0.0–1.0 (gradient, never binary).

Usage:
    python3 factor_engine.py --ticker NVDA --side long --market-state /path/to/market-state.json
    python3 factor_engine.py --ticker BTC-USD --side short --market-state /path/to/market-state.json --macro-state /path/to/macro.json

Exit codes: 0=GO (≥65), 1=REJECT (<50), 2=CAUTION (50-64), 3=Error
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def linear_scale(value, low, high, invert=False):
    """Scale value linearly between low (0.0) and high (1.0). Invert flips."""
    if high == low:
        return 0.5
    score = clamp((value - low) / (high - low))
    return 1.0 - score if invert else score


class FactorEngineV2:
    """Pre-trade factor validation engine v2 — gradient scoring."""

    CATEGORY_WEIGHTS = {
        'trend': 0.15,
        'momentum': 0.20,
        'volume': 0.25,
        'volatility': 0.10,
        'risk': 0.20,
        'macro': 0.10,
    }

    GO_THRESHOLD = 65
    CAUTION_THRESHOLD = 50
    
    # Sizing tiers (factor engine = sizer, not gate)
    # Score <20 = REJECT (garbage data protection only)
    # Score 20-40 = SCOUT max (2% of book)
    # Score 40-60 = CONFIRM (8% of book)
    # Score 60+ = CONVICTION (15%+ of book)
    SIZING_TIERS = {
        "REJECT": 20,      # below this = reject (garbage protection)
        "SCOUT": 40,       # 20-40 = SCOUT
        "CONFIRM": 60,     # 40-60 = CONFIRM
        "CONVICTION": 100, # 60+ = CONVICTION
    }

    def __init__(self, ticker: str, side: str, market_state_path: str, macro_state_path: str = None):
        self.ticker = ticker.upper()
        self.side = side.lower()
        self.market_state_path = market_state_path
        self.macro_state_path = macro_state_path
        self.market_data = None
        self.macro_data = {}

    # ── Data loading ──────────────────────────────────────────────

    def load_market_state(self) -> bool:
        try:
            if not os.path.exists(self.market_state_path):
                print(json.dumps({"error": f"Market state not found: {self.market_state_path}", "exit_code": 3}), file=sys.stderr)
                return False

            file_age = time.time() - os.path.getmtime(self.market_state_path)
            if file_age > 120:
                print(json.dumps({"error": f"Market state stale ({file_age:.0f}s, max 120s)", "exit_code": 3}), file=sys.stderr)
                return False

            with open(self.market_state_path, 'r') as f:
                raw = json.load(f)

            if 'tickers' in raw and isinstance(raw['tickers'], dict):
                lookup = self.ticker.replace('-USD', '').upper()
                if lookup not in raw['tickers']:
                    print(json.dumps({"error": f"Ticker '{lookup}' not in market-state. Available: {list(raw['tickers'].keys())}", "exit_code": 3}), file=sys.stderr)
                    return False
                td = raw['tickers'][lookup]
                tech = td.get('technicals', {})
                self.market_data = {
                    'price': td.get('price', 0),
                    'rsi': tech.get('rsi', 50),
                    'ema9': tech.get('ema9', td.get('price', 0)),
                    'ema21': tech.get('ema21', td.get('price', 0)),
                    'ma50': tech.get('ma50'),
                    'macd': tech.get('macd', 0),
                    'macd_signal': tech.get('macd_signal') or 0,
                    'macd_histogram': tech.get('macd_histogram') or 0,
                    'volume': td.get('volume_24h', 0),
                    'volume_20d_avg': td.get('volume_20d_avg'),
                    'change_24h_pct': td.get('change_24h_pct', 0),
                    'atr': tech.get('atr'),
                    'ema_cross': tech.get('ema_cross'),
                    'vwap': tech.get('vwap'),
                    'funding_rate': td.get('funding_rate'),
                    'btc_correlation': td.get('btc_correlation'),
                }
                if self.market_data['atr'] is None:
                    self.market_data['atr'] = td.get('price', 0) * max(abs(td.get('change_24h_pct', 2.0)), 0.5) / 100 * 1.5
            else:
                self.market_data = raw

            for f in ['price', 'rsi', 'ema9', 'ema21', 'volume']:
                if f not in self.market_data or self.market_data[f] is None:
                    print(json.dumps({"error": f"Missing field: {f}", "exit_code": 3}), file=sys.stderr)
                    return False

            if self.market_data.get('atr') is None:
                self.market_data['atr'] = self.market_data['price'] * 0.02

            return True
        except Exception as e:
            print(json.dumps({"error": str(e), "exit_code": 3}), file=sys.stderr)
            return False

    def load_macro_state(self):
        """Load optional macro state (DXY, VIX, etc.)."""
        if not self.macro_state_path or not os.path.exists(self.macro_state_path):
            return
        try:
            with open(self.macro_state_path, 'r') as f:
                self.macro_data = json.load(f)
        except Exception:
            pass

    # ── Factor categories ─────────────────────────────────────────

    def evaluate_trend(self) -> Dict[str, float]:
        d = self.market_data
        price, ema9, ema21 = d['price'], d['ema9'], d['ema21']
        factors = {}

        # EMA alignment — gradient based on spread %
        if ema21 > 0:
            spread_pct = ((ema9 - ema21) / ema21) * 100
            if self.side == 'short':
                spread_pct = -spread_pct
            factors['ema_alignment'] = clamp(linear_scale(spread_pct, -2.0, 2.0))

        # Price vs EMA9 — distance matters
        if ema9 > 0:
            dist_pct = ((price - ema9) / ema9) * 100
            if self.side == 'short':
                dist_pct = -dist_pct
            factors['price_vs_ema'] = clamp(linear_scale(dist_pct, -1.5, 1.5))

        # MACD histogram strength
        macd_hist = d.get('macd_histogram', 0)
        price_norm = abs(macd_hist) / (price * 0.01) if price > 0 else 0  # normalize to 1% of price
        score = clamp(linear_scale(price_norm, 0, 1.0))
        if self.side == 'short':
            factors['macd_direction'] = score if macd_hist < 0 else 1.0 - score
        else:
            factors['macd_direction'] = score if macd_hist > 0 else 1.0 - score

        # Price vs MA50
        ma50 = d.get('ma50', price)
        if ma50 and ma50 > 0:
            dist50 = ((price - ma50) / ma50) * 100
            if self.side == 'short':
                dist50 = -dist50
            factors['price_vs_ma50'] = clamp(linear_scale(dist50, -5.0, 5.0))

        return factors

    def evaluate_momentum(self) -> Dict[str, float]:
        d = self.market_data
        factors = {}
        rsi = d['rsi']

        # RSI — gradient scoring
        if self.side == 'long':
            # Best zone: 35-55 (recovering from oversold). Bad: >75 overbought
            if rsi <= 30:
                factors['rsi_level'] = 0.75  # oversold, bounce likely but risky
            elif rsi <= 55:
                factors['rsi_level'] = clamp(linear_scale(rsi, 20, 55))
            elif rsi <= 70:
                factors['rsi_level'] = clamp(linear_scale(rsi, 70, 55))  # declining
            else:
                factors['rsi_level'] = clamp(linear_scale(rsi, 85, 70))  # overbought penalty
        else:
            if rsi >= 70:
                factors['rsi_level'] = 0.9
            elif rsi >= 50:
                factors['rsi_level'] = clamp(linear_scale(rsi, 45, 70))
            elif rsi >= 30:
                factors['rsi_level'] = clamp(linear_scale(rsi, 30, 45))
            else:
                factors['rsi_level'] = 0.1

        # MACD crossover strength
        macd = d.get('macd', 0)
        macd_sig = d.get('macd_signal', 0)
        diff = macd - macd_sig
        if self.side == 'short':
            diff = -diff
        price = d['price']
        norm_diff = diff / (price * 0.005) if price > 0 else 0
        factors['macd_crossover'] = clamp(linear_scale(norm_diff, -1.0, 1.0))

        # 24h change momentum
        change = d.get('change_24h_pct', 0)
        if self.side == 'short':
            change = -change
        factors['price_momentum'] = clamp(linear_scale(change, -3.0, 3.0))

        return factors

    def evaluate_volume(self) -> Dict[str, float]:
        d = self.market_data
        factors = {}

        vol = d.get('volume', 0)
        avg_vol = d.get('volume_20d_avg', vol)
        if avg_vol and avg_vol > 0:
            ratio = vol / avg_vol
            factors['volume_ratio'] = clamp(linear_scale(ratio, 0.5, 2.0))
        else:
            factors['volume_ratio'] = 0.5

        # VWAP position (if available)
        vwap = d.get('vwap')
        price = d['price']
        if vwap and vwap > 0:
            vwap_dist = ((price - vwap) / vwap) * 100
            if self.side == 'short':
                vwap_dist = -vwap_dist
            factors['vwap_position'] = clamp(linear_scale(vwap_dist, -1.0, 1.0))

        return factors

    def evaluate_volatility(self) -> Dict[str, float]:
        d = self.market_data
        factors = {}

        atr = d['atr']
        price = d['price']
        atr_pct = (atr / price) * 100 if price > 0 else 2.0

        # Sweet spot 1-4%, penalty outside
        if atr_pct <= 0.5:
            factors['atr_level'] = 0.3
        elif atr_pct <= 1.0:
            factors['atr_level'] = clamp(linear_scale(atr_pct, 0.5, 1.5))
        elif atr_pct <= 4.0:
            factors['atr_level'] = 1.0
        elif atr_pct <= 8.0:
            factors['atr_level'] = clamp(linear_scale(atr_pct, 8.0, 4.0))
        else:
            factors['atr_level'] = 0.2

        return factors

    def evaluate_risk(self) -> Dict[str, float]:
        d = self.market_data
        factors = {}

        # Position correlation (from portfolio data if available)
        corr = d.get('position_correlation', 0.0)
        factors['position_correlation'] = clamp(1.0 - abs(corr))

        # Sector concentration
        conc = d.get('sector_concentration', 0.3)
        factors['sector_concentration'] = clamp(1.0 - conc)

        # Heat cap headroom
        heat = d.get('heat_cap_usage', 0.5)
        factors['heat_cap_headroom'] = clamp(1.0 - heat)

        # BTC correlation (crypto-specific risk)
        btc_corr = d.get('btc_correlation')
        if btc_corr is not None:
            # High BTC correlation = more systematic risk = lower score
            factors['btc_correlation_risk'] = clamp(1.0 - abs(btc_corr))

        return factors

    def evaluate_macro(self) -> Dict[str, float]:
        """NEW: Macro factors — DXY, VIX, funding rates, time-of-day."""
        factors = {}
        m = self.macro_data
        d = self.market_data

        # DXY direction (from macro state)
        dxy_change = m.get('dxy_change_pct', 0)
        if dxy_change != 0:
            # Rising DXY = bearish risk assets, bullish USD-denominated shorts
            if self.side == 'long':
                factors['dxy_direction'] = clamp(linear_scale(-dxy_change, -1.0, 1.0))
            else:
                factors['dxy_direction'] = clamp(linear_scale(dxy_change, -1.0, 1.0))

        # VIX regime
        vix = m.get('vix', 20)
        if vix:
            # Low VIX (<15) = complacent (good for longs), High VIX (>25) = fear (good for shorts/hedges)
            if self.side == 'long':
                factors['vix_regime'] = clamp(linear_scale(vix, 35, 12))  # lower VIX = higher score
            else:
                factors['vix_regime'] = clamp(linear_scale(vix, 12, 35))  # higher VIX = higher score for shorts

        # Crypto funding rate (from market data or macro)
        funding = d.get('funding_rate') or m.get('funding_rate')
        if funding is not None:
            # Positive funding = longs pay shorts (crowded long). Negative = shorts pay (crowded short / squeeze setup)
            if self.side == 'long':
                # Negative funding = good for long (shorts getting squeezed)
                factors['funding_rate'] = clamp(linear_scale(-funding * 10000, -5, 5))  # scale bps
            else:
                factors['funding_rate'] = clamp(linear_scale(funding * 10000, -5, 5))

        # Time of day factor
        try:
            now_utc = datetime.now(timezone.utc)
            et = now_utc.astimezone(timezone(timedelta(hours=-5)))
            hour = et.hour + et.minute / 60.0
            # Best trading: 9:30-11:00 (open) and 15:00-16:00 (close). Worst: 12-14 (lunch)
            if 9.5 <= hour <= 11.0 or 15.0 <= hour <= 16.0:
                factors['time_of_day'] = 0.9
            elif 11.0 < hour < 12.0 or 14.0 <= hour < 15.0:
                factors['time_of_day'] = 0.6
            elif 12.0 <= hour < 14.0:
                factors['time_of_day'] = 0.3  # lunch = low liquidity
            else:
                factors['time_of_day'] = 0.5  # pre/post market or crypto hours
        except Exception:
            factors['time_of_day'] = 0.5

        # If no macro data at all, return neutral
        if not factors:
            factors['no_macro_data'] = 0.5

        return factors

    # ── Scoring ───────────────────────────────────────────────────

    def calculate_total_score(self, all_factors: Dict[str, Dict[str, float]]) -> Tuple[float, Dict[str, float]]:
        category_scores = {}
        for category, factors in all_factors.items():
            if factors:
                category_scores[category] = sum(factors.values()) / len(factors)
            else:
                category_scores[category] = 0.5  # neutral if empty
        total = sum(score * self.CATEGORY_WEIGHTS[cat] for cat, score in category_scores.items()) * 100
        return total, category_scores

    def get_recommendation(self, score: float) -> Tuple[str, int]:
        # Sizer mode: never block above 20. Size the position instead.
        if score < self.SIZING_TIERS["REJECT"]:
            return "REJECT", 1        # garbage protection only
        elif score < self.SIZING_TIERS["SCOUT"]:
            return "SCOUT", 0         # 2% max position
        elif score < self.SIZING_TIERS["CONFIRM"]:
            return "CONFIRM", 0       # 8% max position
        else:
            return "CONVICTION", 0    # 15%+ position

    def evaluate(self) -> Dict[str, Any]:
        if not self.load_market_state():
            sys.exit(3)
        self.load_macro_state()

        all_factors = {
            'trend': self.evaluate_trend(),
            'momentum': self.evaluate_momentum(),
            'volume': self.evaluate_volume(),
            'volatility': self.evaluate_volatility(),
            'risk': self.evaluate_risk(),
            'macro': self.evaluate_macro(),
        }

        total_score, category_scores = self.calculate_total_score(all_factors)
        recommendation, exit_code = self.get_recommendation(total_score)

        reasoning_parts = []
        for cat, score in category_scores.items():
            w = self.CATEGORY_WEIGHTS[cat]
            reasoning_parts.append(f"{cat.title()}: {score:.2f} ({w:.0%}) = {score*w*100:.1f}pts")

        # Determine max position size
        size_map = {"REJECT": 0, "SCOUT": 0.02, "CONFIRM": 0.08, "CONVICTION": 0.15}
        max_position_pct = size_map.get(recommendation, 0.02)

        return {
            "ticker": self.ticker,
            "side": self.side,
            "total_score": round(total_score, 1),
            "recommendation": recommendation,
            "max_position_pct": max_position_pct,
            "exit_code": exit_code,
            "version": "2.1",
            "category_scores": {k: round(v, 3) for k, v in category_scores.items()},
            "factor_details": {k: {fk: round(fv, 3) for fk, fv in fvs.items()} for k, fvs in all_factors.items()},
            "reasoning": " | ".join(reasoning_parts),
        }


def main():
    parser = argparse.ArgumentParser(description='Factor Engine v2 — gradient-scored pre-trade validation')
    parser.add_argument('--ticker', required=True)
    parser.add_argument('--side', required=True, choices=['long', 'short'])
    parser.add_argument('--market-state', required=True)
    parser.add_argument('--macro-state', default=None, help='Optional macro state JSON (DXY, VIX, etc.)')

    args = parser.parse_args()

    try:
        engine = FactorEngineV2(args.ticker, args.side, args.market_state, args.macro_state)
        result = engine.evaluate()
        print(json.dumps(result, indent=2))
        sys.exit(result['exit_code'])
    except Exception as e:
        print(json.dumps({"error": str(e), "exit_code": 3}), file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()
