#!/usr/bin/env python3
"""Quick 5-minute paper trading test using the multi-strategy engine with live data."""

import json
import time
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

from coinbase_client import fetch_candles
from indicators import add_all_multi_indicators
from regime import detect_regime, Regime
from strategy import StrategyConfig
from multi_strategy import MultiStrategyConfig, _position_size

# Config
PRODUCT = "BTC-USD"
CHECK_INTERVAL = 30  # seconds
DURATION = 300  # 5 minutes
INITIAL_CAPITAL = 10_000.0

config = MultiStrategyConfig(initial_capital=INITIAL_CAPITAL)

# State
equity = INITIAL_CAPITAL
in_position = False
entry_price = 0.0
stop_price = 0.0
position_type = None  # 'long' or 'short'
alloc = 1.0
trades = []

def get_market_state():
    """Fetch latest data with indicators and regime."""
    df = fetch_candles(PRODUCT, granularity="5m", days=2)
    df = add_all_multi_indicators(df)
    df = detect_regime(df)
    required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required).reset_index(drop=True)
    return df

def check_signals(df):
    """Check for trading signals based on current regime."""
    global equity, in_position, entry_price, stop_price, position_type, alloc
    
    latest = df.iloc[-1]
    price = float(latest["close"])
    regime = latest["regime"]
    atr = float(latest["atr"])
    rsi = float(latest["rsi"])
    bb_lower = float(latest["bb_lower"])
    bb_upper = float(latest["bb_upper"])
    adx = float(latest["adx"])
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    
    regime_emoji = {"RANGING": "↔️", "TRENDING_UP": "📈", "TRENDING_DOWN": "📉"}.get(regime, "❓")
    
    print(f"\n[{now}] BTC: ${price:,.2f} | Regime: {regime_emoji} {regime.upper()}")
    print(f"  BB: [${bb_lower:,.2f} — ${bb_upper:,.2f}] | RSI: {rsi:.1f} | ADX: {adx:.1f} | ATR: ${atr:,.2f}")
    
    if in_position:
        if position_type == "long":
            pnl_pct = (price - entry_price) / entry_price * 100
            if price <= stop_price:
                realized = (stop_price - entry_price) / entry_price * alloc
                equity *= (1 + realized)
                print(f"  🔴 STOP LOSS HIT | Sold @ ${stop_price:,.2f} | P&L: {realized*100:+.2f}%")
                trades.append({"type": "sell", "price": stop_price, "reason": "stop_loss", "pnl_pct": realized*100})
                in_position = False
            elif regime == "RANGING" and price >= bb_upper and rsi > 70:
                realized = (price - entry_price) / entry_price * alloc
                equity *= (1 + realized)
                print(f"  🟢 TAKE PROFIT | Sold @ ${price:,.2f} | P&L: {realized*100:+.2f}%")
                trades.append({"type": "sell", "price": price, "reason": "signal", "pnl_pct": realized*100})
                in_position = False
            else:
                print(f"  📊 Holding LONG | Entry: ${entry_price:,.2f} | P&L: {pnl_pct:+.2f}% | Stop: ${stop_price:,.2f}")
        elif position_type == "short":
            pnl_pct = (entry_price - price) / entry_price * 100
            if price >= stop_price:
                realized = (entry_price - stop_price) / entry_price * alloc
                equity *= (1 + realized)
                print(f"  🔴 STOP LOSS HIT | Covered @ ${stop_price:,.2f} | P&L: {realized*100:+.2f}%")
                trades.append({"type": "cover", "price": stop_price, "reason": "stop_loss", "pnl_pct": realized*100})
                in_position = False
            else:
                print(f"  📊 Holding SHORT | Entry: ${entry_price:,.2f} | P&L: {pnl_pct:+.2f}% | Stop: ${stop_price:,.2f}")
    else:
        # Look for entries
        if regime == "RANGING":
            if price <= bb_lower and rsi < 30:
                alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                entry_price = price
                stop_price = price * 0.97  # 3% stop
                position_type = "long"
                in_position = True
                print(f"  🟢 BUY SIGNAL | Entry: ${price:,.2f} | Stop: ${stop_price:,.2f} | Alloc: {alloc*100:.1f}%")
                trades.append({"type": "buy", "price": price, "regime": regime})
            else:
                dist_to_lower = (price - bb_lower) / price * 100
                print(f"  👀 Ranging — waiting for dip. {dist_to_lower:.2f}% above lower BB")
                
        elif regime == "TRENDING_UP":
            # Buy on pullback to EMA20 in uptrend
            ema20 = float(latest["ema_20"])
            if price <= ema20 * 1.005 and adx > 25:
                alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                entry_price = price
                stop_price = price - 2 * atr
                position_type = "long"
                in_position = True
                print(f"  🟢 TREND LONG | Entry: ${price:,.2f} | Stop: ${stop_price:,.2f}")
                trades.append({"type": "buy", "price": price, "regime": regime})
            else:
                print(f"  👀 Uptrend — waiting for pullback to EMA20 (${ema20:,.2f})")
                
        elif regime == "TRENDING_DOWN":
            # Short on rally to EMA20 in downtrend
            ema20 = float(latest["ema_20"])
            if price >= ema20 * 0.995 and adx > 25:
                alloc = _position_size(equity, atr, price, config.max_risk_per_trade)
                entry_price = price
                stop_price = price + 2 * atr
                position_type = "short"
                in_position = True
                print(f"  🔴 TREND SHORT | Entry: ${price:,.2f} | Stop: ${stop_price:,.2f}")
                trades.append({"type": "short", "price": price, "regime": regime})
            else:
                print(f"  👀 Downtrend — waiting for rally to EMA20 (${ema20:,.2f})")
    
    print(f"  💰 Equity: ${equity:,.2f} | Trades: {len([t for t in trades if 'pnl_pct' in t])}")

def main():
    print(f"🚀 Multi-Strategy Paper Test — {PRODUCT}")
    print(f"   Capital: ${INITIAL_CAPITAL:,.2f} | Duration: {DURATION//60}min | Check: every {CHECK_INTERVAL}s")
    print("=" * 60)
    
    start = time.time()
    checks = 0
    
    while time.time() - start < DURATION:
        try:
            df = get_market_state()
            check_signals(df)
            checks += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        remaining = DURATION - (time.time() - start)
        if remaining > CHECK_INTERVAL:
            time.sleep(CHECK_INTERVAL)
        else:
            break
    
    # Final summary
    closed = [t for t in trades if "pnl_pct" in t]
    total_pnl = sum(t["pnl_pct"] for t in closed)
    wins = sum(1 for t in closed if t["pnl_pct"] > 0)
    
    print("\n" + "=" * 60)
    print(f"📊 FINAL RESULTS — {checks} checks over {DURATION//60} minutes")
    print(f"  💰 Final Equity: ${equity:,.2f} (started ${INITIAL_CAPITAL:,.2f})")
    print(f"  📈 Return: {(equity/INITIAL_CAPITAL - 1)*100:+.4f}%")
    print(f"  🔄 Trades: {len(closed)} closed | {wins} wins")
    if closed:
        print(f"  💵 Total P&L: {total_pnl:+.4f}%")
    print(f"  {'Position still open (' + position_type + ')' if in_position else 'No open position'}")
    print("=" * 60)

if __name__ == "__main__":
    main()
