#!/usr/bin/env python3
"""
Pre-Trade Factor Engine v1.0
Scores every trade setup against relevant factors before entry.
NO TRADE WITHOUT RUNNING THIS CHECKLIST.

Usage:
  python3 pretrade_factor_engine.py --ticker AAPL --action BUY --timeframe day
  python3 pretrade_factor_engine.py --ticker BTC-USD --action BUY --timeframe swing
"""

import argparse
import json
import sys
from datetime import datetime, timezone

# ============================================================
# FACTOR DEFINITIONS — organized by check type
# ============================================================

# Factors that can be checked programmatically (API-driven)
AUTO_FACTORS = {
    # Microstructure
    "rvol": {
        "id": 57, "name": "Relative Volume (RVOL)",
        "check": "RVOL > 1.5x average",
        "weight": 3, "category": "microstructure",
    },
    "premarket_vol": {
        "id": 58, "name": "Pre-Market Volume",
        "check": "> 500K shares pre-market",
        "weight": 2, "category": "microstructure",
    },
    "short_interest": {
        "id": 59, "name": "Short Interest / Squeeze Risk",
        "check": "SI > 20% float OR days-to-cover > 10",
        "weight": 2, "category": "microstructure",
    },

    # Technical
    "vwap_position": {
        "id": 55, "name": "Price vs VWAP",
        "check": "Price above VWAP (for longs) or below (for shorts)",
        "weight": 2, "category": "technical",
    },
    "mtf_alignment": {
        "id": 80, "name": "Multiple Timeframe Alignment",
        "check": "Weekly + Daily + Hourly trends align with trade direction",
        "weight": 3, "category": "technical",
    },
    "rsi_level": {
        "id": 75, "name": "RSI Position",
        "check": "Not buying overbought (>70) or shorting oversold (<30)",
        "weight": 2, "category": "technical",
    },
    "bb_squeeze": {
        "id": 77, "name": "Bollinger Band Width",
        "check": "Squeeze = breakout imminent; wide = trend in progress",
        "weight": 1, "category": "technical",
    },

    # Fundamental (slower-changing, can cache daily)
    "earnings_revision": {
        "id": 91, "name": "Earnings Revision Momentum",
        "check": "Consensus EPS rising in last 30 days",
        "weight": 2, "category": "fundamental",
    },
    "insider_activity": {
        "id": 8, "name": "Insider Buying/Selling",
        "check": "Net insider buying in last 90 days",
        "weight": 2, "category": "fundamental",
    },

    # Macro
    "vix_level": {
        "id": 9, "name": "VIX Level & Term Structure",
        "check": "VIX < 20 = calm; 20-30 = elevated; > 30 = fear",
        "weight": 2, "category": "macro",
    },
    "dxy_trend": {
        "id": 135, "name": "Dollar Index Trend",
        "check": "DXY declining = bullish for equities",
        "weight": 1, "category": "macro",
    },
    "yield_curve": {
        "id": 131, "name": "Yield Curve (10Y-2Y)",
        "check": "Normal = bullish; Inverted = caution; Re-steepening = danger",
        "weight": 2, "category": "macro",
    },
}

# Factors that require manual/qualitative assessment
MANUAL_FACTORS = {
    "catalyst_quality": {
        "id": "velocity", "name": "Catalyst Quality",
        "prompt": "What's the catalyst? (earnings/news/upgrade/sector/none)",
        "weight": 3, "category": "event",
    },
    "sector_confirmation": {
        "id": 89, "name": "Sector Confirmation",
        "prompt": "Are sector peers moving in the same direction?",
        "weight": 2, "category": "technical",
    },
    "congressional_signal": {
        "id": 106, "name": "Congressional/Insider Signal",
        "prompt": "Any congressional trades or activist filings in this name/sector?",
        "weight": 2, "category": "event",
    },
    "correlation_regime": {
        "id": 150, "name": "Correlation Regime",
        "prompt": "Is this a macro-driven (high correlation) or stock-picker's market?",
        "weight": 1, "category": "quant",
    },
    "risk_reward": {
        "id": "velocity", "name": "Risk/Reward Ratio",
        "prompt": "Target distance vs stop distance (min 2:1 for scouts, 3:1 for conviction)",
        "weight": 3, "category": "risk",
    },
    "portfolio_overlap": {
        "id": "velocity", "name": "Portfolio Correlation",
        "prompt": "Does this overlap with existing positions? (same sector, correlated moves)",
        "weight": 2, "category": "risk",
    },
}

