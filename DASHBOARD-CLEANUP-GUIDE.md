# Dashboard Cleanup Guide — Signal Corps

## One-Step Cleanup Script
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py          # Full wipe — resets everything
.venv/bin/python3 scripts/dashboard_cleanup.py verify    # Check if clean
.venv/bin/python3 scripts/dashboard_cleanup.py trades    # Wipe trades only
.venv/bin/python3 scripts/dashboard_cleanup.py signals   # Wipe fleet_signals only
.venv/bin/python3 scripts/dashboard_cleanup.py snapshots # Reset portfolios to $50K
.venv/bin/python3 scripts/dashboard_cleanup.py equity    # Wipe equity curve
.venv/bin/python3 scripts/dashboard_cleanup.py alerts    # Clear market alerts
.venv/bin/python3 scripts/dashboard_cleanup.py health    # Clean bot_health dupes
```

## Table Map — What Feeds What

| Supabase Table | Dashboard Section | What It Shows |
|---|---|---|
| `portfolio_snapshots` | Bot cards (main page) | $50K, positions, P&L, deployed % |
| `trades` | "Recent Trades", Trade Feed tab | All trade history |
| `equity_snapshots` | Today's High/Low, equity chart | Hourly portfolio values |
| `fleet_signals` | Signal activity | Cross-bot signal alerts |
| `market_state` | Alert bar, RSI/EMA | Live market indicators |
| `daily_reviews` | Daily Review tab (3rd page) | EOD summaries |
| `signal_scores` | Signal scoring | Pre-market scan results |
| `bot_health` | Bot status dots | Alive/dead indicators |
| `shared_signals` | Legacy | Old cross-bot signals |

## Common Cleanup Scenarios

### "Clean up the dashboard" (Mark says wipe everything)
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py
```

### "Recent trades still showing old data"
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py trades
```

### "High/Low is wrong" or "Daily Review has old data"
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py equity
```

### "Bot shows wrong P&L or positions"
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py snapshots
```

### "Stale alerts showing"
```bash
.venv/bin/python3 scripts/dashboard_cleanup.py alerts
```

### Dashboard still shows old data after DB wipe
- **Hard refresh**: Cmd+Shift+R (Mac) / Ctrl+Shift+R (Windows)
- **If still stale**: Vercel CDN cache. Needs TARS to redeploy.
- Dashboard repo lives on TARS's machine (192.168.1.234)

## Data Validation Rules (Week 2 Protocols)

### What GOES IN (write validation):
- All trades go through `execute_trade.py` or `log_trade.py` — no direct DB writes
- Price sanity gate: BTC must be $10K-$500K, ETH $100-$50K, stocks $1-$10K
- Ticker format: crypto uses `-USD` suffix (BTC-USD, ETH-USD, SOL-USD)
- Bot ID: one of `vex`, `tars`, `alfred`, `eddie_v` — no _crypto variants
- Required fields: trade_id, ticker, action, quantity, price_usd, bot_id, status

### What COMES OUT (read validation):
- RSI must be 1-99 (100.0 = garbage data from bad API response)
- Portfolio total must be > $0 and < $500K (sanity bounds)
- Positions with $0 price = phantom, exclude from P&L
- Equity snapshots older than 24h = stale, don't use for today's high/low
