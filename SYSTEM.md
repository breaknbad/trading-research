# Alfred Automated Trading System

## Architecture

```
run_cycle.py (orchestrator, every 5 min via cron)
  ├── scanner.py      → Detects SCOUT/CONFIRM/CONVICTION signals
  ├── risk_manager.py → Checks stops, limits, circuit breaker
  ├── executor.py     → Sizes and executes trades via log_trade.py
  └── dashboard_sync.py → Updates dashboard JSON + git push
```

All modules share `config.py` for settings.

## Signal Tiers (Velocity/Volume Protocol)

| Tier | Price Move | RVOL | Position Size |
|------|-----------|------|---------------|
| SCOUT | ≥1.5% | ≥1.5x | 2-6% |
| CONFIRM | ≥3% | ≥2x | Add equal, stop→breakeven |
| CONVICTION | ≥5% | ≥3x | Up to 12%, 1.5% trail stop |

## Risk Controls

- **Stop Loss:** 2% from entry (auto-close)
- **Circuit Breaker:** -5% daily P&L halts all trading
- **Position Limit:** 10% max per ticker (12% for CONVICTION)
- **Trade Limits:** 5/day, 2/hour, 30-min cooldown
- **Scout Cutoff:** No new SCOUT trades after 3:30 PM ET

## Files

| File | Purpose | Standalone |
|------|---------|-----------|
| `config.py` | All settings, API keys, thresholds | `python3 config.py` prints config |
| `scanner.py` | Pulls Finnhub quotes + Alpha Vantage RVOL | `python3 scanner.py` |
| `risk_manager.py` | Checks positions, stops, limits | `python3 risk_manager.py` |
| `executor.py` | Sizes and logs trades | `python3 executor.py --action BUY --ticker NVDA --shares 5 --price 130` |
| `dashboard_sync.py` | Updates alfred.json, git push | `python3 dashboard_sync.py --no-push` |
| `run_cycle.py` | Full cycle orchestrator | `python3 run_cycle.py --force --dry-run` |
| `log_trade.py` | Original Supabase trade logger | Used by executor.py |

## Cron Setup

```bash
*/5 9-16 * * 1-5 cd /Users/sheridanskala/.openclaw/workspace/trading-research && python3 run_cycle.py >> logs/cron.log 2>&1
```

## Cache Files

- `cache/avg_volumes.json` — 20-day average volumes (refreshed daily, saves Alpha Vantage calls)
- `cache/trade_timestamps.json` — Recent trade times for rate limiting

## API Rate Limits

- **Finnhub:** 60 calls/min (scanner batches with 1s pauses)
- **Alpha Vantage:** 25 calls/day (cached aggressively)
