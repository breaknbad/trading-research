"""
5-Minute Multi-Crypto Scalping Bot.

Polls Coinbase REST API every N minutes, computes directional signals
across multiple pairs using a weighted indicator ensemble, then paper-trades
or live-trades the top signals.
"""

import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

from coinbase_client import fetch_candles
from indicators import (
    add_bollinger_bands, add_rsi, add_macd, add_ema,
)
from auth_client import CoinbaseAuthClient

try:
    from supabase_writer import SupabaseWriter
    _supabase_available = True
except ImportError:
    _supabase_available = False

logger = logging.getLogger(__name__)

# ── Constants ──

DEFAULT_PAIRS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD",
    "AVAX-USD", "LINK-USD", "SHIB-USD",
]

SIGNAL_UP = "UP"
SIGNAL_DOWN = "DOWN"
SIGNAL_SKIP = "SKIP"

# Indicator weights (total = 6.0)
WEIGHTS = {
    "rsi":       1.0,
    "macd":      1.0,
    "volume":    0.8,
    "bb":        1.0,
    "ema_cross": 1.2,
    "momentum":  1.0,
}
TOTAL_WEIGHT = sum(WEIGHTS.values())
CONFIDENCE_THRESHOLD = 0.55  # fraction of total weight needed to trade


# ── Data classes ──

@dataclass
class Signal:
    pair: str
    direction: str  # UP / DOWN / SKIP
    score: float    # -1.0 to +1.0 (normalized)
    raw_score: float
    price: float
    details: Dict[str, str] = field(default_factory=dict)


@dataclass
class Position:
    pair: str
    direction: str
    entry_price: float
    size_usd: float
    entry_time: str
    stop_loss: float


@dataclass
class Trade:
    pair: str
    direction: str
    score: float
    entry_price: float
    exit_price: float
    size_usd: float
    pnl: float
    entry_time: str
    exit_time: str


# ── Signal computation ──