# ============================================================
# SCORING ENGINE
# ============================================================

class PreTradeScore:
    """Score a trade setup against the factor checklist."""

    def __init__(self, ticker, action, timeframe="day"):
        self.ticker = ticker.upper()
        self.action = action.upper()
        self.timeframe = timeframe
        self.scores = {}
        self.total_weight = 0
        self.total_score = 0
        self.flags = []  # Red flags that may block the trade
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def check_auto_factors(self):
        """Run automated factor checks (API-driven)."""
        print(f"\n{'='*60}")
        print(f"PRE-TRADE FACTOR ENGINE v1.0")
        print(f"{'='*60}")
        print(f"Ticker: {self.ticker} | Action: {self.action} | Timeframe: {self.timeframe}")
        print(f"Timestamp: {self.timestamp}")
        print(f"{'='*60}")

        # For now, these are scored manually with prompts
        # TODO: Wire up APIs (Yahoo Finance, Finnhub, Alpha Vantage)
        # for automated scoring

        print("\n📊 AUTOMATED CHECKS (score 0-3 each):")
        print("-" * 40)

        for key, factor in AUTO_FACTORS.items():
            print(f"\n[{factor['category'].upper()}] #{factor['id']}: {factor['name']}")
            print(f"  Check: {factor['check']}")

            # In production, these would be API calls
            # For now, prompt for manual input
            try:
                score = int(input(f"  Score (0=fail, 1=neutral, 2=pass, 3=strong): ") or "1")
            except (ValueError, EOFError):
                score = 1

            score = max(0, min(3, score))
            self.scores[key] = {
                "factor": factor["name"],
                "score": score,
                "weight": factor["weight"],
                "weighted": score * factor["weight"],
            }
            self.total_weight += factor["weight"] * 3  # max possible
            self.total_score += score * factor["weight"]

            if score == 0 and factor["weight"] >= 3:
                self.flags.append(f"🔴 FAIL on high-weight factor: {factor['name']}")

    def check_manual_factors(self):
        """Run manual/qualitative factor checks."""
        print("\n\n🧠 QUALITATIVE CHECKS (score 0-3 each):")
        print("-" * 40)

        for key, factor in MANUAL_FACTORS.items():
            print(f"\n[{factor['category'].upper()}] {factor['name']}")
            print(f"  {factor['prompt']}")

            try:
                score = int(input(f"  Score (0=fail, 1=neutral, 2=pass, 3=strong): ") or "1")
            except (ValueError, EOFError):
                score = 1

            score = max(0, min(3, score))
            self.scores[key] = {
                "factor": factor["name"],
                "score": score,
                "weight": factor["weight"],
                "weighted": score * factor["weight"],
            }
            self.total_weight += factor["weight"] * 3
            self.total_score += score * factor["weight"]

            if score == 0 and factor["weight"] >= 3:
                self.flags.append(f"🔴 FAIL on high-weight factor: {factor['name']}")

    def generate_verdict(self):
        """Calculate final score and trade recommendation."""
        if self.total_weight == 0:
            pct = 0
        else:
            pct = (self.total_score / self.total_weight) * 100

        print(f"\n\n{'='*60}")
        print(f"VERDICT")
        print(f"{'='*60}")
        print(f"Raw Score: {self.total_score} / {self.total_weight}")
        print(f"Factor Score: {pct:.1f}%")

        # Determine tier
        if pct >= 80:
            tier = "CONVICTION"
            size = "8-12% of portfolio"
            emoji = "🟢"
        elif pct >= 60:
            tier = "CONFIRM"
            size = "4-8% of portfolio"
            emoji = "🟡"
        elif pct >= 40:
            tier = "SCOUT"
            size = "2-4% of portfolio"
            emoji = "🟠"
        else:
            tier = "NO TRADE"
            size = "0%"
            emoji = "🔴"

        print(f"\n{emoji} TIER: {tier}")
        print(f"Recommended Size: {size}")

        if self.flags:
            print(f"\n⚠️  RED FLAGS:")
            for flag in self.flags:
                print(f"  {flag}")
            if tier != "NO TRADE":
                print(f"  → Consider downgrading tier or reducing size")

        # Summary by category
        categories = {}
        for key, data in self.scores.items():
            cat = AUTO_FACTORS.get(key, MANUAL_FACTORS.get(key, {})).get("category", "other")
            if cat not in categories:
                categories[cat] = {"score": 0, "max": 0}
            categories[cat]["score"] += data["weighted"]
            categories[cat]["max"] += data["weight"] * 3

        print(f"\n📊 BREAKDOWN BY CATEGORY:")
        for cat, vals in sorted(categories.items()):
            cat_pct = (vals["score"] / vals["max"] * 100) if vals["max"] > 0 else 0
            bar = "█" * int(cat_pct / 10) + "░" * (10 - int(cat_pct / 10))
            print(f"  {cat:15s} {bar} {cat_pct:.0f}%")

        return {
            "ticker": self.ticker,
            "action": self.action,
            "timeframe": self.timeframe,
            "score_pct": round(pct, 1),
            "tier": tier,
            "size": size,
            "flags": self.flags,
            "scores": self.scores,
            "timestamp": self.timestamp,
        }


