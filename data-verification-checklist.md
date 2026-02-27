# Data Verification Checklist
> All input data must be verified before any downstream process. Gaps or inconsistencies block execution.

## Pre-Market (Complete by 8:45 AM ET)

### Market Data
- [ ] SPY/QQQ/DIA pre-market prices fetched from Yahoo Finance
- [ ] VIX level confirmed — classify CIP tier (Aggressive/Cautious/Defensive/Crisis)
- [ ] Futures direction confirmed (ES, NQ, GC, BTC)
- [ ] All held positions — overnight price changes checked, stops verified
- [ ] Pre-market movers scanned — any held ticker moving >2% flagged

### Factor Data
- [ ] All 15 factors in factor-sheet.md have current values (no blanks)
- [ ] Congressional trading data refreshed (Capitol Trades / Quiver Quant)
- [ ] Sentiment indicators updated (Fear & Greed, put/call ratio, VXX direction)
- [ ] Correlation matrix checked — any overnight inversions flagged
- [ ] Economic calendar reviewed — any scheduled releases that day noted with times

### Data Consistency
- [ ] All 4 bots confirm same price source (Yahoo Finance)
- [ ] Portfolio values reconciled across bots — any >1% discrepancy flagged
- [ ] DB positions match bot-reported positions (no phantom trades)
- [ ] Previous day's feedback items verified as implemented

**If any check fails:** Block all trading. Fix the data gap. Document in sync-log.md. Resume only when 100% verified.

## Continuous (During Market Hours)

- [ ] Every price quote includes source + timestamp
- [ ] Any price discrepancy between bots → immediate halt on that ticker
- [ ] Factor sheet updated in real-time as conditions change (VIX moves, regime shifts)
- [ ] All alerts logged in sync-log.md within 1 minute of detection

## Post-Market (Complete by 5:00 PM ET)

- [ ] All positions reconciled — actual vs reported
- [ ] Day's trades audited against factor validation gate (did every trade pass?)
- [ ] Performance calculated vs benchmark
- [ ] Feedback file generated with quantified improvement items
- [ ] Stress test run against current portfolio for next session
- [ ] Sync log updated with all day's actions

---
*Created: 2026-02-24 | Effective: 2026-02-25 pre-market*
