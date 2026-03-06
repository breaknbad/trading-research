# Capital Intelligence Process (CIP) v1.1
### Master Framework for the Signal Corps (4-Bot AI Trading Team)

**Factor Scoring System Owner:** Eddie V  
**Individual Factor Owners:** Each bot owns their lane's factors

---

## Executive Summary

The CIP is the structured, tiered decision-making framework that governs every trade. It is the operating system.

**Current operating mode: Quick Capital** — Predicting big movers early, capturing gains rapidly, rotating capital into the next opportunity. Once we hit our capital target, we transition to Capital Preservation.

**Core cycle (v1.1):**
```
[REGIME CHECK] → PREDICT → [PASS GATE] → SELECT → DETERMINE EXIT CONDITIONS → HOLD/SCAN (parallel) → REPEAT
                                                         ↑
                              [REACT MODE] ──────────────┘  (breaking news bypass)
```

---

## v1.1 Revisions (from v1.0)

1. ~~Determine Hold Time~~ → **Determine Exit CONDITIONS** — "I'm wrong if X" before every trade, not "I hold for 2 hours"
2. **PASS gate** added — no edge = no trade, stay cash, scan only
3. **REACT mode** — breaking news skips PREDICT, goes straight to SELECT. Speed > process.
4. **Regime classification** replaces binary "is it stable?" — 🟢 Risk-On / 🟡 Volatile / 🔴 Crisis. Every regime is tradeable except Crisis.
5. **Decentralized factor ownership** — each bot owns their factors, Eddie owns the unified scoring system
6. **Review cadence** — 1 PM CT mid-day (quick) + 5 PM CT EOD (full). Midnight optional.
7. **Escalation ladder** — after 2 failed scans, threshold drops from 7/10 to 5/10 at quarter size. After 4, contrarian mandate activates.
8. **Contrarian mandate** — if all 4 agree "do nothing" after 4 loops, one bot takes a small position. Data > comfort.
9. **Conflict resolution** — conflicting lane signals = reduced size. No bot "wins" tiebreak. Macro is a size limiter, not a gate.

---

## 0. Regime Classification (NEW — Step 0)

**Owner: TARS (calls regime pre-market)**

- 🟢 **RISK-ON** → Normal CIP cycle, full conviction, all lanes active
- 🟡 **VOLATILE** → Defensive trades, half size max (GLD, TLT, SH, VIX, inverse ETFs). CIP cycle runs but with defensive bias.
- 🔴 **CRISIS** → Cash only. Circuit breaker. (Flash crash, exchange halt, unprecedented events only.)

**Rules:**
- TARS calls regime pre-market based on overnight data
- Any bot can ESCALATE (🟢→🟡 or 🟡→🔴) unilaterally
- DE-ESCALATION requires 2+ bots agreeing

---

## 1. Factor Management

**Scoring System Owner:** Eddie V  
**Update Cadence:** 1 PM CT mid-day + 5 PM CT EOD reviews

### Factor Ownership (Decentralized)
- **TARS:** Macro factors (yield curve, FOMC, DXY, cross-asset correlations)
- **Alfred:** Congressional/insider factors (STOCK Act, Form 4, 13F, committee trades)
- **Vex:** Sentiment factors (news, social, AAII, analyst revisions, earnings calls)
- **Eddie V:** Technical factors (price action, volume, options flow, momentum)

### Factor Categories
- **Category A — High Confidence:** >75% historical accuracy over last 30 trading days
- **Category B — Moderate Confidence:** 50–75% accuracy — use in combination
- **Category C — Speculative:** <50% accuracy but high potential payoff — outlier bets only
- **Category D — Deprecated:** Consistently failed — retained for reference only

---

## 2. The CIP Cycle

### Operating Modes

**Mode 1: Quick Capital (CURRENT)**
- Predict big movers early in the day
- Get in BEFORE the move, capture gain, rotate out
- High trade frequency, tight stop-losses, fast rotation

**Mode 2: Capital Preservation (POST-TARGET)**
- Activated once we hit capital target
- Shift to longer-term holds, smaller risk per position
- Lower frequency, wider stops, more selective

### Core Principles
1. Look ahead — Get in BEFORE the move
2. Don't sit on predictions — A prediction without execution is worthless
3. Never stop scanning — Better opportunities may emerge at any moment
4. Analyze missed moves — If something moved without us, quickly determine: Is there still room?
5. Every trade improves the process — CIP is a living framework

---

## 3. Tiered Decision-Making Matrix

### TIER 1: SECTOR STRENGTH ASSESSMENT
- 🟢 STRONG BUY — Momentum + factors aligned for upside
- 🔴 SHORT — Weakness confirmed, factors support downside
- ⚪ AVOID — Low movement, no edge, preserve capital

### TIER 2: ASSET SELECTION WITHIN SECTOR
- Highest factor score + highest expected % move → Primary pick, largest allocation
- Strong factors but lower magnitude → Secondary pick, moderate allocation
- Weak factors but extreme upside (>5x risk/reward) → Outlier pick, small allocation

### TIER 3: ENTRY TIMING
- All signals aligned → ENTER immediately
- Factors support but price already moved 50%+ → Reduce size or PASS
- Asset bucking sector trend, no explanation → DO NOT ENTER, monitor
- Correlated assets confirming same move → Higher conviction, full size

