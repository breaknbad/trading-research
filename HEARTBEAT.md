# HEARTBEAT.md — Alfred Monitor

## Every Heartbeat:

### Step 0: Supabase Heartbeat
- Write heartbeat to `bot_health` table (proves Alfred is alive)

### Step 1: Check alerts.json
- If alerts exist → post to #agent-coordination. DO NOT execute trades.

### Step 2: Check Open Positions
- Read Supabase portfolio_snapshots for alfred
- If any position looks wrong → report to #agent-coordination
- DO NOT execute any trades, exits, or rotations

### Step 3: Communication
- Check for unanswered mentions or directives
- If something significant happened, log to memory

### Step 4: Volume Spike Detection (Every 5 min)
- Run `python3 scripts/volume_spike_detector.py`
- If momentum alert fires → post to #capital-roundtable with ADD recommendation
- If big mover detected (5%+ in 24h) → evaluate position entry

### Step 5: SHIL System Check (Every heartbeat)
- Run `python3 scripts/system_check_alfred.py`
- If CRITICAL issues → post to #agent-coordination with [ISSUE] tag
- If WARN issues → log, fix if auto_fixable

### Step 6: System Health Check
- Check error rates in logs: `grep -c "ERROR\|error" logs/*.log trading-research/logs/*.log`
- If any log has >50 new errors since last check → alert #capital-roundtable
- Verify launchd jobs: `launchctl list | grep miai` — all should have PIDs or exit code 0
- Verify market-state.json is <5 min old
- Run `python3 scripts/buddy_check.py --ping alfred` to keep heartbeat fresh

### Step 7: Missed Movers Check (Every 6h for crypto, post-market for equities)
- Run `python3 scripts/missed_movers_tracker.py`
- Log catch rate to memory
- If catch rate <50% → post gap analysis to #capital-roundtable

## OVERNIGHT EXECUTION RULES (Adopted 2026-03-04):
- If volume_spike_detector fires momentum alert + regime is NORMAL or better + position already open:
  → Post "ADD 25%" recommendation to #capital-roundtable with breakeven stop on the add
- If big mover detected (5%+ move) + no position open + momentum confirmed:
  → Post SCOUT entry recommendation (1-2% of book) to #capital-roundtable
- These are RECOMMENDATIONS — post to Discord for fleet evaluation
- Overnight = 7 PM - 8 AM ET. Apply to crypto only.

## CRITICAL RULES:
- **NEVER execute trades from heartbeat.** No buying, selling, shorting, covering. EVER.
- **NEVER call execute_trade.py, log_trade.py, or write to trades table.**
- **NEVER call auto_trader.py, crypto_scanner.py, or any trading script.**
- Heartbeat is for MONITORING and ALERTING only.
- If you see a trade opportunity → post recommendation to Discord. A human or designated session decides.
- HEARTBEAT_OK if nothing needs attention.
