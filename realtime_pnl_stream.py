#!/usr/bin/env python3
"""Real-time P&L stream — polls positions, computes unrealized P&L, fires alerts."""

import sys, os, json, time, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, FINNHUB_KEY, CACHE_DIR, STARTING_CAPITAL

PNL_STATE_FILE = os.path.join(CACHE_DIR, "pnl_state.json")
ALERT_SWING_THRESHOLD = 50.0  # $ swing per position
DRAWDOWN_THRESHOLD_PCT = 2.0  # % from portfolio peak


def _load_state():
    if os.path.exists(PNL_STATE_FILE):
        with open(PNL_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state):
    os.makedirs(os.path.dirname(PNL_STATE_FILE), exist_ok=True)
    with open(PNL_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _get_quote(ticker: str) -> float:
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=10,
        )
        data = r.json()
        return data.get("c", 0.0)
    except Exception:
        return 0.0


def _fetch_open_positions() -> list:
    """Fetch open positions from Supabase."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/paper_positions?bot_id=eq.{BOT_ID}&status=eq.open&select=*",
            headers=SUPABASE_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  [warn] Failed to fetch positions: {e}")
    return []


def _fetch_cash() -> float:
    """Fetch current cash from Supabase portfolio."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/paper_portfolio?bot_id=eq.{BOT_ID}&select=cash&limit=1",
            headers=SUPABASE_HEADERS,
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                return float(data[0].get("cash", STARTING_CAPITAL))
    except Exception:
        pass
    return STARTING_CAPITAL


def compute_realtime_pnl() -> dict:
    """Compute mark-to-market unrealized P&L for all open positions.

    Returns:
        {positions: list, total_unrealized: float, portfolio_value: float, cash: float}
    """
    positions = _fetch_open_positions()
    cash = _fetch_cash()
    total_unrealized = 0.0
    pos_details = []

    for pos in positions:
        ticker = pos.get("ticker", "")
        entry = float(pos.get("entry_price", 0))
        shares = float(pos.get("shares", 0))
        side = pos.get("side", "long")

        current = _get_quote(ticker)
        if current <= 0:
            continue

        if side == "long":
            unrealized = (current - entry) * shares
        else:
            unrealized = (entry - current) * shares

        total_unrealized += unrealized
        pos_details.append({
            "ticker": ticker,
            "side": side,
            "shares": shares,
            "entry_price": entry,
            "current_price": current,
            "unrealized_pnl": round(unrealized, 2),
            "pnl_pct": round((unrealized / (entry * shares)) * 100, 2) if entry * shares > 0 else 0.0,
        })
        time.sleep(0.25)

    portfolio_value = cash + sum(p["current_price"] * p["shares"] for p in pos_details)

    result = {
        "positions": pos_details,
        "total_unrealized": round(total_unrealized, 2),
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "timestamp": time.time(),
    }

    # Update HWM in state
    state = _load_state()
    hwm = state.get("portfolio_hwm", portfolio_value)
    if portfolio_value > hwm:
        hwm = portfolio_value
    state["portfolio_hwm"] = hwm
    state["last"] = result
    _save_state(state)

    return result


def check_alerts(prev_state: dict, curr_state: dict) -> list:
    """Compare two P&L states and return alert strings.

    Alerts on:
        - Any position swinging >$50 since last check
        - New portfolio high-water mark
        - Drawdown >2% from peak
    """
    alerts = []
    if not prev_state or not curr_state:
        return alerts

    # Build lookup for previous positions
    prev_lookup = {}
    for p in prev_state.get("positions", []):
        prev_lookup[p["ticker"]] = p

    # Position swing alerts
    for p in curr_state.get("positions", []):
        prev = prev_lookup.get(p["ticker"])
        if prev:
            swing = abs(p["unrealized_pnl"] - prev["unrealized_pnl"])
            if swing >= ALERT_SWING_THRESHOLD:
                direction = "📈" if p["unrealized_pnl"] > prev["unrealized_pnl"] else "📉"
                alerts.append(
                    f"{direction} **{p['ticker']}** swung ${swing:.2f} "
                    f"(now ${p['unrealized_pnl']:+.2f})"
                )

    # Portfolio HWM
    state = _load_state()
    hwm = state.get("portfolio_hwm", curr_state["portfolio_value"])
    if curr_state["portfolio_value"] >= hwm:
        prev_hwm = prev_state.get("portfolio_value", 0)
        if prev_hwm < hwm:
            alerts.append(f"🏆 New portfolio high-water mark: ${curr_state['portfolio_value']:,.2f}")

    # Drawdown alert
    if hwm > 0:
        drawdown_pct = ((hwm - curr_state["portfolio_value"]) / hwm) * 100
        if drawdown_pct >= DRAWDOWN_THRESHOLD_PCT:
            alerts.append(
                f"🚨 Portfolio drawdown: -{drawdown_pct:.2f}% from peak "
                f"(${curr_state['portfolio_value']:,.2f} vs HWM ${hwm:,.2f})"
            )

    return alerts


def run_pnl_loop(interval: int = 60):
    """Continuous polling loop (for standalone execution)."""
    print(f"Starting P&L stream (polling every {interval}s)...")
    prev = _load_state().get("last", {})

    while True:
        try:
            curr = compute_realtime_pnl()
            alerts = check_alerts(prev, curr)

            print(f"\n[{time.strftime('%H:%M:%S')}] Portfolio: ${curr['portfolio_value']:,.2f} | "
                  f"Unrealized: ${curr['total_unrealized']:+,.2f} | Cash: ${curr['cash']:,.2f}")

            for pos in curr["positions"]:
                print(f"  {pos['ticker']:6s} {pos['side']:5s} {pos['shares']:>6.0f}sh "
                      f"${pos['entry_price']:>8.2f}→${pos['current_price']:>8.2f} "
                      f"P&L: ${pos['unrealized_pnl']:>+8.2f} ({pos['pnl_pct']:>+.1f}%)")

            for alert in alerts:
                print(f"  ⚡ ALERT: {alert}")

            prev = curr
        except Exception as e:
            print(f"  [error] {e}")

        time.sleep(interval)


if __name__ == "__main__":
    # Single snapshot
    result = compute_realtime_pnl()
    print(json.dumps(result, indent=2))
