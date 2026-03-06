#!/usr/bin/env python3
"""auto_trader.py — Autonomous trade scanner + executor.
Runs on a timer. No AI in the loop.

Reads market-state.json, runs factor_engine on all tickers,
executes trades that pass threshold, posts results to Supabase.

Usage: python3 auto_trader.py --bot-id tars [--dry-run]
"""

import argparse, json, os, sys, subprocess, time, uuid
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
MARKET_STATE = WORKSPACE / "market-state.json"
TRADING_STATE = WORKSPACE / "trading-state.json"
LOG_FILE = WORKSPACE / "logs" / "auto-trader.log"

try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
except ImportError:
    pass

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Config
SCORE_THRESHOLD = 60  # Factor score to trigger trade (lowered from 65 for more activity)
MAX_POSITION_PCT = 0.10  # 10% max per position
MAX_DEPLOYED_PCT = 0.70  # 70% max deployed
MAX_POSITIONS = 8  # Don't hold more than 8 positions
STOP_PCT = 0.02  # 2% stop loss
TARGET_PCT = 0.03  # 3% profit target

# Tickers to scan
CRYPTO_TICKERS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "ADA", "DOGE", "SUI"]
# Stock tickers scanned during market hours only
STOCK_TICKERS = ["SPY", "QQQ", "NVDA", "GLD", "TLT", "XLV"]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass


def load_market_state():
    if not MARKET_STATE.exists():
        log("ERROR: market-state.json not found")
        return None
    age = time.time() - MARKET_STATE.stat().st_mtime
    if age > 120:
        log(f"WARNING: market-state.json is {age:.0f}s old (stale)")
        return None
    with open(MARKET_STATE) as f:
        return json.load(f)


