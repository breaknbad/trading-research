# Mark's Protocol v2 — Identify → Analyze → ACT → Test → Lock

> The process for making any system change, trade process improvement, or protocol update.
> "Implement to fidelity" + ACTION steps + 3x testing. Permanent directive.

---

## Phase 1: IDENTIFY (What's broken?)
1. **State the problem in one sentence.** No jargon. What actually went wrong?
2. **Quantify the damage.** How much money did it cost? How much time? What opportunity was missed?
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

## Trade Execution Addendum (ACTION = SPEED)

The protocol above is for system changes. For TRADES, action is the priority:

### See → Score → Size → Execute
1. **See the setup** — factor engine, scanner, or manual spot (< 1 min)
2. **Score it** — factor engine CONFIRM+ (65+)? Exit signals clear? (< 2 min)
3. **Size it** — risk calc, position limits, stops defined (< 1 min)
4. **Execute** — `execute_trade.py` with all parameters. Done. (< 30 sec)

**Total: < 5 minutes from signal to execution.**

If the factor engine scores CONFIRM+ and exit signals are clean: **TRADE. No committee. No "let me check one more thing."**

The deployment clock (STANDING_ORDERS.md) enforces this:
- 8:00-8:45 AM: Analysis window
- 9:00 AM: Execute or explain why not
- 10:00 AM: 40% deployed or explain why not

---

*This protocol is permanent. Every change goes through it. No exceptions.*
*— Locked by Mark directive, Mar 4 2026*
