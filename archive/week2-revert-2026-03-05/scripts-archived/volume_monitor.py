# CALLED BY: cron volume-regime-monitor (every 15 min 24/7)
#!/usr/bin/env python3
"""
Volume Monitor — The glide killer.
Tracks real-time volume vs averages and triggers regime changes.

REGIMES:
  🟢 SURGE  — Volume >2x average → DEPLOY AGGRESSIVELY, moves are real
  🟡 NORMAL — Volume 0.75x-2x average → Standard trading, hold winners
  🟠 FADING — Volume 0.5x-0.75x average → TIGHTEN STOPS, prepare to trim
  🔴 DEAD   — Volume <0.5x average → TRIM TO 60%, set limit orders, WAIT

Checks BTC, ETH, SOL, SPY, QQQ volume every 15 minutes.
Posts regime changes to stdout (for cron to post to Discord).
"""

import json
import urllib.request
import time
from datetime import datetime


WATCHLIST = {
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "NEAR-USD", "AVAX-USD"],
    "equities": ["SPY", "QQQ", "GLD", "XLE"],
}

# Crypto trades 24/7 — always check crypto. Equities only during market hours.
def is_market_hours():
    now = datetime.now()
    return now.weekday() < 5 and 9 <= now.hour < 16

# Store state between runs
STATE_FILE = "/Users/sheridanskala/.openclaw/workspace/logs/volume_state.json"


