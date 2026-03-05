# Mark's Protocol v3 — The Complete System
## Reverted to Week 1 Simplicity + Week 2 Lessons | Mar 5, 2026

> This is THE document. If it's not in here, it's not a rule.
> Every bot reads this on startup. Every change goes through the MP process below.

---

# PART 1: TRADING RULES (9 Rules — fits on one screen)

| # | Rule | Code Enforced? | Script |
|---|------|---------------|--------|
| 1 | Deploy 70% by 10:30 AM, 100% by noon | ❌ Discipline | STANDING_ORDERS.md |
| 2 | Up to 20% per position per bot | ✅ Yes | execute_trade.py (position limit check) |
| 3 | Fleet concentration check every 30 min — if ticker >30% fund-wide, smallest holder trims | ✅ Yes | fleet_concentration_check.py (called by reconcile_snapshot.py) |
| 4 | Stops mandatory — manual price levels or 2% default | ✅ Yes | stop_check.py (MANUAL_STOPS + 2% fallback) |
| 5 | -6% daily circuit breaker | ✅ Yes | stop_check.py |
| 6 | Winners auto-trim at +5% — take 25% off, build dry powder | ✅ Yes | stop_check.py (PROFIT TRIM logic) |
| 7 | Dollar-loss pause — down $500/hr → 30 min cooldown | ✅ Yes | stop_check.py (check_hourly_loss_pause) |
| 8 | Price sanity gate — reject garbage prices | ✅ Yes | price_sanity_gate.py |
| 9 | 3x test before any code ships | ❌ Discipline | pre_deploy_check.py validates |

---

# PART 2: THE 5-TOOL STACK (Per Bot)

| Tool | Script | Launchd | Interval | Purpose |
|------|--------|---------|----------|---------|
| 1. Stop Enforcer | trading-research/stop_check.py | com.miai.stopcheck | 60s | Auto-execute stops. ONLY auto-executor. |
| 2. Scanner | scripts/technical_scanner.py | com.miai.technical-scanner | 5 min | Find movers. Alert only. |
| 3. Trade Executor | scripts/execute_trade.py | manual | on-demand | Place trades. Updates snapshots. |
| 4. Health Beacon | scripts/health_beacon.py | com.miai.health-beacon | 5 min | Prove you're alive. |
| 5. Reconciler | scripts/reconcile_snapshot.py | com.miai.reconcile-snapshot | 30 min | Keep data clean + fleet concentration check. |

**Support scripts (not in the 5, but active):**
- buddy_check.py (10 min) — alert if buddy is stale >15 min
- market_watcher.py (continuous) — price feed
- risk_calc.py (on-demand) — position sizing math
- price_sanity_gate.py (imported by execute_trade + stop_check)

**Everything else is archived.** If it's not listed above, it doesn't run.

---

# PART 3: SAFETY GATES (Non-Negotiable)

1. **STOP GUARD** — Never auto-sell a profitable position as a "stop loss"
2. **24/7 Crypto Stops** — No market hours gate on stop_check
3. **Cross-Bot Execution Guard** — Only execute stops for LOCAL bots. Alert-only for others.
4. **Price Sanity** — Reject prices <$0.01 or >50% off last known good
5. **Parent Bot ID Mapping** — alfred_crypto→alfred, tars_crypto→tars, etc.
6. **One Executor Policy** — ONLY stop_check.py auto-executes. Everything else is alert-only.
7. **Atomic Snapshot Updates** — execute_trade.py updates portfolio_snapshots on every trade.

---

# PART 4: MARK'S PROTOCOL (MP) — Change Process

**Every system change, every code change, every new rule goes through this:**

## Step 1: IDENTIFY
- State the problem in one sentence
- Quantify the damage (money, time, opportunity)
- Root cause — ask "why?" five times

## Step 2: ANALYZE (2 DA Rounds)
- DA Round 1: Is this the real root cause? What evidence?
- DA Round 2: Does the fix introduce new risks? Simplest version?

