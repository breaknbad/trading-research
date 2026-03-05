# STANDING_ORDERS.md — Permanent Directives

> These survive compaction. Every session reads this.

## 3x Test Cycle Protocol (Mark directive, Mar 4 2026)
- ALL code changes must pass 3 consecutive test cycles before shipping
- If ANY cycle fails → rewrite the code → retest 3x from scratch
- Test against live crypto data when possible
- Unit tests must also pass (11 tests in `trading-research/tests/test_stop_check.py`)
- `pre_deploy_check.py` (7 validations) must pass before any deploy

## Auto-Execution Policy
- ONLY `stop_check.py` retains auto-execution (stop losses with STOP GUARD + price sanity)
- All other scripts are ALERT-ONLY
- Heartbeat is for MONITORING only — NEVER execute trades from heartbeat
- `.DISABLED` scripts stay disabled permanently: auto_trader, auto_rotation_daemon, auto_signal_publisher

## SHIL Cycles (Mark directive, Mar 4 2026)
- 3 SHIL cycles before moving on from any review
- Daily sweep at 8 AM ET
- Weekly fidelity audit Sundays

## Deployment Clock (from Round 13 analysis)
- 8:00 AM — pre_deploy_check.py + system_check_alfred.py
- 8:15 AM — exit_engine_v2.py scan
- 8:30 AM — factor engine scan with real technicals
- 8:45 AM — top 3 setups posted, sized, stops set
- 9:00 AM — EXECUTE first 20% on highest conviction
- 9:30 AM — second 20% if confirmation holds
- 10:00 AM — 40% deployed or explain why not

## Risk Limits
- 10% max single position
- 60% heat cap
- -5% daily circuit breaker
- 2% trailing stop default (regime-adjusted)

## Stop Enforcement
- stop_check.py runs every 60s, 24/7
- CoinGecko fallback for Yahoo failures
- Price sanity floor: reject prices < $0.01 (crypto) or deviating >50% from entry
- STOP GUARD: never sell a position showing gain (prevents inverted math sells)
- Cross-bot guard: only execute on local bot_id positions
