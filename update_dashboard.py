"""
Dashboard data writer for trading bots.

Usage:
    from dashboard.update_dashboard import DashboardWriter
    writer = DashboardWriter()
    writer.update_bot_status("scalper", running=True)
    writer.add_trade("scalper", pair="BTC-USD", direction="long",
                     entry_price=51000, exit_price=51200, size=0.05, pnl=10.0)
    writer.update_position("scalper", pair="BTC-USD", direction="long",
                           entry_price=51000, current_price=51200, size=0.05)
    writer.save()
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import threading

DATA_FILE = Path(__file__).parent / "data.json"
_lock = threading.Lock()


def _now_iso():
    return datetime.now().astimezone().isoformat()


def _default_data():
    return {
        "last_updated": _now_iso(),
        "aggregate": {
            "total_pnl": 0, "daily_pnl": 0, "total_trades": 0,
            "win_rate": 0, "active_positions": 0,
            "best_trade": 0, "worst_trade": 0,
        },
        "bots": {},
        "positions": [],
        "trades": [],
        "pnl_history": [],
        "asset_breakdown": {},
    }


class DashboardWriter:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path) if path else DATA_FILE
        self._load()

    def _load(self):
        with _lock:
            if self.path.exists():
                with open(self.path) as f:
                    self.data = json.load(f)
            else:
                self.data = _default_data()

    def update_bot_status(self, bot_id: str, *, running: bool = True,
                          name: Optional[str] = None, error: bool = False,
                          uptime_seconds: int = 0):
        status = "error" if error else ("running" if running else "stopped")
        if bot_id not in self.data["bots"]:
            self.data["bots"][bot_id] = {
                "name": name or bot_id.replace("_", " ").title(),
                "status": status,
                "last_update": _now_iso(),
                "uptime_seconds": uptime_seconds,
                "stats": {"total_pnl": 0, "daily_pnl": 0, "total_trades": 0, "win_rate": 0},
            }
        else:
            b = self.data["bots"][bot_id]
            b["status"] = status
            b["last_update"] = _now_iso()
            b["uptime_seconds"] = uptime_seconds
            if name:
                b["name"] = name

    def update_position(self, bot_id: str, *, pair: str, direction: str = "long",
                        entry_price: float, current_price: float, size: float,
                        opened_at: Optional[str] = None):
        positions = self.data["positions"]
        # Update existing or add new
        for p in positions:
            if p["bot"] == bot_id and p["pair"] == pair:
                p.update(direction=direction, entry_price=entry_price,
                         current_price=current_price, size=size)
                if direction == "long":
                    p["unrealized_pnl"] = round((current_price - entry_price) * size, 2)
                else:
                    p["unrealized_pnl"] = round((entry_price - current_price) * size, 2)
                return
        pnl = round(((current_price - entry_price) if direction == "long"
                      else (entry_price - current_price)) * size, 2)
        positions.append({
            "bot": bot_id, "pair": pair, "direction": direction,
            "entry_price": entry_price, "current_price": current_price,
            "size": size, "unrealized_pnl": pnl,
            "opened_at": opened_at or _now_iso(),
        })

    def close_position(self, bot_id: str, pair: str):
        self.data["positions"] = [
            p for p in self.data["positions"]
            if not (p["bot"] == bot_id and p["pair"] == pair)
        ]

    def add_trade(self, bot_id: str, *, pair: str, direction: str = "long",
                  entry_price: float, exit_price: float, size: float, pnl: float,
                  closed_at: Optional[str] = None):
        self.data["trades"].insert(0, {
            "bot": bot_id, "pair": pair, "direction": direction,
            "entry_price": entry_price, "exit_price": exit_price,
            "size": size, "pnl": round(pnl, 2),
            "closed_at": closed_at or _now_iso(),
        })
        # Keep last 500
        self.data["trades"] = self.data["trades"][:500]
        # Update per-bot stats
        self._update_bot_stats(bot_id)
        # Update asset breakdown
        ab = self.data.setdefault("asset_breakdown", {})
        if pair not in ab:
            ab[pair] = {"total_trades": 0, "total_pnl": 0, "win_rate": 0}
        a = ab[pair]
        a["total_trades"] += 1
        a["total_pnl"] = round(a["total_pnl"] + pnl, 2)
        pair_trades = [t for t in self.data["trades"] if t["pair"] == pair]
        wins = sum(1 for t in pair_trades if t["pnl"] > 0)
        a["win_rate"] = round(wins / len(pair_trades) * 100, 1) if pair_trades else 0

    def add_pnl_snapshot(self, cumulative_pnl: float):
        self.data["pnl_history"].append({
            "timestamp": _now_iso(),
            "cumulative_pnl": round(cumulative_pnl, 2),
        })

    def _update_bot_stats(self, bot_id: str):
        if bot_id not in self.data["bots"]:
            return
        bot_trades = [t for t in self.data["trades"] if t["bot"] == bot_id]
        s = self.data["bots"][bot_id]["stats"]
        s["total_trades"] = len(bot_trades)
        s["total_pnl"] = round(sum(t["pnl"] for t in bot_trades), 2)
        wins = sum(1 for t in bot_trades if t["pnl"] > 0)
        s["win_rate"] = round(wins / len(bot_trades) * 100, 1) if bot_trades else 0
        today = datetime.now().date().isoformat()
        s["daily_pnl"] = round(sum(
            t["pnl"] for t in bot_trades if t["closed_at"][:10] == today
        ), 2)

    def _recalc_aggregate(self):
        trades = self.data["trades"]
        a = self.data["aggregate"]
        a["total_trades"] = len(trades)
        a["total_pnl"] = round(sum(t["pnl"] for t in trades), 2)
        a["active_positions"] = len(self.data["positions"])
        wins = sum(1 for t in trades if t["pnl"] > 0)
        a["win_rate"] = round(wins / len(trades) * 100, 1) if trades else 0
        a["best_trade"] = max((t["pnl"] for t in trades), default=0)
        a["worst_trade"] = min((t["pnl"] for t in trades), default=0)
        today = datetime.now().date().isoformat()
        a["daily_pnl"] = round(sum(
            t["pnl"] for t in trades if t["closed_at"][:10] == today
        ), 2)

    def save(self):
        self._recalc_aggregate()
        self.data["last_updated"] = _now_iso()
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2)
            tmp.rename(self.path)
