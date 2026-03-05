#!/usr/bin/env python3
"""
risk_calc.py — Fleet-wide crypto risk calculator.

Pure math, no AI, no pandas/numpy. Designed to run every 5 min via cron/launchd.

Reads:
  - market-state.json (local file with prices, positions, optional rolling price history)
  - Supabase tables: crypto_positions, trades, portfolio_snapshots

Outputs:
  - risk-state.json (atomic write via .tmp + rename)

Fields in risk-state.json:
  - fleet_heat: total stop exposure as % of total portfolio value
  - per_bot_exposure: dict of bot_id → {long_exposure, short_exposure, net_exposure, heat}
  - correlation_matrix: pairwise correlation of position returns
  - drawdown_velocity: portfolio loss rate over rolling 30-min window
  - concentration_score: largest position %, top-3 concentration %
  - timestamp: ISO 8601 freshness timestamp

Usage:
  python3 risk_calc.py                          # uses defaults
  python3 risk_calc.py --market market-state.json --output risk-state.json

Supabase connection string read from ~/.supabase_db_url (single line, postgresql://... format).
"""

import json
import logging
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [risk_calc] %(levelname)s %(message)s", stream=sys.stderr)
log = logging.getLogger("risk_calc")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MARKET = SCRIPT_DIR / "market-state.json"
DEFAULT_OUTPUT = SCRIPT_DIR / "risk-state.json"
DB_URL_FILE = Path.home() / ".supabase_db_url"

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_url():
    try:
        return DB_URL_FILE.read_text().strip()
    except FileNotFoundError:
        log.warning("No ~/.supabase_db_url found — Supabase queries disabled")
        return None