def _fetch_pair_data(pair: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch 1m and 5m candles for a pair (minimal history needed)."""
    now = int(time.time())
    # Need ~50 candles of each for indicators
    df_1m = fetch_candles(pair, "1m", start=now - 3600, end=now)
    time.sleep(0.15)
    df_5m = fetch_candles(pair, "5m", start=now - 18000, end=now)
    return df_1m, df_5m


def compute_signal(pair: str) -> Signal:
    """
    Compute a directional signal for a single pair.

    Uses 6 indicators, each voting UP (+weight) or DOWN (-weight) or 0.
    """
    try:
        df_1m, df_5m = _fetch_pair_data(pair)
    except Exception as e:
        logger.warning("Failed to fetch data for %s: %s", pair, e)
        return Signal(pair=pair, direction=SIGNAL_SKIP, score=0, raw_score=0,
                      price=0, details={"error": str(e)})

    # Enrich 5m frame (primary)
    df = df_5m.copy()
    df = add_rsi(df, window=14)
    df = add_macd(df)
    df = add_bollinger_bands(df, window=20, num_std=2.0)
    df = add_ema(df, window=9, col_name="ema_9")
    df = add_ema(df, window=21, col_name="ema_21")

    # Also get 1m RSI
    df_1m = add_rsi(df_1m, window=14)

    if len(df) < 21 or len(df_1m) < 14:
        return Signal(pair=pair, direction=SIGNAL_SKIP, score=0, raw_score=0,
                      price=0, details={"error": "insufficient data"})

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last["close"])
    details: Dict[str, str] = {}
    raw = 0.0

    # 1) RSI — combine 1m and 5m
    rsi_5m = float(last["rsi"])
    rsi_1m = float(df_1m.iloc[-1]["rsi"])
    rsi_avg = (rsi_5m + rsi_1m) / 2
    if rsi_avg < 35:
        raw += WEIGHTS["rsi"]
        details["rsi"] = f"UP (avg={rsi_avg:.1f})"
    elif rsi_avg > 65:
        raw -= WEIGHTS["rsi"]
        details["rsi"] = f"DOWN (avg={rsi_avg:.1f})"
    else:
        details["rsi"] = f"NEUTRAL ({rsi_avg:.1f})"

    # 2) MACD histogram direction + crossover
    hist_now = float(last["macd_hist"])
    hist_prev = float(prev["macd_hist"])
    macd_rising = hist_now > hist_prev
    macd_cross_up = hist_prev < 0 and hist_now > 0
    macd_cross_down = hist_prev > 0 and hist_now < 0
    if macd_cross_up or (macd_rising and hist_now > 0):
        raw += WEIGHTS["macd"]
        details["macd"] = f"UP (hist={hist_now:.4f})"
    elif macd_cross_down or (not macd_rising and hist_now < 0):
        raw -= WEIGHTS["macd"]
        details["macd"] = f"DOWN (hist={hist_now:.4f})"
    else:
        details["macd"] = f"NEUTRAL (hist={hist_now:.4f})"

    # 3) Volume — current vs 20-period average
    vol_avg = float(df["volume"].tail(20).mean())
    vol_now = float(last["volume"])
    vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0
    # High volume confirms the price direction
    price_change = price - float(prev["close"])
    if vol_ratio > 1.3:
        if price_change > 0:
            raw += WEIGHTS["volume"]
            details["volume"] = f"UP (ratio={vol_ratio:.2f})"
        else:
            raw -= WEIGHTS["volume"]
            details["volume"] = f"DOWN (ratio={vol_ratio:.2f})"
    else:
        details["volume"] = f"NEUTRAL (ratio={vol_ratio:.2f})"

    # 4) Bollinger Band position
    bb_pband = float(last["bb_pband"])  # 0=lower, 0.5=mid, 1=upper
    if bb_pband < 0.15:
        raw += WEIGHTS["bb"]
        details["bb"] = f"UP (pband={bb_pband:.2f})"
    elif bb_pband > 0.85:
        raw -= WEIGHTS["bb"]
        details["bb"] = f"DOWN (pband={bb_pband:.2f})"
    else:
        details["bb"] = f"NEUTRAL (pband={bb_pband:.2f})"

    # 5) EMA crossover (9 vs 21)
    ema9 = float(last["ema_9"])
    ema21 = float(last["ema_21"])
    ema9_prev = float(prev["ema_9"])
    ema21_prev = float(prev["ema_21"])
    if ema9 > ema21 and ema9_prev <= ema21_prev:
        raw += WEIGHTS["ema_cross"]
        details["ema"] = "UP (golden cross)"
    elif ema9 > ema21:
        raw += WEIGHTS["ema_cross"] * 0.5
        details["ema"] = "UP (above)"
    elif ema9 < ema21 and ema9_prev >= ema21_prev:
        raw -= WEIGHTS["ema_cross"]
        details["ema"] = "DOWN (death cross)"
    elif ema9 < ema21:
        raw -= WEIGHTS["ema_cross"] * 0.5
        details["ema"] = "DOWN (below)"
    else:
        details["ema"] = "NEUTRAL"

    # 6) Price momentum — rate of change over last 5 candles
    if len(df) >= 6:
        roc = (price - float(df.iloc[-6]["close"])) / float(df.iloc[-6]["close"])
        if roc > 0.003:
            raw += WEIGHTS["momentum"]
            details["momentum"] = f"UP (roc={roc:.4f})"
        elif roc < -0.003:
            raw -= WEIGHTS["momentum"]
            details["momentum"] = f"DOWN (roc={roc:.4f})"
        else:
            details["momentum"] = f"NEUTRAL (roc={roc:.4f})"
    else:
        details["momentum"] = "NEUTRAL (insufficient)"

    # Normalize score to [-1, +1]
    score = raw / TOTAL_WEIGHT

    # Determine direction
    if score >= CONFIDENCE_THRESHOLD:
        direction = SIGNAL_UP
    elif score <= -CONFIDENCE_THRESHOLD:
        direction = SIGNAL_DOWN
    else:
        direction = SIGNAL_SKIP

    return Signal(pair=pair, direction=direction, score=score,
                  raw_score=raw, price=price, details=details)


# ── Scalper engine ──

class Scalper:
    """Main scalping engine — paper or live."""

    def __init__(
        self,
        pairs: List[str] = None,
        balance: float = 1000.0,
        live: bool = False,
        max_positions: int = 3,
        max_per_trade: float = 0.30,  # 30% of capital
        stop_loss_pct: float = 0.005,  # 0.5%
        state_file: str = "scalper_trades.json",
    ):
        self.pairs = pairs or DEFAULT_PAIRS
        self.balance = balance
        self.initial_balance = balance
        self.live = live
        self.max_positions = max_positions
        self.max_per_trade = max_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.state_file = state_file

        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.round_num = 0

        self.auth_client: Optional[CoinbaseAuthClient] = None
        if self.live:
            self.auth_client = CoinbaseAuthClient()

        self._load_state()

    # ── State persistence ──

    def _load_state(self):
        try:
            with open(self.state_file) as f:
                data = json.load(f)
            self.balance = data.get("balance", self.balance)
            self.trades = [Trade(**t) for t in data.get("trades", [])]
            self.positions = {k: Position(**v) for k, v in data.get("positions", {}).items()}
            self.round_num = data.get("round_num", 0)
            logger.info("Loaded state: balance=$%.2f, %d trades, %d positions",
                        self.balance, len(self.trades), len(self.positions))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_state(self):
        data = {
            "balance": self.balance,
            "initial_balance": self.initial_balance,
            "round_num": self.round_num,
            "trades": [asdict(t) for t in self.trades],
            "positions": {k: asdict(v) for k, v in self.positions.items()},
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    # ── Trading logic ──

    def _close_position(self, pair: str, exit_price: float):
        """Close an existing position and record the trade."""
        pos = self.positions.pop(pair)
        now = datetime.now(timezone.utc).isoformat()

        if pos.direction == SIGNAL_UP:
            pnl = (exit_price - pos.entry_price) / pos.entry_price * pos.size_usd
        else:  # DOWN
            pnl = (pos.entry_price - exit_price) / pos.entry_price * pos.size_usd

        self.balance += pos.size_usd + pnl

        trade = Trade(
            pair=pair, direction=pos.direction, score=0,
            entry_price=pos.entry_price, exit_price=exit_price,
            size_usd=pos.size_usd, pnl=pnl,
            entry_time=pos.entry_time, exit_time=now,
        )
        self.trades.append(trade)
        logger.info("CLOSED %s %s: entry=%.6f exit=%.6f pnl=$%.2f",
                     pos.direction, pair, pos.entry_price, exit_price, pnl)

        if self.live and self.auth_client:
            self._live_close(pos, exit_price)

    def _open_position(self, signal: Signal):
        """Open a new position from a signal."""
        size_usd = min(self.balance * self.max_per_trade, self.balance)
        if size_usd < 1.0:
            logger.warning("Insufficient balance ($%.2f) to open position", self.balance)
            return

        self.balance -= size_usd
        now = datetime.now(timezone.utc).isoformat()

        stop = signal.price * (1 - self.stop_loss_pct) if signal.direction == SIGNAL_UP \
            else signal.price * (1 + self.stop_loss_pct)

        pos = Position(
            pair=signal.pair, direction=signal.direction,
            entry_price=signal.price, size_usd=size_usd,
            entry_time=now, stop_loss=stop,
        )
        self.positions[signal.pair] = pos
        logger.info("OPENED %s %s @ %.6f ($%.2f) stop=%.6f",
                     signal.direction, signal.pair, signal.price, size_usd, stop)

        if self.live and self.auth_client:
            self._live_open(signal, size_usd)

    def _live_open(self, signal: Signal, size_usd: float):
        side = "BUY" if signal.direction == SIGNAL_UP else "SELL"
        try:
            result = self.auth_client.place_order(
                product_id=signal.pair, side=side,
                order_type="MARKET", quote_size=f"{size_usd:.2f}",
            )
            logger.info("LIVE ORDER: %s", result)
        except Exception as e:
            logger.error("LIVE ORDER FAILED: %s", e)

    def _live_close(self, pos: Position, exit_price: float):
        side = "SELL" if pos.direction == SIGNAL_UP else "BUY"
        base_size = pos.size_usd / pos.entry_price
        try:
            result = self.auth_client.place_order(
                product_id=pos.pair, side=side,
                order_type="MARKET", base_size=f"{base_size:.8f}",
            )
            logger.info("LIVE CLOSE: %s", result)
        except Exception as e:
            logger.error("LIVE CLOSE FAILED: %s", e)

    def _check_stop_losses(self, signals: List[Signal]):
        """Close positions that hit their stop loss."""
        price_map = {s.pair: s.price for s in signals if s.price > 0}
        for pair in list(self.positions):
            pos = self.positions[pair]
            price = price_map.get(pair, 0)
            if price <= 0:
                continue
            if pos.direction == SIGNAL_UP and price <= pos.stop_loss:
                logger.info("STOP LOSS triggered for %s @ %.6f", pair, price)
                self._close_position(pair, price)
            elif pos.direction == SIGNAL_DOWN and price >= pos.stop_loss:
                logger.info("STOP LOSS triggered for %s @ %.6f", pair, price)
                self._close_position(pair, price)

    # ── Main loop ──

    def run_round(self) -> List[Signal]:
        """Execute one scalping round: fetch signals, manage positions, print dashboard."""
        self.round_num += 1
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n{'='*70}")
        print(f"  SCALPER ROUND #{self.round_num}  |  {now_str}  |  {'LIVE' if self.live else 'PAPER'}")
        print(f"{'='*70}")

        # 1. Compute signals for all pairs
        signals: List[Signal] = []
        for pair in self.pairs:
            sig = compute_signal(pair)
            signals.append(sig)
            time.sleep(0.1)  # rate limit courtesy

        # 2. Check stop losses
        self._check_stop_losses(signals)

        # 3. Close existing positions (exit after one round)
        for pair in list(self.positions):
            price_map = {s.pair: s.price for s in signals if s.price > 0}
            if pair in price_map:
                self._close_position(pair, price_map[pair])

        # 4. Rank actionable signals by absolute score
        actionable = [s for s in signals if s.direction != SIGNAL_SKIP]
        actionable.sort(key=lambda s: abs(s.score), reverse=True)

        # 5. Open new positions (top N)
        slots = self.max_positions - len(self.positions)
        for sig in actionable[:slots]:
            if sig.pair not in self.positions:
                self._open_position(sig)

        # 6. Dashboard
        self._print_dashboard(signals)
        self._save_state()
        self._push_to_supabase()
        return signals

    def _print_dashboard(self, signals: List[Signal]):
        """Print a formatted status table."""
        total_pnl = sum(t.pnl for t in self.trades)
        win_count = sum(1 for t in self.trades if t.pnl > 0)
        total_count = len(self.trades)
        win_rate = (win_count / total_count * 100) if total_count else 0

        print(f"\n{'PAIR':<12} {'SIGNAL':<6} {'SCORE':>7} {'PRICE':>14} {'INDICATORS'}")
        print("-" * 70)
        for sig in sorted(signals, key=lambda s: abs(s.score), reverse=True):
            indicators = " | ".join(f"{k}:{v}" for k, v in sig.details.items())
            arrow = "🟢" if sig.direction == SIGNAL_UP else "🔴" if sig.direction == SIGNAL_DOWN else "⚪"
            print(f"{sig.pair:<12} {arrow} {sig.direction:<4} {sig.score:>+.3f}  "
                  f"${sig.price:>12,.2f}  {indicators[:60]}")

        if self.positions:
            print(f"\n  ACTIVE POSITIONS:")
            for pair, pos in self.positions.items():
                print(f"    {pos.direction} {pair} @ ${pos.entry_price:,.2f} "
                      f"(${pos.size_usd:.2f}) stop=${pos.stop_loss:,.2f}")

        print(f"\n  BALANCE: ${self.balance:,.2f}  |  "
              f"P&L: ${total_pnl:>+,.2f}  |  "
              f"TRADES: {total_count}  |  "
              f"WIN RATE: {win_rate:.1f}%")
        print(f"{'='*70}\n")

    def _push_to_supabase(self):
        """Push current state to Supabase for dashboard display."""
        if not _supabase_available:
            return
        try:
            writer = SupabaseWriter()
            total_pnl = sum(t.pnl for t in self.trades)
            win_count = sum(1 for t in self.trades if t.pnl > 0)
            total_count = len(self.trades)
            win_rate = (win_count / total_count * 100) if total_count else 0
            initial = 1000.0
            pnl_pct = (total_pnl / initial * 100) if initial else 0

            writer.update_bot_status(
                "Alfred-Scalper", emoji="🎩", status="running",
                strategy="5-Min Multi-Crypto Scalper",
                balance=self.balance, total_pnl=total_pnl,
                pnl_pct=pnl_pct, total_trades=total_count,
                win_rate=win_rate,
                best_trade=max((t.pnl for t in self.trades), default=0),
                worst_trade=min((t.pnl for t in self.trades), default=0),
            )

            # Clear and re-push positions
            writer.clear_positions("Alfred-Scalper")
            for pair, pos in self.positions.items():
                writer.upsert_position(
                    "Alfred-Scalper", pair=pair, direction=pos.direction,
                    entry_price=pos.entry_price, current_price=pos.entry_price,
                    size=pos.size_usd,
                )

            # Push any new trades (last 5 to avoid duplicates on restart)
            for t in self.trades[-5:]:
                writer.add_trade(
                    "Alfred-Scalper", pair=t.pair, direction=t.direction,
                    entry_price=t.entry_price, exit_price=t.exit_price,
                    pnl=t.pnl,
                )

            # P&L snapshot for charting
            writer.snapshot_pnl("Alfred-Scalper", self.balance)
            logger.info("Pushed state to Supabase")
        except Exception as e:
            logger.warning("Supabase push failed: %s", e)

    def run(self, interval_minutes: int = 5):
        """Run the scalper loop indefinitely."""
        mode = "LIVE" if self.live else "PAPER"
        print(f"Starting scalper ({mode}) — {len(self.pairs)} pairs, "
              f"${self.balance:,.2f} balance, {interval_minutes}m interval")
        print(f"Pairs: {', '.join(self.pairs)}")

        while True:
            try:
                self.run_round()
            except KeyboardInterrupt:
                print("\nScalper stopped by user.")
                self._save_state()
                break
            except Exception as e:
                logger.error("Round failed: %s", e, exc_info=True)

            time.sleep(interval_minutes * 60)
