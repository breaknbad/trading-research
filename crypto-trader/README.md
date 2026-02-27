# Crypto Mean-Reversion Backtester & Paper Trader

A Python backtesting engine and paper trading simulator that tests a **Bollinger Bands + RSI mean-reversion strategy** on cryptocurrency data fetched from the Coinbase Advanced Trade API.

## Strategy

| Signal | Condition |
|--------|-----------|
| **Buy** | Price ≤ Lower Bollinger Band **AND** RSI < 30 |
| **Sell** | Price ≥ Upper Bollinger Band **AND** RSI > 70 |
| **Stop Loss** | Price drops 3% below entry |

- Bollinger Bands: 20-period SMA, 2 standard deviations
- RSI: 14-period
- Long-only, fully invested per trade, one position at a time

## Project Structure

```
crypto-trader/
├── main.py              # Entry point — run a backtest
├── coinbase_client.py   # Coinbase public API client (OHLCV candles)
├── auth_client.py       # Authenticated Coinbase API client (JWT/ES256)
├── indicators.py        # Bollinger Bands & RSI calculations
├── strategy.py          # Mean-reversion backtest engine
├── metrics.py           # Performance metrics & reporting
├── paper_trader.py      # Paper trading engine (simulated trades)
├── run_paper.py         # CLI entry point for paper trading
├── requirements.txt     # Python dependencies
├── .env                 # API keys (not committed)
└── README.md
```

## Setup

```bash
cd crypto-trader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### API Keys (for authenticated endpoints)

Create a `.env` file with your Coinbase Advanced Trade API credentials:

```
COINBASE_API_KEY=organizations/xxx/apiKeys/xxx
COINBASE_API_SECRET=-----BEGIN EC PRIVATE KEY-----
...
-----END EC PRIVATE KEY-----
```

The paper trader only needs public market data endpoints (no auth required). The authenticated client (`auth_client.py`) is available for future live trading.

## Usage

### Backtesting

```bash
# Default: BTC-USD, 90 days, hourly candles
python main.py

# ETH-USD, 60 days
python main.py --product ETH-USD --days 60
```

### Paper Trading

Paper trading uses **live market data** but simulates all trades — no real orders are placed.

```bash
# Default: BTC-USD, $10,000 starting balance, check every 5 minutes
python run_paper.py

# Custom settings
python run_paper.py --product ETH-USD --balance 5000 --interval 2

# Verbose logging
python run_paper.py -v
```

The paper trader:
- Fetches live 5-minute candles from Coinbase
- Applies the mean reversion strategy in real-time
- Tracks virtual portfolio with P&L
- Saves state to `paper_trades.json` (auto-resumes on restart)
- Press `Ctrl+C` to stop (state is saved)

## Metrics

The backtest report includes:
- **Total Return** — overall P&L percentage
- **Win Rate** — percentage of profitable trades
- **Sharpe Ratio** — annualized risk-adjusted return
- **Max Drawdown** — largest peak-to-trough decline
- **Profit Factor** — gross profits / gross losses
- **Trade log** — entry/exit times, prices, and reasons

## Data Source

Uses the **Coinbase Advanced Trade REST API**:
- Public endpoints for market data (no auth needed)
- Authenticated endpoints use JWT with ES256 signing
