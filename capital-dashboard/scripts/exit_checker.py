# CALLED BY: cron or manual — use --all --auto-execute for automated hard exit enforcement
#!/usr/bin/env python3
"""
exit_checker.py — Factor-based exit validation engine.

Checks every open position against exit factors. Returns HOLD/TRIM/EXIT.
Runs as part of stop-loss enforcer cron and on-demand.

Usage:
    python3 exit_checker.py --bot tars                    # Check all TARS positions
    python3 exit_checker.py --bot tars --ticker GLD       # Check specific position
    python3 exit_checker.py --all                         # Check all bots
    python3 exit_checker.py --hard-only                   # Only check hard exit triggers
    python3 exit_checker.py --json                        # JSON output for automation
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
SUPABASE_URL = "https://vghssoltipiajiwzhkyn.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SB_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

STARTING_CAPITAL = 50000.0

# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def yahoo_price(ticker: str) -> dict:
    """Fetch current price + historical data from Yahoo Finance."""
    try:
        url = f"{YAHOO_BASE}/{ticker}?interval=1d&range=3mo"
        r = requests.get(url, headers=HEADERS, timeout=10)
        result = r.json()["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]
        closes = [c for c in quote["close"] if c is not None]
        volumes = [v for v in quote["volume"] if v is not None]
        highs = [h for h in quote["high"] if h is not None]
        lows = [l for l in quote["low"] if l is not None]
        
        return {
            "price": closes[-1] if closes else 0,
            "prev_close": closes[-2] if len(closes) > 1 else 0,
            "closes": closes,
            "volumes": volumes,
            "highs": highs,
            "lows": lows,
        }
    except Exception as e:
        return {"price": 0, "error": str(e), "closes": [], "volumes": [], "highs": [], "lows": []}


def get_open_positions(bot_id: str) -> list:
    """Get open positions from Supabase trades table."""
    url = f"{SUPABASE_URL}/rest/v1/trades?bot_id=eq.{bot_id}&status=eq.OPEN&select=*&order=id.asc"
    r = requests.get(url, headers=SB_HEADERS, timeout=10)
    if r.status_code != 200:
        return []
    return r.json()


def get_vix() -> float:
    """Get current VIX level."""
    try:
        data = yahoo_price("^VIX")
        return data["price"]
    except:
        return 20.0  # default moderate


def get_portfolio_snapshot(bot_id: str) -> dict:
    """Get portfolio snapshot from Supabase."""
    url = f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?bot_id=eq.{bot_id}&select=*"
    r = requests.get(url, headers=SB_HEADERS, timeout=10)
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return {}


# ---------------------------------------------------------------------------
# Exit factor checks — each returns (signal, severity, reason)
# signal: "HOLD" | "TRIM" | "EXIT"
# severity: "HARD" | "SOFT"
# ---------------------------------------------------------------------------

def check_hard_stop(entry_price: float, current_price: float, action: str) -> tuple:
    """Hard stop at -2% from entry."""
    if action == "SHORT":
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    else:
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    
    if pnl_pct <= -2.0:
        return ("EXIT", "HARD", f"🚨 HARD STOP: {pnl_pct:+.1f}% (limit -2.0%)")
    elif pnl_pct <= -1.5:
        return ("TRIM", "SOFT", f"⚠️ Approaching stop: {pnl_pct:+.1f}% (stop at -2.0%)")
    return ("HOLD", "NONE", f"P&L: {pnl_pct:+.1f}%")


def check_trailing_stop(entry_price: float, current_price: float, highs: list, lows: list, closes: list, action: str) -> tuple:
    """Trailing stop based on 1.5x ATR from recent high (10-day)."""
    if not highs or len(highs) < 14 or not lows or not closes:
        return ("HOLD", "NONE", "Insufficient data for trailing stop")
    
    # Proper ATR calculation (14-day)
    trs = []
    for i in range(-14, 0):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    atr = sum(trs) / len(trs) if trs else 0
    
    # Use 10-day high (recent, not 3-month)
    high_since = max(highs[-10:])
    trailing_stop = high_since - (1.5 * atr)
    
    if action != "SHORT" and current_price < trailing_stop and current_price > entry_price:
        return ("EXIT", "HARD", f"🚨 TRAILING STOP: price ${current_price:.2f} < trail ${trailing_stop:.2f} (10d high ${high_since:.2f})")
    return ("HOLD", "NONE", f"Trail stop at ${trailing_stop:.2f} (10d high ${high_since:.2f})")


def check_gap_down(current_price: float, prev_close: float, action: str = "BUY") -> tuple:
    """Gap down >3% at open. For shorts, gap down is favorable."""
    if prev_close == 0:
        return ("HOLD", "NONE", "No previous close data")
    gap_pct = ((current_price - prev_close) / prev_close) * 100
    
    if action == "SHORT":
        # Gap down is GOOD for shorts — gap UP is bad
        if gap_pct >= 3.0:
            return ("EXIT", "HARD", f"🚨 GAP UP against short: +{gap_pct:.1f}% — cover immediately")
        return ("HOLD", "NONE", f"Gap: {gap_pct:+.1f}% (favorable for short)")
    else:
        if gap_pct <= -3.0:
            return ("EXIT", "HARD", f"🚨 GAP DOWN: {gap_pct:.1f}% — sell immediately")
        return ("HOLD", "NONE", f"Gap: {gap_pct:+.1f}%")


def check_rsi_overbought(closes: list) -> tuple:
    """RSI >80 = overbought, suggest trim."""
    if len(closes) < 15:
        return ("HOLD", "NONE", "Insufficient RSI data")
    
    changes = [closes[i] - closes[i-1] for i in range(-14, 0)]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = sum(gains) / 14 if gains else 0.001
    avg_loss = sum(losses) / 14 if losses else 0.001
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    if rsi > 80:
        return ("TRIM", "SOFT", f"⚠️ RSI {rsi:.0f} — overbought, take partial profit")
    elif rsi < 30:
        return ("HOLD", "NONE", f"RSI {rsi:.0f} — oversold, hold for bounce")
    return ("HOLD", "NONE", f"RSI {rsi:.0f}")


def check_ma_breakdown(current_price: float, closes: list) -> tuple:
    """Price below key moving averages."""
    if len(closes) < 50:
        return ("HOLD", "NONE", "Insufficient MA data")
    
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / 50
    
    if current_price < ma50:
        return ("TRIM", "SOFT", f"⚠️ Below MA50 (${ma50:.2f}) — trend weakening")
    elif current_price < ma20:
        return ("HOLD", "NONE", f"Below MA20 (${ma20:.2f}) but above MA50")
    return ("HOLD", "NONE", f"Above MA20 (${ma20:.2f}) and MA50 (${ma50:.2f})")


def check_volume_distribution(volumes: list, closes: list) -> tuple:
    """Volume spike on red day = distribution."""
    if len(volumes) < 20 or len(closes) < 2:
        return ("HOLD", "NONE", "Insufficient volume data")
    
    avg_vol = sum(volumes[-20:]) / 20
    last_vol = volumes[-1] if volumes[-1] else 0
    last_change = closes[-1] - closes[-2]
    
    if last_vol > 2 * avg_vol and last_change < 0:
        rvol = last_vol / avg_vol
        return ("TRIM", "SOFT", f"⚠️ Distribution: {rvol:.1f}x volume on red day")
    return ("HOLD", "NONE", "Volume normal")


def check_consecutive_red(closes: list) -> tuple:
    """3+ consecutive lower closes."""
    if len(closes) < 4:
        return ("HOLD", "NONE", "Insufficient data")
    
    red_days = 0
    for i in range(-1, -4, -1):
        if closes[i] < closes[i-1]:
            red_days += 1
        else:
            break
    
    if red_days >= 3:
        return ("TRIM", "SOFT", f"⚠️ {red_days} consecutive red days — trend breaking")
    return ("HOLD", "NONE", f"{red_days} red days (threshold: 3)")


def check_time_stop(timestamp: str) -> tuple:
    """Position held >2 days with no movement = dead money."""
    try:
        entry_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_held = (now - entry_time).days
        
        if days_held > 5:
            return ("EXIT", "SOFT", f"⚠️ Held {days_held} days — reassess or exit")
        elif days_held > 2:
            return ("TRIM", "SOFT", f"⚠️ Held {days_held} days — dead money check")
        return ("HOLD", "NONE", f"Held {days_held} days")
    except:
        return ("HOLD", "NONE", "Cannot parse entry timestamp")


def check_profit_target(entry_price: float, current_price: float, action: str) -> tuple:
    """R:R ratio achieved — take partial profit."""
    if action == "SHORT":
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    else:
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
    
    if pnl_pct >= 10:
        return ("TRIM", "SOFT", f"💰 +{pnl_pct:.1f}% — take 50% profit (>10% gain)")
    elif pnl_pct >= 5:
        return ("TRIM", "SOFT", f"💰 +{pnl_pct:.1f}% — consider taking 25% profit")
    return ("HOLD", "NONE", f"P&L: {pnl_pct:+.1f}%")


def check_vix_regime(vix: float) -> tuple:
    """VIX regime check."""
    if vix > 30:
        return ("EXIT", "HARD", f"🚨 VIX {vix:.1f} — EXIT all positions <7/10")
    elif vix > 25:
        return ("TRIM", "SOFT", f"⚠️ VIX {vix:.1f} — tighten all stops")
    return ("HOLD", "NONE", f"VIX {vix:.1f}")


def check_inverse_etf(ticker: str) -> tuple:
    """Inverse/leveraged ETFs must exit by 3:50 PM same day."""
    INVERSE_ETFS = {"SQQQ", "TQQQ", "UVXY", "SPXU", "SH", "QID", "DOG", "SDOW", "SOXS"}
    if ticker in INVERSE_ETFS:
        now = datetime.now(timezone(timedelta(hours=-5)))  # ET
        if now.hour >= 15 and now.minute >= 50:
            return ("EXIT", "HARD", f"🚨 INVERSE ETF {ticker} — must exit by 3:50 PM ET")
        elif now.hour >= 15:
            return ("TRIM", "SOFT", f"⚠️ INVERSE ETF {ticker} — approaching 3:50 PM deadline")
    return ("HOLD", "NONE", "Not an inverse ETF or before deadline")


def check_portfolio_heat(bot_id: str) -> tuple:
    """Total stop-loss exposure across all positions >6% of portfolio."""
    positions = get_open_positions(bot_id)
    if not positions:
        return ("HOLD", "NONE", "No positions")
    
    total_risk = 0
    for pos in positions:
        entry = float(pos["price_usd"])
        qty = float(pos["quantity"])
        stop_pct = 0.02  # 2% stop
        risk = entry * qty * stop_pct
        total_risk += risk
    
    heat_pct = (total_risk / STARTING_CAPITAL) * 100
    if heat_pct > 6:
        return ("EXIT", "HARD", f"🚨 PORTFOLIO HEAT {heat_pct:.1f}% > 6% — trim weakest position")
    return ("HOLD", "NONE", f"Portfolio heat: {heat_pct:.1f}%")


# ---------------------------------------------------------------------------
# STAY score — overrides for soft exits
# ---------------------------------------------------------------------------

def stay_score(ticker: str, entry_price: float, current_price: float, 
               closes: list, volumes: list, timestamp: str) -> dict:
    """Calculate stay score — reasons to HOLD through soft exit signals."""
    score = 0.0
    reasons = []
    
    # 1. VWAP position (above = bullish, stay)
    if len(closes) >= 5 and len(volumes) >= 5:
        # Approximate VWAP from recent data
        typical_prices = closes[-5:]
        vols = volumes[-5:]
        total_vol = sum(vols) if sum(vols) > 0 else 1
        vwap = sum(tp * v for tp, v in zip(typical_prices, vols)) / total_vol
        if current_price > vwap:
            score += 2.0
            reasons.append(f"Above VWAP (${vwap:.2f}) — institutions still buying")
    
    # 2. OBV accumulation (volume on up days > down days)
    if len(closes) >= 10 and len(volumes) >= 10:
        up_vol = sum(volumes[i] for i in range(-10, 0) if closes[i] > closes[i-1])
        down_vol = sum(volumes[i] for i in range(-10, 0) if closes[i] < closes[i-1])
        if up_vol > down_vol * 1.5:
            score += 1.5
            reasons.append("OBV accumulation — up-volume > 1.5x down-volume")
    
    # 3. Higher lows pattern
    if len(closes) >= 10:
        lows_5d = min(closes[-5:])
        lows_10d = min(closes[-10:-5]) if len(closes) >= 10 else lows_5d
        if lows_5d > lows_10d:
            score += 1.5
            reasons.append("Higher lows — trend accelerating")
    
    # 4. Recently entered (<4 hours)
    try:
        entry_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        hours_held = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
        if hours_held < 4:
            score += 2.0
            reasons.append(f"Entered {hours_held:.1f}h ago — give thesis time")
    except:
        pass
    
    # 5. Position is profitable — harder to exit winners
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    if pnl_pct > 3:
        score += 1.0
        reasons.append(f"Profitable +{pnl_pct:.1f}% — trend is working")
    
    # 6. Volume contracting on pullbacks (healthy)
    if len(volumes) >= 5:
        recent_vol = sum(volumes[-3:]) / 3
        prior_vol = sum(volumes[-5:-3]) / 2 if len(volumes) >= 5 else recent_vol
        if recent_vol < prior_vol * 0.7 and current_price > entry_price:
            score += 1.0
            reasons.append("Volume contracting on pullback — healthy consolidation")
    
    return {
        "stay_score": round(score, 1),
        "max_possible": 9.0,
        "reasons": reasons,
    }


def relative_strength(ticker: str, closes: list) -> tuple:
    """Relative strength vs SPY declining."""
    try:
        spy_data = yahoo_price("SPY")
        spy_closes = spy_data["closes"]
        
        if len(closes) < 5 or len(spy_closes) < 5:
            return ("HOLD", "NONE", "Insufficient RS data")
        
        stock_chg = (closes[-1] - closes[-5]) / closes[-5] * 100
        spy_chg = (spy_closes[-1] - spy_closes[-5]) / spy_closes[-5] * 100
        rs = stock_chg - spy_chg
        
        if rs < -5:
            return ("TRIM", "SOFT", f"⚠️ RS vs SPY: {rs:+.1f}% (5d) — significant underperformance")
        elif rs < -2:
            return ("HOLD", "NONE", f"RS vs SPY: {rs:+.1f}% (5d) — mild underperformance")
        return ("HOLD", "NONE", f"RS vs SPY: {rs:+.1f}% (5d)")
    except:
        return ("HOLD", "NONE", "RS check failed")


# ---------------------------------------------------------------------------
# Main exit scoring engine
# ---------------------------------------------------------------------------

def check_position(trade: dict, market_data: dict = None, vix: float = None) -> dict:
    """Run all exit checks on a single position."""
    ticker = trade["ticker"]
    entry_price = float(trade["price_usd"])
    action = trade["action"]  # BUY or SHORT
    timestamp = trade.get("timestamp", "")
    
    if market_data is None:
        market_data = yahoo_price(ticker)
    
    if vix is None:
        vix = get_vix()
    
    current_price = market_data.get("price", entry_price)
    closes = market_data.get("closes", [])
    volumes = market_data.get("volumes", [])
    highs = market_data.get("highs", [])
    prev_close = market_data.get("prev_close", 0)
    
    checks = {
        "hard_stop": check_hard_stop(entry_price, current_price, action),
        "trailing_stop": check_trailing_stop(entry_price, current_price, highs, market_data.get("lows", []), closes, action),
        "gap_down": check_gap_down(current_price, prev_close, action),
        "rsi": check_rsi_overbought(closes),
        "ma_breakdown": check_ma_breakdown(current_price, closes),
        "volume_distribution": check_volume_distribution(volumes, closes),
        "consecutive_red": check_consecutive_red(closes),
        "time_stop": check_time_stop(timestamp),
        "profit_target": check_profit_target(entry_price, current_price, action),
        "vix_regime": check_vix_regime(vix),
        "inverse_etf": check_inverse_etf(ticker),
        "relative_strength": relative_strength(ticker, closes),
    }
    
    # Determine overall signal
    hard_exits = [k for k, (sig, sev, _) in checks.items() if sig == "EXIT" and sev == "HARD"]
    soft_exits = [k for k, (sig, sev, _) in checks.items() if sig == "EXIT" and sev == "SOFT"]
    trims = [k for k, (sig, _, _) in checks.items() if sig == "TRIM"]
    
    # Calculate stay score for soft exit override
    stay = stay_score(ticker, entry_price, current_price, closes, 
                      market_data.get("volumes", []), timestamp)
    
    if hard_exits:
        overall = "🚨 EXIT"
        action_needed = "HARD EXIT — auto-execute immediately"
    elif soft_exits:
        if stay["stay_score"] > 5.0:
            overall = "🟡 MONITOR"
            action_needed = f"Soft exit overridden by STAY score {stay['stay_score']}/9 — recheck 1hr"
        else:
            overall = "⚠️ EXIT"
            action_needed = f"SOFT EXIT (stay={stay['stay_score']}/9) — 15 min to act or auto-executes"
    elif len(trims) >= 3:
        if stay["stay_score"] > 4.0:
            overall = "🟡 WATCH"
            action_needed = f"Trim signals present but STAY score {stay['stay_score']}/9 — monitor"
        else:
            overall = "⚠️ TRIM"
            action_needed = "Multiple trim signals — reduce position"
    elif trims:
        overall = "🟡 WATCH"
        action_needed = "Monitor — trim signals present"
    else:
        overall = "🟢 HOLD"
        action_needed = "All clear"
    
    pnl_pct = ((current_price - entry_price) / entry_price) * 100
    if action == "SHORT":
        pnl_pct = ((entry_price - current_price) / entry_price) * 100
    
    return {
        "ticker": ticker,
        "action": action,
        "entry": entry_price,
        "current": current_price,
        "pnl_pct": round(pnl_pct, 2),
        "overall": overall,
        "action_needed": action_needed,
        "hard_exits": hard_exits,
        "soft_exits": soft_exits,
        "trims": trims,
        "stay": stay,
        "checks": {k: {"signal": s, "severity": v, "reason": r} for k, (s, v, r) in checks.items()},
    }


def auto_execute_exit(bot_id: str, ticker: str, qty: float, price: float, action: str, reasons: list):
    """Auto-execute a HARD EXIT via log_trade.py."""
    import subprocess
    sell_action = "COVER" if action == "SHORT" else "SELL"
    reason_str = f"[HARD_EXIT] {', '.join(reasons)}"
    cmd = [
        "python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_trade.py"),
        "--bot", bot_id,
        "--action", sell_action,
        "--ticker", ticker,
        "--qty", str(qty),
        "--price", str(price),
        "--reason", reason_str,
        "--skip-validation"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✅ HARD EXIT EXECUTED: {sell_action} {ticker} {qty}x @ ${price:.2f}")
            return True
        else:
            print(f"  ❌ HARD EXIT FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ HARD EXIT ERROR: {e}")
        return False


def check_bot(bot_id: str, hard_only: bool = False, auto_execute: bool = False):
    """Check all positions for a bot. If auto_execute=True, HARD exits fire automatically."""
    positions = get_open_positions(bot_id)
    if not positions:
        print(f"  No open positions for {bot_id}")
        return []
    
    vix = get_vix()
    results = []
    
    for trade in positions:
        ticker = trade["ticker"]
        data = yahoo_price(ticker)
        result = check_position(trade, data, vix)
        results.append(result)
        
        if hard_only and not result["hard_exits"]:
            continue
        
        icon = result["overall"]
        pnl = result["pnl_pct"]
        print(f"  {icon} {ticker:8s} {pnl:+6.1f}%  ${result['current']:.2f}  {result['action_needed']}")
        
        # Print triggered factors
        for check_name, info in result["checks"].items():
            if info["signal"] != "HOLD":
                print(f"      {info['reason']}")
        
        # AUTO-EXECUTE HARD EXITS
        if auto_execute and result["hard_exits"]:
            qty = float(trade.get("quantity", 0))
            current = result["current"]
            action = trade.get("action", "BUY")
            if qty > 0 and current > 0:
                print(f"  🚨 AUTO-EXECUTING HARD EXIT: {ticker} — {result['hard_exits']}")
                auto_execute_exit(bot_id, ticker, qty, current, action, result["hard_exits"])
        
        time.sleep(0.3)  # Rate limit
    
    return results


def check_all_bots(hard_only: bool = False, auto_execute: bool = False):
    """Check all 4 bots."""
    bots = ["tars", "alfred", "vex", "eddie_v"]
    all_results = {}
    
    for bot in bots:
        print(f"\n{'='*50}")
        print(f"  {bot.upper()} — Exit Check")
        print(f"{'='*50}")
        results = check_bot(bot, hard_only, auto_execute)
        all_results[bot] = results
    
    # Summary
    print(f"\n{'='*50}")
    print(f"  SUMMARY")
    print(f"{'='*50}")
    
    total_exits = 0
    total_trims = 0
    for bot, results in all_results.items():
        exits = sum(1 for r in results if "EXIT" in r["overall"])
        trims = sum(1 for r in results if "TRIM" in r["overall"] or "WATCH" in r["overall"])
        total_exits += exits
        total_trims += trims
        if exits or trims:
            print(f"  {bot}: {exits} exits, {trims} trims/watches")
    
    if total_exits == 0 and total_trims == 0:
        print("  ✅ All positions clean — no exit signals")
    
    return all_results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exit factor checker")
    parser.add_argument("--bot", help="Bot ID to check")
    parser.add_argument("--ticker", help="Specific ticker to check")
    parser.add_argument("--all", action="store_true", help="Check all bots")
    parser.add_argument("--hard-only", action="store_true", help="Only check hard exit triggers")
    parser.add_argument("--auto-execute", action="store_true", help="Auto-execute HARD exits (sells/covers)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    args = parser.parse_args()
    
    print(f"\n📊 EXIT CHECKER — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    
    if args.all:
        results = check_all_bots(args.hard_only, getattr(args, 'auto_execute', False))
        if args.json:
            print(json.dumps(results, indent=2, default=str))
    elif args.bot:
        if args.ticker:
            positions = get_open_positions(args.bot)
            trade = next((t for t in positions if t["ticker"] == args.ticker), None)
            if trade:
                result = check_position(trade)
                if args.json:
                    print(json.dumps(result, indent=2, default=str))
                else:
                    print(f"  {result['overall']} {result['ticker']} {result['pnl_pct']:+.1f}% — {result['action_needed']}")
                    for k, info in result["checks"].items():
                        icon = "🔴" if info["signal"] == "EXIT" else "🟡" if info["signal"] == "TRIM" else "🟢"
                        print(f"    {icon} {k}: {info['reason']}")
            else:
                print(f"  No open {args.ticker} position for {args.bot}")
        else:
            check_bot(args.bot, args.hard_only)
    else:
        parser.print_help()