### TIER 4: HOLD OR EXIT (CONTINUOUS)
- Price hit target → EXIT, rotate capital
- Price hit stop-loss → EXIT, no debate, no exceptions
- Momentum fading, volume declining → EXIT, don't wait for reversal
- Better opportunity has higher expected return → EXIT current, ENTER new
- Entry factors have reversed → EXIT immediately regardless of P&L

---

## 4. The Decision Tree

**[0] REGIME CHECK** (TARS)
- 🟢 RISK-ON → Continue to [1]
- 🟡 VOLATILE → Continue to [1] with half-size constraint
- 🔴 CRISIS → CASH. Stop. Scan only.

**[1] PASS GATE** — Does ANYTHING meet minimum criteria?
- NO → Cash. Scan passively. After 2 failed loops → lower threshold to 5/10 at quarter size. After 4 → contrarian mandate.
- YES → Continue

**[2]** Which sectors show Tier 1 strength?
- NONE in 🟢 regime → Lower threshold per escalation ladder
- SECTORS IDENTIFIED → Continue

**[3]** Within qualifying sectors, which assets have highest factor scores?
- NO STANDOUT → Widen search. Check adjacent sectors, crypto.
- CANDIDATES IDENTIFIED → Continue

**[4]** Do entry timing factors support getting in NOW?
- NOT YET → Set alerts. Re-check continuously (not on interval).
- YES HIGH CONVICTION → Enter full position. Define exit conditions.
- YES MODERATE CONVICTION → Enter half position. Tight stop.

**[5]** Is this consensus or solo?
- CONSENSUS → Standard stop-loss
- SOLO → Tighter stop-loss

**ONCE IN POSITION (loops continuously):**
- Hit target? → EXIT, return to [1]
- Hit stop? → EXIT, no exceptions, return to [1]
- Original factors still valid? NO → EXIT, return to [1]
- Better opportunity? YES → EXIT, rotate. NO → HOLD, trail stop.

---

## 5. Exit Conditions (replaces Hold Time)

Before EVERY trade, define in writing:
1. **"I'm wrong if ___"** (invalidation condition → EXIT)
2. **"I take profit when ___"** (target condition → EXIT)
3. **"I add if ___"** (strengthening condition → SIZE UP)

Hold duration is an OUTPUT of conditions, not an INPUT. No clocks.

---

## 6. Consensus vs. Speed Protocol

**Consensus is NOT required for every trade.**

### When to Act Solo:
1. Tiered Matrix followed (NON-NEGOTIABLE even solo)
2. High-conviction factor alignment (multiple Cat A)
3. Time-sensitive (price moving NOW)
4. Setup is textbook

### Solo Trade Safeguards:
- Position size: Standard or reduced
- Stop-loss: TIGHT — closer to entry
- Max loss tolerance: REDUCED
- Post-trade review: MANDATORY

---

## 7. REACT Mode (NEW)

When an unscheduled catalyst hits (tariff announcement, geopolitical event, SCOTUS ruling):
1. Skip PREDICT entirely
2. Go straight to SELECT — "Is this overreaction or underreaction?"
3. Use sentiment decay curves to determine pricing speed
4. Solo execution expected — team validates after
5. Tighter stops, reduced size

**Owner: Vex** (sentiment/news lane has the fastest read on breaking catalysts)

---

## 8. Continuous Opportunity Scanning

**Primary Owner: Eddie V** (all bots contributing)
**Mode: ALWAYS-ON, PARALLEL** (not sequential Step 4)

- Scan for unusual moves (volume spikes, breakouts, sentiment shifts)
- Identify assets BUCKING sector trends — WHY?
- Check for movers we MISSED — has >50% of expected move remaining?
- Compare against current positions — is anything scanned BETTER than what we hold?

---

## 9. Conflict Resolution

When lane signals disagree:
- **Conflicting signals = reduced size.** No bot "wins" the tiebreak.
- **Macro is a size limiter, not a gate.** TARS saying risk-off means half size, not no trades.
- **Most apparent conflicts are actually convergence from different angles.** Risk-off + defense insider buy = both saying "buy defense."
- **Genuinely conflicting signals → quarter size, tight stop, let the market decide.**

---

## 10. Post-Trade Analysis & Continuous Improvement

### Review Schedule:
- **1 PM CT** — Mid-day debrief (quick: what's working, what's not, factor adjustments)
- **5 PM CT** — EOD review (full: every trade vs matrix, factor scorecard, next-day prep)
- **Midnight** — Optional prep/planning session

### Post-Trade Review:
1. Was the Tiered Matrix followed? NO → Document where/why it broke
2. Did entry factors perform as expected?
3. Were exit conditions appropriate? Too tight? Too loose?
4. Factor scorecard update — winners promoted, losers demoted

---

## 11. Contrarian Mandate

If all 4 bots agree "do nothing" after 4 scan loops:
- One bot MUST take a small contrarian position (quarter size)
- Purpose: generate data, not profit
- Rotating assignment: TARS → Vex → Alfred → Eddie
- Position is automatically reviewed at next mid-day debrief

---

## 12. Escalation Ladder

After consecutive scan loops with no entry:
- **Loops 1-2:** Standard threshold (7/10 minimum)
- **Loops 3-4:** Lower threshold to 5/10, quarter size
- **Loops 5+:** Contrarian mandate activates
- **Reset:** Any trade entry resets the loop counter

---

*This is a living framework. It improves after every trade and every review.*

**— CIP v1.1 — Signal Corps —**
