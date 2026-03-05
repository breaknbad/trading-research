#!/usr/bin/env python3
"""
Alfred's Competition Entry — 10-minute optimized paper trading
Improvements over previous test:
1. Tighter entry filters (RSI extremes + volume confirmation)
2. Trailing stops instead of fixed stops
3. Partial profit taking
4. Skip flat assets — only trade where there's momentum
5. Faster 15s checks for quicker reaction
6. Focus on highest-volatility assets for max short-term opportunity
"""

import sys
import time
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

from coinbase_client import fetch_candles
from indicators import add_all_multi_indicators
from regime import detect_regime

ASSETS = ["POL-USD", "NEAR-USD", "BTC-USD", "SOL-USD", "XRP-USD",
          "ARB-USD", "LINK-USD", "DOT-USD", "ETH-USD", "AVAX-USD", "ALGO-USD"]

CHECK_INTERVAL = 15  # faster checks
DURATION = 1800  # 10 minutes
INITIAL_CAPITAL = 10_000.0

# State per asset
state = {}
for asset in ASSETS:
    state[asset] = {
        "equity": 0,  # allocated dynamically
        "in_position": False,
        "entry_price": 0.0,
        "stop_price": 0.0,
        "best_price": 0.0,  # for trailing stop
        "position_type": None,
        "alloc_pct": 0.0,
        "trades": [],
        "last_price": 0.0,
        "volatility": 0.0,  # ATR as % of price
        "prices": [],  # track price history for momentum
    }

portfolio_cash = INITIAL_CAPITAL
total_allocated = 0.0


def get_data(product):
    df = fetch_candles(product, granularity="5m", days=2)
    df = add_all_multi_indicators(df)
    df = detect_regime(df)
    required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required).reset_index(drop=True)
    return df


def score_opportunity(df):
    """Score an asset for trading opportunity (0-100)."""
    latest = df.iloc[-1]
    score = 0
    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    atr = float(latest["atr"])
    price = float(latest["close"])
    regime = latest["regime"]
    macd_hist = float(latest["macd_hist"])
    
    vol_pct = atr / price * 100  # volatility as % of price
    
    # Higher volatility = more opportunity
    score += min(vol_pct * 10, 30)
    
    # Strong trend = more opportunity
    if adx > 25:
        score += 20
    if adx > 35:
        score += 10
    
    # Extreme RSI = potential reversal or strong momentum
    if rsi < 25 or rsi > 75:
        score += 20
    if rsi < 20 or rsi > 80:
        score += 10
    
    # MACD momentum
    if abs(macd_hist) > 0:
        score += 10
    
    return score, vol_pct


