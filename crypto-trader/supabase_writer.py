"""
SupabaseWriter — writes bot data to Supabase via psycopg2.

Reads DB URL from:
  1. SUPABASE_DB_URL env var
  2. .env file (SUPABASE_DB_URL=...)
  3. ~/.supabase_db_url file
"""

import os
import json
from typing import Optional
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def _find_db_url() -> str:
    # 1. Environment variable
    url = os.environ.get("SUPABASE_DB_URL")
    if url:
        return url

    # 2. .env in project root
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith("SUPABASE_DB_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    # 3. Home dotfile
    home_path = os.path.expanduser("~/.supabase_db_url")
    if os.path.exists(home_path):
        return open(home_path).read().strip()

    raise RuntimeError("No Supabase DB URL found. Set SUPABASE_DB_URL env var, add to .env, or create ~/.supabase_db_url")


class SupabaseWriter:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or _find_db_url()

    @contextmanager
    def _conn(self):
        conn = psycopg2.connect(self.db_url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def update_bot_status(self, bot_name: str, *, emoji: str = "", status: str = "running",
                          strategy: str = "", balance: float = 25000, total_pnl: float = 0,
                          pnl_pct: float = 0, total_trades: int = 0, win_rate: float = 0,
                          best_trade: float = 0, worst_trade: float = 0):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_status (bot_name, emoji, status, strategy, balance, total_pnl,
                                            pnl_pct, total_trades, win_rate, best_trade, worst_trade, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (bot_name) DO UPDATE SET
                        emoji=EXCLUDED.emoji, status=EXCLUDED.status, strategy=EXCLUDED.strategy,
                        balance=EXCLUDED.balance, total_pnl=EXCLUDED.total_pnl, pnl_pct=EXCLUDED.pnl_pct,
                        total_trades=EXCLUDED.total_trades, win_rate=EXCLUDED.win_rate,
                        best_trade=EXCLUDED.best_trade, worst_trade=EXCLUDED.worst_trade, updated_at=NOW()
                """, (bot_name, emoji, status, strategy, balance, total_pnl, pnl_pct,
                      total_trades, win_rate, best_trade, worst_trade))

    def upsert_position(self, bot_name: str, pair: str, direction: str,
                        entry_price: float, current_price: float,
                        unrealized_pnl: float, size: float):
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Delete existing position for this bot+pair, then insert fresh
                cur.execute("DELETE FROM positions WHERE bot_name=%s AND pair=%s", (bot_name, pair))
                cur.execute("""
                    INSERT INTO positions (bot_name, pair, direction, entry_price, current_price, unrealized_pnl, size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (bot_name, pair, direction, entry_price, current_price, unrealized_pnl, size))

    def close_position(self, bot_name: str, pair: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM positions WHERE bot_name=%s AND pair=%s", (bot_name, pair))

    def add_trade(self, bot_name: str, pair: str, direction: str,
                  entry_price: float, exit_price: float, pnl: float,
                  pnl_pct: float, opened_at: Optional[str] = None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trades (bot_name, pair, direction, entry_price, exit_price, pnl, pnl_pct, opened_at, closed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (bot_name, pair, direction, entry_price, exit_price, pnl, pnl_pct, opened_at))

    def snapshot_pnl(self, bot_name: str, balance: float):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO pnl_snapshots (bot_name, balance, timestamp) VALUES (%s, %s, NOW())
                """, (bot_name, balance))

    def clear_positions(self, bot_name: str):
        """Remove all positions for a bot."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM positions WHERE bot_name=%s", (bot_name,))


if __name__ == "__main__":
    w = SupabaseWriter()
    print("Connected successfully. Testing write...")
    w.update_bot_status("test_bot", emoji="🧪", status="testing", strategy="test")
    print("✅ bot_status write OK")
    w.snapshot_pnl("test_bot", 25000)
    print("✅ pnl_snapshot write OK")
    # Cleanup
    with w._conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bot_status WHERE bot_name='test_bot'")
            cur.execute("DELETE FROM pnl_snapshots WHERE bot_name='test_bot'")
    print("✅ Cleanup done. All good!")
