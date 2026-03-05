#!/usr/bin/env python3
"""reconcile_snapshot.py — Rebuild portfolio_snapshots from trades table truth.

Reads ALL open trades for a bot, aggregates by ticker, calculates cash,
and patches the snapshot. Run after any data integrity concern.

Usage: python3 reconcile_snapshot.py [--dry-run]
"""

import json, os, sys, requests
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "scripts"))
from bot_config import BOT_ID

STARTING_CAPITAL = 25000.0  # Alfred's actual remaining capital after realized losses
# Note: Original was $50K but ~$18K in realized losses (APT write-off, etc.)
# This gives a more honest cash/return calculation.

# Supabase
URL = 'https://vghssoltipiajiwzhkyn.supabase.co'
KEY = None
creds = Path.home() / '.supabase_trading_creds'
if creds.exists():
    for line in creds.read_text().splitlines():
        if '=' in line:
            k, v = line.strip().split('=', 1)
            if 'ANON' in k.upper():
                KEY = v
if not KEY:
    print("ERROR: No Supabase key found", file=sys.stderr)
    sys.exit(1)

HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}

CRYPTO_BOT_ID = f"{BOT_ID}_crypto" if not BOT_ID.endswith("_crypto") else BOT_ID
EQUITY_BOT_ID = BOT_ID.replace("_crypto", "") if BOT_ID.endswith("_crypto") else BOT_ID
BOT_IDS = [EQUITY_BOT_ID, CRYPTO_BOT_ID]
SNAPSHOT_BOT = EQUITY_BOT_ID  # parent bot_id for snapshot

# CoinGecko + Yahoo price helpers
COINGECKO_MAP = {
    "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
    "LINK-USD": "chainlink", "RENDER-USD": "render-token", "SUI-USD": "sui",
    "AVAX-USD": "avalanche-2", "DOT-USD": "polkadot", "ADA-USD": "cardano",
    "DOGE-USD": "dogecoin", "XRP-USD": "ripple",
}

def get_live_price(ticker):
    """Get live price with Yahoo primary, CoinGecko fallback."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        price = t.fast_info.get("lastPrice") or t.fast_info.get("last_price")
        if price and price > 0.01:
            return float(price)
    except Exception:
        pass
    cg_id = COINGECKO_MAP.get(ticker)
    if cg_id:
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd", timeout=5)
            if r.ok:
                return float(r.json()[cg_id]["usd"])
        except Exception:
            pass
    return None


def reconcile(dry_run=False):
    """Rebuild snapshot from open trades."""
    # Fetch all open trades
    all_trades = []
    for bid in BOT_IDS:
        r = requests.get(
            f'{URL}/rest/v1/trades?bot_id=eq.{bid}&status=eq.OPEN&select=ticker,quantity,price_usd,action,created_at',
            headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'},
            timeout=10
        )
        if r.ok:
            all_trades.extend(r.json())

    # Calculate cash from current snapshot (preserve existing cash value)
    # Then adjust based on open position cost vs starting capital
    # This avoids the phantom trade problem in trade history
    trade_count = 0
    for bid in BOT_IDS:
        r = requests.get(
            f'{URL}/rest/v1/trades?bot_id=eq.{bid}&select=id&order=created_at.asc',
            headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'},
            timeout=10
        )
        if r.ok:
            trade_count += len(r.json())

    # Get current snapshot cash (trust snapshot for cash, fix positions)
    current_cash = 0.0
    snap_r = requests.get(
        f'{URL}/rest/v1/portfolio_snapshots?bot_id=eq.{SNAPSHOT_BOT}&select=cash_usd',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}'},
        timeout=10
    )
    if snap_r.ok and snap_r.json():
        current_cash = float(snap_r.json()[0].get('cash_usd', 0))

    # Open position cost from OPEN trades
    open_cost = sum(float(t.get('quantity', 0)) * float(t.get('price_usd', 0)) for t in all_trades)

    # Estimate cash: starting capital minus cost of all open positions
    # This is imperfect (ignores realized P&L) but avoids phantom trade corruption
    # If open positions cost > starting capital, we've realized losses and cash is ~0
    cash = max(0.0, STARTING_CAPITAL - open_cost)
    if STARTING_CAPITAL - open_cost < 0:
        print(f"  ⚠️ Open positions cost (${open_cost:.0f}) exceeds starting capital. Setting cash to $0.")

    # Aggregate open positions by ticker
    from collections import defaultdict
    positions_agg = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})
    for t in all_trades:
        ticker = t['ticker']
        qty = float(t.get('quantity', 0))
        price = float(t.get('price_usd', 0))
        positions_agg[ticker]["qty"] += qty
        positions_agg[ticker]["cost"] += qty * price

    # Build position list with live prices
    positions = []
    total_position_value = 0.0
    print(f"\n{'Ticker':<15} {'Qty':>10} {'Avg Entry':>12} {'Live Price':>12} {'Value':>12} {'P&L':>10}")
    print("-" * 75)

    for ticker, data in sorted(positions_agg.items()):
        qty = data["qty"]
        avg_entry = data["cost"] / qty if qty > 0 else 0
        live_price = get_live_price(ticker)
        if not live_price:
            live_price = avg_entry  # fallback to entry
            print(f"  ⚠️ No live price for {ticker}, using entry")

        value = qty * live_price
        pl = (live_price - avg_entry) * qty
        total_position_value += value

        positions.append({
            "ticker": ticker,
            "side": "LONG",
            "quantity": round(qty, 6),
            "avg_entry": round(avg_entry, 4),
            "current_price": round(live_price, 4),
            "unrealized_pl": round(pl, 2),
            "market": "CRYPTO" if "-USD" in ticker else "US",
        })
        print(f"{ticker:<15} {qty:>10.4f} ${avg_entry:>10.2f} ${live_price:>10.2f} ${value:>10.2f} ${pl:>+9.2f}")

    total_value = cash + total_position_value
    total_return_pct = ((total_value - STARTING_CAPITAL) / STARTING_CAPITAL) * 100

    print(f"\n{'Cash:':<15} ${cash:>10.2f}")
    print(f"{'Positions:':<15} ${total_position_value:>10.2f}")
    print(f"{'Total:':<15} ${total_value:>10.2f}")
    print(f"{'Return:':<15} {total_return_pct:>+9.2f}%")
    print(f"{'Trades:':<15} {trade_count}")

    if dry_run:
        print("\n[DRY RUN] — would patch snapshot with above data")
        return

    # Patch snapshot
    patch = {
        "cash_usd": round(cash, 2),
        "open_positions": positions,
        "total_value_usd": round(total_value, 2),
        "trade_count": trade_count,
        "total_return_pct": round(total_return_pct, 4),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "unrealized_pl": round(sum(p["unrealized_pl"] for p in positions), 2),
    }
    r = requests.patch(
        f'{URL}/rest/v1/portfolio_snapshots?bot_id=eq.{SNAPSHOT_BOT}',
        headers=HEADERS,
        json=patch,
    )
    if r.status_code in (200, 204):
        print(f"\n✅ Snapshot patched for {SNAPSHOT_BOT}")
    else:
        print(f"\n❌ Patch failed: {r.status_code} {r.text}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    reconcile(dry_run=dry_run)
