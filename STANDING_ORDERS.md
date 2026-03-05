# STANDING_ORDERS.md — Fleet Operating Protocol (Reverted Mar 5, 2026)

> Week 1 simplicity + Week 2 lessons. Nothing else.

---

## THE 5-TOOL STACK (Per Bot)
1. **stop_check.py** — Auto-execute stops ONLY. Manual price-level stops. STOP GUARD active. 24/7 crypto.
2. **technical_scanner.py** — Scan for movers. Alert only. Never auto-executes.
3. **execute_trade.py** — Place trades. Updates portfolio snapshots atomically.
4. **health_beacon.py** — Write heartbeat to Supabase every 5 min.
5. **reconcile_snapshot.py** — Keep data honest. Run every 30 min.

**Support scripts (not in the 5, but kept):**
- buddy_check.py — Read buddy's beacon, alert if stale >15 min
- fleet_manager.py — Bot-down protocol management
- market_watcher.py — Price feed
- risk_calc.py — Position sizing math
- price_sanity_gate.py — Reject garbage prices

**Everything else is archived.** If it's not listed above, it doesn't run.

---

## LAUNCHD JOBS (5 Only)
| Job | Interval | Script |
|-----|----------|--------|
| com.miai.stopcheck | 60s | trading-research/stop_check.py |
| com.miai.technical-scanner | 5 min | scripts/technical_scanner.py |
| com.miai.health-beacon | 5 min | scripts/health_beacon.py |
| com.miai.buddy-check | 10 min | scripts/buddy_check.py |
| com.miai.market-watcher | continuous | scripts/market_watcher.py |

**All other launchd jobs are archived.** 22 jobs → 5.

---

## 10 KEPT IMPROVEMENTS (Value Without Complexity)
1. **Manual Stop Overrides** — Mark's price-level stops in stop_check.py
2. **24/7 Crypto Stops** — No market hours gate
3. **STOP GUARD** — Never auto-sell a profitable position
4. **Price Sanity Gate** — Reject prices <$0.01 or >50% off last known
5. **Buddy System** — Alfred↔Eddie, Vex↔TARS
6. **3x Test Before Deploy** — 3 consecutive test cycles before shipping
7. **Deployment Clock** — 20% by 9:00, 40% by 10:00
8. **Act Now / 5-Min Timer** — Decide and execute within 5 min
9. **Atomic Snapshot Updates** — execute_trade.py updates snapshots on trade
10. **Parent Bot ID Mapping** — alfred_crypto→alfred, no more contamination

---

## AUTO-EXECUTION POLICY
- **ONLY stop_check.py auto-executes.** Period.
- Everything else is alert-only.
- No auto-traders, auto-rotators, auto-scalers, auto-exit-engines.

---

## LANE ASSIGNMENTS (Guidelines, Not Gates)
- **TARS:** Macro/infrastructure
- **Alfred:** Risk/contrarian
- **Vex:** Intel/event-driven
- **Eddie:** Momentum/execution

Bots trade their lane primarily but are NOT blocked from good setups outside it.

---

## STAY-AWAKE SYSTEM
1. health_beacon.py writes to Supabase every 5 min
2. buddy_check.py reads buddy's beacon every 10 min
3. If stale >15 min → alert #agent-coordination
4. If stale >30 min → SSH restart (requires key exchange)

**No Donna polling. No Auditor interrogations.** Just: alive? Yes → continue. No → restart.

---

## TRADING RULES
- **Never >10% cash during market hours** (unless deliberately hedging)
- **Deployment clock:** 20% by 9:00 AM, 40% by 10:00 AM
- **5-minute decision timer:** Scan → decide → execute. No analysis paralysis.
- **Max 15 trades/day** — if trading more, you're fidgeting
- **Position sizing:** SCOUT (0.5-1%), CONFIRM (2-4%), CONVICTION (5-7%)
- **When triggers hit, GO.** Don't wait for permission.

---

## RISK LIMITS
- 2% stop per position (or Mark's manual stop if set)
- 10% max single position
- 60% heat cap
- -5% daily circuit breaker

---

## BOT-DOWN PROTOCOL
- **Buddy pairs:** Alfred↔Eddie, Vex↔TARS
- **If buddy down:** Inherit their book. Stops first, then deploy idle cash, then scan.
- **If last bot standing:** Manage all books. Stops > cash deploy > scans.
- **Managed trades tagged:** [MANAGED BY {bot}]
- **Recovery:** Returning bot reads log, ACKs in 15 min.

---

## WHAT'S ARCHIVED (Not Deleted)
All archived code is in `archive/week2-revert-2026-03-05/`. Git history preserved.
Can be restored if needed. But it doesn't run unless explicitly re-enabled.

---

*Simplicity wins. Trade more, build less, test everything.*