def get_volume_data(ticker):
    """Get current volume and average volume from Yahoo Finance."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        result = data["chart"]["result"][0]
        volumes = result["indicators"]["quote"][0]["volume"]
        
        # Current (today's) volume — last element
        current_vol = volumes[-1] if volumes[-1] else 0
        
        # Average of previous 4 days
        prev_vols = [v for v in volumes[:-1] if v]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 1
        
        # Current price for reference
        price = result["meta"]["regularMarketPrice"]
        
        return {
            "ticker": ticker,
            "current_volume": current_vol,
            "avg_volume": avg_vol,
            "rvol": current_vol / avg_vol if avg_vol > 0 else 0,
            "price": price,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def classify_regime(rvol):
    """Classify volume regime."""
    if rvol >= 2.0:
        return "🟢 SURGE", "DEPLOY AGGRESSIVELY — moves are backed by real volume"
    elif rvol >= 0.75:
        return "🟡 NORMAL", "Standard trading — hold winners, scout opportunities"
    elif rvol >= 0.5:
        return "🟠 FADING", "TIGHTEN STOPS — volume dying, moves becoming unreliable"
    else:
        return "🔴 DEAD", "TRIM TO 60% — no fuel, prices will drift. Set limit buys 2% below."


# ---------------------------------------------------------------------------
# NEW: Activity-based guardrails (DA consensus Mar 3 evening)
# ---------------------------------------------------------------------------

ENTRY_RULES = {
    "SURGE":  {"allowed_tiers": ["SCOUT", "CONFIRM", "CONVICTION"], "size_mult": 1.0, "note": "Full entry — but only if SURGE + trend aligned + score >7 for 1.5x"},
    "NORMAL": {"allowed_tiers": ["SCOUT", "CONFIRM", "CONVICTION"], "size_mult": 1.0, "note": "Standard entries"},
    "FADING": {"allowed_tiers": ["SCOUT"],                          "size_mult": 0.5, "note": "SCOUT ONLY — half size, volume dying"},
    "DEAD":   {"allowed_tiers": [],                                 "size_mult": 0.0, "note": "ENTRY LOCKOUT — no new positions until volume returns"},
}

STOP_RULES = {
    "SURGE":  "2%",
    "NORMAL": "1.5%",
    "FADING": "1% or breakeven",
    "DEAD":   "breakeven only",
}


def get_rvol_delta(state):
    """Calculate RVOL delta — is volume rising or falling?
    Checks last 3 readings from state history.
    Returns: 'RISING', 'FALLING', or 'FLAT'"""
    checks = state.get("checks", [])
    if len(checks) < 3:
        return "FLAT", 0
    
    recent = [c["avg_rvol"] for c in checks[-3:]]
    delta = recent[-1] - recent[0]
    
    if delta > 0.15:
        return "RISING", delta
    elif delta < -0.15:
        return "FALLING", delta
    else:
        return "FLAT", delta


def check_velocity_spike(ticker_data_list):
    """Detect price velocity spikes — >2% move in last bar.
    Returns list of tickers with velocity spikes."""
    spikes = []
    for d in ticker_data_list:
        if "error" in d:
            continue
        # Check if we have intraday price change
        try:
            ticker = d["ticker"]
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=30m"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(urllib.request.urlopen(req, timeout=8).read())
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c]
            if len(closes) >= 2:
                pct_change = abs(closes[-1] - closes[-2]) / closes[-2] * 100
                if pct_change >= 2.0:
                    direction = "UP" if closes[-1] > closes[-2] else "DOWN"
                    spikes.append({"ticker": ticker, "pct": pct_change, "direction": direction, "price": closes[-1]})
        except Exception:
            pass
    return spikes


def check_cascade(state):
    """Cascade circuit breaker: 3+ stops in 30 min = HALT all new entries.
    Reads from stop history file."""
    try:
        with open("/tmp/stop_history.json", "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False, 0
    
    # Count stops across ALL bots in last 30 minutes
    from datetime import timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    cutoff_str = cutoff.isoformat()
    
    recent_stops = 0
    for key, timestamps in history.items():
        for ts in timestamps:
            if ts > cutoff_str:
                recent_stops += 1
    
    return recent_stops >= 3, recent_stops


def get_regime_for_team(team, equity_rvol, crypto_rvol, state):
    """Get activity-based regime for a specific team.
    Capital Growth uses equity RVOL during market hours, crypto after.
    Crypto Team always uses crypto RVOL."""
    
    rvol_delta, delta_val = get_rvol_delta(state)
    
    if team == "crypto":
        base_rvol = crypto_rvol
    elif team == "capital_growth":
        if is_market_hours():
            base_rvol = equity_rvol
        else:
            base_rvol = crypto_rvol  # After hours, Capital Growth watches crypto
    else:
        base_rvol = max(equity_rvol or 0, crypto_rvol or 0)
    
    regime, action = classify_regime(base_rvol)
    
    # RVOL Delta override: if RVOL is FALLING, downgrade regime
    regime_key = regime.split(" ")[-1]  # Extract SURGE/NORMAL/FADING/DEAD
    if rvol_delta == "FALLING" and regime_key in ("SURGE", "NORMAL"):
        # Downgrade by one level when volume is actively declining
        if regime_key == "SURGE":
            regime = "🟡 NORMAL"
            action = "Volume declining from surge — CONFIRM+ entries only, no new SCOUTS"
            regime_key = "NORMAL"
        elif regime_key == "NORMAL":
            regime = "🟠 FADING"
            action = "Volume declining into fade — SCOUT only, tighten stops"
            regime_key = "FADING"
    
    entry_rule = ENTRY_RULES.get(regime_key, ENTRY_RULES["NORMAL"])
    stop_rule = STOP_RULES.get(regime_key, "1.5%")
    
    return {
        "regime": regime,
        "regime_key": regime_key,
        "action": action,
        "rvol": base_rvol,
        "rvol_delta": rvol_delta,
        "delta_val": delta_val,
        "entry_rule": entry_rule,
        "stop_rule": stop_rule,
    }


def load_state():
    """Load previous regime state."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_regime": None, "morning_avg_rvol": None, "checks": []}


