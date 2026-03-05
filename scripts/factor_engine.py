#!/usr/bin/env python3
"""
Factor Engine - Pre-trade factor validation engine

Evaluates trading factors across multiple categories to generate a go/no-go recommendation
for trade execution. Analyzes trend, momentum, volume, volatility, and risk factors.

Usage:
    python3 factor_engine.py --ticker NVDA --side short --market-state /path/to/market-state.json

Exit codes:
    0: GO (score >= 65)
    1: REJECT (score < 50)
    2: CAUTION (score 50-64)
    3: Error (missing/stale market-state file)
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Tuple


class FactorEngine:
    """Pre-trade factor validation engine."""
    
    # Default weights (overridden by lane_config.json if present)
    DEFAULT_WEIGHTS = {
        'trend': 0.25,
        'momentum': 0.20,
        'volume': 0.15,
        'volatility': 0.10,
        'risk': 0.10,
        'sentiment': 0.10,
        'regime': 0.10
    }

    @staticmethod
    def load_lane_weights():
        """Load lane-specific factor weights from lane_config.json."""
        lane_path = os.path.join(os.path.dirname(__file__), "lane_config.json")
        try:
            with open(lane_path) as f:
                config = json.load(f)
            weights = config.get("factor_weights", {})

            # Check for SURGE override
            surge = config.get("surge_override", {})
            if surge.get("enabled"):
                vol_path = os.path.join(os.path.dirname(__file__), "..", "volume_state.json")
                try:
                    with open(vol_path) as vf:
                        vol = json.load(vf)
                    rvol = vol.get("rvol", 1.0)
                    if rvol >= surge.get("rvol_threshold", 2.0):
                        shift = surge.get("shift_amount", 0.15)
                        src = surge.get("shift_from", "sentiment")
                        dst = surge.get("shift_to", "momentum")
                        if src in weights and dst in weights:
                            weights[src] = max(0, weights[src] - shift)
                            weights[dst] = weights[dst] + shift
                except (FileNotFoundError, json.JSONDecodeError):
                    pass

            return weights
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    CATEGORY_WEIGHTS = load_lane_weights.__func__() or DEFAULT_WEIGHTS
    
    # Score thresholds
    GO_THRESHOLD = 65
    CAUTION_THRESHOLD = 50
    
    def __init__(self, ticker: str, side: str, market_state_path: str):
        self.ticker = ticker.upper()
        self.side = side.lower()
        self.market_state_path = market_state_path
        self.market_data = None
        
    def load_market_state(self) -> bool:
        """Load and validate market state file."""
        try:
            # Check if file exists
            if not os.path.exists(self.market_state_path):
                print(json.dumps({
                    "error": f"Market state file not found: {self.market_state_path}",
                    "exit_code": 3
                }), file=sys.stderr)
                return False
                
            # Check if file is stale (>120 seconds old)
            file_age = time.time() - os.path.getmtime(self.market_state_path)
            if file_age > 120:
                print(json.dumps({
                    "error": f"Market state file is stale ({file_age:.1f}s old, max 120s)",
                    "exit_code": 3
                }), file=sys.stderr)
                return False
                
            # Load market data
            with open(self.market_state_path, 'r') as f:
                self.market_data = json.load(f)
                
            # Validate required fields
            required_fields = ['price', 'rsi', 'ema9', 'ema21', 'macd', 'volume', 'atr']
            for field in required_fields:
                if field not in self.market_data:
                    print(json.dumps({
                        "error": f"Missing required field in market state: {field}",
                        "exit_code": 3
                    }), file=sys.stderr)
                    return False
                    
            return True
            
        except Exception as e:
            print(json.dumps({
                "error": f"Failed to load market state: {str(e)}",
                "exit_code": 3
            }), file=sys.stderr)
            return False
    
    def evaluate_trend_factors(self) -> Dict[str, float]:
        """Evaluate trend-based factors."""
        factors = {}
        
        # EMA9 vs EMA21 alignment
        ema9 = self.market_data['ema9']
        ema21 = self.market_data['ema21']
        price = self.market_data['price']
        
        if self.side == 'long':
            # For long: want EMA9 > EMA21 and price > EMA9
            ema_alignment = 1.0 if ema9 > ema21 else 0.0
            price_alignment = 1.0 if price > ema9 else 0.0
        else:  # short
            # For short: want EMA9 < EMA21 and price < EMA9
            ema_alignment = 1.0 if ema9 < ema21 else 0.0
            price_alignment = 1.0 if price < ema9 else 0.0
            
        factors['ema_alignment'] = ema_alignment
        factors['price_vs_ema'] = price_alignment
        
        # MACD histogram direction
        macd_hist = self.market_data.get('macd_histogram', 0)
        if self.side == 'long':
            factors['macd_direction'] = 1.0 if macd_hist > 0 else 0.0
        else:
            factors['macd_direction'] = 1.0 if macd_hist < 0 else 0.0
            
        # Price vs 50-day MA
        ma50 = self.market_data.get('ma50', price)  # Default to current price if missing
        if self.side == 'long':
            factors['price_vs_ma50'] = 1.0 if price > ma50 else 0.0
        else:
            factors['price_vs_ma50'] = 1.0 if price < ma50 else 0.0
            
        return factors
    
    def evaluate_momentum_factors(self) -> Dict[str, float]:
        """Evaluate momentum-based factors."""
        factors = {}
        
        rsi = self.market_data['rsi']
        
        # RSI overbought/oversold for side
        if self.side == 'long':
            # For long: prefer RSI not overbought (< 70), ideally oversold recovery (30-50)
            if rsi <= 30:
                factors['rsi_level'] = 0.8  # Oversold, good for long
            elif rsi <= 50:
                factors['rsi_level'] = 1.0  # Sweet spot for long
            elif rsi <= 70:
                factors['rsi_level'] = 0.6  # Neutral
            else:
                factors['rsi_level'] = 0.2  # Overbought, bad for long
        else:  # short
            # For short: prefer RSI overbought (> 70), avoid oversold
            if rsi >= 70:
                factors['rsi_level'] = 1.0  # Overbought, good for short
            elif rsi >= 50:
                factors['rsi_level'] = 0.8  # Elevated, decent for short
            elif rsi >= 30:
                factors['rsi_level'] = 0.4  # Neutral
            else:
                factors['rsi_level'] = 0.1  # Oversold, bad for short
                
        # MACD crossover recency (mock - would need historical data)
        macd = self.market_data.get('macd_line', 0)
        macd_signal = self.market_data.get('macd_signal', 0)
        
        if self.side == 'long':
            factors['macd_crossover'] = 1.0 if macd > macd_signal else 0.3
        else:
            factors['macd_crossover'] = 1.0 if macd < macd_signal else 0.3
            
        return factors
    
    def evaluate_volume_factors(self) -> Dict[str, float]:
        """Evaluate volume-based factors."""
        factors = {}
        
        volume = self.market_data['volume']
        avg_volume = self.market_data.get('volume_20d_avg', volume)  # Default to current if missing
        
        # Volume vs 20-day average ratio
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        if volume_ratio >= 1.5:
            factors['volume_ratio'] = 1.0  # High volume, good confirmation
        elif volume_ratio >= 1.2:
            factors['volume_ratio'] = 0.8  # Above average
        elif volume_ratio >= 0.8:
            factors['volume_ratio'] = 0.5  # Normal
        else:
            factors['volume_ratio'] = 0.2  # Low volume, weak signal
            
        # Volume trend (mock - would need historical data)
        volume_trend = self.market_data.get('volume_trend', 'neutral')
        if volume_trend == 'increasing':
            factors['volume_trend'] = 1.0
        elif volume_trend == 'neutral':
            factors['volume_trend'] = 0.5
        else:
            factors['volume_trend'] = 0.2
            
        return factors
    
    def evaluate_volatility_factors(self) -> Dict[str, float]:
        """Evaluate volatility-based factors."""
        factors = {}
        
        atr = self.market_data['atr']
        price = self.market_data['price']
        
        # ATR-based stop distance (as % of price)
        atr_percent = (atr / price) * 100 if price > 0 else 0
        
        # Prefer moderate volatility (1-4% ATR)
        if 1.0 <= atr_percent <= 4.0:
            factors['atr_level'] = 1.0  # Good volatility for trading
        elif 0.5 <= atr_percent < 1.0 or 4.0 < atr_percent <= 6.0:
            factors['atr_level'] = 0.7  # Acceptable
        else:
            factors['atr_level'] = 0.3  # Too low or too high volatility
            
        # Intraday range vs average (mock)
        intraday_range = self.market_data.get('intraday_range_pct', 2.0)
        avg_range = self.market_data.get('avg_intraday_range_pct', 2.0)
        
        range_ratio = intraday_range / avg_range if avg_range > 0 else 1.0
        if 0.8 <= range_ratio <= 1.5:
            factors['intraday_range'] = 1.0  # Normal range
        else:
            factors['intraday_range'] = 0.5  # Abnormal range
            
        return factors
    
    def evaluate_risk_factors(self) -> Dict[str, float]:
        """Evaluate risk management factors."""
        factors = {}
        
        # Existing position correlation (mock - would need portfolio data)
        position_correlation = self.market_data.get('position_correlation', 0.0)
        factors['position_correlation'] = max(0.0, 1.0 - abs(position_correlation))
        
        # Sector concentration (mock)
        sector_concentration = self.market_data.get('sector_concentration', 0.3)
        factors['sector_concentration'] = max(0.0, 1.0 - sector_concentration)
        
        # Heat cap headroom (mock)
        heat_cap_usage = self.market_data.get('heat_cap_usage', 0.5)
        factors['heat_cap_headroom'] = max(0.0, 1.0 - heat_cap_usage)
        
        return factors
    
    def calculate_total_score(self, all_factors: Dict[str, Dict[str, float]]) -> Tuple[float, Dict[str, float]]:
        """Calculate weighted total score across all categories."""
        category_scores = {}
        
        # Calculate average score for each category
        for category, factors in all_factors.items():
            if factors:
                category_scores[category] = sum(factors.values()) / len(factors)
            else:
                category_scores[category] = 0.0
                
        # Calculate weighted total score
        total_score = sum(
            score * self.CATEGORY_WEIGHTS[category] 
            for category, score in category_scores.items()
        ) * 100  # Convert to 0-100 scale
        
        return total_score, category_scores
    
    def get_recommendation(self, total_score: float) -> Tuple[str, int]:
        """Get recommendation and exit code based on total score."""
        if total_score >= self.GO_THRESHOLD:
            return "GO", 0
        elif total_score >= self.CAUTION_THRESHOLD:
            return "CAUTION", 2
        else:
            return "REJECT", 1
    
    def evaluate_sentiment_factors(self) -> Dict[str, float]:
        """Evaluate news sentiment and Fear & Greed factors."""
        factors = {}
        sentiment_path = os.path.join(os.path.dirname(__file__), "sentiment_state.json")
        try:
            with open(sentiment_path) as f:
                sentiment = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"fng_alignment": 0.5, "news_sentiment": 0.5}

        fng = sentiment.get("last_fng", 50)

        # F&G alignment with trade side
        if self.side == "long":
            # Contrarian: extreme fear = good for longs (bounce), extreme greed = risky
            if fng <= 15:
                factors["fng_alignment"] = 0.9  # Extreme fear = contrarian long
            elif fng <= 30:
                factors["fng_alignment"] = 0.7
            elif fng <= 50:
                factors["fng_alignment"] = 0.5
            elif fng <= 70:
                factors["fng_alignment"] = 0.4
            else:
                factors["fng_alignment"] = 0.2  # Extreme greed = risky long
        else:  # short
            if fng >= 80:
                factors["fng_alignment"] = 0.9  # Extreme greed = good for shorts
            elif fng >= 60:
                factors["fng_alignment"] = 0.7
            elif fng >= 40:
                factors["fng_alignment"] = 0.5
            elif fng >= 20:
                factors["fng_alignment"] = 0.4
            else:
                factors["fng_alignment"] = 0.2  # Extreme fear = risky short

        # News headline sentiment (placeholder — reads from sentiment_state)
        headlines = sentiment.get("last_headlines", [])
        if headlines:
            factors["news_sentiment"] = 0.6  # Neutral-positive when headlines exist
        else:
            factors["news_sentiment"] = 0.5

        return factors

    def evaluate_regime_factors(self) -> Dict[str, float]:
        """Evaluate volume regime (RVOL-based, replaces clock penalties)."""
        factors = {}
        volume_state_path = os.path.join(os.path.dirname(__file__), "..", "volume_state.json")
        try:
            with open(volume_state_path) as f:
                vol_state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"regime_alignment": 0.5, "rvol_strength": 0.5}

        # Read regime from TARS's volume_monitor output
        regime = vol_state.get("regime", "NORMAL")
        rvol = vol_state.get("rvol", 1.0)

        # Regime alignment — SURGE is best, DEAD blocks at pipeline level but still score low
        regime_scores = {"SURGE": 1.0, "NORMAL": 0.7, "FADING": 0.4, "DEAD": 0.1}
        factors["regime_alignment"] = regime_scores.get(regime, 0.5)

        # RVOL strength — higher is better for any trade direction
        if rvol >= 2.0:
            factors["rvol_strength"] = 1.0
        elif rvol >= 1.5:
            factors["rvol_strength"] = 0.8
        elif rvol >= 1.0:
            factors["rvol_strength"] = 0.6
        elif rvol >= 0.5:
            factors["rvol_strength"] = 0.3
        else:
            factors["rvol_strength"] = 0.1

        return factors

    def evaluate_catalyst_factors(self) -> Dict[str, float]:
        """Evaluate catalyst proximity (earnings, congressional, geopolitical)."""
        factors = {}
        score = 0.0

        # Check intel_signals.json for active signals on this ticker
        intel_path = os.path.join(os.path.dirname(__file__), "..", "intel_signals.json")
        try:
            with open(intel_path) as f:
                signals = json.load(f)
            for sig in signals:
                if sig.get("ticker", "").upper() == self.ticker:
                    sig_score = sig.get("score", 0)
                    # Side alignment bonus
                    if sig.get("side") == self.side:
                        score = max(score, min(1.0, sig_score / 10.0))
                    else:
                        score = max(score, min(0.3, sig_score / 30.0))  # Opposing signal = low
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Check alerts.json for geopolitical catalysts
        alerts_path = os.path.join(os.path.dirname(__file__), "..", "alerts.json")
        try:
            with open(alerts_path) as f:
                alerts = json.load(f)
            if isinstance(alerts, list) and len(alerts) > 0:
                high_alerts = [a for a in alerts if a.get("severity") in ("critical", "high")]
                if high_alerts:
                    score = max(score, 0.6)  # Active geopolitical catalyst
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        factors["catalyst_proximity"] = score if score > 0 else 0.3  # Default: no catalyst = neutral-low
        return factors

    def evaluate(self) -> Dict[str, Any]:
        """Run complete factor evaluation."""
        if not self.load_market_state():
            sys.exit(3)
            
        # Evaluate all factor categories (only include catalyst if weight > 0)
        all_factors = {
            'trend': self.evaluate_trend_factors(),
            'momentum': self.evaluate_momentum_factors(),
            'volume': self.evaluate_volume_factors(),
            'volatility': self.evaluate_volatility_factors(),
            'risk': self.evaluate_risk_factors(),
            'sentiment': self.evaluate_sentiment_factors(),
            'regime': self.evaluate_regime_factors()
        }
        if self.CATEGORY_WEIGHTS.get('catalyst', 0) > 0:
            all_factors['catalyst'] = self.evaluate_catalyst_factors()
        
        # Calculate total score
        total_score, category_scores = self.calculate_total_score(all_factors)
        
        # Get recommendation
        recommendation, exit_code = self.get_recommendation(total_score)
        
        # Build reasoning
        reasoning_parts = []
        for category, score in category_scores.items():
            weight = self.CATEGORY_WEIGHTS[category]
            contribution = score * weight * 100
            reasoning_parts.append(f"{category.title()}: {score:.2f} (weight {weight:.0%}) = {contribution:.1f} pts")
        
        reasoning = f"Factor breakdown: {' | '.join(reasoning_parts)}"
        
        result = {
            "ticker": self.ticker,
            "side": self.side,
            "total_score": round(total_score, 1),
            "recommendation": recommendation,
            "exit_code": exit_code,
            "category_scores": {k: round(v, 3) for k, v in category_scores.items()},
            "factor_details": all_factors,
            "reasoning": reasoning
        }
        
        return result


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description='Pre-trade factor validation engine')
    parser.add_argument('--ticker', required=True, help='Stock ticker symbol')
    parser.add_argument('--side', required=True, choices=['long', 'short'], help='Trade side')
    parser.add_argument('--market-state', required=True, help='Path to market-state.json file')
    
    args = parser.parse_args()
    
    try:
        engine = FactorEngine(args.ticker, args.side, args.market_state)
        result = engine.evaluate()
        
        # Output JSON to stdout
        print(json.dumps(result, indent=2))
        
        # Exit with appropriate code
        sys.exit(result['exit_code'])
        
    except Exception as e:
        error_result = {
            "error": f"Factor engine failed: {str(e)}",
            "exit_code": 3
        }
        print(json.dumps(error_result), file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()