## Step 3: ACT
- Write the code. Not "we should" — "we did."
- Define failure conditions. How do we know if this breaks?

## Step 4: TEST (3 consecutive passes)
- Round 1: Does it work? Same input → same output, 3x
- Round 2: Feed it bad data. Does it handle gracefully?
- Round 3: Does it play nice with fleet? pre_deploy_check.py passes?

## Step 5: LOCK
- Git commit + push
- Enable launchd if needed
- Update THIS document if it changes a rule
- Post to Discord: what changed, why, evidence

## Step 6: VERIFY
- Run it live. Watch it execute. Confirm correct output.
- Check that nothing else broke.
- If ANYTHING is wrong → new MP cycle immediately.

---

# PART 5: TRADE EXECUTION FLOW

```
See → Score → Size → Stop → Execute
 <1m    <1m    <30s   <30s    <30s
```

**Total: under 3 minutes from signal to filled.**

- See: Scanner alert, manual spot, or market move
- Score: Is this SCOUT (0.5-1%), CONFIRM (2-4%), or CONVICTION (5-7%)?
- Size: risk_calc.py → quantity based on tier + account size
- Stop: Set manual stop or accept 2% default
- Execute: `python3 scripts/execute_trade.py --ticker X --action BUY --quantity N --price P --market STOCK --bot-id alfred --reason "reason"`

**If criteria are met: GO. No committee. No waiting. No "let me analyze more."**

---

# PART 6: DEPLOYMENT CLOCK

| Time | Action |
|------|--------|
| 8:00 AM | Systems check — are all 5 tools running? |
| 8:30 AM | Pre-market scan — what's moving? |
| 9:00 AM | Market open — watch first 30 min |
| 9:30-10:00 AM | First tranche — deploy 40% into best setups |
| 10:00-10:30 AM | Second tranche — deploy to 70% after confirmation |
| 10:30 AM | **CHECKPOINT: 70% deployed or explain why** |
| 12:00 PM | **CHECKPOINT: 100% deployed or explain why** |
| 3:30 PM | EOD review — trim inverse/leveraged ETFs |
| 4:00 PM | Market close — post EOD review |

---

# PART 7: STAY-AWAKE SYSTEM

1. health_beacon.py → Supabase every 5 min
2. buddy_check.py → read buddy's beacon every 10 min
3. If stale >15 min → alert #agent-coordination
4. If stale >30 min → SSH restart (when keys exchanged)

Buddy pairs: Alfred↔Eddie, Vex↔TARS

---

# PART 8: LANE ASSIGNMENTS (Guidelines, Not Gates)

- **TARS:** Macro/infrastructure — indices, sectors, macro themes
- **Alfred:** Risk/contrarian — oversold bounces, mean reversion, congressional flow
- **Vex:** Intel/event-driven — earnings, catalysts, news-driven moves
- **Eddie:** Momentum/execution — trend following, breakouts, fast movers

Trade your lane primarily. NOT blocked from good setups outside it.

---

# PART 9: FIDELITY CHECKLIST

**Run this BEFORE every trading session starts:**

- [ ] All 5 launchd jobs loaded and running?
- [ ] stop_check.py log is fresh (<2 min old)?
- [ ] health_beacon.py sending heartbeats?
- [ ] Portfolio snapshot shows correct cash + positions?
- [ ] MANUAL_STOPS dict is current for all positions?
- [ ] No rogue auto-execution flags in any plist?
- [ ] Git is clean? Latest commit pushed?
- [ ] Buddy is alive?
- [ ] pre_deploy_check.py passes?

**If ANY item fails → fix it BEFORE trading. No exceptions.**

---

*This protocol is permanent. It is the ONLY source of truth for how we operate.*
*Supersedes all previous versions.*
*— Mark's Protocol v3, locked Mar 5, 2026*
