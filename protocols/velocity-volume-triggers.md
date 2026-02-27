# Velocity/Volume Trigger Protocol v1.1

**Updated:** 2026-02-26 by Alfred (Mark directive: remove trade caps)

## Change Log
- **v1.0** (Feb 25): Initial protocol with 5/day cap, 2/hr cap, no scouts after 3:30 PM
- **v1.1** (Feb 26): Removed all trade caps per Mark's directive. Stops are the guardrail.

## Tiers

### SCOUT
- **Trigger:** 1.5% move + 1.5x RVOL
- **Size:** 2-6% of portfolio by conviction score
- **Stop:** 1.5-2%

### CONFIRM
- **Trigger:** 3% move + 2x RVOL, scout position already green
- **Action:** Add equal size, move stop to breakeven
- **Stop:** Breakeven on original, 2% on add

### CONVICTION
- **Trigger:** 5%+ move + 3x RVOL + sector confirmation
- **Size:** Max 12% of portfolio
- **Stop:** 1.5% trailing

## Conviction Scoring (10 factors)
Score each setup 1-10. Minimum 4/10 to enter a scout.

1. Price move magnitude
2. Relative volume (RVOL)
3. Catalyst quality (earnings, news, upgrade)
4. Sector confirmation (peers moving same direction)
5. Technical level (support/resistance, VWAP)
6. Market context (indices, VIX)
7. Time of day (morning > afternoon)
8. Institutional flow signals
9. Risk/reward ratio (target vs stop distance)
10. Portfolio correlation (does it overlap existing positions?)

## Guardrails

### Active (v1.2)
- **2% stop-loss** on all positions — no exceptions
- **10% max single position** size
- **-5% daily circuit breaker** — if portfolio drops 5% in a day, stop all new entries
- **10-min cooldown** on same ticker re-entry (prevents revenge trading, short enough for new catalysts)
- **No cooldown between different tickers** — if 5 setups trigger simultaneously, take all 5
- **Conviction scoring minimum** — 2/10 for scouts (velocity + volume are the two required). Higher conviction = bigger size.
- **Min scout size: $1,000 (4%)** — if it's not worth $1K, skip it entirely
- **Sector cap: 30%** — applies equally to all sectors including crypto. No special penalties.
- **Min $500M market cap** for any entry (replaces price-based filter)
- **Earnings freeze: same ticker only** — don't freeze the whole book because one name reports

### Removed (v1.1 / v1.2)
- ~~5 trades/day cap~~
- ~~2 trades/hour cap~~
- ~~No scouts after 3:30 PM~~
- ~~30-min cooldown~~ → reduced to 10-min, same ticker only
- ~~4/10 conviction minimum~~ → reduced to 2/10 for scouts
- ~~Lunch lull scale-back to 50-60%~~ — if positions are winning, hold
- ~~Wait for VWAP pullback on P1 triggers~~ — preferred not required, enter on strength if momentum + volume confirm
- ~~No penny stocks~~ — replaced with $500M market cap floor
- ~~Crypto equity cap 20%~~ → 30% same as all sectors
- ~~Freeze all entries before major earnings~~ → same ticker only

## Philosophy (v1.2)
Cap RISK, not ACTIVITY. Every trade has a defined stop. Conviction scoring sizes the bet. The market decides how many opportunities exist — we don't put an artificial ceiling on it. More at-bats with discipline = more winners. C2E.
