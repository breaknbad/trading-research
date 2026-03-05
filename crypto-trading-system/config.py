"""Configuration for the crypto trading system."""
from dataclasses import dataclass, field
from typing import Dict, List

# ── Assets ──────────────────────────────────────────────────────────────────
ASSETS: List[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT", "DOGEUSDT"]

# ── Timeframes (Binance kline intervals) ────────────────────────────────────
TIMEFRAMES: List[str] = ["1m", "5m", "15m", "1h"]

# ── Risk Management ────────────────────────────────────────────────────────
@dataclass
class RiskConfig:
    max_position_pct: float = 0.05        # 5% of portfolio per trade
    stop_loss_pct: float = 0.015          # 1.5% stop loss
    min_reward_risk: float = 2.0          # 2:1 minimum R:R
    max_total_exposure_pct: float = 0.25  # 25% total exposure
    daily_drawdown_limit_pct: float = 0.03  # -3% daily circuit breaker
    max_correlated_positions: int = 2     # max positions in correlated assets
    correlation_threshold: float = 0.7    # above this = "correlated"
    correlation_lookback: int = 100       # candles for correlation calc

# ── Signal Engine ───────────────────────────────────────────────────────────
@dataclass
class SignalConfig:
    min_score: int = 55                   # minimum combined score to trade
    strong_score: int = 75                # strong signal threshold
    strategy_weights: Dict[str, float] = field(default_factory=lambda: {
        "momentum": 0.20,
        "mean_reversion": 0.20,
        "funding_rate": 0.10,
        "cross_timeframe": 0.20,
        "vwap_deviation": 0.15,
        "order_flow": 0.15,
    })

# ── Indicator Parameters ───────────────────────────────────────────────────
@dataclass
class IndicatorConfig:
    # RSI
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0
    # ATR
    atr_period: int = 14
    # VWAP — reset each session (calculated from candle data)
    # Volume profile bins
    volume_profile_bins: int = 24
    # Momentum
    momentum_lookback: int = 10
    volume_spike_mult: float = 2.0  # volume > 2x avg = spike

# ── Execution / Paper Trading ──────────────────────────────────────────────
@dataclass
class ExecutionConfig:
    slippage_pct: float = 0.001    # 0.1%
    maker_fee_pct: float = 0.001   # 0.1%
    taker_fee_pct: float = 0.001   # 0.1%
    initial_capital: float = 10_000.0  # USDT

# ── Data Feed ──────────────────────────────────────────────────────────────
@dataclass
class DataFeedConfig:
    binance_base: str = "https://api.binance.com"
    binance_ws: str = "wss://stream.binance.com:9443/ws"
    coingecko_base: str = "https://api.coingecko.com/api/v3"
    history_limit: int = 500          # candles to fetch on startup
    ws_reconnect_delay: float = 5.0

# ── Backtest ───────────────────────────────────────────────────────────────
@dataclass
class BacktestConfig:
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"
    timeframe: str = "5m"

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"
LOG_FILE: str = "trading.log"
TRADE_LOG_FILE: str = "trades.jsonl"

# ── Singleton instances ────────────────────────────────────────────────────
risk = RiskConfig()
signal = SignalConfig()
indicators = IndicatorConfig()
execution = ExecutionConfig()
data_feed = DataFeedConfig()
backtest = BacktestConfig()
