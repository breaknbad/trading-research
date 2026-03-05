# Crypto Trading System

Intraday cryptocurrency paper trading system with multi-strategy signal scoring, comprehensive risk management, and backtesting.

## Features

- **6 strategies**: Momentum/breakout, mean reversion, funding rate, cross-timeframe, VWAP deviation, order flow
- **Signal scoring engine**: Weighted votes from all strategies → combined 0-100 score
- **Risk management**: Position sizing, stop loss, exposure limits, correlation checks, daily drawdown circuit breaker
- **Paper trading**: Simulated execution with slippage and fees against live Binance data
- **Backtesting**: Walk-forward replay of historical data
- **Performance tracking**: Sharpe, max drawdown, win rate, profit factor, trades/day

## Setup

```bash
pip3 install -r requirements.txt
```

## Usage

### Live Paper Trading
```bash
python3 main.py
```
Connects to Binance WebSocket streams, evaluates signals every 30 seconds, executes paper trades with full risk management.

### Backtesting
```bash
python3 backtest.py
```
Fetches last 1000 candles for all assets and replays through the signal engine.

## Configuration

All parameters in `config.py`:
- **Assets**: BTC, ETH, SOL, AVAX, LINK, DOGE (vs USDT)
- **Risk**: 5% max per trade, 1.5% stop loss, 2:1 R:R, 25% max exposure, -3% daily circuit breaker
- **Signals**: Min score 55, weighted strategy votes
- **Fees**: 0.1% slippage + 0.1% maker/taker

## Architecture

```
data_feed.py     → Binance REST + WebSocket (no auth needed)
indicators.py    → RSI, MACD, Bollinger, VWAP, ATR, volume profile
strategies.py    → 6 strategy classes, each outputs Signal(direction, score, reason)
signal_engine.py → Combines signals into TradeSignal with entry/SL/TP
risk_manager.py  → Position sizing, exposure, correlation, circuit breaker
executor.py      → Paper execution with slippage simulation
portfolio.py     → P&L tracking, equity curve, performance metrics
backtest.py      → Walk-forward backtesting harness
main.py          → Async main loop
```

## Logs

- `trading.log` — full application log
- `trades.jsonl` — every trade entry/exit with reasoning
