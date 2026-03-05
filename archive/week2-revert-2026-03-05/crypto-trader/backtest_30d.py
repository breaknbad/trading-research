#!/usr/bin/env python3
"""30-day backtest of the multi-strategy engine across all 11 assets."""

import sys
import warnings
warnings.filterwarnings("ignore")

from coinbase_client import fetch_candles
from indicators import add_all_multi_indicators
from regime import detect_regime
from multi_strategy import MultiStrategyConfig, _position_size

ASSETS = ["POL-USD", "NEAR-USD", "BTC-USD", "SOL-USD", "XRP-USD",
          "ARB-USD", "LINK-USD", "DOT-USD", "ETH-USD", "AVAX-USD", "ALGO-USD"]

INITIAL_CAPITAL = 10_000.0
config = MultiStrategyConfig()


def backtest_asset(product, days=30):
    """Backtest one asset using hourly candles."""
    try:
        df = fetch_candles(product, granularity="1h", days=days)
    except Exception as e:
        return {"asset": product, "error": str(e)}
    
    df = add_all_multi_indicators(df)
    df = detect_regime(df)
    required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required).reset_index(drop=True)
    
    if len(df) < 50:
        return {"asset": product, "error": "insufficient data"}
    
    equity = INITIAL_CAPITAL / len(ASSETS)  # equal allocation
    start_equity = equity
    in_position = False
    entry_price = 0.0
    stop_price = 0.0
    best_price = 0.0
    position_type = None
    alloc = 1.0
    trades = []
    equity_curve = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row["close"])
        regime = row["regime"]
        atr = float(row["atr"])
        rsi = float(row["rsi"])
        adx = float(row["adx"])
        bb_lower = float(row["bb_lower"])
        bb_upper = float(row["bb_upper"])
        ema20 = float(row["ema_20"])
        macd_hist = float(row["macd_hist"])
        ts = str(row.get("datetime", i))
        
        if in_position:
            if position_type == "long":
                pnl_pct = (price - entry_price) / entry_price * 100
                if price > best_price:
                    best_price = price
                    stop_price = max(stop_price, price - 1.5 * atr)
                
                if price <= stop_price:
                    realized = (stop_price - entry_price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "long", "entry": entry_price, "exit": stop_price, "pnl_pct": realized * 100, "reason": "trail_stop", "ts": ts})
                    in_position = False
                elif price >= bb_upper and rsi > 70:
                    realized = (price - entry_price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "long", "entry": entry_price, "exit": price, "pnl_pct": realized * 100, "reason": "take_profit", "ts": ts})
                    in_position = False
                elif price >= entry_price + 2 * atr:
                    realized = (price - entry_price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "long", "entry": entry_price, "exit": price, "pnl_pct": realized * 100, "reason": "atr_target", "ts": ts})
                    in_position = False
            
            elif position_type == "short":
                pnl_pct = (entry_price - price) / entry_price * 100
                if price < best_price:
                    best_price = price
                    stop_price = min(stop_price, price + 1.5 * atr)
                
                if price >= stop_price:
                    realized = (entry_price - stop_price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "short", "entry": entry_price, "exit": stop_price, "pnl_pct": realized * 100, "reason": "trail_stop", "ts": ts})
                    in_position = False
                elif price <= bb_lower and rsi < 30:
                    realized = (entry_price - price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "short", "entry": entry_price, "exit": price, "pnl_pct": realized * 100, "reason": "take_profit", "ts": ts})
                    in_position = False
                elif price <= entry_price - 2 * atr:
                    realized = (entry_price - price) / entry_price
                    equity *= (1 + realized * alloc)
                    trades.append({"type": "short", "entry": entry_price, "exit": price, "pnl_pct": realized * 100, "reason": "atr_target", "ts": ts})
                    in_position = False
        
        else:
            # Score opportunity
            vol_pct = atr / price * 100
            score = min(vol_pct * 10, 30)
            if adx > 25: score += 20
            if adx > 35: score += 10
            if rsi < 25 or rsi > 75: score += 20
            if rsi < 20 or rsi > 80: score += 10
            if abs(macd_hist) > 0: score += 10
            
            if score >= 40:
                alloc_pct = min(0.05 + (score / 100) * 0.10, 0.15)
                alloc = min(alloc_pct * 3, 1.0)  # scale up for backtest
                
                if regime == "TRENDING_DOWN" and adx > 25 and rsi < 55 and macd_hist < 0:
                    entry_price = price
                    stop_price = price + 1.5 * atr
                    best_price = price
                    position_type = "short"
                    in_position = True
                
                elif regime == "TRENDING_UP" and adx > 25 and rsi > 45 and macd_hist > 0 and price <= ema20 * 1.01:
                    entry_price = price
                    stop_price = price - 1.5 * atr
                    best_price = price
                    position_type = "long"
                    in_position = True
                
                elif regime == "RANGING":
                    if price <= bb_lower and rsi < 30:
                        entry_price = price
                        stop_price = price - 1.5 * atr
                        best_price = price
                        position_type = "long"
                        in_position = True
                    elif price >= bb_upper and rsi > 70:
                        entry_price = price
                        stop_price = price + 1.5 * atr
                        best_price = price
                        position_type = "short"
                        in_position = True
        
        # Record equity (including unrealized)
        eq = equity
        if in_position:
            if position_type == "long":
                eq = equity * (1 + (price - entry_price) / entry_price * alloc)
            else:
                eq = equity * (1 + (entry_price - price) / entry_price * alloc)
        equity_curve.append(eq)
    
    # Close any open position at end
    if in_position:
        last_price = float(df.iloc[-1]["close"])
        if position_type == "long":
            realized = (last_price - entry_price) / entry_price
        else:
            realized = (entry_price - last_price) / entry_price
        equity *= (1 + realized * alloc)
        trades.append({"type": position_type, "entry": entry_price, "exit": last_price, "pnl_pct": realized * 100, "reason": "end_of_test"})
    
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    losses = sum(1 for t in trades if t["pnl_pct"] <= 0)
    total_return = (equity / start_equity - 1) * 100
    
    best_trade = max((t["pnl_pct"] for t in trades), default=0)
    worst_trade = min((t["pnl_pct"] for t in trades), default=0)
    avg_win = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0) / max(wins, 1)
    avg_loss = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0) / max(losses, 1)
    
    # Max drawdown
    peak = start_equity
    max_dd = 0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)
    
    return {
        "asset": product.replace("-USD", ""),
        "return_pct": total_return,
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / max(len(trades), 1) * 100,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_dd,
        "final_equity": equity,
        "start_equity": start_equity,
        "trade_log": trades,
    }


