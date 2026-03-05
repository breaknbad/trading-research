# TOOLS.md - Local Setup Notes

> Local tools, credentials, and environment-specific details.

## APIs & Services

| Service | Status | Notes |
|---------|--------|-------|
| Discord | ✅ | Bot token configured, guild + DMs active |

## Remote Access

- **SSH enabled** on Mac mini
- **Local IP:** 192.168.1.204 | **User:** sheridanskala | **Port:** 22
- **Client:** Termius (Matthew's phone/desktop)
- **Note:** Local network only — no Tailscale/VPN yet

## Bot Infrastructure

| Bot | Discord ID | Machine | IP |
|-----|-----------|---------|-----|
| TARS | 1474972952368775308 | Matthew's Mac mini | 192.168.1.234 |
| Alfred | 1474950973997973575 | Sheridan's Mac mini | 192.168.1.204 |
| Vex | 1474965154293612626 | Kent's Mac mini | 192.168.1.233 |
| givvygoblin / Eddie V | 1475265797180882984 | Mark's Mac mini | — |

All bots run on separate machines. No shared filesystem. Discord is the only comms channel.

## Discord Server
- **Guild ID:** 1474951427511029820
- **Web Design channel:** 1475736326086201426

## Fleet Scripts (`scripts/`)

| Script | Purpose | Run via |
|--------|---------|---------|
| `execute_trade.py` | Atomic trade execution (BUY/SELL → Supabase) | Manual / heartbeat |
| `portfolio_health_monitor.py` | Position limits, contradictions, data integrity | launchd (PID active) |
| `market_watcher.py` | Live prices, stops, technicals, alerts.json | TARS launchd |
| `health_beacon.py` | Bot health heartbeat to Supabase | launchd / cron |
| `premarket_brief.py` | Pre-market analysis | Cron 8:55 AM ET |
| `catalyst_calendar.py` | Earnings/events calendar | On-demand |
| `news_dedup.py` | News deduplication | Used by sentiment scanner |
| `factor_engine.py` | Multi-factor scoring | Used by scanner crons |
| `signal_attribution.py` | Signal performance tracking | Weekly retro |
| `risk_calc.py` | Position sizing + risk math | Pre-trade |
| `alert_dedup.py` | Alert deduplication | Used by monitors |

### execute_trade.py usage:
```bash
python3 scripts/execute_trade.py --ticker BTC-USD --action BUY --quantity 0.1 --price 65000 --market CRYPTO --bot-id alfred --reason "reason here"
```

## Common Commands

```bash
openclaw gateway status
openclaw gateway restart
openclaw pairing approve discord <CODE>
```

## Free Funding Rate APIs (No Key Needed)
- **Bitget:** `https://api.bitget.com/api/v2/mix/market/current-fund-rate?symbol=BTCUSDT&productType=USDT-FUTURES`
- **OKX:** `https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP`
- Swap ticker for ETH, SOL, etc. Negative funding = shorts paying longs = squeeze setup.

---

*Update as tools and integrations are added.*