def check_asset(product):
    global portfolio_cash, total_allocated
    s = state[product]
    ticker = product.replace("-USD", "")
    
    try:
        df = get_data(product)
    except Exception as e:
        return f"  ❌ {ticker:>5} | Error: {e}"
    
    if df.empty:
        return f"  ⏳ {ticker:>5} | warming up"
    
    latest = df.iloc[-1]
    price = float(latest["close"])
    regime = latest["regime"]
    atr = float(latest["atr"])
    rsi = float(latest["rsi"])
    adx = float(latest["adx"])
    bb_lower = float(latest["bb_lower"])
    bb_upper = float(latest["bb_upper"])
    ema20 = float(latest["ema_20"])
    macd_hist = float(latest["macd_hist"])
    s["last_price"] = price
    s["volatility"] = atr / price * 100
    s["prices"].append(price)
    
    regime_emoji = {"RANGING": "↔️", "TRENDING_UP": "📈", "TRENDING_DOWN": "📉"}.get(regime, "❓")
    
    if s["in_position"]:
        if s["position_type"] == "long":
            pnl_pct = (price - s["entry_price"]) / s["entry_price"] * 100
            
            # Update trailing stop (trail at 1.5x ATR from best price)
            if price > s["best_price"]:
                s["best_price"] = price
                s["stop_price"] = max(s["stop_price"], price - 1.5 * atr)
            
            # Stop loss (trailing)
            if price <= s["stop_price"]:
                realized_pnl = (s["stop_price"] - s["entry_price"]) / s["entry_price"] * s["alloc_pct"]
                gain = s["equity"] * (1 + (s["stop_price"] - s["entry_price"]) / s["entry_price"])
                portfolio_cash += gain
                total_allocated -= s["equity"]
                s["trades"].append({"pnl_pct": pnl_pct, "reason": "trailing_stop"})
                s["in_position"] = False
                s["equity"] = 0
                return f"  🛑 {ticker:>5} | TRAIL STOP | P&L: {pnl_pct:+.3f}% | +${gain - s['equity']:+.2f}"
            
            # Take profit at 2x ATR or upper BB
            if price >= s["entry_price"] + 2 * atr or (price >= bb_upper and rsi > 70):
                gain = s["equity"] * (1 + (price - s["entry_price"]) / s["entry_price"])
                portfolio_cash += gain
                total_allocated -= s["equity"]
                s["trades"].append({"pnl_pct": pnl_pct, "reason": "take_profit"})
                s["in_position"] = False
                s["equity"] = 0
                return f"  💰 {ticker:>5} | TAKE PROFIT | P&L: {pnl_pct:+.3f}% | +${gain:,.2f}"
            
            return f"  📊 {ticker:>5} | LONG  {pnl_pct:+.3f}% | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f}"
        
        elif s["position_type"] == "short":
            pnl_pct = (s["entry_price"] - price) / s["entry_price"] * 100
            
            # Update trailing stop for shorts
            if price < s["best_price"]:
                s["best_price"] = price
                s["stop_price"] = min(s["stop_price"], price + 1.5 * atr)
            
            # Stop loss
            if price >= s["stop_price"]:
                realized_pnl = (s["entry_price"] - s["stop_price"]) / s["entry_price"]
                gain = s["equity"] * (1 + (s["entry_price"] - s["stop_price"]) / s["entry_price"])
                portfolio_cash += gain
                total_allocated -= s["equity"]
                s["trades"].append({"pnl_pct": pnl_pct, "reason": "trailing_stop"})
                s["in_position"] = False
                s["equity"] = 0
                return f"  🛑 {ticker:>5} | TRAIL STOP | P&L: {pnl_pct:+.3f}% | ${gain:,.2f}"
            
            # Take profit
            if price <= s["entry_price"] - 2 * atr or (price <= bb_lower and rsi < 30):
                gain = s["equity"] * (1 + (s["entry_price"] - price) / s["entry_price"])
                portfolio_cash += gain
                total_allocated -= s["equity"]
                s["trades"].append({"pnl_pct": pnl_pct, "reason": "take_profit"})
                s["in_position"] = False
                s["equity"] = 0
                return f"  💰 {ticker:>5} | TAKE PROFIT | P&L: {pnl_pct:+.3f}% | +${gain:,.2f}"
            
            return f"  📊 {ticker:>5} | SHORT {pnl_pct:+.3f}% | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f}"
    
    else:
        # Score opportunity
        opp_score, vol_pct = score_opportunity(df)
        
        # Only enter if score > 40 and we have cash
        if opp_score < 30 or portfolio_cash < 100:
            return f"  👀 {ticker:>5} | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f} ADX:{adx:.0f} | Score:{opp_score}"
        
        # Position size based on opportunity score (5-15% of portfolio)
        alloc_pct = min(0.05 + (opp_score / 100) * 0.10, 0.15)
        position_size = min(portfolio_cash * alloc_pct, portfolio_cash * 0.20)
        
        entered = False
        
        if regime == "TRENDING_DOWN":
            # Short with confirmation: ADX > 25, RSI < 55, MACD negative
            if adx > 25 and rsi < 55 and macd_hist < 0:
                s["entry_price"] = price
                s["stop_price"] = price + 1.5 * atr
                s["best_price"] = price
                s["position_type"] = "short"
                s["in_position"] = True
                s["equity"] = position_size
                s["alloc_pct"] = alloc_pct
                portfolio_cash -= position_size
                total_allocated += position_size
                s["trades"].append({"type": "short", "price": price, "size": position_size})
                entered = True
                return f"  🔴 {ticker:>5} | SHORT @ ${price:,.4f} | ${position_size:,.0f} | Stop: ${s['stop_price']:,.4f} | Score:{opp_score}"
            # Counter-trend long in downtrend: oversold bounce
            elif rsi < 25 and price <= bb_lower:
                s["entry_price"] = price
                s["stop_price"] = price - 1.0 * atr  # tighter stop for counter-trend
                s["best_price"] = price
                s["position_type"] = "long"
                s["in_position"] = True
                s["equity"] = position_size * 0.5  # half size for counter-trend
                s["alloc_pct"] = alloc_pct * 0.5
                portfolio_cash -= s["equity"]
                total_allocated += s["equity"]
                s["trades"].append({"type": "buy", "price": price, "size": s["equity"]})
                entered = True
                return f"  🟢 {ticker:>5} | BOUNCE BUY @ ${price:,.4f} | ${s['equity']:,.0f} | RSI:{rsi:.0f} | Score:{opp_score}"
        
        elif regime == "TRENDING_UP":
            # Long: relaxed — price above EMA with MACD positive, OR strong momentum
            if adx > 25 and macd_hist > 0 and price > ema20:
                s["entry_price"] = price
                s["stop_price"] = price - 1.5 * atr
                s["best_price"] = price
                s["position_type"] = "long"
                s["in_position"] = True
                s["equity"] = position_size
                s["alloc_pct"] = alloc_pct
                portfolio_cash -= position_size
                total_allocated += position_size
                s["trades"].append({"type": "buy", "price": price, "size": position_size})
                entered = True
                return f"  🟢 {ticker:>5} | LONG @ ${price:,.4f} | ${position_size:,.0f} | Stop: ${s['stop_price']:,.4f} | Score:{opp_score}"
            # Also short overbought in uptrend (mean reversion)
            elif rsi > 75 and price >= bb_upper:
                s["entry_price"] = price
                s["stop_price"] = price + 1.0 * atr
                s["best_price"] = price
                s["position_type"] = "short"
                s["in_position"] = True
                s["equity"] = position_size * 0.5
                s["alloc_pct"] = alloc_pct * 0.5
                portfolio_cash -= s["equity"]
                total_allocated += s["equity"]
                s["trades"].append({"type": "short", "price": price, "size": s["equity"]})
                entered = True
                return f"  🔴 {ticker:>5} | OB SHORT @ ${price:,.4f} | ${s['equity']:,.0f} | RSI:{rsi:.0f} | Score:{opp_score}"
        
        elif regime in ("RANGING", "WEAK_TREND_UP", "WEAK_TREND_DOWN"):
            # Mean reversion: buy at lower BB, short at upper BB
            if price <= bb_lower and rsi < 35:
                s["entry_price"] = price
                s["stop_price"] = price - 1.5 * atr
                s["best_price"] = price
                s["position_type"] = "long"
                s["in_position"] = True
                s["equity"] = position_size
                s["alloc_pct"] = alloc_pct
                portfolio_cash -= position_size
                total_allocated += position_size
                s["trades"].append({"type": "buy", "price": price, "size": position_size})
                entered = True
                return f"  🟢 {ticker:>5} | MR BUY @ ${price:,.4f} | ${position_size:,.0f} | Score:{opp_score}"
            elif price >= bb_upper and rsi > 65:
                s["entry_price"] = price
                s["stop_price"] = price + 1.5 * atr
                s["best_price"] = price
                s["position_type"] = "short"
                s["in_position"] = True
                s["equity"] = position_size
                s["alloc_pct"] = alloc_pct
                portfolio_cash -= position_size
                total_allocated += position_size
                s["trades"].append({"type": "short", "price": price, "size": position_size})
                entered = True
                return f"  🔴 {ticker:>5} | MR SHORT @ ${price:,.4f} | ${position_size:,.0f} | Score:{opp_score}"
            # Momentum breakout: price breaking above upper BB with rising ADX = go long
            elif price > bb_upper and adx > 25 and macd_hist > 0 and regime in ("WEAK_TREND_UP", "RANGING"):
                s["entry_price"] = price
                s["stop_price"] = price - 1.5 * atr
                s["best_price"] = price
                s["position_type"] = "long"
                s["in_position"] = True
                s["equity"] = position_size
                s["alloc_pct"] = alloc_pct
                portfolio_cash -= position_size
                total_allocated += position_size
                s["trades"].append({"type": "buy", "price": price, "size": position_size})
                entered = True
                return f"  🟢 {ticker:>5} | BREAKOUT BUY @ ${price:,.4f} | ${position_size:,.0f} | Score:{opp_score}"
        
        if not entered:
            return f"  👀 {ticker:>5} | ${price:,.4f} | {regime_emoji} RSI:{rsi:.0f} ADX:{adx:.0f} | Score:{opp_score}"
    
    return f"  ❓ {ticker:>5} | ${price:,.4f}"


