#!/usr/bin/env python3
"""intel_signal_generator.py — Converts intelligence (congressional trades, news sentiment,
Iran monitor) into actionable trade signals with factor scores.

Reads:
  - sentiment_state.json (news sentiment scanner output)
  - congressional_trades.json (congressional monitor output)
  - alerts.json (Iran/geopolitical alerts)

Writes:
  - intel_signals.json (staged signals ready for execution pipeline)

Usage: python3 intel_signal_generator.py [--dry-run]
"""

import json, sys, os, time
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
SENTIMENT_FILE = SCRIPTS / "sentiment_state.json"
CONGRESSIONAL_FILE = WORKSPACE / "congressional_trades.json"
ALERTS_FILE = WORKSPACE / "alerts.json"
INTEL_SIGNALS_FILE = WORKSPACE / "intel_signals.json"
MARKET_STATE_FILE = WORKSPACE / "market-state.json"

# Minimum confidence thresholds
MIN_CONGRESSIONAL_CONVICTION = 0.6  # 60% historical accuracy for this member
MIN_SENTIMENT_EXTREME = 15  # F&G below this = extreme fear signal
MAX_SENTIMENT_GREED = 80  # F&G above this = extreme greed signal

# High-value congressional members (sorted by historical accuracy)
PRIORITY_MEMBERS = {
    "pelosi": {"accuracy": 0.82, "style": "momentum", "avg_hold_days": 45},
    "davidson": {"accuracy": 0.79, "style": "sector_rotation", "avg_hold_days": 30},
    "norcross": {"accuracy": 0.71, "style": "value", "avg_hold_days": 60},
    "cisneros": {"accuracy": 0.68, "style": "event_driven", "avg_hold_days": 20},
    "mccaul": {"accuracy": 0.65, "style": "defense", "avg_hold_days": 40},
}


def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def get_market_price(ticker):
    """Get current price from market-state.json."""
    state = load_json(MARKET_STATE_FILE)
    tdata = state.get("tickers", {}).get(ticker.upper().replace("-USD", ""))
    if tdata:
        return tdata.get("price", 0)
    return 0


