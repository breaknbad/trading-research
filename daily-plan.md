# Alfred Daily Plan — Thursday, March 5, 2026

## Overnight Summary
- Crypto drifted slightly positive overnight: BTC $72,970 (+0.4%), ETH $2,139 (+0.6%), SOL $92.04 (+1.3%), LINK $9.47 (+1.3%)
- ES futures 5864, NQ 25070 — flat pre-market
- Gold $5,173 — still elevated (risk hedge bid)
- No fleet signals overnight. No alerts fired.

## Current Book ($31,767 | ~100% deployed | P&L: +$2 flat)

| Ticker | Qty | Entry | Current | P&L | Weight |
|--------|-----|-------|---------|-----|--------|
| BTC-USD | 0.2068 | ~71,067 avg | 72,970 | +$394 | 47.5% |
| ETH-USD | 4.15 | ~2,197 avg | 2,139 | -$240 | 27.9% |
| RENDER-USD | 2,193 | 1.45 | 1.39 | -$132 | 9.6% |
| LINK-USD | 250 | 9.48 | 9.47 | -$3 | 7.5% |
| COIN | 10 | 210.49 | 208.93 | -$16 | 6.6% |
| SOL-USD | 3.2 | 92.75 | 92.04 | -$2 | 0.9% |

## Critical Issues
1. **BTC+ETH = 75.4% concentration** — exceeds 60% heat cap. Must reduce.
2. **COIN thesis broken** — flat on crypto rip days. Exit at open.
3. **RENDER stale pricing** — CoinGecko rate-limited, Yahoo delisted RNDR-USD. Need manual check.
4. **Cash = ~$0** — no dry powder for opportunities.

## Today's Plan

### 8:00 AM — System Check (NOW)
- [x] Read yesterday EOD + STANDING_ORDERS
- [x] Sync positions + get live prices
- [ ] Run pre_deploy_check.py
- [ ] Run system_check_alfred.py
- [ ] Verify stop_check.py running (PID alive, stops current)

### 8:15 AM — Exit Engine Scan
- Run exit_engine_v2.py
- Expected flags: BTC concentration (47.5%), ETH concentration (27.9%)
- **ACTION: Exit COIN at market open** ($2,089 freed → rebalance or cash reserve)
- **ACTION: Trim BTC by ~$3,000** (sell 0.041 BTC) to bring under 40%
- **ACTION: Trim ETH by ~$1,500** (sell 0.7 ETH) to bring under 25%

### 8:30 AM — Factor Engine / Pre-Market Scan
- Check AVGO reaction (reported last night)
- Check MRVL, BABA, COST for earnings plays
- Factor score any crypto movers

### 8:45 AM — Top 3 Setups (Sized + Stops)
After freeing ~$5,600 from trims:
1. **Hold core BTC** (0.166 after trim) — stop $70,000 (Mark's wide stop)
2. **Hold core ETH** (3.45 after trim) — stop $2,050
3. **SOL add** if confirms >$93 — add 5 SOL ($460) with stop $88
4. **Cash reserve: ~$5,000** (16% of book) for intraday opportunities

### 9:00 AM — Execute
- COIN market sell
- BTC trim 0.041
- ETH trim 0.7
- Post executions to #capital-roundtable

### 9:30-10:00 AM — Confirmation Wave
- If trims filled, verify stops on remaining positions
- If AVGO gaps up, evaluate COIN replacement (tech proxy with better beta)
- Target: 84% deployed, 16% cash by 10 AM

### Ongoing
- SHIL Cycle 2 at 8 AM, Cycle 3 at 10 AM
- Onboard TARS/Eddie when they come online (FLEET_BRIEFING_2026-03-05.md ready)
- Stop enforcement: BTC $70K, ETH $2,050, SOL $85, LINK $8.80, RENDER $1.20, COIN $190 (until sold)

## Risk Limits Today
- Max single position: 40% (rebalancing BTC down from 47.5%)
- Heat cap: 85% (freeing 15% cash)
- Daily circuit breaker: -5% ($1,588)
- Trailing stops: 2% default, Mark's manual levels override

## Key Earnings Today
- AVGO (after-hours yesterday — check gap)
- MRVL, BABA, COST (today)
- Broadcom reaction sets tone for semis