def query_db(conn_str, sql, params=None):
    """Run a query via psycopg2 if available, else return empty list."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        log.warning("psycopg2 not installed — skipping DB query")
        return []
    try:
        conn = psycopg2.connect(conn_str, connect_timeout=10)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        log.error("DB query failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# Math helpers (no numpy)
# ---------------------------------------------------------------------------

def mean(xs):
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def pearson(xs, ys):
    """Pearson correlation coefficient. Returns None if undefined."""
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def returns_from_prices(prices):
    """Convert price series to simple return series."""
    if len(prices) < 2:
        return []
    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------

def load_market_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error("Failed to load market-state.json: %s", e)
        return {}


def fetch_positions(conn_str):
    """Fetch open positions from crypto_positions AND trades tables."""
    if not conn_str:
        return []
    # Crypto positions
    crypto = query_db(conn_str, """
        SELECT *, 'crypto' AS market FROM crypto_positions
        WHERE status = 'open' OR closed_at IS NULL
        ORDER BY bot_id, symbol
    """)
    # Equity positions
    equities = query_db(conn_str, """
        SELECT *, 'equities' AS market FROM trades
        WHERE action = 'BUY' AND status = 'open'
        ORDER BY bot_id, ticker
    """)
    return (crypto or []) + (equities or [])


def fetch_portfolio_snapshots(conn_str, minutes=35):
    """Fetch recent portfolio snapshots for drawdown velocity."""
    if not conn_str:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = query_db(conn_str, """
        SELECT * FROM portfolio_snapshots
        WHERE created_at >= %s
        ORDER BY created_at ASC
    """, (cutoff,))
    return rows


def calc_per_bot_exposure(positions, prices):
    """Calculate per-bot exposure from positions list."""
    bots = {}
    for pos in positions:
        bot = pos.get("bot_id", "unknown")
        symbol = pos.get("symbol", "")
        side = pos.get("side", "long").lower()
        qty = float(pos.get("quantity", 0) or 0)
        entry = float(pos.get("price_usd", pos.get("entry_price", 0)) or 0)
        stop = pos.get("stop_price")
        price = prices.get(symbol, entry)
        notional = abs(qty * price)

        if bot not in bots:
            bots[bot] = {"long_exposure": 0.0, "short_exposure": 0.0, "stop_exposure": 0.0}

        if side in ("long", "buy"):
            bots[bot]["long_exposure"] += notional
        else:
            bots[bot]["short_exposure"] += notional

        # Stop exposure = loss if stop hit
        if stop is not None:
            stop = float(stop)
            if side in ("long", "buy"):
                loss = max(0, (price - stop) * abs(qty))
            else:
                loss = max(0, (stop - price) * abs(qty))
            bots[bot]["stop_exposure"] += loss

    # Derive net exposure and heat
    result = {}
    for bot, exp in bots.items():
        net = exp["long_exposure"] - exp["short_exposure"]
        total = exp["long_exposure"] + exp["short_exposure"]
        heat = exp["stop_exposure"] / total if total > 0 else 0.0
        result[bot] = {
            "long_exposure": round(exp["long_exposure"], 2),
            "short_exposure": round(exp["short_exposure"], 2),
            "net_exposure": round(net, 2),
            "heat": round(heat, 4),
        }
    return result


def calc_fleet_heat(per_bot):
    """Total stop exposure as % of total portfolio value."""
    total_exp = sum(b["long_exposure"] + b["short_exposure"] for b in per_bot.values())
    # Heat weighted by exposure
    if total_exp == 0:
        return 0.0
    weighted = sum(b["heat"] * (b["long_exposure"] + b["short_exposure"]) for b in per_bot.values())
    return round(weighted / total_exp, 4)


def calc_concentration(positions, prices):
    """Largest single position as % of portfolio, top-3 concentration."""
    notionals = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        qty = float(pos.get("quantity", 0) or 0)
        entry = float(pos.get("price_usd", pos.get("entry_price", 0)) or 0)
        price = prices.get(symbol, entry)
        notionals.append(abs(qty * price))
    total = sum(notionals)
    if total == 0:
        return {"max_single_pct": 0.0, "top3_pct": 0.0, "total_notional": 0.0}
    notionals.sort(reverse=True)
    max_single = notionals[0] / total
    top3 = sum(notionals[:3]) / total
    return {
        "max_single_pct": round(max_single, 4),
        "top3_pct": round(top3, 4),
        "total_notional": round(total, 2),
    }


def calc_correlation_matrix(positions, market_state):
    """Build pairwise correlation matrix from rolling price data."""
    # Extract rolling prices from market_state
    price_history = market_state.get("price_history", {})
    symbols = list({pos.get("symbol", "") for pos in positions if pos.get("symbol")})
    symbols.sort()

    matrix = {}
    for i, s1 in enumerate(symbols):
        row = {}
        for j, s2 in enumerate(symbols):
            if s1 == s2:
                row[s2] = 1.0
                continue
            p1 = price_history.get(s1, [])
            p2 = price_history.get(s2, [])
            if p1 and p2:
                r1 = returns_from_prices(p1)
                r2 = returns_from_prices(p2)
                c = pearson(r1, r2)
                row[s2] = round(c, 4) if c is not None else None
            else:
                # Flag as same asset class if symbols share base
                base1 = s1.replace("USDT", "").replace("USD", "").replace("/", "")
                base2 = s2.replace("USDT", "").replace("USD", "").replace("/", "")
                row[s2] = "same_base" if base1 == base2 else None
        matrix[s1] = row
    return matrix


def calc_drawdown_velocity(snapshots):
    """Rate of portfolio loss over rolling 30-min window."""
    if len(snapshots) < 2:
        return {"drawdown_pct": None, "velocity_per_min": None, "window_minutes": None, "note": "insufficient snapshots"}

    latest = snapshots[-1]
    latest_val = float(latest.get("total_value", 0) or latest.get("portfolio_value", 0) or 0)
    latest_ts = latest.get("created_at")

    # Find snapshot closest to 30 min ago
    target_time = None
    if isinstance(latest_ts, str):
        try:
            from datetime import datetime as dt
            latest_dt = dt.fromisoformat(latest_ts.replace("Z", "+00:00"))
            target_time = latest_dt - timedelta(minutes=30)
        except Exception:
            pass
    elif hasattr(latest_ts, 'timestamp'):
        target_time = latest_ts - timedelta(minutes=30)
        latest_dt = latest_ts

    if target_time is None:
        # Fallback: just compare first and last
        earliest = snapshots[0]
        earliest_val = float(earliest.get("total_value", 0) or earliest.get("portfolio_value", 0) or 0)
        if earliest_val == 0:
            return {"drawdown_pct": 0.0, "velocity_per_min": 0.0, "window_minutes": None}
        dd = (latest_val - earliest_val) / earliest_val
        return {"drawdown_pct": round(dd, 4), "velocity_per_min": None, "window_minutes": None}

    # Find closest snapshot to target_time
    best = None
    best_dist = float("inf")
    for s in snapshots:
        ts = s.get("created_at")
        if isinstance(ts, str):
            try:
                sdt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
        elif hasattr(ts, 'timestamp'):
            sdt = ts
        else:
            continue
        dist = abs((sdt - target_time).total_seconds())
        if dist < best_dist:
            best_dist = dist
            best = s
            best_dt = sdt

    if best is None:
        return {"drawdown_pct": None, "velocity_per_min": None, "window_minutes": None}

    ref_val = float(best.get("total_value", 0) or best.get("portfolio_value", 0) or 0)
    if ref_val == 0:
        return {"drawdown_pct": 0.0, "velocity_per_min": 0.0, "window_minutes": 0}

    dd = (latest_val - ref_val) / ref_val
    elapsed_min = (latest_dt - best_dt).total_seconds() / 60.0
    velocity = dd / elapsed_min if elapsed_min > 0 else 0.0

    return {
        "drawdown_pct": round(dd, 4),
        "velocity_per_min": round(velocity, 6),
        "window_minutes": round(elapsed_min, 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fleet-wide crypto risk calculator")
    parser.add_argument("--market", default=str(DEFAULT_MARKET), help="Path to market-state.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output path for risk-state.json")
    args = parser.parse_args()

    market_state = load_market_state(args.market)
    prices = market_state.get("prices", {})
    conn_str = get_db_url()

    # Merge positions: from market-state.json and/or Supabase
    positions = market_state.get("positions", [])
    db_positions = fetch_positions(conn_str)
    if db_positions:
        # Prefer DB positions, merge by dedup on (bot_id, symbol)
        seen = {(p.get("bot_id"), p.get("symbol")) for p in db_positions}
        for p in positions:
            key = (p.get("bot_id"), p.get("symbol"))
            if key not in seen:
                db_positions.append(p)
        positions = db_positions
        log.info("Loaded %d positions from DB + market-state", len(positions))
    else:
        log.info("Using %d positions from market-state.json only", len(positions))

    per_bot = calc_per_bot_exposure(positions, prices)
    fleet_heat = calc_fleet_heat(per_bot)
    concentration = calc_concentration(positions, prices)
    corr_matrix = calc_correlation_matrix(positions, market_state)

    snapshots = fetch_portfolio_snapshots(conn_str)
    drawdown = calc_drawdown_velocity(snapshots)

    result = {
        "fleet_heat": fleet_heat,
        "per_bot_exposure": per_bot,
        "correlation_matrix": corr_matrix,
        "drawdown_velocity": drawdown,
        "concentration_score": concentration,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "positions_count": len(positions),
    }

    # Atomic write
    output_path = Path(args.output)
    tmp_path = output_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        os.replace(str(tmp_path), str(output_path))
        log.info("Wrote %s (fleet_heat=%.4f, %d bots, %d positions)",
                 output_path.name, fleet_heat, len(per_bot), len(positions))
    except Exception as e:
        log.error("Failed to write output: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
