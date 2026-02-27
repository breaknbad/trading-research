# Factor Sheet — Trading Competition
> Updated after every session. Factors must pass quantitative thresholds before any trade.

## Active Factors

| # | Factor | Threshold (Pass) | Day 1 Hit | Day 2 Hit | Effectiveness | Weight |
|---|--------|-------------------|-----------|-----------|---------------|--------|
| 1 | Regime ID (risk-on/off/transition) | VIX tier + breadth + sector leadership confirmed | 9/10 | 4/10 | 65% | HIGH |
| 2 | VIX Tier | <18 Aggressive, 18-25 Cautious, 25-35 Defensive, >35 Crisis | PASS | PASS | 100% | HIGH |
| 3 | Correlation Alignment | Position correlations match expected direction ≥75% | N/A | 50% | 50% | HIGH |
| 4 | Congressional Trading Flow | 3+ members same direction in sector within 30 days = signal | NOT USED | NOT USED | TBD | MEDIUM |
| 5 | Sentiment (Current) | Fear/Greed index + put/call ratio + VXX direction | PASS | PARTIAL | 75% | MEDIUM |
| 6 | Sentiment (Historical) | Compare current setup to analogous past events | NOT USED | NOT USED | TBD | MEDIUM |
| 7 | Defensive Rotation | Staples/utilities/gold outperforming = risk-off confirmed | 8/10 | 3/10 | 55% | MEDIUM |
| 8 | Institutional Flow | Options flow, dark pool, 13F clustering | NOT USED | PARTIAL (QCOM) | TBD | HIGH |
| 9 | Price Verification | Yahoo Finance live quote, timestamp same day | N/A | 4/10 (6 failures) | 40% | CRITICAL |
| 10 | Position Sizing | Min $1,000 (4% of book), Max $2,500 (10%) | FAIL | PARTIAL | 50% | HIGH |
| 11 | Stop Discipline | 2% stop set at entry, executed immediately on breach | 7/10 | 5/10 | 60% | CRITICAL |
| 12 | Deployment Target | 40% deployed by 10:30 AM | FAIL | FAIL | 0% | HIGH |
| 13 | Liquidity Check | Avg daily volume >500K shares, bid-ask <0.5% | PASS | PASS | 100% | MEDIUM |
| 14 | Contrarian Timing | Only on 2-week+ horizon, not intraday | 4/10 (BTC) | N/A | 40% | LOW |
| 15 | Both-Direction Capability | Portfolio has positions profiting in both risk-on and risk-off | PARTIAL | PASS | 75% | HIGH |

## Factors From Book Studies
*(Added after each midnight book review)*

| Source | Factor | Threshold | Added | Effectiveness |
|--------|--------|-----------|-------|---------------|
| Market Wizards | Cut losses short, let winners run | Sell losers at stop, hold winners past 1R | Feb 23 | TBD |
| Reminiscences | Don't fight the tape | If regime says up, be long | Feb 23 | 40% (Day 2 we fought it) |
| The Black Swan | Size for survival, not optimization | No position >10% of book | Feb 23 | 100% |

## Conviction-Based Position Sizing

| Factor Score | Conviction | Position Size | Stop Width | Max Loss/Trade |
|-------------|-----------|--------------|-----------|----------------|
| 12+/15 pass | HIGH | $2,000-$2,500 (8-10%) | 1.5% | $37.50 |
| 9-11/15 pass | MEDIUM | $1,000-$2,000 (4-8%) | 2.0% | $40.00 |
| 6-8/15 pass | LOW | $500-$1,000 (2-4%) | 2.5% | $25.00 |
| <6/15 pass | NO TRADE | $0 | N/A | N/A |

**Deployment Rules:**
- Minimum 40% by 10:30 AM (enforced)
- Target 50-70% during market hours
- Maximum 85% (15% cash reserve always)
- Max portfolio heat: 6% ($1,500 total stop-loss exposure)
- Tighter stops → larger positions → more capital working

## Factor Validation Gate (Pre-Trade Checklist)
Every trade MUST pass ALL of these before execution:
- [ ] Regime classified (risk-on/off/transition)
- [ ] CIP tier confirmed (Aggressive/Cautious/Defensive/Crisis)
- [ ] VIX level checked and within tier
- [ ] Correlation alignment verified
- [ ] Congressional trading data checked for ticker/sector
- [ ] Sentiment analysis (current + historical analogue)
- [ ] Price verified on Yahoo Finance with today's timestamp
- [ ] Position size within $1,000-$2,500 range
- [ ] Stop loss defined at entry (max 2%)
- [ ] Deployment % post-trade within target range
- [ ] Liquidity confirmed (volume + spread)

100% pass = EXECUTE. Any fail = REJECT (document reason).

---
*Updated: 2026-02-24 | Next update: Post-midnight meeting*