def quick_score(ticker, action, factors_dict):
    """
    Programmatic scoring without interactive prompts.
    factors_dict: {"rvol": 3, "vwap_position": 2, "catalyst_quality": 3, ...}
    Returns the verdict dict.
    """
    engine = PreTradeScore(ticker, action)

    all_factors = {**AUTO_FACTORS, **MANUAL_FACTORS}
    for key, score in factors_dict.items():
        if key in all_factors:
            factor = all_factors[key]
            score = max(0, min(3, score))
            engine.scores[key] = {
                "factor": factor["name"],
                "score": score,
                "weight": factor["weight"],
                "weighted": score * factor["weight"],
            }
            engine.total_weight += factor["weight"] * 3
            engine.total_score += score * factor["weight"]

            if score == 0 and factor["weight"] >= 3:
                engine.flags.append(f"🔴 FAIL: {factor['name']}")

    return engine.generate_verdict()


# ============================================================
# PRE-TRADE PROCESS (the process Mark asked for)
# ============================================================

PRE_TRADE_PROCESS = """
╔══════════════════════════════════════════════════════════╗
║           MI AI PRE-TRADE PROCESS v1.0                  ║
║     "Every trade passes through the engine or           ║
║      it doesn't get logged."                            ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  1. SIGNAL DETECTION                                     ║
║     → Shared signal bus (every 15 min)                   ║
║     → Velocity/Volume triggers (RVOL, price move)        ║
║     → Congressional/insider filing alerts                ║
║     → Earnings/guidance surprises                        ║
║                                                          ║
║  2. FACTOR ENGINE (this script)                          ║
║     → Score against 150 factors                          ║
║     → Minimum thresholds:                                ║
║       • Scout: 40%+ factor score, min 2/10 conviction    ║
║       • Confirm: 60%+, existing scout in profit          ║
║       • Conviction: 80%+, sector + macro aligned         ║
║                                                          ║
║  3. RISK CHECK                                           ║
║     → Position size within limits (2-12%)                ║
║     → Sector exposure < 30%                              ║
║     → Portfolio heat < 50% (total risk exposure)         ║
║     → Stop loss defined (2% max)                         ║
║     → No >25% gapper without 9/10 conviction             ║
║                                                          ║
║  4. EXECUTION                                            ║
║     → Log to Supabase via log_trade.py                   ║
║     → Announce in #capital-roundtable                    ║
║     → Push to shared signal bus                          ║
║     → Set stop in trailing_stop.py                       ║
║                                                          ║
║  5. POST-TRADE                                           ║
║     → Monitor via stop_monitor (5 min)                   ║
║     → Confirm/add on strength (CONFIRM tier)             ║
║     → EOD sweep for inverse/leveraged (3:45 PM)          ║
║     → Dashboard auto-updates via streamer                ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pre-Trade Factor Engine")
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--action", required=True, choices=["BUY", "SELL", "SHORT", "COVER"])
    parser.add_argument("--timeframe", default="day", choices=["scalp", "day", "swing", "position"])
    parser.add_argument("--process", action="store_true", help="Show the pre-trade process")

    args = parser.parse_args()

    if args.process:
        print(PRE_TRADE_PROCESS)
        sys.exit(0)

    engine = PreTradeScore(args.ticker, args.action, args.timeframe)
    engine.check_auto_factors()
    engine.check_manual_factors()
    verdict = engine.generate_verdict()

    # Save verdict
    filename = f"pretrade_{args.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(verdict, f, indent=2)
    print(f"\n💾 Saved to {filename}")
