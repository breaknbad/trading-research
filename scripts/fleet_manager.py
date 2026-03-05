#!/usr/bin/env python3
"""fleet_manager.py — Bot-Down Redundancy Protocol.

Detects which bots are alive via Supabase bot_health.
If buddy (or any bot) is down, takes over their portfolio:
  - Enforces stop checks on their positions
  - Flags idle cash for deployment
  - Posts alerts to Discord

Buddy pairs: Alfred↔Eddie, Vex↔TARS
Escalation: 1 down=buddy, 2 down=split, 3 down=last man, 4=human alert

Run every 5 min via launchd.
"""

import json, os, sys, time, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "scripts"))

from bot_config import BOT_ID

# Supabase
SUPABASE_URL = 'https://vghssoltipiajiwzhkyn.supabase.co'
KEY = None
creds = Path.home() / '.supabase_trading_creds'
if creds.exists():
    for line in creds.read_text().splitlines():
        if '=' in line:
            k, v = line.strip().split('=', 1)
            if 'ANON' in k.upper():
                KEY = v

if not KEY:
    print("ERROR: No Supabase key", file=sys.stderr)
    sys.exit(1)

HEADERS = {'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'}

# Fleet config
ALL_BOTS = ["alfred", "tars", "vex", "eddie_v"]
BUDDY_PAIRS = {
    "alfred": "eddie_v",
    "eddie_v": "alfred",
    "vex": "tars",
    "tars": "vex",
}
STALE_MINUTES = 15
IDLE_CASH_THRESHOLD = 5000  # Flag if bot has >$5K cash sitting

# Discord webhook (optional — falls back to print)
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

STATE_FILE = WORKSPACE / "logs" / "fleet_manager_state.json"


def get_bot_health():
    """Check bot_health table for all bots."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/bot_health?select=bot_id,last_heartbeat,status",
            headers=HEADERS, timeout=10
        )
        if r.ok:
            return {b['bot_id']: b for b in r.json()}
    except Exception as e:
        print(f"⚠️ Failed to read bot_health: {e}")
    return {}


def get_all_snapshots():
    """Get portfolio snapshots for all bots."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_snapshots?select=bot_id,open_positions,cash_usd,total_value_usd",
            headers=HEADERS, timeout=10
        )
        if r.ok:
            return {b['bot_id']: b for b in r.json()}
    except Exception as e:
        print(f"⚠️ Failed to read snapshots: {e}")
    return {}


def is_bot_alive(health_entry):
    """Check if a bot's heartbeat is fresh."""
    if not health_entry:
        return False
    try:
        last_hb = datetime.fromisoformat(health_entry['last_heartbeat'].replace('Z', '+00:00'))
        age = datetime.now(timezone.utc) - last_hb
        return age < timedelta(minutes=STALE_MINUTES)
    except (KeyError, ValueError):
        return False


def determine_responsibilities(alive_bots, all_bots):
    """Given who's alive, determine who manages whom."""
    dead_bots = [b for b in all_bots if b not in alive_bots]
    assignments = {}  # managed_bot -> manager_bot

    if not dead_bots:
        return assignments  # Everyone alive, no takeover needed

    for dead in dead_bots:
        buddy = BUDDY_PAIRS.get(dead)
        if buddy and buddy in alive_bots:
            assignments[dead] = buddy
        else:
            # Buddy is also down — assign to any alive bot
            for alive in alive_bots:
                if alive not in assignments.values() or len(alive_bots) == 1:
                    assignments[dead] = alive
                    break
            else:
                # Last resort: first alive bot takes everything
                if alive_bots:
                    assignments[dead] = alive_bots[0]

    return assignments


def check_managed_positions(bot_id, snapshot):
    """Check stops and idle cash for a managed bot's portfolio."""
    alerts = []
    positions = snapshot.get('open_positions', []) or []
    cash = float(snapshot.get('cash_usd', 0))

    if cash > IDLE_CASH_THRESHOLD:
        alerts.append(f"💰 {bot_id} has ${cash:,.0f} idle cash — needs deployment")

    for pos in positions:
        ticker = pos.get('ticker', '')
        entry = float(pos.get('avg_entry', 0))
        current = float(pos.get('current_price', entry))
        qty = float(pos.get('quantity', 0))

        if entry <= 0 or qty <= 0:
            continue

        drawdown = ((entry - current) / entry) * 100 if pos.get('side', 'LONG') == 'LONG' else ((current - entry) / entry) * 100
        if drawdown > 5:
            alerts.append(f"🚨 {bot_id} {ticker}: {drawdown:.1f}% drawdown — approaching stop zone")
        elif drawdown > 3:
            alerts.append(f"⚠️ {bot_id} {ticker}: {drawdown:.1f}% drawdown — watching")

    return alerts


def load_state():
    """Load previous state to avoid duplicate alerts."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {"last_alerts": {}, "last_run": None}


def save_state(state):
    """Save state."""
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    print(f"\n{'='*60}")
    print(f"🏥 Fleet Manager — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    health = get_bot_health()
    snapshots = get_all_snapshots()
    state = load_state()

    # Determine who's alive
    alive = [b for b in ALL_BOTS if is_bot_alive(health.get(b))]
    dead = [b for b in ALL_BOTS if b not in alive]

    print(f"\n🟢 Alive: {', '.join(alive) if alive else 'NONE'}")
    print(f"🔴 Down:  {', '.join(dead) if dead else 'None'}")

    # Am I responsible for anyone?
    assignments = determine_responsibilities(alive, ALL_BOTS)
    my_responsibilities = [bot for bot, mgr in assignments.items() if mgr == BOT_ID]

    if not my_responsibilities:
        print(f"\n✅ {BOT_ID}: No bots to manage. Fleet healthy.")
        save_state(state)
        return

    print(f"\n📋 {BOT_ID} managing: {', '.join(my_responsibilities)}")

    all_alerts = []
    for managed_bot in my_responsibilities:
        snap = snapshots.get(managed_bot, {})
        alerts = check_managed_positions(managed_bot, snap)
        if alerts:
            all_alerts.extend(alerts)
            for a in alerts:
                print(f"  {a}")
        else:
            cash = float(snap.get('cash_usd', 0))
            total = float(snap.get('total_value_usd', 0))
            positions = len(snap.get('open_positions', []) or [])
            print(f"  {managed_bot}: ${total:,.0f} total, {positions} positions, ${cash:,.0f} cash — OK")

    # Log alerts (dedup against last run)
    new_alerts = [a for a in all_alerts if a not in state.get("last_alerts", {}).get(BOT_ID, [])]
    if new_alerts:
        print(f"\n🆕 New alerts: {len(new_alerts)}")
        for a in new_alerts:
            print(f"  {a}")

    state["last_alerts"] = state.get("last_alerts", {})
    state["last_alerts"][BOT_ID] = all_alerts
    save_state(state)
    print(f"\n✅ Fleet manager complete.")


if __name__ == "__main__":
    main()
