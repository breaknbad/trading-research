#!/usr/bin/env python3
"""Portfolio Health Monitor — dumb loop, zero AI.
Runs every 60s via launchd. Checks position limits, heat cap, contradictions, data integrity.
Writes alerts to alerts.json. AI reads alerts on heartbeat.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

# Config
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vghssoltipiajiwzhkyn.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaHNzb2x0aXBpYWppd3poa3luIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MTczOTQ4OCwiZXhwIjoyMDg3MzE1NDg4fQ.xLUUt4yrFL8kRnjFN87fbxc294A-oaeN61klyL0qPVc")
WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
# Auto-detect bot identity
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bot_config import BOT_ID, BOT_IDS
LOG_FILE = os.path.join(WORKSPACE, "logs", "portfolio_health.log")
ALERTS_FILE = os.path.join(WORKSPACE, "alerts.json")
EXIT_RULES_FILE = os.path.join(WORKSPACE, "exit_rules.json")

# Ensure dirs
os.makedirs(os.path.join(WORKSPACE, "logs"), exist_ok=True)

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_exit_rules():
    try:
        with open(EXIT_RULES_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "max_positions": 10,
            "max_position_pct": 10,
            "max_sector_concentration_pct": 30,
            "hard_exits": {"max_loss_pct": 5}
        }

def fetch_positions():
    positions = []
    for bid in BOT_IDS:
        url = f"{SUPABASE_URL}/rest/v1/trades?select=*&status=eq.OPEN&bot_id=eq.{bid}"
        req = urllib.request.Request(url, headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        })
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            for t in data:
                positions.append({
                    "trade_id": t.get("trade_id"),
                    "bot_id": t.get("bot_id"),
                    "ticker": t.get("ticker"),
                    "side": t.get("action", "BUY"),
                    "quantity": t.get("quantity", 0),
                    "entry_price": t.get("price_usd", 0),
                    "market": t.get("market", "UNKNOWN"),
                    "total_usd": t.get("total_usd", 0),
                })
        except Exception as e:
            log(f"Error fetching {bid}: {e}")
    return positions

def check_health(positions, rules):
    alerts = []
    max_pos = rules.get("max_positions", 10)
    max_loss_pct = rules.get("hard_exits", {}).get("max_loss_pct", 5)

    # 1. Position count
    if len(positions) > max_pos:
        alerts.append({
            "type": "position_limit_exceeded",
            "severity": "high",
            "message": f"Position count {len(positions)} exceeds cap of {max_pos}. Need to trim {len(positions) - max_pos} positions.",
            "count": len(positions),
            "cap": max_pos
        })

    # 2. Contradictory positions (long + short same ticker)
    ticker_sides = {}
    for p in positions:
        t = p["ticker"]
        if t not in ticker_sides:
            ticker_sides[t] = set()
        ticker_sides[t].add(p["side"])
    
    for ticker, sides in ticker_sides.items():
        if len(sides) > 1:
            alerts.append({
                "type": "contradictory_position",
                "severity": "critical",
                "message": f"Both LONG and SHORT on {ticker}. Net out immediately.",
                "ticker": ticker,
                "sides": list(sides)
            })

    # 3. Duplicate entries (same ticker, same side, similar price)
    seen = {}
    for p in positions:
        key = f"{p['ticker']}_{p['side']}"
        if key not in seen:
            seen[key] = []
        seen[key].append(p)
    
    for key, dupes in seen.items():
        if len(dupes) > 3:  # More than 3 entries = likely fragmented
            alerts.append({
                "type": "fragmented_position",
                "severity": "medium",
                "message": f"{key.replace('_', ' ')}: {len(dupes)} separate entries. Consider consolidating.",
                "ticker": dupes[0]["ticker"],
                "count": len(dupes)
            })

    # 4. Corrupted data
    for p in positions:
        market = p.get("market", "")
        if market and len(market) > 20:  # Market field should be short code
            alerts.append({
                "type": "corrupted_data",
                "severity": "high",
                "message": f"Corrupted market field on {p['ticker']}: '{market[:50]}...'",
                "trade_id": p.get("trade_id")
            })
        if not p.get("entry_price") or p["entry_price"] <= 0:
            alerts.append({
                "type": "corrupted_data",
                "severity": "high",
                "message": f"Missing/invalid entry price on {p['ticker']}",
                "trade_id": p.get("trade_id")
            })

    # 5. Concentration check (single ticker > 25% of total value)
    total_value = sum(abs(p.get("total_usd", 0)) for p in positions)
    if total_value > 0:
        ticker_values = {}
        for p in positions:
            t = p["ticker"]
            ticker_values[t] = ticker_values.get(t, 0) + abs(p.get("total_usd", 0))
        for ticker, val in ticker_values.items():
            pct = (val / total_value) * 100
            if pct > 25:
                alerts.append({
                    "type": "concentration_risk",
                    "severity": "medium",
                    "message": f"{ticker} is {pct:.1f}% of portfolio. Max recommended: 25%.",
                    "ticker": ticker,
                    "pct": round(pct, 1)
                })

    return alerts

def write_alerts(alerts):
    data = {
        "lastChecked": datetime.now(timezone.utc).isoformat(),
        "positionAlerts": alerts,
        "alertCount": len(alerts),
        "criticalCount": sum(1 for a in alerts if a.get("severity") == "critical"),
        "highCount": sum(1 for a in alerts if a.get("severity") == "high")
    }
    
    # Merge with existing alerts (from other monitors)
    existing = {}
    try:
        with open(ALERTS_FILE) as f:
            existing = json.load(f)
    except Exception:
        pass
    
    existing["portfolio"] = data
    existing["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    
    with open(ALERTS_FILE, "w") as f:
        json.dump(existing, f, indent=2)

def write_health_signal(alerts):
    """Write critical alerts to fleet_signals table."""
    critical = [a for a in alerts if a.get("severity") in ("critical", "high")]
    if not critical:
        return
    
    for alert in critical[:3]:  # Max 3 signals per check
        payload = json.dumps({
            "bot_id": BOT_ID,
            "signal_type": "alert",
            "ticker": alert.get("ticker", "PORTFOLIO"),
            "direction": None,
            "score": 10 if alert["severity"] == "critical" else 7,
            "message": alert["message"],
            "metadata": json.dumps(alert)
        }).encode()
        
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/fleet_signals",
            data=payload,
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            log(f"Signal write error: {e}")

def run_once():
    rules = load_exit_rules()
    positions = fetch_positions()
    alerts = check_health(positions, rules)
    write_alerts(alerts)
    
    if alerts:
        write_health_signal(alerts)
        log(f"ALERTS: {len(alerts)} ({sum(1 for a in alerts if a['severity']=='critical')} critical, {sum(1 for a in alerts if a['severity']=='high')} high)")
        for a in alerts:
            log(f"  [{a['severity'].upper()}] {a['message']}")
    else:
        log("OK — no alerts")

def main():
    log("Portfolio Health Monitor started")
    while True:
        try:
            run_once()
        except Exception as e:
            log(f"ERROR in health check: {e}")
        time.sleep(60)

if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
    else:
        main()
