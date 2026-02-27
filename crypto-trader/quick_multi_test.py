#!/usr/bin/env python3
"""5-minute multi-asset paper trading test using the multi-strategy engine."""

import sys
import time
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

from coinbase_client import fetch_candles
from indicators import add_all_multi_indicators
from regime import detect_regime
from multi_strategy import MultiStrategyConfig, _position_size

# Assets
ASSETS = ["POL-USD", "NEAR-USD", "BTC-USD", "SOL-USD", "XRP-USD",
          "ARB-USD", "LINK-USD", "DOT-USD", "ETH-USD", "AVAX-USD", "ALGO-USD"]

CHECK_INTERVAL = 30  # seconds
DURATION = 300  # 5 minutes
INITIAL_CAPITAL = 10_000.0
PER_ASSET_ALLOC = INITIAL_CAPITAL / len(ASSETS)  # equal weight

config = MultiStrategyConfig()

# Per-asset state
state = {}
for asset in ASSETS:
    state[asset] = {
        "equity": PER_ASSET_ALLOC,
        "in_position": False,
        "entry_price": 0.0,
        "stop_price": 0.0,
        "position_type": None,
        "alloc": 1.0,
        "trades": [],
        "last_price": 0.0,
    }


def get_market_state(product):
    df = fetch_candles(product, granularity="5m", days=2)
    df = add_all_multi_indicators(df)
    df = detect_regime(df)
    required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required).reset_index(drop=True)
    return df


def check_asset(product):
    s = state[product]
    try:
        df = get_market_state(product)
    except Exception as e:
        return f"  ❌ {product}: {e}"

    if df.empty:
        return f"  ⏳ {product}: waiting for indicator warmup"

    latest = df.iloc[-1]
    price = float(latest["close"])
    regime = latest["regime"]
    atr = float(latest["atr"])
    rsi = float(latest["rsi"])
    bb_lower = float(latest["bb_lower"])
    bb_upper = float(latest["bb_upper"])
    adx = float(latest["adx"])
    ema20 = float(latest["ema_20"])
    s["last_price"] = price

    regime_emoji = {"RANGING": "↔️", "TRENDING_UP": "📈", "TRENDING_DOWN": "📉"}.get(regime, "❓")
    ticker = product.replace("-USD", "")

    if s["in_position"]:
        if s["position_type"] == "long":
            pnl_pct = (price - s["entry_price"]) / s["entry_price"] * 100
            # Stop loss
            if price <= s["stop_price"]:
                realized = (s["stop_price"] - s["entry_price"]) / s["entry_price"] * s["alloc"]
                s["equity"] *= (1 + realized)
                s["trades"].append({"pnl_pct": realized * 100, "reason": "stop"})
                s["in_position"] = False
                return f"  🔴 {ticker:>5} | STOP LOSS | P&L: {realized*100:+.3f}% | Eq: ${s['equity']:,.2f}"
            # Take profit (ranging)
            if regime == "RANGING" and price >= bb_upper and rsi > 70:
                realized = (price - s["entry_price"]) / s["entry_price"] * s["alloc"]
                s["equity"] *= (1 + realized)
                s["trades"].append({"pnl_pct": realized * 100, "reason": "signal"})
                s["in_position"] = False
                return f"  🟢 {ticker:>5} | TAKE PROFIT | P&L: {realized*100:+.3f}% | Eq: ${s['equity']:,.2f}"
            return f"  📊 {ticker:>5} | LONG  {pnl_pct:+.3f}% | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f}"

        elif s["position_type"] == "short":
            pnl_pct = (s["entry_price"] - price) / s["entry_price"] * 100
            if price >= s["stop_price"]:
                realized = (s["entry_price"] - s["stop_price"]) / s["entry_price"] * s["alloc"]
                s["equity"] *= (1 + realized)
                s["trades"].append({"pnl_pct": realized * 100, "reason": "stop"})
                s["in_position"] = False
                return f"  🔴 {ticker:>5} | STOP LOSS | P&L: {realized*100:+.3f}% | Eq: ${s['equity']:,.2f}"
            return f"  📊 {ticker:>5} | SHORT {pnl_pct:+.3f}% | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f}"
    else:
        # Entry signals
        if regime == "RANGING":
            if price <= bb_lower and rsi < 30:
                s["alloc"] = _position_size(s["equity"], atr, price, config.max_risk_per_trade)
                s["entry_price"] = price
                s["stop_price"] = price * 0.97
                s["position_type"] = "long"
                s["in_position"] = True
                s["trades"].append({"type": "buy", "price": price})
                return f"  🟢 {ticker:>5} | BUY @ ${price:,.4f} | Stop: ${s['stop_price']:,.4f} | {regime_emoji}"
            return f"  👀 {ticker:>5} | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f} ADX:{adx:.0f} | waiting"

        elif regime == "TRENDING_UP":
            if price <= ema20 * 1.005 and adx > 25:
                s["alloc"] = _position_size(s["equity"], atr, price, config.max_risk_per_trade)
                s["entry_price"] = price
                s["stop_price"] = price - 2 * atr
                s["position_type"] = "long"
                s["in_position"] = True
                s["trades"].append({"type": "buy", "price": price})
                return f"  🟢 {ticker:>5} | TREND LONG @ ${price:,.4f} | {regime_emoji}"
            return f"  👀 {ticker:>5} | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f} ADX:{adx:.0f} | waiting"

        elif regime == "TRENDING_DOWN":
            if price >= ema20 * 0.995 and adx > 25:
                s["alloc"] = _position_size(s["equity"], atr, price, config.max_risk_per_trade)
                s["entry_price"] = price
                s["stop_price"] = price + 2 * atr
                s["position_type"] = "short"
                s["in_position"] = True
                s["trades"].append({"type": "short", "price": price})
                return f"  🔴 {ticker:>5} | TREND SHORT @ ${price:,.4f} | {regime_emoji}"
            return f"  👀 {ticker:>5} | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f} ADX:{adx:.0f} | waiting"

    return f"  ❓ {ticker:>5} | ${price:,.4f} | unknown regime: {regime}"