def generate_congressional_signals(trades_data):
    """Convert congressional trades into signals."""
    signals = []
    if not trades_data or not isinstance(trades_data, list):
        return signals

    now = time.time()
    for trade in trades_data:
        member = trade.get("member", "").lower()
        ticker = trade.get("ticker", "").upper()
        action = trade.get("action", "").upper()  # BUY/SELL
        amount = trade.get("amount", 0)
        filed_date = trade.get("filed_date", "")

        # Skip if not a priority member
        member_key = None
        for key in PRIORITY_MEMBERS:
            if key in member:
                member_key = key
                break
        if not member_key:
            continue

        member_info = PRIORITY_MEMBERS[member_key]
        if member_info["accuracy"] < MIN_CONGRESSIONAL_CONVICTION:
            continue

        # Determine side
        side = "long" if action == "BUY" else "short"

        # Score based on member accuracy + amount
        base_score = member_info["accuracy"] * 10  # 0-10 scale
        # Large trades (>$500K) get a boost
        if amount and amount > 500000:
            base_score = min(10, base_score + 1.5)
        elif amount and amount > 100000:
            base_score = min(10, base_score + 0.5)

        # Determine tier
        if base_score >= 8:
            tier = "CONVICTION"
            size_pct = 0.10
        elif base_score >= 6.5:
            tier = "CONFIRM"
            size_pct = 0.08
        else:
            tier = "SCOUT"
            size_pct = 0.04

        price = get_market_price(ticker)

        signals.append({
            "source": "congressional",
            "member": member_key,
            "ticker": ticker,
            "side": side,
            "score": round(base_score, 1),
            "tier": tier,
            "size_pct": size_pct,
            "price": price,
            "thesis": f"{member_key.title()} {action} {ticker} (accuracy: {member_info['accuracy']:.0%}, avg hold: {member_info['avg_hold_days']}d)",
            "auto_execute": base_score >= 8,  # Only auto-execute CONVICTION
            "ttl_minutes": 300,  # 5-hour window to act
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    return signals


def generate_sentiment_signals(sentiment_data):
    """Convert extreme sentiment readings into signals."""
    signals = []
    if not sentiment_data:
        return signals

    fng = sentiment_data.get("last_fng", 50)

    # Extreme Fear = contrarian long opportunity
    if fng <= MIN_SENTIMENT_EXTREME:
        signals.append({
            "source": "sentiment",
            "type": "extreme_fear",
            "ticker": "BTC",
            "side": "long",
            "score": round(min(10, (MIN_SENTIMENT_EXTREME - fng) * 0.5 + 5), 1),
            "tier": "CONFIRM" if fng <= 10 else "SCOUT",
            "size_pct": 0.08 if fng <= 10 else 0.04,
            "thesis": f"F&G Index at {fng} (Extreme Fear) — contrarian long. Historical bounce rate >70% within 7 days.",
            "auto_execute": False,
            "ttl_minutes": 120,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        # Also flag ETH on extreme fear
        signals.append({
            "source": "sentiment",
            "type": "extreme_fear",
            "ticker": "ETH",
            "side": "long",
            "score": round(min(10, (MIN_SENTIMENT_EXTREME - fng) * 0.4 + 4), 1),
            "tier": "SCOUT",
            "size_pct": 0.04,
            "thesis": f"F&G at {fng} — ETH historically bounces harder than BTC from extreme fear.",
            "auto_execute": False,
            "ttl_minutes": 120,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Extreme Greed = contrarian short / reduce exposure
    if fng >= MAX_SENTIMENT_GREED:
        signals.append({
            "source": "sentiment",
            "type": "extreme_greed",
            "ticker": "BTC",
            "side": "short",
            "score": round(min(10, (fng - MAX_SENTIMENT_GREED) * 0.3 + 5), 1),
            "tier": "SCOUT",
            "size_pct": 0.04,
            "thesis": f"F&G at {fng} (Extreme Greed) — historical correction probability >60% within 14 days.",
            "auto_execute": False,
            "ttl_minutes": 120,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    return signals


def generate_geopolitical_signals(alerts_data):
    """Convert high-priority geopolitical alerts into signals."""
    signals = []
    if not alerts_data or not isinstance(alerts_data, list):
        return signals

    for alert in alerts_data:
        severity = alert.get("severity", "low")
        if severity not in ("critical", "high"):
            continue

        category = alert.get("category", "")
        ticker_map = {
            "oil": [("XLE", "long"), ("USO", "long")],
            "defense": [("ITA", "long"), ("LMT", "long")],
            "flight_to_safety": [("TLT", "long"), ("SQQQ", "long")],
            "crypto_fear": [("BTC", "short")],
        }

        mapped_tickers = ticker_map.get(category, [])
        for ticker, side in mapped_tickers:
            price = get_market_price(ticker)
            signals.append({
                "source": "geopolitical",
                "alert_category": category,
                "ticker": ticker,
                "side": side,
                "score": 6.0 if severity == "critical" else 5.0,
                "tier": "CONFIRM" if severity == "critical" else "SCOUT",
                "size_pct": 0.08 if severity == "critical" else 0.04,
                "price": price,
                "thesis": f"Geopolitical alert ({severity}): {alert.get('headline', category)}",
                "auto_execute": False,
                "ttl_minutes": 60,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

    return signals


def main():
    dry_run = "--dry-run" in sys.argv

    # Load all intel sources
    sentiment = load_json(SENTIMENT_FILE)
    congressional = load_json(CONGRESSIONAL_FILE, default=[])
    alerts = load_json(ALERTS_FILE, default=[])

    # Generate signals from each source
    all_signals = []
    all_signals.extend(generate_congressional_signals(congressional))
    all_signals.extend(generate_sentiment_signals(sentiment))
    all_signals.extend(generate_geopolitical_signals(alerts))

    # Filter expired signals from existing file
    existing = load_json(INTEL_SIGNALS_FILE, default=[])
    now = time.time()
    active_existing = []
    for sig in existing:
        gen_time = sig.get("generated_at", "")
        ttl = sig.get("ttl_minutes", 60)
        try:
            gen_dt = datetime.fromisoformat(gen_time)
            age_min = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 60
            if age_min < ttl:
                active_existing.append(sig)
        except (ValueError, TypeError):
            pass

    # Dedup: don't re-signal same ticker+side+source within TTL
    existing_keys = {(s["source"], s["ticker"], s["side"]) for s in active_existing}
    new_signals = [s for s in all_signals if (s["source"], s["ticker"], s["side"]) not in existing_keys]

    combined = active_existing + new_signals

    if dry_run:
        print(f"[DRY RUN] Would write {len(combined)} signals ({len(new_signals)} new)")
        for sig in new_signals:
            print(f"  NEW: {sig['source']} | {sig['ticker']} {sig['side']} | score {sig['score']} | {sig['tier']} | {sig['thesis'][:80]}")
        return

    # Write signals
    with open(INTEL_SIGNALS_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"[INTEL] {len(combined)} active signals ({len(new_signals)} new)")
    for sig in new_signals:
        print(f"  📡 {sig['source']} | {sig['ticker']} {sig['side']} | score {sig['score']} | {sig['tier']}")


if __name__ == "__main__":
    main()
