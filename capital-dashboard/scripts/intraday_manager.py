# CALLED BY: cron intraday-manager (every 15 min during market hours) + cron intraday-manager-eod-sweep (3:55 PM)
#!/usr/bin/env python3
"""
Intraday Manager — Scale-out ladder, rotation clock, gain protection
Runs every 15 minutes during market hours.
Implements Dead Zone Protocol v1.0 + Intraday Rules v1.0
"""

import os
import json
import time
import requests
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BOT_IDS = ["tars", "alfred", "vex", "eddie_v"]
INITIAL_CAPITAL = 50000


def get_yahoo_price(ticker):
    """Get current price from Yahoo Finance."""
    import urllib.request
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        return data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None


def get_open_positions(bot_id):
    """Get all OPEN positions for a bot."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/trades",
        params={
            "bot_id": f"eq.{bot_id}",
            "status": "eq.OPEN",
            "action": "eq.BUY",
            "select": "id,ticker,quantity,price_usd,timestamp",
            "order": "timestamp.asc",
        },
        headers=HEADERS,
    )
    if r.status_code == 200:
        return r.json()
    return []


def get_portfolio_value(bot_id):
    """Get latest portfolio total from snapshots."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/portfolio_snapshots",
        params={
            "bot_id": f"eq.{bot_id}",
            "select": "total_value_usd,day_start_value",
            "order": "last_updated.desc",
            "limit": "1",
        },
        headers=HEADERS,
    )
    if r.status_code == 200 and r.json():
        row = r.json()[0]
        return float(row["total_value_usd"]), float(row.get("day_start_value") or INITIAL_CAPITAL)
    return INITIAL_CAPITAL, INITIAL_CAPITAL


INVERSE_ETFS = {"SQQQ", "SH", "SPXU", "SDOW", "TECS", "SOXS", "FAZ", "TZA"}

# Glide killer state file — tracks whether we're in glide mode
GLIDE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glide_state.json")


def get_volume_regime():
    """Read current volume regime from volume_state.json."""
    vs_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "volume_state.json"),
        os.path.expanduser("~/.openclaw/workspace/capital-dashboard/scripts/volume_state.json"),
    ]
    for p in vs_paths:
        if os.path.exists(p):
            try:
                with open(p) as f:
                    data = json.load(f)
                return data.get("last_regime", "NORMAL"), data.get("avg_rvol", 1.0)
            except Exception:
                pass
    return "NORMAL", 1.0


def execute_glide_killer(bot_id, positions):
    """
    HYBRID GLIDE KILLER (Mark approved Mar 3):
    - Winners (>+1%): RIDE — tighten stop to breakeven, let them run
    - Flat positions (-1% to +1%): CUT — trim 50% immediately
    - Losers (<-1%): CUT FULL — close entirely, thesis is dead in low volume
    
    Only activates when volume regime is FADING or DEAD.
    """
    actions = []
    regime, rvol = get_volume_regime()
    
    if "FADING" not in regime and "DEAD" not in regime:
        return actions
    
    # Read glide state to avoid re-executing on same positions
    glide_state = {}
    if os.path.exists(GLIDE_STATE_FILE):
        try:
            with open(GLIDE_STATE_FILE) as f:
                glide_state = json.load(f)
        except Exception:
            glide_state = {}
    
    trimmed_key = f"{bot_id}_trimmed"
    already_trimmed = set(glide_state.get(trimmed_key, []))
    
    for pos in positions:
        ticker = pos["ticker"]
        pos_id = str(pos["id"])
        
        if pos_id in already_trimmed:
            continue
            
        entry = float(pos["price_usd"])
        qty = float(pos["quantity"])
        current = get_yahoo_price(ticker)
        if current is None:
            continue
        
        pct_gain = (current - entry) / entry * 100
        
        if pct_gain > 1.0:
            # WINNER — ride it, but tighten stop to breakeven
            actions.append({
                "type": "TIGHTEN_STOP",
                "bot_id": bot_id,
                "ticker": ticker,
                "msg": f"🛡️ GLIDE KILLER: {bot_id} {ticker} +{pct_gain:.1f}% — WINNER rides, stop → breakeven (${entry:.2f})"
            })
        elif pct_gain > -1.0:
            # FLAT — trim 50%
            trim_qty = round(qty * 0.5, 6)
            actions.append({
                "type": "TRIM",
                "bot_id": bot_id,
                "ticker": ticker,
                "qty": trim_qty,
                "price": current,
                "msg": f"✂️ GLIDE KILLER: {bot_id} SELL {ticker} {trim_qty}x @ ${current:.2f} — FLAT position trimmed 50% (was {pct_gain:+.1f}%)"
            })
            already_trimmed.add(pos_id)
        else:
            # LOSER — close entirely
            actions.append({
                "type": "CLOSE",
                "bot_id": bot_id,
                "ticker": ticker,
                "qty": qty,
                "price": current,
                "msg": f"🔴 GLIDE KILLER: {bot_id} SELL {ticker} {qty}x @ ${current:.2f} — LOSER closed ({pct_gain:+.1f}%) in low volume"
            })
            already_trimmed.add(pos_id)
    
    # Save glide state
    glide_state[trimmed_key] = list(already_trimmed)
    glide_state["last_activated"] = datetime.now().isoformat()
    glide_state["regime"] = regime
    try:
        with open(GLIDE_STATE_FILE, "w") as f:
            json.dump(glide_state, f, indent=2)
    except Exception:
        pass
    
    return actions