def print_summary():
    total_equity = sum(s["equity"] for s in state.values())
    # Include unrealized P&L for open positions
    total_unrealized = 0
    for asset, s in state.items():
        if s["in_position"] and s["last_price"] > 0:
            if s["position_type"] == "long":
                total_unrealized += (s["last_price"] - s["entry_price"]) / s["entry_price"] * s["alloc"] * PER_ASSET_ALLOC
            elif s["position_type"] == "short":
                total_unrealized += (s["entry_price"] - s["last_price"]) / s["entry_price"] * s["alloc"] * PER_ASSET_ALLOC

    total_value = total_equity + total_unrealized
    ret = (total_value / INITIAL_CAPITAL - 1) * 100

    open_positions = [(a, s) for a, s in state.items() if s["in_position"]]
    closed_trades = []
    for a, s in state.items():
        for t in s["trades"]:
            if "pnl_pct" in t:
                closed_trades.append((a, t))

    wins = sum(1 for _, t in closed_trades if t["pnl_pct"] > 0)

    print(f"\n{'='*60}")
    print(f"📊 FINAL RESULTS — {len(ASSETS)} assets")
    print(f"  💰 Total Value: ${total_value:,.2f} (started ${INITIAL_CAPITAL:,.2f})")
    print(f"  📈 Return: {ret:+.4f}%")
    print(f"  🔄 Closed: {len(closed_trades)} trades | {wins} wins")
    print(f"  📂 Open: {len(open_positions)} positions")

    if open_positions:
        print(f"\n  Open positions:")
        for a, s in open_positions:
            ticker = a.replace("-USD", "")
            if s["position_type"] == "long":
                pnl = (s["last_price"] - s["entry_price"]) / s["entry_price"] * 100
            else:
                pnl = (s["entry_price"] - s["last_price"]) / s["entry_price"] * 100
            print(f"    {ticker:>5} {s['position_type'].upper():>5} @ ${s['entry_price']:,.4f} → ${s['last_price']:,.4f} ({pnl:+.3f}%)")

    if closed_trades:
        print(f"\n  Closed trades:")
        for a, t in closed_trades:
            ticker = a.replace("-USD", "")
            print(f"    {ticker:>5} {t['reason']:>8} | P&L: {t['pnl_pct']:+.3f}%")

    # Best/worst performers
    perf = []
    for a, s in state.items():
        ticker = a.replace("-USD", "")
        asset_ret = (s["equity"] / PER_ASSET_ALLOC - 1) * 100
        if s["in_position"] and s["last_price"] > 0:
            if s["position_type"] == "long":
                asset_ret += (s["last_price"] - s["entry_price"]) / s["entry_price"] * s["alloc"] * 100
            elif s["position_type"] == "short":
                asset_ret += (s["entry_price"] - s["last_price"]) / s["entry_price"] * s["alloc"] * 100
        perf.append((ticker, asset_ret))
    perf.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  Asset performance:")
    for ticker, ret in perf:
        bar = "█" * max(1, int(abs(ret) * 100)) if ret != 0 else "·"
        direction = "+" if ret >= 0 else "-"
        print(f"    {ticker:>5} {ret:+.4f}% {bar}")

    print(f"{'='*60}")
    sys.stdout.flush()


def main():
    print(f"🚀 Multi-Asset Paper Test — {len(ASSETS)} cryptocurrencies")
    print(f"   Capital: ${INITIAL_CAPITAL:,.2f} (${PER_ASSET_ALLOC:,.2f}/asset)")
    print(f"   Duration: {DURATION//60}min | Check: every {CHECK_INTERVAL}s")
    print(f"   Assets: {', '.join(a.replace('-USD','') for a in ASSETS)}")
    print("=" * 60)
    sys.stdout.flush()

    start = time.time()
    check_num = 0

    while time.time() - start < DURATION:
        check_num += 1
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        elapsed = int(time.time() - start)
        remaining = DURATION - elapsed
        print(f"\n⏰ Check #{check_num} [{now}] — {remaining}s remaining")
        sys.stdout.flush()

        for asset in ASSETS:
            result = check_asset(asset)
            print(result)
            sys.stdout.flush()
            time.sleep(0.3)  # rate limit

        remaining = DURATION - (time.time() - start)
        if remaining > CHECK_INTERVAL:
            time.sleep(CHECK_INTERVAL)
        else:
            break

    print_summary()


if __name__ == "__main__":
    main()