def save_state(state):
    """Save current state."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def calculate_time_adjusted_rvol(rvol_raw):
    """
    Adjust RVOL for time of day.
    At 10 AM, we've only had 30 min of trading — raw volume will be low.
    Scale up based on how much of the day has elapsed.
    """
    now = datetime.now()
    # Market hours: 9:30 AM - 4:00 PM ET = 6.5 hours
    market_start = now.replace(hour=9, minute=30, second=0)
    market_end = now.replace(hour=16, minute=0, second=0)
    
    if now < market_start:
        return rvol_raw  # Pre-market, don't adjust
    if now > market_end:
        return rvol_raw  # After hours, don't adjust
    
    elapsed = (now - market_start).total_seconds() / 3600  # hours since open
    total_hours = 6.5
    time_fraction = elapsed / total_hours
    
    if time_fraction < 0.05:  # First 20 min — too early to judge
        return None
    
    # Project full-day volume from current pace
    projected_rvol = rvol_raw / time_fraction
    return projected_rvol


def run_volume_check():
    """Run full volume analysis."""
    now = datetime.now()
    state = load_state()
    
    print(f"\n{'='*60}")
    print(f"📊 VOLUME MONITOR — {now.strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"{'='*60}")
    
    all_data = []
    regime_votes = []
    
    # Determine which categories to check
    active_categories = {"crypto": WATCHLIST["crypto"]}  # Always check crypto
    if is_market_hours():
        active_categories["equities"] = WATCHLIST["equities"]
    
    for category, tickers in active_categories.items():
        print(f"\n--- {category.upper()} ---")
        for ticker in tickers:
            data = get_volume_data(ticker)
            if "error" in data:
                print(f"  {ticker}: ERROR — {data['error']}")
                continue
            
            all_data.append(data)
            
            # Time-adjusted RVOL for equities during market hours
            adj_rvol = data["rvol"]
            if category == "equities":
                adjusted = calculate_time_adjusted_rvol(data["rvol"])
                if adjusted is not None:
                    adj_rvol = adjusted
            
            regime, action = classify_regime(adj_rvol)
            regime_votes.append(adj_rvol)
            
            vol_str = f"{data['current_volume']:,.0f}" if data['current_volume'] else "N/A"
            avg_str = f"{data['avg_volume']:,.0f}" if data['avg_volume'] else "N/A"
            
            print(f"  {ticker:10} ${data['price']:>10,.2f} | Vol: {vol_str:>12} | Avg: {avg_str:>12} | RVOL: {adj_rvol:.2f}x | {regime}")
    
    # SPLIT regimes by team (DA consensus: separate equity vs crypto)
    crypto_rvols = [d["rvol"] for d in all_data if d["ticker"] in WATCHLIST["crypto"] and "error" not in d and d.get("rvol")]
    equity_rvols = [d["rvol"] for d in all_data if d["ticker"] in WATCHLIST.get("equities", []) and "error" not in d and d.get("rvol")]
    
    crypto_avg = sum(crypto_rvols) / len(crypto_rvols) if crypto_rvols else 0
    equity_avg = sum(equity_rvols) / len(equity_rvols) if equity_rvols else 0
    
    # Team-specific regimes
    crypto_regime = get_regime_for_team("crypto", equity_avg, crypto_avg, state)
    capital_regime = get_regime_for_team("capital_growth", equity_avg, crypto_avg, state)
    
    print(f"\n{'='*60}")
    print(f"📊 CRYPTO TEAM (TARS + Eddie V):")
    print(f"   Regime: {crypto_regime['regime']} (RVOL {crypto_regime['rvol']:.2f}x, delta: {crypto_regime['rvol_delta']})")
    print(f"   Entries: {crypto_regime['entry_rule']['note']}")
    print(f"   Stops: {crypto_regime['stop_rule']}")
    print(f"   Size mult: {crypto_regime['entry_rule']['size_mult']}x")
    
    print(f"\n📊 CAPITAL GROWTH (Vex + Alfred):")
    print(f"   Regime: {capital_regime['regime']} (RVOL {capital_regime['rvol']:.2f}x, delta: {capital_regime['rvol_delta']})")
    print(f"   Entries: {capital_regime['entry_rule']['note']}")
    print(f"   Stops: {capital_regime['stop_rule']}")
    print(f"   Size mult: {capital_regime['entry_rule']['size_mult']}x")
    
    # Velocity spike detection
    spikes = check_velocity_spike(all_data)
    if spikes:
        print(f"\n⚡ VELOCITY SPIKES DETECTED:")
        for s in spikes:
            print(f"   {s['ticker']} {s['direction']} {s['pct']:.1f}% in 30 min → ${s['price']:,.2f}")
        print(f"   ACTION: SURGE OVERRIDE — treat as SURGE regardless of RVOL")
    
    # Cascade circuit breaker
    cascade_triggered, stop_count = check_cascade(state)
    if cascade_triggered:
        print(f"\n🚨🚨🚨 CASCADE CIRCUIT BREAKER: {stop_count} stops in last 30 min!")
        print(f"   ALL NEW ENTRIES HALTED. Tighten remaining stops to breakeven.")
        print(f"   Wait for volume regime change before re-entering.")
    
    # Use crypto regime as overall for backward compat
    if regime_votes:
        avg_rvol = sum(regime_votes) / len(regime_votes)
        overall_regime, overall_action = classify_regime(avg_rvol)
        
        print(f"\n{'='*60}")
        print(f"OVERALL REGIME: {overall_regime} (avg RVOL: {avg_rvol:.2f}x)")
        print(f"ACTION: {overall_action}")
        print(f"{'='*60}")
        
        # Check for regime change
        if state["last_regime"] and state["last_regime"] != overall_regime:
            print(f"\n⚡ REGIME CHANGE: {state['last_regime']} → {overall_regime}")
            print(f"   {overall_action}")
        
        # Track morning RVOL for afternoon comparison
        if now.hour < 12 and avg_rvol > (state.get("morning_avg_rvol") or 0):
            state["morning_avg_rvol"] = avg_rvol
        
        # Afternoon glide detection (equities)
        if now.hour >= 12 and state.get("morning_avg_rvol") and is_market_hours():
            morning = state["morning_avg_rvol"]
            afternoon_ratio = avg_rvol / morning
            if afternoon_ratio < 0.5:
                print(f"\n🚨 AFTERNOON GLIDE DETECTED!")
                print(f"   Morning RVOL: {morning:.2f}x → Current: {avg_rvol:.2f}x")
                print(f"   Volume dropped {(1 - afternoon_ratio)*100:.0f}% from morning peak")
                print(f"   ACTION: TRIM positions, protect gains, wait for power hour")
                print(f"\n🏠 Running Safe Harbor Scanner...")
                try:
                    from safe_harbor import find_safe_harbors
                    find_safe_harbors(max_tier=2)
                except Exception as e:
                    print(f"   Safe harbor scan failed: {e}")
        
        # 24/7 CRYPTO GLIDE DETECTION — rolling window comparison
        # Uses last 4h of checks vs 12h average to detect volume die-off anytime
        checks = state.get("checks", [])
        if len(checks) >= 4:
            recent_4 = [c["avg_rvol"] for c in checks[-4:]]  # ~1 hour of 15-min checks
            older = [c["avg_rvol"] for c in checks[:-4]]
            if older:
                recent_avg = sum(recent_4) / len(recent_4)
                older_avg = sum(older[-12:]) / len(older[-12:])  # up to 3h of older data
                if older_avg > 0:
                    rolling_ratio = recent_avg / older_avg
                    if rolling_ratio < 0.5 and crypto_avg < 0.75:
                        print(f"\n🚨 CRYPTO GLIDE DETECTED (24/7)!")
                        print(f"   Recent RVOL: {recent_avg:.2f}x → Prior avg: {older_avg:.2f}x")
                        print(f"   Volume dropped {(1 - rolling_ratio)*100:.0f}% — glide killer active")
                        print(f"   ACTION: Tighten crypto stops to 1% or breakeven. No new entries.")
                    elif rolling_ratio > 1.5 and recent_avg > 1.0:
                        glide_was_active = state.get("crypto_glide_active", False)
                        if glide_was_active:
                            print(f"\n✅ CRYPTO GLIDE CLEARED — Volume recovered!")
                            print(f"   Recent RVOL: {recent_avg:.2f}x (was {older_avg:.2f}x)")
                            print(f"   ACTION: All clear — resume normal entries")
                        state["crypto_glide_active"] = False
                    
                    if rolling_ratio < 0.5 and crypto_avg < 0.75:
                        state["crypto_glide_active"] = True
        
        # Tiered stop protocol based on volume regime
        stop_tiers = {
            "SURGE": {"pct": "2%", "note": "Normal stops — big moves need room"},
            "NORMAL": {"pct": "1.5%", "note": "Tighter — less vol = less room needed"},
            "FADING": {"pct": "1%", "note": "GLIDE KILLER — stop the slow bleed"},
            "DEAD": {"pct": "0.5% or breakeven", "note": "GLIDE KILLER — protect everything"},
        }
        for regime_key, tier in stop_tiers.items():
            if regime_key in overall_regime:
                print(f"\n🛑 STOP PROTOCOL: {tier['pct']} stops ({tier['note']})")
                if regime_key in ("FADING", "DEAD"):
                    print(f"   ⚠️  Winners → breakeven stops. Flat/losers → {tier['pct']} max.")
                    print(f"   ⚠️  FLEET: Tighten ALL stops NOW per glide killer protocol.")
                break

        # Dead zone — run safe harbor + re-entry triggers
        if "DEAD" in overall_regime or "FADING" in overall_regime:
            print(f"\n🏠 GLIDE KILLER ACTIVE — Running Safe Harbor + Re-Entry Triggers...")
            try:
                from safe_harbor import find_safe_harbors
                find_safe_harbors(max_tier=2)
            except Exception as e:
                print(f"   Safe harbor scan failed: {e}")
            try:
                from reentry_triggers import check_triggers
                fired = check_triggers()
                if fired:
                    print(f"\n⚡ RE-ENTRY DETECTED — EXITING GLIDE KILLER MODE")
                    print(f"   {len(fired)} trigger(s) fired. Fleet should re-enter per playbook.")
            except Exception as e:
                print(f"   Re-entry trigger check failed: {e}")
        
        # Overnight crypto surge detection (11PM - 8AM)
        if now.hour >= 23 or now.hour < 8:
            crypto_data = [d for d in all_data if d["ticker"] in ["BTC-USD", "ETH-USD", "SOL-USD"] and "error" not in d]
            for cd in crypto_data:
                if cd["rvol"] >= 1.8:
                    print(f"\n🚨 OVERNIGHT CRYPTO SURGE: {cd['ticker']} RVOL {cd['rvol']:.2f}x!")
                    print(f"   Price: ${cd['price']:,.2f} | Volume {cd['rvol']:.1f}x normal")
                    print(f"   ACTION: Check for catalyst, consider adding if directional")
        
        state["last_regime"] = overall_regime
        state["checks"].append({
            "time": now.isoformat(),
            "avg_rvol": round(avg_rvol, 3),
            "regime": overall_regime,
        })
        # Keep last 50 checks only
        state["checks"] = state["checks"][-50:]
        save_state(state)
        
        # Write regime file that stop_check.py and other scripts can read
        regime_key = overall_regime.split(" ")[-1]  # SURGE/NORMAL/FADING/DEAD
        regime_output = {
            "regime": regime_key,
            "rvol": round(avg_rvol, 3),
            "rvol_delta": capital_regime["rvol_delta"],
            "stop_rule": capital_regime["stop_rule"],
            "entry_rule": capital_regime["entry_rule"],
            "glide_killer_active": regime_key in ("FADING", "DEAD"),
            "updated_at": now.isoformat(),
            "morning_avg_rvol": state.get("morning_avg_rvol"),
        }
        regime_file = "/Users/sheridanskala/.openclaw/workspace/logs/volume_regime.json"
        with open(regime_file, "w") as f:
            json.dump(regime_output, f, indent=2)
        
        return overall_regime, overall_action, avg_rvol
    
    return None, None, None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Volume Monitor")
    parser.add_argument("--continuous", action="store_true", help="Run every 15 min")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()
    
    if args.continuous:
        while True:
            try:
                run_volume_check()
            except Exception as e:
                print(f"ERROR: {e}")
            time.sleep(900)
    else:
        regime, action, rvol = run_volume_check()
        if args.json and regime:
            print(json.dumps({"regime": regime, "action": action, "rvol": rvol}))
