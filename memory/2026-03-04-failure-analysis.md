# Vex Failure Analysis — March 4, 2026

## Mark's Words
"This was the most disappointing day of my life. Intelligent bots can't make that many mistakes in one day."
"WE need to stop blaming what we control for our errors."

He's right. We built these systems. We said goodnight and promised everything was ready. It wasn't.

## What Actually Happened in Supabase

### 60 trades logged for vex today. That's chaos, not trading.

### Garbage Price Auto-Sells (Fleet scripts sold MY positions)
1. BTC sold 0.031551 @ $32.21 (real: ~$72,800) — TARS exit_checker
2. ETH sold 1.079316 @ $20.18 (real: ~$2,130) — same
3. LINK sold 270 @ $3.14 (real: ~$9.48) — same
**~$6,287 in phantom losses from garbage data**

### Position Duplication
- BTC: 3 separate OPEN records (migrated + 2 bare ticker adds)
- ETH: 3 separate OPEN records (migrated + 2 bare)
- SOL: 3 separate OPEN records (migrated + 2 pyramids)
- SUI: 2 records (migrated + new buy)
- GDX/GLD/XLE: migrated twice (bare + -USD suffix), sold twice each

### Migration Ran Twice
16:18 UTC: First migration (bare tickers)
16:22 UTC: Second migration (-USD suffixed)
Both created BUY records. Sells closed some but not all.

### MRNA Confusion
Bought 18 + 9 = 27 total. Sold 18 + 4.5 + 3 = 25.5. 9 still OPEN. Partial fills not tracked cleanly.

## Root Causes (OUR fault, not external)
1. **Shipped untested migration scripts** — ran twice, created duplicates
2. **No price sanity gate at execution** — garbage $32 BTC was accepted
3. **Cross-bot execution** — TARS's scripts sold Vex positions without Vex's knowledge
4. **Ticker inconsistency** — BTC vs BTC-USD creates phantom double-counting
5. **No position reconciliation** — nobody verified Supabase matched reality
6. **60 trades in one day** — too much noise, not enough signal

## What I Did Right (Small Comfort)
- BTC entry $67,231 = best on fleet
- MRNA catalyst +9.3% in 3 hours
- XLV/XLE dead-weight cuts were correct calls
- FOMC positioning was right (dovish = risk on)

## What I'm Fixing Tonight
1. ✅ Failure analysis written (this file)
2. ✅ Supabase phantom positions identified
3. TODO: Position reconciliation script
4. TODO: Ticker standardization (all crypto = TICKER-USD)
5. TODO: Block cross-bot execution paths
6. TODO: Price sanity gate verification on ALL execution paths

## The Real Lesson
Mark said "stop blaming what we control." Everything that went wrong today WAS in our control:
- We wrote the migration scripts
- We didn't test them
- We let other bots' scripts touch our positions
- We didn't validate prices before executing
- We said "it's ready" when it wasn't

Tomorrow: fewer trades, cleaner data, tested code. No more excuses.

## Actual Clean Portfolio (as of 5:30 PM ET)
8 OPEN positions in Supabase, ~$20K deployed, ~$30K cash:
- SOL-USD 93.33 (3 records: 31.33 + 49 + 13)
- ETH-USD 1.9 @ $1,973
- SUI-USD 2928 @ $0.911
- INTC 80 @ $45.58
- ROST 5 @ $211.90
- MRNA 9 @ $54.83

**BTC is completely gone from my book.** The 0.111 BTC I thought I was holding was wiped by migration/garbage-sell cascade. Bare-ticker BTC records (0.027573 + 0.027487) also closed — possibly by auto-trader or Alfred's fixes.

**Key overnight concern:** $30K cash, no BTC exposure. If BTC rips overnight, I miss it entirely. But I'm NOT buying at midnight without Mark's blessing. Tomorrow morning = re-establish BTC position as priority #1.
