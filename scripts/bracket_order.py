#!/usr/bin/env python3
"""
Bracket Order — Atomic Stop + Target with Every BUY
====================================================
Upgrade #3: Every BUY auto-sets a stop-loss and profit-take target.
Wraps execute_trade.py — fires the BUY, then writes bracket levels to Supabase.

Bracket levels stored in `trade_brackets` table (or as metadata on the trade).
trailing_stop.py (#7) can override the initial bracket stop.

Usage:
  python3 bracket_order.py --ticker NVDA --price 220 --quantity 25 --market STOCK \\
    --stop-pct 2.0 --target-pct 5.0 --reason "Breakout buy"
  python3 bracket_order.py --once  # Dry run / test mode
"""

import argparse, json, os, sys, subprocess, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID

WORKSPACE = Path(__file__).resolve().parent.parent
BRACKETS_PATH = WORKSPACE / "logs" / "brackets.json"
LOG_PATH = WORKSPACE / "logs" / "bracket_order.log"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = ""
try:
    from dotenv import load_dotenv
    load_dotenv(WORKSPACE / ".env")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
except Exception:
    pass

DEFAULT_STOP_PCT = 2.0    # 2% stop loss
DEFAULT_TARGET_PCT = 5.0  # 5% profit target

os.makedirs(WORKSPACE / "logs", exist_ok=True)


def log(msg):
    ts = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def execute_buy(ticker, price, quantity, market, reason):
    """Execute the BUY via execute_trade.py."""
    cmd = [
        sys.executable, str(WORKSPACE / "scripts" / "execute_trade.py"),
        "--ticker", ticker, "--action", "BUY",
        "--quantity", str(quantity), "--price", f"{price:.2f}",
        "--market", market, "--bot-id", BOT_ID,
        "--reason", f"[BRACKET] {reason}",
    ]
    log(f"Executing BUY: {quantity} {ticker} @ ${price:.2f}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(WORKSPACE))
    if result.returncode != 0:
        log(f"❌ BUY FAILED: {result.stderr.strip() or result.stdout.strip()}")
        return False
    log(f"✅ BUY SUCCESS: {result.stdout.strip()}")
    return True


def set_bracket(ticker, entry_price, quantity, stop_pct, target_pct, market):
    """Write bracket levels to local state + Supabase."""
    stop_price = round(entry_price * (1 - stop_pct / 100), 4)
    target_price = round(entry_price * (1 + target_pct / 100), 4)

    bracket = {
        "ticker": ticker,
        "bot_id": BOT_ID,
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_price": stop_price,
        "stop_pct": stop_pct,
        "target_price": target_price,
        "target_pct": target_pct,
        "market": market,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ACTIVE",
    }

    # Local state
    try:
        brackets = json.load(open(BRACKETS_PATH)) if BRACKETS_PATH.exists() else {}
    except Exception:
        brackets = {}
    key = f"{BOT_ID}:{ticker}"
    brackets[key] = bracket
    with open(BRACKETS_PATH, "w") as f:
        json.dump(brackets, f, indent=2)

    log(f"📐 BRACKET SET: {ticker} entry=${entry_price:.2f} stop=${stop_price:.2f} ({stop_pct}%) target=${target_price:.2f} ({target_pct}%)")

    # Supabase (best effort — trailing_stop.py and stop_check.py read local state)
    if SUPABASE_KEY:
        try:
            import urllib.request
            url = f"{SUPABASE_URL}/rest/v1/trade_brackets"
            req = urllib.request.Request(url, method="POST",
                data=json.dumps(bracket).encode(),
                headers={
                    "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json", "Prefer": "return=minimal",
                })
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            log(f"Supabase bracket write failed (non-blocking): {e}")

    return bracket


def main():
    parser = argparse.ArgumentParser(description="Bracket Order — BUY + auto stop/target")
    parser.add_argument("--ticker", help="Ticker symbol")
    parser.add_argument("--price", type=float, help="Entry price")
    parser.add_argument("--quantity", type=float, help="Quantity")
    parser.add_argument("--market", default="STOCK", choices=["STOCK", "CRYPTO"])
    parser.add_argument("--stop-pct", type=float, default=DEFAULT_STOP_PCT)
    parser.add_argument("--target-pct", type=float, default=DEFAULT_TARGET_PCT)
    parser.add_argument("--reason", default="Bracket order")
    parser.add_argument("--once", action="store_true", help="Dry run test")
    args = parser.parse_args()

    if args.once:
        log("Dry run mode — testing bracket logic")
        bracket = set_bracket("TEST", 100.0, 10, 2.0, 5.0, "STOCK")
        log(f"Test bracket: {json.dumps(bracket, indent=2)}")
        return

    if not args.ticker or not args.price or not args.quantity:
        parser.error("--ticker, --price, and --quantity are required")

    # Execute BUY
    success = execute_buy(args.ticker, args.price, args.quantity, args.market, args.reason)
    if not success:
        log("Bracket aborted — BUY failed")
        sys.exit(1)

    # Set bracket
    set_bracket(args.ticker, args.price, args.quantity, args.stop_pct, args.target_pct, args.market)
    log("✅ Bracket order complete")


if __name__ == "__main__":
    main()
