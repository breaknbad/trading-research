# CALLED BY: volume_monitor.py when regime is FADING/DEAD
#!/usr/bin/env python3
"""
Re-Entry Trigger Monitor — Watches for conditions that signal end of dead zone.
Called by volume_monitor.py when regime is FADING or DEAD.
Also runs standalone to check all 5 triggers.

TARS owns activation/deactivation of glide killer mode.
When ANY trigger fires → post to Discord, exit glide killer mode, fleet re-enters.
"""

import json
import urllib.request
from datetime import datetime


def get_price(ticker):
    """Get current price and day change."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=8).read())
        r = data["chart"]["result"][0]
        price = r["meta"]["regularMarketPrice"]
        prev = r["meta"]["chartPreviousClose"]
        pct = (price - prev) / prev * 100
        volumes = r["indicators"]["quote"][0]["volume"]
        vol = volumes[-1] if volumes[-1] else 0
        prev_vol = volumes[-2] if len(volumes) > 1 and volumes[-2] else 1
        rvol = vol / prev_vol if prev_vol > 0 else 1
        return {"price": price, "pct": pct, "rvol": rvol}
    except Exception as e:
        return {"price": 0, "pct": 0, "rvol": 0, "error": str(e)}


def check_triggers():
    """Check all 5 re-entry triggers. Returns list of fired triggers."""
    now = datetime.now()
    fired = []
    
    print(f"\n{'='*60}")
    print(f"⚡ RE-ENTRY TRIGGER CHECK — {now.strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"{'='*60}")
    
    # Trigger 1: VIX reversal below 24
    vix = get_price("^VIX")
    if "error" not in vix:
        status = "🟢 FIRED" if vix["price"] < 24 else "🔴 NOT FIRED"
        print(f"\n1. VIX < 24: {status} (VIX = {vix['price']:.2f})")
        if vix["price"] < 24:
            fired.append({
                "trigger": "VIX_REVERSAL",
                "detail": f"VIX dropped to {vix['price']:.2f} (below 24 threshold)",
                "action": "Trim SQQQ 50%, add BTC SCOUT (4%), staged entry",
            })
    
    # Trigger 2: BTC breakout above $69K with volume
    btc = get_price("BTC-USD")
    if "error" not in btc:
        btc_break = btc["price"] > 69000 and btc["rvol"] > 1.2
        status = "🟢 FIRED" if btc_break else "🔴 NOT FIRED"
        print(f"2. BTC > $69K + RVOL > 1.2x: {status} (${btc['price']:,.0f}, RVOL {btc['rvol']:.2f}x)")
        if btc_break:
            fired.append({
                "trigger": "BTC_BREAKOUT",
                "detail": f"BTC broke ${btc['price']:,.0f} with {btc['rvol']:.1f}x volume",
                "action": "Add NEAR SCOUT→CONFIRM (higher beta), stop $1.30",
            })
    
    # Trigger 3: Power hour (3 PM+) with volume
    is_power_hour = now.hour >= 15
    spy = get_price("SPY")
    if "error" not in spy:
        power_trigger = is_power_hour and spy["rvol"] > 1.5
        reason = "not 3PM yet" if not is_power_hour else f"RVOL {spy['rvol']:.1f}x"
        status = "🟢 FIRED" if power_trigger else f"🔴 NOT FIRED ({reason})"
        print(f"3. Power hour + RVOL > 1.5x: {status}")
        if power_trigger:
            fired.append({
                "trigger": "POWER_HOUR",
                "detail": f"Power hour with SPY RVOL {spy['rvol']:.1f}x",
                "action": "Deploy into day's top performer only, max 2 trades, stops at breakeven",
            })
    
    # Trigger 4: 3-asset confirmation (BTC green + SPY stops falling + gold stabilizes)
    gld = get_price("GLD")
    btc_green = btc.get("pct", 0) > 0
    spy_stabilized = spy.get("pct", 0) > -1.0  # improved from lows
    gld_stabilized = gld.get("pct", 0) > -3.0 if "error" not in gld else False
    
    confirmation_count = sum([btc_green, spy_stabilized, gld_stabilized])
    all_confirmed = confirmation_count == 3
    status = "🟢 FIRED" if all_confirmed else f"🔴 NOT FIRED ({confirmation_count}/3)"
    details = []
    if btc_green: details.append("BTC ✅")
    else: details.append(f"BTC ❌ ({btc.get('pct', 0):+.1f}%)")
    if spy_stabilized: details.append("SPY ✅")
    else: details.append(f"SPY ❌ ({spy.get('pct', 0):+.1f}%)")
    if gld_stabilized: details.append("GLD ✅")
    else: details.append(f"GLD ❌ ({gld.get('pct', 0):+.1f}%)")
    print(f"4. 3-asset confirmation: {status} [{', '.join(details)}]")
    if all_confirmed:
        fired.append({
            "trigger": "THREE_ASSET_CONFIRM",
            "detail": "BTC green + SPY stabilized + GLD stabilized",
            "action": "Risk-off is over. Deploy 30% into BTC, staged. Add winners.",
        })
    
    # Trigger 5: NEAR still surging (specific to today)
    near = get_price("NEAR-USD")
    if "error" not in near:
        near_surge = near["rvol"] > 2.0 and near["pct"] > 0
        status = "🟢 ACTIVE" if near_surge else "🔴 FADING"
        print(f"5. NEAR surge continuation: {status} ({near['pct']:+.1f}%, RVOL {near['rvol']:.1f}x)")
        if near_surge:
            fired.append({
                "trigger": "NEAR_SURGE",
                "detail": f"NEAR +{near['pct']:.1f}% with {near['rvol']:.1f}x volume — money flowing here",
                "action": "Add NEAR if not already max position. Follow the flow.",
            })
    
    # Summary
    print(f"\n{'='*60}")
    if fired:
        print(f"⚡ {len(fired)} TRIGGER(S) FIRED — EXIT GLIDE KILLER MODE")
        for t in fired:
            print(f"  → {t['trigger']}: {t['detail']}")
            print(f"    ACTION: {t['action']}")
        print(f"\n🟢 GLIDE KILLER: DEACTIVATED — re-entry signals detected")
    else:
        print(f"🔴 NO TRIGGERS FIRED — GLIDE KILLER REMAINS ACTIVE")
        print(f"   Stay in capital preservation mode. Check again in 15 min.")
    print(f"{'='*60}")
    
    return fired


def execute_buy(bot_id, ticker, qty, price, reason):
    """Execute a buy via log_trade.py."""
    import subprocess, os
    cmd = [
        "python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_trade.py"),
        "--bot", bot_id, "--action", "BUY", "--ticker", ticker,
        "--qty", str(qty), "--price", str(price),
        "--reason", f"[RE_ENTRY] {reason}", "--skip-validation"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  ✅ RE-ENTRY EXECUTED: BUY {ticker} {qty}x @ ${price:.2f}")
            return True
        else:
            print(f"  ❌ RE-ENTRY FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ RE-ENTRY ERROR: {e}")
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-execute", action="store_true", help="Auto-execute re-entry trades at SCOUT size")
    args = parser.parse_args()
    
    triggers = check_triggers()
    if triggers:
        print(f"\n{len(triggers)} trigger(s) ready for execution.")
        if args.auto_execute:
            # Execute SCOUT-sized entries based on trigger actions
            # Each trigger defines an action with suggested entry
            for t in triggers:
                print(f"  → Would execute: {t['action']}")
                # Note: actual ticker/size/price parsing from trigger actions
                # would need more structured data. For now, flag for manual review.
                print(f"  ⚠️  Auto-execute for re-entry requires structured trigger output — flagging for manual review")
