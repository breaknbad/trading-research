#!/usr/bin/env python3
"""Fix Alfred's dashboard data from Supabase truth."""

import sys, os, json, requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, STARTING_CAPITAL, DASHBOARD_DIR

def get_trades():
    """Get all Alfred trades from Supabase."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades",
        headers=SUPABASE_HEADERS,
        params={"bot_id": f"eq.{BOT_ID}", "select": "*", "order": "created_at.asc"}
    )
    return r.json() if r.status_code == 200 else []

def replay_portfolio(trades):
    """Replay trades to compute current portfolio state."""
    cash = STARTING_CAPITAL
    positions = {}  # ticker -> {qty, avg_entry, side}
    realized_pl = 0
    trade_count = 0
    wins = 0
    
    for t in trades:
        action = t.get("action", "")
        ticker = t.get("ticker", "")
        price = float(t.get("price_usd", 0) or t.get("price", 0) or 0)
        qty = float(t.get("quantity", 0))
        
        if action == "BUY":
            cost = price * qty
            if cash >= cost:
                cash -= cost
                if ticker in positions and positions[ticker]["side"] == "LONG":
                    old = positions[ticker]
                    total_qty = old["qty"] + qty
                    avg = ((old["avg_entry"] * old["qty"]) + (price * qty)) / total_qty
                    positions[ticker] = {"qty": total_qty, "avg_entry": avg, "side": "LONG"}
                else:
                    positions[ticker] = {"qty": qty, "avg_entry": price, "side": "LONG"}
                trade_count += 1
                
        elif action == "SELL":
            if ticker in positions and positions[ticker]["side"] == "LONG":
                pos = positions[ticker]
                sell_qty = min(qty, pos["qty"])
                proceeds = price * sell_qty
                cash += proceeds
                pl = (price - pos["avg_entry"]) * sell_qty
                realized_pl += pl
                if pl > 0:
                    wins += 1
                trade_count += 1
                pos["qty"] -= sell_qty
                if pos["qty"] <= 0.001:
                    del positions[ticker]
                    
        elif action == "SHORT":
            proceeds = price * qty
            cash += proceeds
            if ticker in positions and positions[ticker]["side"] == "SHORT":
                old = positions[ticker]
                total_qty = old["qty"] + qty
                avg = ((old["avg_entry"] * old["qty"]) + (price * qty)) / total_qty
                positions[ticker] = {"qty": total_qty, "avg_entry": avg, "side": "SHORT"}
            else:
                positions[ticker] = {"qty": qty, "avg_entry": price, "side": "SHORT"}
            trade_count += 1
            
        elif action == "COVER":
            if ticker in positions and positions[ticker]["side"] == "SHORT":
                pos = positions[ticker]
                cover_qty = min(qty, pos["qty"])
                cost = price * cover_qty
                cash -= cost
                pl = (pos["avg_entry"] - price) * cover_qty
                realized_pl += pl
                if pl > 0:
                    wins += 1
                trade_count += 1
                pos["qty"] -= cover_qty
                if pos["qty"] <= 0.001:
                    del positions[ticker]
    
    return cash, positions, realized_pl, trade_count, wins

def build_dashboard_json(cash, positions, realized_pl, trade_count, wins):
    """Build the dashboard JSON for Alfred."""
    # Use last known prices from positions (we'll use entry as proxy since market is closed)
    # These are the AH prices from Feb 26
    price_overrides = {
        "AAPL": 272.95, "AMZN": 207.92, "BBAI": 4.15, "CRM": 181.50,
        "GLD": 476.00, "MSFT": 404.69, "PLTR": 135.63, "XLP": 80.00,
        "SQQQ": 70.74, "NVDA": 184.89, "AMD": 203.68,
    }
    
    pos_list = []
    total_long_value = 0
    total_short_obligation = 0
    unrealized_pl = 0
    
    for ticker, pos in sorted(positions.items()):
        price = price_overrides.get(ticker, pos["avg_entry"])
        mv = price * pos["qty"]
        
        if pos["side"] == "LONG":
            pl = (price - pos["avg_entry"]) * pos["qty"]
            pnl_pct = ((price - pos["avg_entry"]) / pos["avg_entry"]) * 100
            total_long_value += mv
        else:  # SHORT
            pl = (pos["avg_entry"] - price) * pos["qty"]
            pnl_pct = ((pos["avg_entry"] - price) / pos["avg_entry"]) * 100
            total_short_obligation += mv
        
        unrealized_pl += pl
        pos_list.append({
            "ticker": ticker,
            "side": pos["side"],
            "quantity": pos["qty"],
            "avg_entry": round(pos["avg_entry"], 2),
            "current_price": round(price, 2),
            "unrealized_pl": round(pl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "market_value": round(mv, 2),
        })
    
    # Portfolio = Cash + Long_value - Short_obligation
    total_value = cash + total_long_value - total_short_obligation
    total_return_pct = ((total_value - STARTING_CAPITAL) / STARTING_CAPITAL) * 100
    win_rate = (wins / trade_count * 100) if trade_count > 0 else 0
    
    dashboard = {
        "bot_id": BOT_ID,
        "bot_name": "Alfred",
        "emoji": "🎩",
        "strategy": "Congressional & Insider Flow",
        "status": "running",
        "updated_at": datetime.now().isoformat(),
        "total_value_usd": round(total_value, 2),
        "cash_usd": round(cash, 2),
        "total_return_pct": round(total_return_pct, 2),
        "daily_pnl": round(realized_pl + unrealized_pl, 2),
        "daily_return_pct": round(total_return_pct, 2),
        "realized_pl": round(realized_pl, 2),
        "unrealized_pl": round(unrealized_pl, 2),
        "day_start_value": STARTING_CAPITAL,
        "win_rate": round(win_rate, 1),
        "trade_count": trade_count,
        "positions": pos_list,
        "equity_curve": [
            {"date": "2026-02-23", "value": STARTING_CAPITAL},
            {"date": "2026-02-24", "value": 25155},
            {"date": "2026-02-25", "value": 25050},
            {"date": "2026-02-26", "value": round(total_value, 2)},
        ],
    }
    
    return dashboard

def main():
    print("Fetching trades from Supabase...")
    trades = get_trades()
    print(f"Found {len(trades)} trades")
    
    cash, positions, realized_pl, trade_count, wins = replay_portfolio(trades)
    
    print(f"\nPortfolio replay:")
    print(f"  Cash: ${cash:,.2f}")
    print(f"  Positions: {len(positions)}")
    for tk, pos in sorted(positions.items()):
        print(f"    {pos['side']} {tk}: {pos['qty']}x @ ${pos['avg_entry']:.2f}")
    print(f"  Realized P&L: ${realized_pl:,.2f}")
    print(f"  Trades: {trade_count} ({wins} wins)")
    
    dashboard = build_dashboard_json(cash, positions, realized_pl, trade_count, wins)
    
    print(f"\n  Total Value: ${dashboard['total_value_usd']:,.2f}")
    print(f"  Return: {dashboard['total_return_pct']:.2f}%")
    
    # Write
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    out_path = os.path.join(DASHBOARD_DIR, "alfred.json")
    with open(out_path, "w") as f:
        json.dump(dashboard, f, indent=2)
    print(f"\nDashboard written to {out_path}")

if __name__ == "__main__":
    main()