def execute_trade(bot_id, action, ticker, qty, price, reason):
    """Actually execute a trade via log_trade.py."""
    import subprocess
    cmd = [
        "python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_trade.py"),
        "--bot", bot_id,
        "--action", action,
        "--ticker", ticker,
        "--qty", str(qty),
        "--price", str(price),
        "--reason", reason,
        "--skip-validation"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✅ EXECUTED: {action} {ticker} {qty}x @ ${price:.2f}")
            return True
        else:
            print(f"  ❌ FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


def reset_glide_state():
    """Reset glide state when regime exits FADING/DEAD."""
    regime, _ = get_volume_regime()
    if "FADING" not in regime and "DEAD" not in regime:
        if os.path.exists(GLIDE_STATE_FILE):
            try:
                with open(GLIDE_STATE_FILE) as f:
                    state = json.load(f)
                if state.get("last_activated"):
                    print("  🔓 Glide killer DEACTIVATED — volume regime recovered")
                    os.remove(GLIDE_STATE_FILE)
            except Exception:
                pass

def check_inverse_etf_trim(bot_id, positions):
    """Auto-trim inverse ETFs at +5%. Auto-liquidate at 3:55 PM."""
    alerts = []
    now = datetime.now(timezone.utc)
    # Convert to ET (UTC-5 or UTC-4 DST)
    et_hour = (now.hour - 5) % 24  # simplified, close enough
    
    for pos in positions:
        ticker = pos["ticker"].upper()
        if ticker not in INVERSE_ETFS:
            continue
        entry = float(pos["price_usd"])
        qty = float(pos["quantity"])
        current = get_yahoo_price(ticker)
        if current is None:
            continue
        pct_gain = (current - entry) / entry * 100
        
        # Auto-liquidate at 3:55 PM ET
        if et_hour >= 19 and now.minute >= 55:  # 19:55 UTC = 3:55 PM ET (winter)
            alerts.append(f"🚨 INVERSE ETF CLOSE: {bot_id} SELL {ticker} {qty}x @ ${current:.2f} — 3:55 PM auto-liquidation")
        # Auto-trim 50% at +5%
        elif pct_gain >= 5:
            trim_qty = round(qty * 0.5, 2)
            alerts.append(f"🟢 INVERSE TRIM +5%: {bot_id} SELL {ticker} {trim_qty}x @ ${current:.2f} (+{pct_gain:.1f}%) — auto-trim 50%")
    
    return alerts


def check_scale_out(bot_id, positions):
    """Scale-out ladder: trim at +3%, +5%, +8%."""
    alerts = []
    for pos in positions:
        ticker = pos["ticker"]
        entry = float(pos["price_usd"])
        qty = float(pos["quantity"])
        current = get_yahoo_price(ticker)
        if current is None:
            continue
        pct_gain = (current - entry) / entry * 100

        if pct_gain >= 8:
            trim_qty = round(qty * 0.25, 6)
            alerts.append(f"🟢 SCALE-OUT +8%: {bot_id} {ticker} @ ${current:.2f} (+{pct_gain:.1f}%) — TRIM {trim_qty} (25%), trail stop at +5%")
        elif pct_gain >= 5:
            trim_qty = round(qty * 0.25, 6)
            alerts.append(f"🟡 SCALE-OUT +5%: {bot_id} {ticker} @ ${current:.2f} (+{pct_gain:.1f}%) — TRIM {trim_qty} (25%), trail stop at +2%")
        elif pct_gain >= 3:
            trim_qty = round(qty * 0.25, 6)
            alerts.append(f"📊 SCALE-OUT +3%: {bot_id} {ticker} @ ${current:.2f} (+{pct_gain:.1f}%) — TRIM {trim_qty} (25%), move stop to breakeven")
        elif pct_gain <= -2:
            alerts.append(f"🔴 STOP CHECK: {bot_id} {ticker} @ ${current:.2f} ({pct_gain:.1f}%) — AT OR BELOW -2% THRESHOLD")

    return alerts


def check_gain_protection(bot_id):
    """If portfolio up >2.5%, switch to gain protection mode."""
    total, day_start = get_portfolio_value(bot_id)
    daily_pct = (total - day_start) / day_start * 100

    if daily_pct >= 4:
        return f"🛡️ GAIN PROTECTION (HIGH): {bot_id} +{daily_pct:.1f}% — ALL stops should be at +1% minimum"
    elif daily_pct >= 2.5:
        return f"🛡️ GAIN PROTECTION: {bot_id} +{daily_pct:.1f}% — ALL stops should be at breakeven"
    elif daily_pct <= -2:
        return f"⚠️ DRAWDOWN ALERT: {bot_id} {daily_pct:.1f}% — Review all positions for thesis integrity"
    return None


def find_rotation_candidate(bot_id, positions):
    """Find weakest held vs strongest non-held for rotation."""
    if not positions:
        return None

    # Score each position by current % gain
    scored = []
    for pos in positions:
        current = get_yahoo_price(pos["ticker"])
        if current is None:
            continue
        entry = float(pos["price_usd"])
        pct = (current - entry) / entry * 100
        scored.append({"ticker": pos["ticker"], "pct": pct, "qty": pos["quantity"], "id": pos["id"]})

    if not scored:
        return None

    scored.sort(key=lambda x: x["pct"])
    weakest = scored[0]

    # Check non-held movers
    held_tickers = {p["ticker"] for p in positions}
    watchlist = ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "AVAX-USD", "LINK-USD", "GLD", "XLE", "NVDA"]
    non_held = [t for t in watchlist if t not in held_tickers]

    best_non_held = None
    best_pct = -999
    for ticker in non_held[:5]:  # Check top 5 non-held
        price = get_yahoo_price(ticker)
        if price is None:
            continue
        # We don't have a baseline for non-held, so skip pure rotation for now
        # Just flag the weakest for potential trim
        pass

    if weakest["pct"] < -1:
        return f"🔄 ROTATION CANDIDATE: {bot_id} weakest = {weakest['ticker']} ({weakest['pct']:+.1f}%) — consider trimming"

    return None


