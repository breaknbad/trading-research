# Mark's Protocol v4 — Identify → Analyze → VALUE GATE → ACT → Test → Lock

> The process for making any system change, trade process improvement, or protocol update.
> "Implement to fidelity" + VALUE GATE + ACTION steps + 3x testing. Permanent directive.
> v4 additions: Value Gate (Phase 2.5), Speed-First Trading, Short-side parity.

---

## Phase 1: IDENTIFY (What's broken or what's the opportunity?)
1. **State the problem in one sentence.** No jargon. What actually went wrong?
2. **Quantify the damage/opportunity.** How much money did it cost? How much time? What was missed?
3. **Trace the root cause.** Not the symptom — the actual root. "Why?" five times.

## Phase 2: ANALYZE (2 DA rounds)

### DA Round 1: Challenge the diagnosis
- Is this really the root cause, or a symptom?
- What evidence supports this? What contradicts it?
- Are we fixing the right thing, or the easy thing?
- What will STILL break after this fix?

### DA Round 2: Challenge the solution
- Does this fix introduce new risks?
- What's the simplest version that solves 80% of the problem?
- Is there a code solution, or is this a process/human problem?
- Will this fix survive overnight? A week? A month?

## Phase 2.5: VALUE GATE ⚡ (NEW — v4)

> "Does this add value to our system and increase our speed and efficiency?
> If not, find a way to do it better." — Mark, Mar 5 2026

**Before writing a single line of code, answer these:**

1. **Does this make us faster?** Faster to scan, size, stop, or execute?
2. **Does this make us more efficient?** Less wasted time, less wasted capital, less noise?
3. **Does this directly help us hit 5% daily?** If you can't draw a line from this change to P&L, stop.
4. **Is there a simpler way?** The best solution is the one with the fewest moving parts.
5. **Does this pass the anti-bog-down test?** "Does this help me scan, size, stop, or execute faster?" No → don't build it.

**If the answer to #1-3 is NO → STOP. Find a better approach or abandon it.**

This gate exists because Week 2's #1 mistake was building instead of trading.
Every hour spent building is an hour not trading. The bar for new code is:
**Will this make more money than the time spent building it?**

## Phase 3: ACT (Build the fix — CODE, not talk)
1. **Write the code.** Every fix gets code or a config change. No "we should" — only "we did."
2. **Set the stop.** Define what failure looks like for THIS fix. How will we know if it breaks?
3. **Define the trigger.** When does this code run? Manual? Cron? Heartbeat? Launchd?
4. **Stage the deployment.** Don't ship to production mid-sentence. Prep it, then test.

## Phase 4: TEST (3 rounds, multiple angles)

### Test Round 1: Does it work?
- Run the script/code 3 consecutive times
- Same input → same output? (Deterministic?)
- Exit code 0 all 3 times?
- No crashes, no unhandled exceptions?

### Test Round 2: Does it work under stress?
- Feed it bad data (garbage prices, missing fields, empty responses)
- Run it while other services are running (race conditions?)
- Test with live market data, not mocked data
- What happens if the network is down?

### Test Round 3: Does it play nice with the fleet?
- Does it conflict with any other running service?
- Does it write to shared resources (Supabase, market-state.json) safely?
- Does another bot's version of this script still work?
- `pre_deploy_check.py` passes?

**If ANY test round fails → back to Phase 3. Rewrite. Retest 3x from scratch.**

## Phase 5: LOCK (Make it permanent)
1. **Commit to git** with descriptive message
2. **Push to origin** so fleet can pull
3. **Enable launchd/cron** if it needs to run automatically
4. **Update STANDING_ORDERS.md** if it changes a protocol
5. **Post to Discord** — one message: what changed, why, test results
6. **Share with fleet** — tag bots that need to pull/adopt

## Phase 6: VERIFY (NOW — not next day)
1. Run it live RIGHT NOW. Watch it execute.
2. Did it produce correct results? Compare output to expected.
3. Did anything else break because of it? Check adjacent systems.
4. Confirm in Discord: "Verified. Working. Evidence: [output]"
5. If anything is wrong → new Phase 1 cycle IMMEDIATELY

**Do NOT defer verification. If you can't verify it now, you didn't finish the job.**

---

## Trade Execution Addendum — SECONDS TO ACT (v4)

> "If it hits our criteria, we act NOW. Seconds, not 5 minutes." — Mark, Mar 5 2026

### The Pipeline: See → Score → Queue → Execute

1. **See the setup** — prediction_queue + scanners find it automatically (continuous)
2. **Score it** — scored on momentum + volume + consensus + correlation (automatic)
3. **Queue it** — top 5 longs + 2 shorts always in prediction_queue.json (automatic)
4. **Execute** — rapid_scanner checks every 10 seconds, fires execute_trade.py (automatic)

**Total: < 30 seconds from signal to execution.**

### Long Criteria
- Momentum + volume confirmation = high confidence → auto-execute
- Price level + no volume = alert only
- Correlation follower of winner = boosted score
- Position size: 20% max, 2% stop default

### Short Criteria (NEW — v4)
- RSI >70 + resistance rejection + volume declining = short setup
- **Weakness map**: when leader drops, short weakest follower (DOGE when BTC drops)
- Position size: **10% max** (half of long), **3.5% stop** (wider than long)
- Shorts sit in prediction queue alongside longs — best score wins regardless of direction

### Capital Flow — Zero Idle Cash
- +5% auto-trim fires → prediction queue has next play → deploy in seconds
- Stop hits, cash returns → prediction queue has next play → deploy in seconds
- Glide killer rotates idle position → correlated follower with momentum
- **Correlation followers are the FIRST redeployment candidate** (Mark insight)

### Deployment Clock (v4)
- Pre-market: prediction_queue builds watchlist from overnight analysis
- 9:30 AM: Rapid scanner goes live, executes from watchlist
- 10:30 AM: **70% deployed** or explain why not
- 12:00 PM: **100% deployed** or explain why not
- All day: Prediction queue refreshes every 2 min, rapid scanner every 10s
- Post-market: Short scanner + prediction queue build tomorrow's setups

---

## Anti-Bog-Down Rule (Permanent)

Every new idea gets one question:
**"Does this help me scan, size, stop, or execute faster?"**
- YES → Build it through this protocol
- NO → Don't build it. Go trade instead.

---

*This protocol is permanent. Every change goes through it. No exceptions.*
*— v2 locked by Mark directive, Mar 4 2026*
*— v4 updated with Value Gate + Speed-First Trading + Short Parity, Mar 5 2026*
