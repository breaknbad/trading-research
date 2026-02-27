#!/usr/bin/env python3
"""Update competition dashboard data by running a paper trading session."""

import sys
import os
import json
import time
import warnings
import argparse
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent.parent))

from coinbase_client import fetch_candles
from indicators import add_all_multi_indicators
from regime import detect_regime
from multi_strategy import MultiStrategyConfig, _position_size

DATA_FILE = Path(__file__).parent / "competition_data.json"
ASSETS = ["POL-USD", "NEAR-USD", "BTC-USD", "SOL-USD", "XRP-USD",
          "ARB-USD", "LINK-USD", "DOT-USD", "ETH-USD", "AVAX-USD", "ALGO-USD"]

config = MultiStrategyConfig()


def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return None


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def get_data(product):
    df = fetch_candles(product, granularity="5m", days=2)
    df = add_all_multi_indicators(df)
    df = detect_regime(df)
    required = ["bb_lower", "bb_upper", "rsi", "adx", "atr", "ema_20", "macd_hist", "sma_50"]
    df = df.dropna(subset=required).reset_index(drop=True)
    return df


def run_session(bot_name, duration_seconds=300, check_interval=30):
    data = load_data()
    if not data:
        print("No competition_data.json found")
        return

    if bot_name not in data["bots"]:
        print(f"Bot '{bot_name}' not found")
        return

    bot = data["bots"][bot_name]
    bot["status"] = "active"
    initial_capital = bot["current_equity"]
    per_asset = initial_capital / len(ASSETS)

    state = {}
    for asset in ASSETS:
        state[asset] = {
            "equity": per_asset, "in_position": False, "entry_price": 0.0,
            "stop_price": 0.0, "best_price": 0.0, "position_type": None,
            "alloc": 1.0, "last_price": 0.0,
        }

    trades_this_session = []
    equity_snapshots = []

    print(f"Running {bot['name']} {bot['emoji']} for {duration_seconds}s")
    sys.stdout.flush()
    start = time.time()

    while time.time() - start < duration_seconds:
        now_iso = datetime.now(timezone.utc).isoformat()

        for asset in ASSETS:
            s = state[asset]
            ticker = asset.replace("-USD", "")
            try:
                df = get_data(asset)
                if df.empty:
                    continue
            except Exception as e:
                continue

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

            if s["in_position"]:
                if s["position_type"] == "short":
                    pnl_pct = (s["entry_price"] - price) / s["entry_price"] * 100
                    if price < s["best_price"]:
                        s["best_price"] = price
                        s["stop_price"] = min(s["stop_price"], price + 2.5 * atr)
                    if price >= s["stop_price"] or price <= s["entry_price"] - 2 * atr or (price <= bb_lower and rsi < 30):
                        realized = (s["entry_price"] - price) / s["entry_price"]
                        s["equity"] *= (1 + realized * s["alloc"])
                        trades_this_session.append({
                            "time": now_iso, "asset": ticker, "side": "short",
                            "pnl": round(realized * s["equity"], 2), "pnl_pct": round(pnl_pct, 3),
                            "entry_price": s["entry_price"], "exit_price": price
                        })
                        s["in_position"] = False
                        print(f"  CLOSE {ticker} SHORT {pnl_pct:+.3f}%")
                        sys.stdout.flush()

                elif s["position_type"] == "long":
                    pnl_pct = (price - s["entry_price"]) / s["entry_price"] * 100
                    if price > s["best_price"]:
                        s["best_price"] = price
                        s["stop_price"] = max(s["stop_price"], price - 2.5 * atr)
                    if price <= s["stop_price"] or price >= s["entry_price"] + 2 * atr or (price >= bb_upper and rsi > 70):
                        realized = (price - s["entry_price"]) / s["entry_price"]
                        s["equity"] *= (1 + realized * s["alloc"])
                        trades_this_session.append({
                            "time": now_iso, "asset": ticker, "side": "long",
                            "pnl": round(realized * s["equity"], 2), "pnl_pct": round(pnl_pct, 3),
                            "entry_price": s["entry_price"], "exit_price": price
                        })
                        s["in_position"] = False
                        print(f"  CLOSE {ticker} LONG {pnl_pct:+.3f}%")
                        sys.stdout.flush()
            else:
                vol_pct = atr / price * 100
                score = min(vol_pct * 10, 30)
                if adx > 25: score += 20
                if adx > 35: score += 10
                if rsi < 25 or rsi > 75: score += 20
                if abs(macd_hist) > 0: score += 10

                if score >= 25:
                    alloc_pct = min(0.05 + (score / 100) * 0.10, 0.15)
                    s["alloc"] = min(alloc_pct * 3, 1.0)

                    if regime in ("TRENDING_DOWN", "WEAK_TREND_DOWN") and adx > 20 and rsi < 55:
                        s["entry_price"] = price
                        s["stop_price"] = price + 2.5 * atr
                        s["best_price"] = price
                        s["position_type"] = "short"
                        s["in_position"] = True
                        print(f"  SHORT {ticker} @ ${price:,.4f}")
                        sys.stdout.flush()

                    elif regime in ("TRENDING_UP", "WEAK_TREND_UP") and adx > 20 and rsi > 45 and price <= ema20 * 1.01:
                        s["entry_price"] = price
                        s["stop_price"] = price - 2.5 * atr
                        s["best_price"] = price
                        s["position_type"] = "long"
                        s["in_position"] = True
                        print(f"  LONG {ticker} @ ${price:,.4f}")
                        sys.stdout.flush()

                    elif regime == "RANGING":
                        if price <= bb_lower and rsi < 30:
                            s["entry_price"] = price
                            s["stop_price"] = price - 2.5 * atr
                            s["best_price"] = price
                            s["position_type"] = "long"
                            s["in_position"] = True
                            print(f"  MR LONG {ticker} @ ${price:,.4f}")
                            sys.stdout.flush()
                        elif price >= bb_upper and rsi > 70:
                            s["entry_price"] = price
                            s["stop_price"] = price + 2.5 * atr
                            s["best_price"] = price
                            s["position_type"] = "short"
                            s["in_position"] = True
                            print(f"  MR SHORT {ticker} @ ${price:,.4f}")
                            sys.stdout.flush()

            time.sleep(0.2)

        total = sum(s["equity"] for s in state.values())
        equity_snapshots.append({"time": now_iso, "value": round(total, 2)})
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s/{duration_seconds}s] Equity: ${total:,.2f}")
        sys.stdout.flush()

        # Save after each check (including any new trades)
        bot["current_equity"] = round(total, 2)
        bot["equity_curve"].extend(equity_snapshots[-1:])
        if trades_this_session:
            bot["total_trades"] += len(trades_this_session)
            bot["winning_trades"] += sum(1 for t in trades_this_session if t["pnl_pct"] > 0)
            all_pnls = [t["pnl_pct"] for t in (bot["trade_log"] + trades_this_session)]
            if all_pnls:
                bot["best_trade_pct"] = max(all_pnls)
                bot["worst_trade_pct"] = min(all_pnls)
            bot["trade_log"].extend(trades_this_session)
            for t in trades_this_session:
                asset = t["asset"]
                if asset not in bot["asset_breakdown"]:
                    bot["asset_breakdown"][asset] = {"trades": 0, "pnl": 0, "pnl_pct": 0}
                bot["asset_breakdown"][asset]["trades"] += 1
                bot["asset_breakdown"][asset]["pnl_pct"] += t["pnl_pct"]
            trades_this_session = []
        save_data(data)

        remaining = duration_seconds - (time.time() - start)
        if remaining > check_interval:
            time.sleep(check_interval)

    final_equity = sum(s["equity"] for s in state.values())
    bot["current_equity"] = round(final_equity, 2)
    bot["total_trades"] += len(trades_this_session)
    bot["winning_trades"] += sum(1 for t in trades_this_session if t["pnl_pct"] > 0)

    all_pnls = [t["pnl_pct"] for t in (bot["trade_log"] + trades_this_session)]
    if all_pnls:
        bot["best_trade_pct"] = max(all_pnls)
        bot["worst_trade_pct"] = min(all_pnls)

    bot["trade_log"].extend(trades_this_session)

    for t in trades_this_session:
        asset = t["asset"]
        if asset not in bot["asset_breakdown"]:
            bot["asset_breakdown"][asset] = {"trades": 0, "pnl": 0, "pnl_pct": 0}
        bot["asset_breakdown"][asset]["trades"] += 1
        bot["asset_breakdown"][asset]["pnl_pct"] += t["pnl_pct"]

    save_data(data)
    ret = (final_equity / initial_capital - 1) * 100
    print(f"Done: ${final_equity:,.2f} ({ret:+.4f}%) | {len(trades_this_session)} new trades")
    sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", default="alfred", help="Bot name")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    args = parser.parse_args()
    run_session(args.bot, args.duration, args.interval)
