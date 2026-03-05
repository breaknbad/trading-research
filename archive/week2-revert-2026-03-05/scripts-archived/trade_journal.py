#!/usr/bin/env python3
"""
Trade Journal — captures thesis at entry, reviews at exit.
Every trade gets a 1-line thesis. At exit, compare thesis to reality.

Usage:
  python3 trade_journal.py --entry BTC-USD alfred "Oversold bounce, RSI 25, negative funding = squeeze"
  python3 trade_journal.py --exit BTC-USD alfred 68500 "Thesis confirmed, took profit at +3%"
  python3 trade_journal.py --review                    # Review all open entries
  python3 trade_journal.py --score                     # Score thesis accuracy
  python3 trade_journal.py --check BTC-USD             # Check if ticker has failed thesis (for re-entry guard)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_FILE = Path(__file__).parent.parent / "trade_journal.json"


def load_journal():
    if JOURNAL_FILE.exists():
        try:
            return json.loads(JOURNAL_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"entries": [], "exits": []}


def save_journal(data):
    JOURNAL_FILE.write_text(json.dumps(data, indent=2))


def add_entry(ticker: str, bot: str, thesis: str, price: float = None):
    journal = load_journal()
    entry = {
        "ticker": ticker.upper(),
        "bot": bot.lower(),
        "thesis": thesis,
        "entry_price": price,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "status": "OPEN"
    }
    journal["entries"].append(entry)
    save_journal(journal)
    print(f"📝 Entry logged: {ticker.upper()} by {bot} — \"{thesis}\"")
    return entry


def add_exit(ticker: str, bot: str, exit_price: float, outcome: str):
    journal = load_journal()
    ticker = ticker.upper()
    bot = bot.lower()

    # Find matching open entry
    matched = None
    for i, entry in enumerate(journal["entries"]):
        if entry["ticker"] == ticker and entry["bot"] == bot and entry["status"] == "OPEN":
            matched = i
            break

    if matched is not None:
        entry = journal["entries"][matched]
        entry["status"] = "CLOSED"
        entry["exit_price"] = exit_price
        entry["exit_time"] = datetime.now(timezone.utc).isoformat()
        entry["outcome"] = outcome

        # Calculate if thesis was right
        if entry.get("entry_price") and exit_price:
            pnl_pct = (exit_price - entry["entry_price"]) / entry["entry_price"] * 100
            entry["pnl_pct"] = round(pnl_pct, 2)
            entry["thesis_correct"] = pnl_pct > 0  # Simple: made money = thesis correct

        print(f"📝 Exit logged: {ticker} by {bot}")
        print(f"   Entry thesis: \"{entry['thesis']}\"")
        print(f"   Outcome: {outcome}")
        if "pnl_pct" in entry:
            print(f"   P&L: {entry['pnl_pct']:+.2f}% | Thesis {'✅ CORRECT' if entry.get('thesis_correct') else '❌ WRONG'}")
    else:
        # Log exit without matching entry
        journal["exits"].append({
            "ticker": ticker,
            "bot": bot,
            "exit_price": exit_price,
            "outcome": outcome,
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "note": "No matching entry found"
        })
        print(f"⚠️  Exit logged for {ticker} but no matching entry found.")

    save_journal(journal)


def review_open():
    journal = load_journal()
    open_entries = [e for e in journal["entries"] if e["status"] == "OPEN"]

    if not open_entries:
        print("No open trade journal entries.")
        return

    print(f"📋 Open Trade Journal — {len(open_entries)} entries")
    print("-" * 70)
    for e in open_entries:
        age = ""
        try:
            entry_time = datetime.fromisoformat(e["entry_time"])
            age_mins = (datetime.now(timezone.utc) - entry_time).total_seconds() / 60
            age = f" ({age_mins:.0f}m ago)"
        except (ValueError, KeyError):
            pass
        price_str = f" @ ${e['entry_price']:,.2f}" if e.get('entry_price') else ""
        print(f"  {e['ticker']:10s} {e['bot']:8s}{price_str}{age}")
        print(f"  Thesis: \"{e['thesis']}\"")
        print()


def check_ticker(ticker: str):
    """Check if a ticker has recent failed theses (re-entry guard)."""
    journal = load_journal()
    ticker = ticker.upper()
    today = datetime.now().strftime("%Y-%m-%d")

    recent_failures = []
    for e in journal["entries"]:
        if (e["ticker"] == ticker and
            e["status"] == "CLOSED" and
            e.get("thesis_correct") is False and
            e.get("exit_time", "").startswith(today)):
            recent_failures.append(e)

    if recent_failures:
        print(f"⚠️  {ticker} has {len(recent_failures)} failed thesis(es) today:")
        for f in recent_failures:
            print(f"   \"{f['thesis']}\" → {f['outcome']} ({f.get('pnl_pct', '?')}%)")
        print(f"   Consider whether your new thesis is DIFFERENT from these.")
        return False
    else:
        print(f"✅ {ticker} — no failed theses today. Clear to enter.")
        return True


def score():
    journal = load_journal()
    closed = [e for e in journal["entries"] if e["status"] == "CLOSED" and "thesis_correct" in e]

    if not closed:
        print("No scored entries yet.")
        return

    correct = sum(1 for e in closed if e["thesis_correct"])
    total = len(closed)
    pct = correct / total * 100

    print(f"📊 Thesis Scorecard: {correct}/{total} correct ({pct:.0f}%)")

    # Per-bot breakdown
    bots = set(e["bot"] for e in closed)
    for bot in sorted(bots):
        bot_entries = [e for e in closed if e["bot"] == bot]
        bot_correct = sum(1 for e in bot_entries if e["thesis_correct"])
        print(f"   {bot}: {bot_correct}/{len(bot_entries)} ({bot_correct/len(bot_entries)*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="Trade Journal")
    parser.add_argument("--entry", nargs=3, metavar=("TICKER", "BOT", "THESIS"),
                        help="Log entry with thesis")
    parser.add_argument("--price", type=float, help="Entry price (with --entry)")
    parser.add_argument("--exit", nargs=4, metavar=("TICKER", "BOT", "EXIT_PRICE", "OUTCOME"),
                        help="Log exit with outcome")
    parser.add_argument("--review", action="store_true", help="Review open entries")
    parser.add_argument("--check", help="Check ticker for failed theses (re-entry guard)")
    parser.add_argument("--score", action="store_true", help="Score thesis accuracy")

    args = parser.parse_args()

    if args.entry:
        ticker, bot, thesis = args.entry
        add_entry(ticker, bot, thesis, args.price)
    elif args.exit:
        ticker, bot, price, outcome = args.exit
        add_exit(ticker, bot, float(price), outcome)
    elif args.review:
        review_open()
    elif args.check:
        ok = check_ticker(args.check)
        sys.exit(0 if ok else 1)
    elif args.score:
        score()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
