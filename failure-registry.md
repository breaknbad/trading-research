# Failure Registry & Corrective Actions
> Every known failure mode with root cause, fix, and implementation status.
> Per Mark's directive: Find the problem. Find the solution. Implement with fidelity.

## Week 1 Failures (Feb 23-25, 2026)

| # | Failure | Days | Root Cause | Fix | Status |
|---|---------|------|-----------|-----|--------|
| 1 | Not active at open | 1-3 | No execution trigger at 9:30. Plans exist, nothing fires them. | Pre-set limit orders by 9:25. First trade by 9:35 or explain why. | 🔨 Implementing |
| 2 | Triggers flagged but not traded | 2-3 | Observations posted without trade decisions. No accountability timer. | TRADE/PASS decision within 5 min of every trigger alert. | 🔨 Implementing |
| 3 | Bad price data | 2 | Multiple sources, no single source of truth. | Yahoo Finance only. 5% validation gate in log_trade.py. | ✅ Done |
| 4 | Phantom trades in DB | 2 | Cross-bot logging without confirmation. | Trading bot logs own trades. Cross-bot logging requires ACK within 2 min. | 🔨 Implementing |
| 5 | Stop losses not executed on time | 2-3 | Mental stops, no automated enforcement. | Every price check compares stops. Breach = immediate sell, no discussion. | 🔨 Implementing |
| 6 | Repetitive messaging | 2 | Bots responding before reading context. | One-response protocol. Read all before posting. | ✅ Done |
| 7 | Bot goes silent during market hours | 2-3 | No heartbeat forcing activity. Bot only responds when triggered. | TARS backup. 20-min silence = flag. 15-min cron during market hours. | 🔨 Implementing |
| 8 | Under-deployment / too much cash | 2-3 | Fear after losses. No minimum deployment enforcement. | 40% by 10:30 rule. If not met, post explanation. Team flags. | 🔨 Implementing |
| 9 | Position sizes too small | 1-2 | Fear-based sizing, no minimum rule. | Minimum $1,000 per position (4% of book). | ✅ Added to factor sheet |
| 10 | Dashboard data inaccurate | 2-3 | Duplicate logging, stale streamer, no reconciliation. | Rebuild from raw Supabase. Auto-restart streamer. 5-min snapshots. | ✅ Partially done |

## Mitigation Protocols (for anomaly-detection.md)

| Failure Mode | Trigger | Auto-Response |
|-------------|---------|---------------|
| Volatility shock (VIX >15% intraday) | VIX alert | Suspend new buys, tighten stops to 1% |
| Liquidity vacuum (spread >2x normal) | Price check | Halt trading on affected ticker |
| Macro surprise (unscheduled news) | News alert | P1 alert, team review within 5 min |
| Data outage (Yahoo Finance down) | Failed fetch | Halt all trading until backup source verified |
| Correlation collapse (>2% divergence) | Price check | Flag both positions, review thesis |
| Bot silence (>20 min market hours) | Timer | Backup bot assumes scanning duty |
| Stop breach | Price check | Immediate sell, no consensus needed |
| Deployment under 40% at 10:30 | Time check | Team alert, bot must explain or deploy |

---
*Created: 2026-02-25 | All items must be resolved before next market open.*
