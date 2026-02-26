#!/usr/bin/env python3
"""
sync_dashboard.py — Pull live data from Supabase and write dashboard JSON files.
Run via cron every 30s or manually.
"""

import json
import os
import sys
from datetime import datetime, timezone, date
from decimal import Decimal
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: pip install psycopg2-binary")
    sys.exit(1)

DATA_DIR = Path(__file__).parent / "data"
DB_URL_FILE = Path.home() / ".supabase_db_url"

BOT_IDS = {
    "alfred": "alfred",
    "tars": "tars",
    "vex": "vex",
    "eddie_v": "eddie",  # DB uses eddie_v, file uses eddie
}


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def get_conn():
    url = DB_URL_FILE.read_text().strip()
    return psycopg2.connect(url)


def query(cur, sql, params=None):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def sync():
    conn = get_conn()
    cur = conn.cursor()

    # 1. Bot status/metadata
    bots = {r["bot_name"]: r for r in query(cur, "SELECT * FROM bot_status")}

    # 2. Latest portfolio snapshot per bot
    snapshots = {}
    for r in query(cur, """
        SELECT DISTINCT ON (bot_id) *
        FROM portfolio_snapshots
        ORDER BY bot_id, last_updated DESC
    """):
        snapshots[r["bot_id"]] = r

    # 3. All trades (newest first)
    all_trades = query(cur, """
        SELECT * FROM trades ORDER BY timestamp DESC
    """)

    # 4. Equity curves for charts
    equity = query(cur, """
        SELECT * FROM equity_snapshots ORDER BY recorded_at ASC
    """)

    conn.close()

    # Map bot_id -> bot_name for lookups
    id_to_name = {"alfred": "Alfred", "tars": "TARS", "vex": "Vex", "eddie_v": "Eddie V"}

    # Build per-bot JSON files
    for db_id, file_id in BOT_IDS.items():
        bot_meta = bots.get(id_to_name.get(db_id, db_id), {})
        snap = snapshots.get(db_id, {})
        bot_trades = [t for t in all_trades if t["bot_id"] == db_id]

        positions = snap.get("open_positions", []) or []

        # Calculate win rate from closed trades
        closed = [t for t in bot_trades if t.get("status") == "CLOSED" or t["action"] in ("SELL", "COVER")]
        # Simple: count sells that had profit vs loss based on reason text
        # Better: use realized_pl from snapshot
        total_trades = len(bot_trades)

        # Calculate unrealized P&L from positions
        unrealized_pl = sum(float(p.get("unrealized_pl", 0) or 0) for p in positions)

        # Position value
        position_value = sum(
            float(p.get("current_price", p.get("avg_entry", 0))) * float(p.get("quantity", 0))
            for p in positions
        )

        cash = float(snap.get("cash_usd", 0))
        total_value = float(snap.get("total_value_usd", cash + position_value))
        total_return_pct = float(snap.get("total_return_pct", 0))
        daily_return_pct = float(snap.get("daily_return_pct", 0))
        day_start_value = float(snap.get("day_start_value", 25000))
        daily_pnl = total_value - day_start_value
        realized_pl = float(snap.get("realized_pl", 0))

        data = {
            "bot_id": file_id,
            "bot_name": id_to_name.get(db_id, db_id),
            "emoji": bot_meta.get("emoji", "🤖"),
            "strategy": bot_meta.get("strategy", ""),
            "status": bot_meta.get("status", "unknown"),
            "updated_at": (snap.get("last_updated") or datetime.now(timezone.utc)).isoformat()
                if hasattr(snap.get("last_updated", ""), "isoformat")
                else str(snap.get("last_updated", datetime.now(timezone.utc).isoformat())),
            "total_value_usd": round(total_value, 2),
            "cash_usd": round(cash, 2),
            "total_return_pct": round(total_return_pct, 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_return_pct": round(daily_return_pct, 4),
            "realized_pl": round(realized_pl, 2),
            "unrealized_pl": round(unrealized_pl, 2),
            "day_start_value": round(day_start_value, 2),
            "win_rate": float(bot_meta.get("win_rate", 0)),
            "trade_count": len(bot_trades),
            "positions": [
                {
                    "ticker": p.get("ticker", ""),
                    "side": p.get("side", "LONG"),
                    "quantity": float(p.get("quantity", 0)),
                    "avg_entry": float(p.get("avg_entry", 0)),
                    "current_price": float(p.get("current_price", p.get("avg_entry", 0))),
                    "unrealized_pl": float(p.get("unrealized_pl", 0) or 0),
                    "pnl_pct": round(
                        ((float(p.get("current_price", p.get("avg_entry", 0))) - float(p.get("avg_entry", 1)))
                         / float(p.get("avg_entry", 1))) * 100
                        * (-1 if p.get("side", "").upper() == "SHORT" else 1),
                        2
                    ) if float(p.get("avg_entry", 0)) != 0 else 0,
                    "market_value": round(
                        float(p.get("current_price", p.get("avg_entry", 0))) * float(p.get("quantity", 0)), 2
                    ),
                }
                for p in positions
            ],
            "recent_trades": [
                {
                    "trade_id": t.get("trade_id", ""),
                    "timestamp": t["timestamp"].isoformat() if hasattr(t["timestamp"], "isoformat") else str(t["timestamp"]),
                    "action": t.get("action", ""),
                    "ticker": t.get("ticker", ""),
                    "quantity": float(t.get("quantity", 0)),
                    "price_usd": float(t.get("price_usd", 0)),
                    "total_usd": float(t.get("total_usd", 0)),
                    "reason": t.get("reason", ""),
                    "status": t.get("status", ""),
                }
                for t in bot_trades[:50]  # Last 50 trades
            ],
        }

        out = DATA_DIR / f"{file_id}.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, cls=DecimalEncoder)
        tmp.rename(out)
        print(f"✅ {file_id}.json — ${total_value:,.2f} ({len(positions)} positions, {len(bot_trades)} trades)")

    # Write fleet summary
    fleet = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "equity_curve": [
            {
                "bot_id": BOT_IDS.get(e["bot_id"], e["bot_id"]),
                "value": float(e["value"]),
                "recorded_at": e["recorded_at"].isoformat() if hasattr(e["recorded_at"], "isoformat") else str(e["recorded_at"]),
            }
            for e in equity
        ],
    }
    with open(DATA_DIR / "fleet.json", "w") as f:
        json.dump(fleet, f, indent=2, cls=DecimalEncoder)
    print(f"✅ fleet.json — {len(equity)} equity points")


if __name__ == "__main__":
    try:
        sync()
        print(f"\n🟢 Sync complete at {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"🔴 Sync failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