def get_portfolio(bot_id):
    """Get current portfolio from Supabase."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=cash_usd,total_value_usd,open_positions",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            timeout=10
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        log(f"ERROR getting portfolio: {e}")
    return None


def get_open_tickers(portfolio):
    """Get set of tickers already in portfolio."""
    positions = portfolio.get("open_positions") or []
    if isinstance(positions, str):
        try:
            positions = json.loads(positions)
        except:
            positions = []
    return {p.get("ticker", "").replace("-USD", "") for p in positions}


def run_factor_engine(ticker, side):
    """Run factor engine wrapper, return score and recommendation."""
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "run_factor_engine.py"),
             "--ticker", ticker, "--side", side],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode <= 2:  # 0=GO, 1=REJECT, 2=CAUTION
            data = json.loads(result.stdout)
            return data.get("total_score", 0), data.get("recommendation", "REJECT"), data
        else:
            return 0, "ERROR", {}
    except Exception as e:
        log(f"Factor engine error for {ticker}: {e}")
        return 0, "ERROR", {}


def execute_trade(bot_id, ticker, action, price, quantity, total, reason, market="crypto"):
    """Write trade to Supabase."""
    trade_id = f"{bot_id}-w2-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "bot_id": bot_id,
        "trade_id": trade_id,
        "ticker": f"{ticker}-USD" if "-USD" not in ticker else ticker,
        "action": action,
        "price_usd": price,
        "quantity": quantity,
        "total_usd": total,
        "market": market,
        "reason": reason,
        "timestamp": now,
        "status": "OPEN"
    }
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/trades",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation"
            },
            json=payload, timeout=10
        )
        if r.status_code in (200, 201):
            log(f"TRADE EXECUTED: {action} {quantity} {ticker} @ ${price:.2f} (${total:.2f}) — {reason}")
            return True
        else:
            log(f"TRADE FAILED: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        log(f"TRADE ERROR: {e}")
        return False


def update_portfolio(bot_id, portfolio, ticker, action, price, quantity, total):
    """Update portfolio snapshot after trade."""
    now = datetime.now(timezone.utc).isoformat()
    cash = portfolio.get("cash_usd", 50000)
    positions = portfolio.get("open_positions") or []
    if isinstance(positions, str):
        try:
            positions = json.loads(positions)
        except:
            positions = []

    if action == "BUY":
        cash -= total
        positions.append({
            "ticker": f"{ticker}-USD" if "-USD" not in ticker else ticker,
            "quantity": quantity,
            "avg_entry": price,
            "current_price": price,
            "unrealized_pl": 0,
            "side": "LONG",
            "market": "crypto",
            "stop": round(price * (1 - STOP_PCT), 2),
            "target": round(price * (1 + TARGET_PCT), 2)
        })
    elif action == "SELL":
        cash += total

    trade_count = (portfolio.get("trade_count") or 0) + 1

    try:
        requests.patch(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "cash_usd": round(cash, 2),
                "total_value_usd": round(cash + sum(
                    p.get("quantity", 0) * p.get("current_price", 0) for p in positions
                ), 2),
                "open_positions": positions,
                "trade_count": trade_count,
                "last_updated": now
            },
            timeout=10
        )
    except Exception as e:
        log(f"Portfolio update error: {e}")


def check_stops(bot_id, portfolio, market_state):
    """Check if any open positions hit their stop loss."""
    positions = portfolio.get("open_positions") or []
    if isinstance(positions, str):
        try:
            positions = json.loads(positions)
        except:
            return

    tickers = market_state.get("tickers", {})
    for pos in positions:
        ticker_raw = pos.get("ticker", "").replace("-USD", "")
        current = tickers.get(ticker_raw, {}).get("price")
        if not current:
            continue

        stop = pos.get("stop", 0)
        side = pos.get("side", "LONG")

        if side == "LONG" and stop > 0 and current <= stop:
            qty = pos.get("quantity", 0)
            total = current * qty
            log(f"STOP HIT: {ticker_raw} at ${current:.2f} (stop was ${stop:.2f})")
            execute_trade(bot_id, ticker_raw, "SELL", current, qty, total,
                         f"Stop loss hit. Entry {pos.get('avg_entry')}, stop {stop}, current {current}")

        elif side == "SHORT" and stop > 0 and current >= stop:
            qty = pos.get("quantity", 0)
            total = current * qty
            log(f"STOP HIT (SHORT): {ticker_raw} at ${current:.2f} (stop was ${stop:.2f})")
            execute_trade(bot_id, ticker_raw, "COVER", current, qty, total,
                         f"Short stop hit. Entry {pos.get('avg_entry')}, stop {stop}, current {current}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bot_id = args.bot_id
    log(f"=== Auto-trader scan for {bot_id} ===")

    # Load market state
    state = load_market_state()
    if not state:
        log("No valid market state. Exiting.")
        return

    tickers_data = state.get("tickers", {})
    log(f"Market data: {len(tickers_data)} tickers, updated {state.get('updated', '?')}")

    # Get portfolio
    portfolio = get_portfolio(bot_id)
    if not portfolio:
        log("Could not load portfolio. Exiting.")
        return

    cash = portfolio.get("cash_usd", 0)
    total_value = portfolio.get("total_value_usd", 50000)
    open_tickers = get_open_tickers(portfolio)
    num_positions = len(open_tickers)

    log(f"Portfolio: ${cash:.0f} cash, ${total_value:.0f} total, {num_positions} positions, open: {open_tickers}")

    # Check stops first
    check_stops(bot_id, portfolio, state)

    # Check deployment limits
    deployed_pct = (total_value - cash) / total_value if total_value > 0 else 0
    if deployed_pct >= MAX_DEPLOYED_PCT:
        log(f"Deployment at {deployed_pct:.0%} (max {MAX_DEPLOYED_PCT:.0%}). No new entries.")
        return

    if num_positions >= MAX_POSITIONS:
        log(f"Max positions ({MAX_POSITIONS}) reached. No new entries.")
        return

    # Determine which tickers to scan
    hour_utc = datetime.now(timezone.utc).hour
    # Crypto always, stocks during US market hours (14:30-21:00 UTC = 9:30-4:00 ET)
    scan_tickers = list(CRYPTO_TICKERS)
    if 14 <= hour_utc <= 21:
        scan_tickers.extend(STOCK_TICKERS)

    # Scan and score
    candidates = []
    for ticker in scan_tickers:
        if ticker in open_tickers:
            continue  # Already holding
        if ticker not in tickers_data:
            continue  # No price data

        price_data = tickers_data[ticker]
        change = price_data.get("change_24h_pct", 0)

        # Determine side based on momentum
        side = "long" if change > -2 else "short"  # Default long unless heavily bearish

        score, rec, details = run_factor_engine(ticker, side)
        if score >= SCORE_THRESHOLD:
            candidates.append((score, ticker, side, price_data.get("price", 0), details))
            log(f"  {ticker} {side}: {score:.1f}/100 → {rec}")
        else:
            log(f"  {ticker} {side}: {score:.1f}/100 → SKIP")

    # Sort by score descending, take top candidates
    candidates.sort(reverse=True)
    max_new_trades = min(3, MAX_POSITIONS - num_positions)  # Max 3 new trades per cycle

    trades_made = 0
    for score, ticker, side, price, details in candidates[:max_new_trades]:
        if cash < total_value * 0.05:  # Keep 5% cash minimum
            log("Cash too low for new trades.")
            break

        # Size: score-based (higher score = bigger position)
        if score >= 80:
            size_pct = MAX_POSITION_PCT  # 10% — conviction
        elif score >= 70:
            size_pct = 0.07  # 7% — confirm
        else:
            size_pct = 0.04  # 4% — scout

        position_usd = min(total_value * size_pct, cash * 0.9)
        if position_usd < 100:
            continue

        quantity = position_usd / price if price > 0 else 0
        if quantity <= 0:
            continue

        # Round quantity sensibly
        if price > 10000:
            quantity = round(quantity, 4)
        elif price > 100:
            quantity = round(quantity, 2)
        elif price > 1:
            quantity = round(quantity, 1)
        else:
            quantity = round(quantity, 0)

        total = round(quantity * price, 2)
        action = "BUY" if side == "long" else "SHORT"
        reason = f"Auto-trader: {ticker} {side} score {score:.0f}/100. 24h chg: {details.get('category_scores', {})}"

        if args.dry_run:
            log(f"DRY RUN: Would {action} {quantity} {ticker} @ ${price:.2f} (${total:.2f})")
        else:
            if execute_trade(bot_id, ticker, action, price, quantity, total, reason):
                update_portfolio(bot_id, portfolio, ticker, action, price, quantity, total)
                trades_made += 1
                cash -= total  # Track for next iteration

    log(f"Scan complete. {trades_made} trades executed, {len(candidates)} candidates found.")


if __name__ == "__main__":
    main()
