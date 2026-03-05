#!/usr/bin/env python3
"""Loss Autopsy — systematic loss pattern detection.

Analyzes losing trades for recurring patterns: same ticker, same hour,
same sector, same holding duration. Feeds avoid signals back into
pretrade_factor_engine.
"""

import sys, os, json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import SUPABASE_URL, SUPABASE_HEADERS, BOT_ID, CACHE_DIR

import requests

AVOID_LIST_FILE = os.path.join(CACHE_DIR, "avoid_list.json")


def _get_closed_trades(date=None):
    """Get all closed trades (SELL/COVER) for a date."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # Get exits
    url = f"{SUPABASE_URL}/rest/v1/trades"
    params = {
        "bot_id": f"eq.{BOT_ID}",
        "action": "in.(SELL,COVER)",
        "select": "*",
        "order": "created_at.desc"
    }
    r = requests.get(url, headers=SUPABASE_HEADERS, params=params)
    exits = r.json() if r.status_code == 200 else []
    
    # Get entries to match
    params["action"] = "in.(BUY,SHORT)"
    r = requests.get(url, headers=SUPABASE_HEADERS, params=params)
    entries = r.json() if r.status_code == 200 else []
    
    # Match exits to entries
    entry_map = {}
    for e in entries:
        ticker = e.get("ticker", "")
        if ticker not in entry_map:
            entry_map[ticker] = []
        entry_map[ticker].append(e)
    
    closed = []
    for exit_trade in exits:
        ticker = exit_trade.get("ticker", "")
        entry_price = None
        entry_time = None
        
        if ticker in entry_map and entry_map[ticker]:
            entry = entry_map[ticker][0]  # Most recent entry
            entry_price = entry.get("price", 0)
            entry_time = entry.get("created_at", "")
        
        exit_price = exit_trade.get("price", 0)
        if entry_price and entry_price > 0:
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            if exit_trade.get("action") in ("COVER",):
                pnl_pct = -pnl_pct  # Short: profit when price drops
        else:
            pnl_pct = 0
        
        closed.append({
            "ticker": ticker,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pct": round(pnl_pct, 2),
            "is_loss": pnl_pct < 0,
            "exit_time": exit_trade.get("created_at", ""),
            "entry_time": entry_time,
            "sector": exit_trade.get("sector", "Unknown"),
        })
    
    return closed


def run_autopsy(date=None):
    """Analyze losing trades for patterns."""
    closed = _get_closed_trades(date)
    losses = [t for t in closed if t["is_loss"]]
    
    if not losses:
        return {
            "patterns": [],
            "total_losses": 0,
            "total_trades": len(closed),
            "loss_rate": 0,
            "worst_ticker": None,
            "worst_hour": None,
        }
    
    # Group by ticker
    ticker_losses = {}
    for t in losses:
        tk = t["ticker"]
        if tk not in ticker_losses:
            ticker_losses[tk] = {"count": 0, "total_pnl": 0}
        ticker_losses[tk]["count"] += 1
        ticker_losses[tk]["total_pnl"] += t["pnl_pct"]
    
    # Group by hour
    hour_losses = {}
    for t in losses:
        if t.get("entry_time"):
            try:
                h = datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00")).hour
                if h not in hour_losses:
                    hour_losses[h] = 0
                hour_losses[h] += 1
            except:
                pass
    
    # Group by sector
    sector_losses = {}
    for t in losses:
        s = t.get("sector", "Unknown")
        if s not in sector_losses:
            sector_losses[s] = 0
        sector_losses[s] += 1
    
    # Find patterns
    patterns = []
    
    # Ticker patterns: losing >60% on same ticker
    for tk, data in ticker_losses.items():
        total_trades_ticker = len([t for t in closed if t["ticker"] == tk])
        if total_trades_ticker >= 2:
            loss_rate = data["count"] / total_trades_ticker
            if loss_rate > 0.6:
                patterns.append({
                    "type": "ticker_repeat_loser",
                    "detail": f"{tk}: {data['count']}/{total_trades_ticker} trades lost ({loss_rate:.0%})",
                    "ticker": tk,
                    "severity": "HIGH" if data["count"] >= 3 else "MEDIUM",
                })
    
    # Hour patterns
    for h, count in hour_losses.items():
        total_hour = len([t for t in closed if t.get("entry_time") and 
                         datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00")).hour == h])
        if total_hour >= 2 and count / total_hour > 0.5:
            patterns.append({
                "type": "bad_hour",
                "detail": f"Hour {h}:00: {count}/{total_hour} trades lost",
                "hour": h,
                "severity": "MEDIUM",
            })
    
    # Sector concentration
    for s, count in sector_losses.items():
        if count >= 3:
            patterns.append({
                "type": "sector_bleeding",
                "detail": f"Sector {s}: {count} losses",
                "sector": s,
                "severity": "HIGH",
            })
    
    worst_ticker = max(ticker_losses, key=lambda k: ticker_losses[k]["count"]) if ticker_losses else None
    worst_hour = max(hour_losses, key=hour_losses.get) if hour_losses else None
    
    return {
        "patterns": patterns,
        "total_losses": len(losses),
        "total_trades": len(closed),
        "loss_rate": round(len(losses) / len(closed) * 100, 1) if closed else 0,
        "worst_ticker": worst_ticker,
        "worst_hour": worst_hour,
        "ticker_breakdown": ticker_losses,
        "hour_breakdown": hour_losses,
        "sector_breakdown": sector_losses,
    }


def get_avoid_list():
    """Get tickers/patterns to avoid based on historical losses."""
    if os.path.exists(AVOID_LIST_FILE):
        with open(AVOID_LIST_FILE) as f:
            return json.load(f)
    return {"tickers": [], "hours": [], "updated_at": None}


def update_avoid_list(autopsy_result):
    """Update avoid list based on autopsy findings."""
    avoid = get_avoid_list()
    
    for p in autopsy_result.get("patterns", []):
        if p["type"] == "ticker_repeat_loser" and p["severity"] == "HIGH":
            if p["ticker"] not in avoid["tickers"]:
                avoid["tickers"].append(p["ticker"])
        elif p["type"] == "bad_hour":
            if p["hour"] not in avoid["hours"]:
                avoid["hours"].append(p["hour"])
    
    avoid["updated_at"] = datetime.now().isoformat()
    
    with open(AVOID_LIST_FILE, "w") as f:
        json.dump(avoid, f, indent=2)
    
    return avoid


def format_autopsy_report(result=None):
    """Format autopsy for Discord posting."""
    if result is None:
        result = run_autopsy()
    
    lines = [f"**📋 Loss Autopsy — {BOT_ID.upper()}**"]
    lines.append(f"Total trades: {result['total_trades']} | Losses: {result['total_losses']} | Loss rate: {result['loss_rate']}%")
    
    if not result["patterns"]:
        lines.append("No recurring loss patterns detected. ✅")
        return "\n".join(lines)
    
    lines.append("\n**Patterns Found:**")
    for p in result["patterns"]:
        severity_emoji = "🔴" if p["severity"] == "HIGH" else "🟡"
        lines.append(f"{severity_emoji} {p['detail']}")
    
    if result.get("worst_ticker"):
        lines.append(f"\nWorst ticker: **{result['worst_ticker']}**")
    if result.get("worst_hour") is not None:
        lines.append(f"Worst hour: **{result['worst_hour']}:00 ET**")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Loss Autopsy Test ===")
    result = run_autopsy()
    print(format_autopsy_report(result))
    print(f"\nAvoid list: {get_avoid_list()}")
