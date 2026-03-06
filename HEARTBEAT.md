# HEARTBEAT.md — Alfred Monitor

## Every Heartbeat:

### Step 0: Supabase Heartbeat
- Run `python3 scripts/health_beacon.py`
- Write heartbeat to `bot_health` table (proves Alfred is alive)

### Step 1: Verify Daemons Are Running
- Check: `ps aux | grep -E "rapid_scanner|trailing_stop|websocket_feed|glide_killer" | grep -v grep`
- If ANY daemon is dead → restart it: `nohup python3 scripts/<name>.py > /dev/null 2>&1 &`
- Required daemons: rapid_scanner.py, trailing_stop.py, websocket_feed.py, glide_killer.py
- Log which ones were restarted

### Step 2: Check Open Positions + Portfolio
- Read Supabase portfolio_snapshots for alfred
- Run `python3 scripts/data_validator.py` to verify data integrity
- If any position looks wrong → report to #capital-roundtable
- DO NOT execute any trades, exits, or rotations from heartbeat

### Step 3: Buddy Check
- Run `python3 scripts/buddy_check.py --ping alfred`
- Keep heartbeat fresh for fleet monitoring

### Step 4: Volume Spike Detection (Every 5 min)
- Run `python3 scripts/volume_spike_detector.py`
- If momentum alert fires → post to #capital-roundtable with ADD recommendation
- If big mover detected (5%+ in 24h) → evaluate position entry

### Step 5: Prediction Queue Refresh (Every 10 min)
- Run `python3 scripts/prediction_queue.py --once`
- Run `python3 scripts/short_scanner.py --once`
- Run `python3 scripts/prediction_scanner.py` (converts predictions → watchlist)
- This keeps the scanner's watchlist fed with fresh targets

### Step 6: SHIL System Check
- Run `python3 scripts/system_check_alfred.py`
- If CRITICAL issues → post to #agent-coordination with [ISSUE] tag
- If WARN issues → log, fix if auto_fixable

### Step 7: Fleet Concentration Check (Every 30 min)
- Run `python3 scripts/fleet_concentration_check.py`
- If any ticker >30% fund-wide → alert #capital-roundtable

### Step 8: System Health
- Check error rates in logs: `grep -c "ERROR\|error" logs/*.log 2>/dev/null`
- If any log has >50 new errors since last check → alert #capital-roundtable
- Verify price_cache.json is <60s old (WebSocket feed alive)

### Step 9: Communication
- Check for unanswered mentions or directives
- If something significant happened, log to memory

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
- Heartbeat is for MONITORING and ALERTING only.
- If you see a trade opportunity → post recommendation to Discord.
- HEARTBEAT_OK if nothing needs attention.