def run_scan():
    """Run full intraday scan for all bots."""
    now = datetime.now()
    print(f"\n{'='*60}")
    print(f"INTRADAY MANAGER — {now.strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"{'='*60}")

    all_alerts = []

    for bot_id in BOT_IDS:
        positions = get_open_positions(bot_id)
        print(f"\n--- {bot_id} ({len(positions)} open positions) ---")

        # Inverse ETF check (auto-trim +5%, auto-close 3:55 PM)
        inverse_alerts = check_inverse_etf_trim(bot_id, positions)
        all_alerts.extend(inverse_alerts)
        for a in inverse_alerts:
            print(f"  {a}")

        # Scale-out check
        scale_alerts = check_scale_out(bot_id, positions)
        all_alerts.extend(scale_alerts)
        for a in scale_alerts:
            print(f"  {a}")

        # Gain protection check
        gain_alert = check_gain_protection(bot_id)
        if gain_alert:
            all_alerts.append(gain_alert)
            print(f"  {gain_alert}")

        # Rotation candidate
        rotation = find_rotation_candidate(bot_id, positions)
        if rotation:
            all_alerts.append(rotation)
            print(f"  {rotation}")

        # GLIDE KILLER — auto-execute in FADING/DEAD regime
        glide_actions = execute_glide_killer(bot_id, positions)
        for ga in glide_actions:
            all_alerts.append(ga["msg"])
            print(f"  {ga['msg']}")
            # Auto-execute TRIM and CLOSE actions
            if ga["type"] in ("TRIM", "CLOSE"):
                execute_trade(ga["bot_id"], "SELL", ga["ticker"], ga["qty"], ga["price"],
                              f"[GLIDE_KILLER] Auto-{ga['type'].lower()} in {get_volume_regime()[0]} regime")

        # Reset glide state if regime recovered
        reset_glide_state()

        if not scale_alerts and not gain_alert and not rotation and not glide_actions:
            print("  ✅ All clear")

    print(f"\n{'='*60}")
    print(f"Total alerts: {len(all_alerts)}")

    return all_alerts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Intraday Manager")
    parser.add_argument("--bot", help="Scan specific bot only")
    parser.add_argument("--continuous", action="store_true", help="Run every 15 min")
    args = parser.parse_args()

    if args.continuous:
        while True:
            try:
                run_scan()
            except Exception as e:
                print(f"ERROR: {e}")
            time.sleep(900)  # 15 minutes
    else:
        alerts = run_scan()
        if alerts:
            print("\n📋 ACTION REQUIRED:")
            for a in alerts:
                print(f"  • {a}")
