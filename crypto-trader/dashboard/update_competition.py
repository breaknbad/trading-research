"""
Competition data writer for bot trade reporting.

Usage:
    from dashboard.update_competition import CompetitionWriter
    writer = CompetitionWriter(bot_name="Alfred", emoji="🎩")
    writer.update_balance(25150.00)
    writer.add_trade(pair="BTC-USD", direction="long", entry=67500, exit=67800, pnl=150.00)
    writer.update_position(pair="ETH-USD", direction="long", entry=3200, current=3250)
    writer.save()
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import fcntl

DATA_FILE = Path(__file__).parent / "competition_data.json"


class CompetitionWriter:
    def __init__(self, bot_name: str, emoji: str = "🤖"):
        self.bot_name = bot_name
        self.emoji = emoji
        self._load()

    def _load(self):
        if DATA_FILE.exists():
            with open(DATA_FILE, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "competition": {
                    "name": "Mi AI Crypto Trading Competition",
                    "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "end_date": "",
                    "starting_capital": 25000,
                    "rules": [
                        "$25,000 starting capital per bot",
                        "2% max stop-loss per trade",
                        "10% max position size",
                        "-5% daily circuit breaker",
                        "Paper trading only",
                        "Crypto pairs only"
                    ]
                },
                "bots": []
            }
        self.bot = self._get_or_create_bot()

    def _get_or_create_bot(self):
        for b in self.data["bots"]:
            if b["name"] == self.bot_name:
                return b
        bot = {
            "name": self.bot_name,
            "emoji": self.emoji,
            "strategy": "",
            "strategy_desc": "",
            "balance": 25000.0,
            "starting_balance": 25000.0,
            "total_pnl": 0.0,
            "pnl_pct": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "equity_curve": [25000],
            "equity_labels": [datetime.now(timezone.utc).strftime("%b %d")],
            "positions": [],
            "trades": []
        }
        self.data["bots"].append(bot)
        return bot

    def update_balance(self, balance: float):
        self.bot["balance"] = balance
        self.bot["total_pnl"] = balance - self.bot["starting_balance"]
        self.bot["pnl_pct"] = round((self.bot["total_pnl"] / self.bot["starting_balance"]) * 100, 2)
        # Update equity curve
        today = datetime.now(timezone.utc).strftime("%b %d")
        if self.bot["equity_labels"] and self.bot["equity_labels"][-1] == today:
            self.bot["equity_curve"][-1] = balance
        else:
            self.bot["equity_labels"].append(today)
            self.bot["equity_curve"].append(balance)

    def add_trade(self, pair: str, direction: str, entry: float, exit: float,
                  pnl: float, timestamp: Optional[str] = None):
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        trade = {
            "timestamp": timestamp,
            "pair": pair,
            "direction": direction,
            "entry": entry,
            "exit": exit,
            "pnl": pnl
        }
        self.bot["trades"].insert(0, trade)
        self.bot["total_trades"] += 1
        if pnl >= 0:
            self.bot["wins"] += 1
        else:
            self.bot["losses"] += 1
        total = self.bot["wins"] + self.bot["losses"]
        self.bot["win_rate"] = round((self.bot["wins"] / total) * 100, 1) if total > 0 else 0.0
        if pnl > self.bot["best_trade"]:
            self.bot["best_trade"] = pnl
        if pnl < self.bot["worst_trade"]:
            self.bot["worst_trade"] = pnl

    def update_position(self, pair: str, direction: str, entry: float,
                        current: float, size: float = 1.0):
        unrealized = round((current - entry) * size * (1 if direction == "long" else -1), 2)
        # Update existing or add new
        for p in self.bot["positions"]:
            if p["pair"] == pair:
                p.update({"direction": direction, "entry": entry, "current": current,
                          "size": size, "unrealized_pnl": unrealized})
                return
        self.bot["positions"].append({
            "pair": pair, "direction": direction, "entry": entry,
            "current": current, "size": size, "unrealized_pnl": unrealized
        })

    def close_position(self, pair: str):
        self.bot["positions"] = [p for p in self.bot["positions"] if p["pair"] != pair]

    def set_strategy(self, name: str, description: str = ""):
        self.bot["strategy"] = name
        self.bot["strategy_desc"] = description

    def save(self):
        with open(DATA_FILE, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(self.data, f, indent=2)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
