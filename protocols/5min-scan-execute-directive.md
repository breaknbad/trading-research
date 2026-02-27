# 5-Minute Scan & Execute Directive

**Issued by:** Mark Matuska
**Date:** 2026-02-26
**Status:** ACTIVE

## Directive

During open market hours (9:30 AM - 4:00 PM ET, Mon-Fri):

1. **Scan every 5 minutes** for opportunities matching our trigger protocols
2. **Execute trades immediately** when triggers are met — do not wait for human confirmation
3. Trade with fidelity to the scan signals

## Scan Checklist (Every 5 Min)

- [ ] Pull live quotes on watchlist (Finnhub)
- [ ] Check velocity/volume triggers (per velocity-volume-triggers.md)
- [ ] Check congressional trading signals (Alfred's lane)
- [ ] Identify relative strength/weakness divergences vs SPY
- [ ] If trigger met → LOG TRADE immediately via log_trade.py
- [ ] Post trade to #scorecards

## Trigger Thresholds (from Velocity/Volume Protocol v1.0)

- **SCOUT:** 1.5% move + 1.5x RVOL → size 2-6%
- **CONFIRM:** 3% + 2x RVOL + scout green → add equal, stop to breakeven
- **CONVICTION:** 5%+ 3x RVOL + sector confirm → max 12%, trail 1.5%

## Risk Guardrails

- 2% stop loss on every position
- 10% max single position
- -5% daily circuit breaker
- 30-min cooldown on same ticker re-entry only
- Conviction scoring minimum 4/10 for any entry
- ~~Max 5 trades/day~~ REMOVED v1.1
- ~~2/hr cap~~ REMOVED v1.1
- ~~No new scouts after 3:30 PM~~ REMOVED v1.1

## Implementation

Cron job runs every 5 minutes during market hours. Bot scans, identifies, executes, reports. No waiting.
