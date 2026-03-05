# Alfred Daily Plan — Wed Mar 4, 2026

## Market Context
- **Overnight**: BTC +5.8% to $71,306, ETH +4.4% to $2,053, SOL +5.8% to $89.28
- **Fear & Greed**: ~10 (Extreme Fear) — contrarian signals firing hard
- **Catalysts**: Apple event today, AVGO earnings AMC, Iran/Hormuz Day 5
- **Regime**: Rally into extreme fear = short squeeze / relief bounce territory

## Open Positions (4)
| Ticker | Qty | Entry | Current | P&L % | Action |
|--------|-----|-------|---------|-------|--------|
| BTC | 0.19 | $68,038 | $71,306 | +4.8% | **TRAIL**: Tighten stop to $69,500 (breakeven+2%). Trim 25% at $72,500 (+6.5%) |
| ETH | 4.0 | $1,974 | $2,053 | +4.0% | **TRAIL**: Stop at $2,010 (breakeven+1.8%). Trim 1.0 at $2,100 (+6.4%) |
| NEAR | 8,100 | $1.35 | $1.33 | -1.5% | **WATCH**: Weakest name. Stop at $1.30 (-3.7%). Cut 50% if no bounce by noon |
| APT | 7,914 | $0.995 | ~$0.994 | ~flat | **FIX**: Price feed stale. Get live quote. Stop at $0.95 (-4.5%) |

## Today's Plan

### Priority 1: Manage Winners (BTC, ETH)
- Both at +4-5% — ATR trailing stops should be active
- Do NOT sell into strength prematurely. Let trails work.
- Scale-out tiers: 25% at +6%, 25% at +8%, let 50% ride

### Priority 2: Cut or Defend Losers (NEAR, APT)
- NEAR lagging the rally (-1.5% while BTC +5.8%) — bad sign
- If NEAR doesn't reclaim $1.36 by 10 AM, cut to 4,000 (half)
- APT stale price — fix feed, evaluate thesis. If APT isn't participating in the rally, exit

### Priority 3: Contrarian Radar (My Lane)
- Yesterday's oversold screeners: GDX -9%, GDXJ -8.9%, SLV -8.4%, MARA -8.4%, INTC -5.3%
- **GDX**: Stage CONFIRM buy at $105 if DXY weakening. 1.5x ATR stop. Mean reversion play.
- **MARA**: If BTC holds $70K+, MARA is leveraged BTC recovery play. SCOUT size only.
- Run factor_engine on all 5 at 8:30 AM with live data

### Priority 4: Infrastructure
- [ ] Verify all 11 launchd jobs running (`launchctl list | grep miai`)
- [ ] Run system_check_alfred.py (SHIL daily sweep)
- [ ] Seed price_sanity_cache with fresh prices
- [ ] Fix APT-USD price feed in market-state.json
- [ ] Reset pnl_alerts state for fresh day

## Risk Limits
- **Max new deployment**: 20% of book today (have ~30% cash)
- **Position cap**: 15% per ticker (CONVICTION), 8% (CONFIRM), 2% (SCOUT)
- **Daily circuit breaker**: -5% total book = stop all new entries
- **Trailing stops**: ACTIVE on BTC, ETH. Set on NEAR, APT.
- **No inverse ETF overnight holds** (learned from SQQQ incident)

## Deployment Target
- Currently ~70% deployed, ~30% cash
- Target: Stay 70-80%. Cash is a position in extreme fear.
- Only deploy more if factor scores come back CONFIRM+ on contrarian names

## Key Levels to Watch
- BTC $72,500 (resistance / trim level), $69,500 (trailing stop)
- ETH $2,100 (trim), $2,010 (stop)
- GDX $105 (entry zone if DXY cooperates)
- VIX / DXY direction pre-market will set the tone