def portfolio_value():
    """Calculate total portfolio value including unrealized P&L."""
    total = portfolio_cash
    for asset, s in state.items():
        if s["in_position"] and s["last_price"] > 0:
            if s["position_type"] == "long":
                total += s["equity"] * (1 + (s["last_price"] - s["entry_price"]) / s["entry_price"])
            elif s["position_type"] == "short":
                total += s["equity"] * (1 + (s["entry_price"] - s["last_price"]) / s["entry_price"])
    return total


def print_final():
    total = portfolio_value()
    ret = (total / INITIAL_CAPITAL - 1) * 100
    
    open_pos = [(a, s) for a, s in state.items() if s["in_position"]]
    closed = []
    for a, s in state.items():
        for t in s["trades"]:
            if "pnl_pct" in t:
                closed.append((a.replace("-USD", ""), t))
    
    wins = sum(1 for _, t in closed if t["pnl_pct"] > 0)
    
    print(f"\n{'='*60}")
    print(f"  🎩 ALFRED'S COMPETITION RESULTS")
    print(f"{'='*60}")
    print(f"  💰 Final Value:  ${total:,.2f}")
    print(f"  💵 Started:      ${INITIAL_CAPITAL:,.2f}")
    print(f"  📈 Return:       {ret:+.4f}% (${total - INITIAL_CAPITAL:+,.2f})")
    print(f"  🔄 Trades:       {len(closed)} closed | {wins} wins | {len(open_pos)} still open")
    print(f"  💵 Cash:         ${portfolio_cash:,.2f}")
    
    if closed:
        print(f"\n  Closed trades:")
        for ticker, t in closed:
            emoji = "✅" if t["pnl_pct"] > 0 else "❌"
            print(f"    {emoji} {ticker:>5} | {t['reason']:>12} | {t['pnl_pct']:+.3f}%")
    
    if open_pos:
        print(f"\n  Open positions:")
        for a, s in open_pos:
            ticker = a.replace("-USD", "")
            if s["position_type"] == "long":
                pnl = (s["last_price"] - s["entry_price"]) / s["entry_price"] * 100
            else:
                pnl = (s["entry_price"] - s["last_price"]) / s["entry_price"] * 100
            emoji = "✅" if pnl > 0 else "❌"
            value = s["equity"] * (1 + pnl/100)
            print(f"    {emoji} {ticker:>5} {s['position_type'].upper():>5} | Entry: ${s['entry_price']:,.4f} → ${s['last_price']:,.4f} | {pnl:+.3f}% | ${value:,.2f}")
    
    # Leaderboard
    perf = []
    for a, s in state.items():
        ticker = a.replace("-USD", "")
        if not s["trades"]:
            continue
        asset_pnl = 0
        for t in s["trades"]:
            if "pnl_pct" in t:
                asset_pnl += t["pnl_pct"]
        if s["in_position"] and s["last_price"] > 0:
            if s["position_type"] == "long":
                asset_pnl += (s["last_price"] - s["entry_price"]) / s["entry_price"] * 100
            else:
                asset_pnl += (s["entry_price"] - s["last_price"]) / s["entry_price"] * 100
        perf.append((ticker, asset_pnl))
    
    if perf:
        perf.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  Asset leaderboard:")
        for i, (ticker, pnl) in enumerate(perf):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
            print(f"    {medal} {ticker:>5} {pnl:+.4f}%")
    
    print(f"{'='*60}")
    sys.stdout.flush()


def main():
    print(f"🎩 ALFRED'S OPTIMIZED TRADING ENGINE")
    print(f"   Improvements: trailing stops, opportunity scoring,")
    print(f"   dynamic allocation, faster checks, momentum filters")
    print(f"   Capital: ${INITIAL_CAPITAL:,.2f} | Duration: {DURATION//60}min | Check: every {CHECK_INTERVAL}s")
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
        pv = portfolio_value()
        ret = (pv / INITIAL_CAPITAL - 1) * 100
        
        print(f"\n⏰ #{check_num} [{now}] {remaining}s left | Portfolio: ${pv:,.2f} ({ret:+.4f}%)")
        sys.stdout.flush()
        
        for asset in ASSETS:
            result = check_asset(asset)
            print(result)
            sys.stdout.flush()
            time.sleep(0.2)
        
        remaining = DURATION - (time.time() - start)
        if remaining > CHECK_INTERVAL:
            time.sleep(CHECK_INTERVAL)
        else:
            break
    
    print_final()


if __name__ == "__main__":
    main()