def main():
    print(f"🔬 30-Day Backtest — Optimized Multi-Strategy Engine")
    print(f"   11 assets | Hourly candles | $10,000 total ($909/asset)")
    print(f"   Trailing stops | Opportunity scoring | MACD confirmation")
    print("=" * 70)
    sys.stdout.flush()
    
    results = []
    total_final = 0
    total_start = 0
    all_trades = 0
    all_wins = 0
    
    for asset in ASSETS:
        ticker = asset.replace("-USD", "")
        print(f"\n  Processing {ticker}...", end=" ")
        sys.stdout.flush()
        r = backtest_asset(asset, days=30)
        results.append(r)
        
        if "error" in r:
            print(f"❌ {r['error']}")
        else:
            total_final += r["final_equity"]
            total_start += r["start_equity"]
            all_trades += r["trades"]
            all_wins += r["wins"]
            emoji = "✅" if r["return_pct"] > 0 else "❌"
            print(f"{emoji} {r['return_pct']:+.2f}% | {r['trades']} trades | {r['win_rate']:.0f}% win | DD: {r['max_drawdown']:.1f}%")
    
    # Portfolio summary
    portfolio_return = (total_final / total_start - 1) * 100
    
    print(f"\n{'='*70}")
    print(f"📊 PORTFOLIO RESULTS — 30 DAY BACKTEST")
    print(f"{'='*70}")
    print(f"  💰 Final Value:    ${total_final:,.2f}")
    print(f"  💵 Starting:       ${total_start:,.2f}")
    print(f"  📈 Total Return:   {portfolio_return:+.2f}%")
    print(f"  🔄 Total Trades:   {all_trades}")
    print(f"  ✅ Win Rate:       {all_wins}/{all_trades} ({all_wins/max(all_trades,1)*100:.1f}%)")
    
    # Leaderboard
    valid = [r for r in results if "error" not in r]
    valid.sort(key=lambda x: x["return_pct"], reverse=True)
    
    print(f"\n  📋 Asset Leaderboard:")
    print(f"  {'Asset':>6} {'Return':>9} {'Trades':>7} {'Win%':>6} {'Best':>8} {'Worst':>8} {'MaxDD':>7}")
    print(f"  {'-'*6} {'-'*9} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*7}")
    
    for i, r in enumerate(valid):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else "  "
        print(f"  {medal}{r['asset']:>4} {r['return_pct']:>+8.2f}% {r['trades']:>6}  {r['win_rate']:>5.0f}% {r['best_trade']:>+7.2f}% {r['worst_trade']:>+7.2f}% {r['max_drawdown']:>6.1f}%")
    
    # Strategy breakdown
    all_trade_logs = []
    for r in valid:
        for t in r.get("trade_log", []):
            t["asset"] = r["asset"]
            all_trade_logs.append(t)
    
    longs = [t for t in all_trade_logs if t["type"] == "long"]
    shorts = [t for t in all_trade_logs if t["type"] == "short"]
    
    print(f"\n  📊 Strategy Breakdown:")
    if longs:
        long_wins = sum(1 for t in longs if t["pnl_pct"] > 0)
        long_avg = sum(t["pnl_pct"] for t in longs) / len(longs)
        print(f"    LONG:  {len(longs)} trades | {long_wins} wins ({long_wins/len(longs)*100:.0f}%) | Avg P&L: {long_avg:+.2f}%")
    if shorts:
        short_wins = sum(1 for t in shorts if t["pnl_pct"] > 0)
        short_avg = sum(t["pnl_pct"] for t in shorts) / len(shorts)
        print(f"    SHORT: {len(shorts)} trades | {short_wins} wins ({short_wins/len(shorts)*100:.0f}%) | Avg P&L: {short_avg:+.2f}%")
    
    # Exit reason breakdown
    reasons = {}
    for t in all_trade_logs:
        r = t.get("reason", "unknown")
        if r not in reasons:
            reasons[r] = {"count": 0, "total_pnl": 0, "wins": 0}
        reasons[r]["count"] += 1
        reasons[r]["total_pnl"] += t["pnl_pct"]
        if t["pnl_pct"] > 0:
            reasons[r]["wins"] += 1
    
    print(f"\n  🚪 Exit Reasons:")
    for reason, data in sorted(reasons.items(), key=lambda x: x[1]["total_pnl"], reverse=True):
        avg = data["total_pnl"] / data["count"]
        print(f"    {reason:>15}: {data['count']:>3} trades | {data['wins']} wins | Avg: {avg:+.2f}% | Total: {data['total_pnl']:+.2f}%")
    
    print(f"\n{'='*70}")
    
    # Monthly projection
    daily_return = portfolio_return / 30
    monthly_proj = portfolio_return
    annual_proj = daily_return * 365
    print(f"  📅 Projections (if conditions persist):")
    print(f"    Daily avg:   {daily_return:+.3f}%")
    print(f"    Monthly:     {monthly_proj:+.2f}%")
    print(f"    Annual:      {annual_proj:+.2f}%")
    print(f"{'='*70}")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
