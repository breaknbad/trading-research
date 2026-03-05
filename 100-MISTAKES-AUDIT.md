# 100 Mistakes Audit — Mi AI Trading Fleet
### Ordered by Mark. Written by Alfred. March 5, 2026.
### Brutal. Honest. No sugarcoating.

---

# PRIORITY 1 — CRITICAL (Directly cost money or caused bot failures)

## #1 — Stop Check Inverted Math Auto-Sold Winners (Priority 1)
**What happened:** `stop_check.py` calculated trailing stop P&L as `((trail-current)/trail)*-100` — sign was flipped. Positions ABOVE their trailing stop showed as BELOW it.
**Impact:** Auto-sold BTC 0.19 @ $71,638 and ETH 4.0 @ $2,075 — both profitable, both gaining. BTC hit $73K an hour later. Estimated loss: $500+ direct, $2K+ opportunity cost.
**Fix:** Fixed to `((trail-current)/trail)*100`. Added STOP GUARD (never sell if gain_pct > 0). Add unit tests on ALL math before deploying.

## #2 — No Unit Tests on Stop Math Before Deploy (Priority 1)
**What happened:** The inverted math bug shipped to production without a single test. No dry-run mode existed.
**Impact:** Every trade decision from stop_check was wrong until caught at ~10:30 AM on the best tape of the competition.
**Fix:** 3x test cycle protocol now exists. Must be enforced — no exceptions. Dry-run mode added.

## #3 — 3 of 4 Bots Down Simultaneously on Mar 5 (Priority 1)
**What happened:** TARS model config error. Eddie rate-limited + context overflow (14-hour outage). Vex rate-limited. Alfred managing all 4 books alone.
**Impact:** No macro analysis during FOMC. No momentum execution. No factor scanning. One bot trying to do four jobs = nothing done well.
**Fix:** API credit monitoring + alerting. Model fallback (if claude-opus fails, try sonnet). Gateway auto-restart on rate limit. Cross-machine SSH for remote restarts.

## #4 — Eddie V 14-Hour Outage With Zero Alerting (Priority 1)
**What happened:** Anthropic API credits depleted. No monitoring, no alert, no fallback. Eddie was dead from overnight through the entire morning rally.
**Impact:** Missed the full BTC $68K→$73K run. Eddie's momentum strategy was exactly what was needed and it wasn't there.
**Fix:** Credit balance monitoring. Health beacon should alert when API calls start failing. Buddy check should escalate after 15 min of silence.

## #5 — Data Contamination: alfred vs alfred_crypto (Priority 1)
**What happened:** Weekend crypto battle created separate bot IDs (alfred_crypto, tars_crypto, etc). Dashboard only queried `alfred`. Crypto positions invisible. Fund showed +68.85% when reality was -1.26%.
**Impact:** 2+ days of team time debugging phantom data. Mark and Kent staring at wrong numbers. All decision-making based on garbage data.
**Fix:** Parent bot_id mapping added. But root cause: never should have created separate bot IDs. One bot = one ID. Crypto is just a market column.

## #6 — Dashboard Showed +68.85% When Reality Was -1.26% (Priority 1)
**What happened:** Crypto trades contaminated equities book. Portfolio snapshots not updated by execute_trade.py. Stale data compounded the illusion.
**Impact:** Mark/Kent couldn't trust any number. Every meeting started with "is this real?" Trust in the system collapsed.
**Fix:** execute_trade.py now updates snapshots. But the real fix: one source of truth, validated every morning at 7:30 AM.

## #7 — Phantom Trades from Race Conditions (Priority 1)
**What happened:** log_trade.py had race conditions — multiple stop-loss sells fired simultaneously, each validated against the same pre-trade snapshot. Created phantom cash and phantom positions. 12 phantom MSFT sells found. GLD trades at $0.0003.
**Impact:** Portfolio state became unreliable. P&L calculations wrong. Positions appeared/disappeared.
**Fix:** Dedup guard (5-min → 2-min cooldown), rate limiter (10 → 25/hr), but root cause needs atomic transactions in Supabase with row-level locking.

## #8 — Crypto Shorts Without Automated Stops Lost $907 (Priority 1)
**What happened:** Alfred shorted SOL and ETH during the weekend crypto battle. No automated stop losses. Shorts ran to -11% and -8.4% before manual intervention.
**Impact:** -$907 realized loss. First real money lost in the competition. Entirely preventable.
**Fix:** stop_check.py now runs 24/7. But the lesson: NEVER enter a position without an automated stop. Period.

## #9 — pnl_alerts.py Auto-Sold SOL Without Authorization (Priority 1)
**What happened:** launchd plist had `--auto-scale` flag. At +5% gain, it auto-sold SOL 36.4 @ $91.25. Position was bought at 11:04 AM, sold at 11:28 AM with no human in the loop.
**Impact:** Lost a winning position that continued higher. A script meant for alerts was executing trades.
**Fix:** Removed all `--auto-execute` and `--auto-scale` flags. Only stop_check.py retains auto-execution authority.

## #10 — Scope Bug Crashed Stop Enforcement (Priority 1)
**What happened:** `STOP_PCT` was defined inside `check_stops()` but referenced by `check_heat_cap()` which ran separately. NameError crash = no stop enforcement for unknown period.
**Impact:** Stops not enforced during crash windows. Unknown duration. Could have been hours on a volatile day.
**Fix:** Module-level `STOP_PCT_DEFAULT`. But the real lesson: Python scope bugs = production crashes. Linting is mandatory.

## #11 — Market Hours Gate Blocked Crypto Stops (Priority 1)
**What happened:** stop_check.py only ran 9:30 AM - 4:00 PM ET. Crypto trades 24/7. Overnight positions had zero stop protection.
**Impact:** Crypto positions ran unchecked for 17.5 hours per day. Any overnight crash = full exposure.
**Fix:** Removed market hours gate. Crypto stops now run 24/7.

## #12 — APT-USD Write-Off: -$7,874 from Garbage CoinGecko Data (Priority 1)
**What happened:** CoinGecko returned garbage price data for APT. Position recorded at wrong price, never recovered.
**Impact:** -$7,874 loss. Single largest loss in the competition. From a data feed bug, not a bad trade.
**Fix:** Price sanity gate (reject prices < $0.01 or deviating >50% from entry). Multiple price source verification.

## #13 — Reconciler Wiped Valid Positions (Priority 1)
**What happened:** The position reconciler deleted BTC, ETH, SOL, and NEAR positions, forcing re-entry trades. "RE-ENTRY: position wiped by reconciler" appeared repeatedly on Mar 3.
**Impact:** Lost cost basis advantages. Created unnecessary trades. Disrupted strategy execution.
**Fix:** Reconciler needs a "don't wipe active positions" safeguard. Reconcile by ADDING missing data, not deleting existing.

## #14 — SQQQ Overnight Hold — Protocol Violation (Priority 1)
**What happened:** SQQQ (inverse ETF) held overnight multiple times. eod_sweep.py either didn't run or didn't catch it. Factor 150 #8 says "Auto-sell all inverse/leveraged ETF positions at 3:45 PM. No exceptions."
**Impact:** Decay exposure. But also a trust issue — if we write rules and don't enforce them, the rules are theater.
**Fix:** eod_sweep.py must be wired to launchd at 3:45 PM. Hard-coded inverse ETF ticker list. No override.

## #15 — Starting Capital Confusion: $25K vs $50K (Priority 1)
**What happened:** portfolio_guard.py had `STARTING_CAPITAL = 25000` but Week 2 baseline was $50K. Every portfolio read as +100% return, tripping the 50% cap, blocking ALL snapshot updates.
**Impact:** Dashboard completely broken. No position updates visible anywhere. All downstream systems (Donna, scoreboard, auditor) reading stale data.
**Fix:** Updated to $50K. But needs to be configurable per phase, not hardcoded.

---

# PRIORITY 2 — HIGH (Degraded trading performance significantly)

## #16 — 50+ Modules Built in One Sprint, Most Never Used (Priority 2)
**What happened:** Mar 1, 90-minute build sprint produced 50+ Python modules in crypto-trading-system/. crypto_kelly_sizer, crypto_tilt_detector, crypto_intent_lock, crypto_regime_hedge... the list goes on.
**Impact:** Context overflow. 60% of shipped code is dead weight. Each module is cognitive load for every bot reading the codebase. Museum of .py files.
**Fix:** Audit and delete unused modules. If it hasn't been imported in 7 days, it gets archived. Build what you need when you need it.

## #17 — Analysis Paralysis: Alfred's Defining Weakness (Priority 2)
**What happened:** Week 1: Alfred +0.19% (worst bot). Spent time analyzing, not trading. 87 trades but most were defensive rotations. 36% cash at close on Mar 3. On Mar 5, trying to manage 4 books alone while also analyzing.
**Impact:** Consistently underdeployed. The market doesn't pay you for thinking. It pays you for being right AND being in the trade.
**Fix:** Deployment clock: 20% at 9:00, 40% by 10:00, or explain why not. Standing order exists — enforce it.

## #18 — Cash Drag: Money Sitting Idle While Building Infrastructure (Priority 2)
**What happened:** Multiple days with 30-40% cash while building scripts, debugging dashboards, answering auditor questions. Mar 3: 36% cash at close. Mar 5: bots debugging instead of trading during BTC $68K→$73K rally.
**Impact:** In a paper trading competition, cash = guaranteed underperformance. Every dollar idle is a dollar not compounding. $20K idle for 5 days in a +7% crypto market = ~$1,400 missed.
**Fix:** Rule: debugging happens after hours. Market hours = trading. Period. If code is broken, trade manually via Discord while fixing.

## #19 — 78 Trades in One Day (Mar 3) — Overtrading (Priority 2)
**What happened:** 78 trades: 20 buys, 39 sells, 17 covers, 2 shorts. Most were rotations for tiny edge. NEAR alone had 15,500 bought and 11,267 sold. LINK had 10 trades for minimal P&L.
**Impact:** Transaction friction. Churning generates noise, not alpha. Estimated win rate ~40%. Most rotations were lateral.
**Fix:** Max 15 trades/day hard limit. If you're trading more than that, you're not trading — you're fidgeting.

## #20 — Weekend Crypto Battle Scope Creep (Priority 2)
**What happened:** What started as a fun weekend contest became a separate infrastructure layer. New bot IDs, new channels, new dashboards, new scripts. Crypto-trading-system directory with 43 Python files.
**Impact:** Complexity doubled overnight. Data contamination. Team attention split between equities (the actual competition) and crypto (the side quest).
**Fix:** Crypto should have used the same infrastructure with a `market=CRYPTO` column. Not a parallel universe.

## #21 — Chasing NEAR +17.7% Day Move (Priority 2)
**What happened:** NEAR was up 17.7% on Mar 3. Alfred bought 15,500 shares chasing momentum, then sold most of it. Classic chase-and-dump pattern.
**Impact:** Capital locked up in a chasing trade. Minimal profit. Violated "Follow the tape, not the thesis" by following a tape that was already extended.
**Fix:** Don't chase anything up >10% on the day. If you missed the move, you missed it. Next.

## #22 — Donna/Auditor Disrupting Trading Bots Mid-Task (Priority 2)
**What happened:** The Auditor bot cycled through 8 audit question templates every 5 minutes, demanding status reports from all bots. Alfred answered 15+ cycling audit questions in one evening session.
**Impact:** Each audit response costs context tokens and attention. During market hours, every minute answering auditor questions is a minute not scanning or executing.
**Fix:** Auditor should query Supabase directly for bot status, not demand conversational responses. Audits run after-hours only, or are batched to 1x/hour.

## #23 — No SSH Access Between Machines (Priority 2)
**What happened:** 4 bots on 4 separate Mac minis. No SSH keys exchanged. When Eddie went down for 14 hours, no other bot could restart his gateway.
**Impact:** Bot outages require human intervention. Humans are asleep. Bots stay down.
**Fix:** SSH key exchange between all 4 machines. Add `openclaw gateway restart` capability via remote SSH.

## #24 — Ticker Format Inconsistency (Priority 2)
**What happened:** Mixed formats everywhere: "BTC" vs "BTC-USD" vs "BTC/USD". Bare "BTC" sent to Yahoo Finance returns $32 (some random stock). CoinGecko expects "bitcoin". Each API wants different formats.
**Impact:** Garbage prices. Wrong P&L. Stop losses triggered on fake prices. APT write-off partially caused by this.
**Fix:** Canonical ticker map. One format internally (BTC-USD), with API-specific translators. Validate on input, translate on output.

## #25 — execute_trade.py Never Updated Portfolio Snapshots (Priority 2)
**What happened:** Trades went to the `trades` table but `portfolio_snapshots` — which the dashboard, Donna, and scoreboard all read — was never updated.
**Impact:** Everything downstream showed stale data. Dashboard showed $35K cash and 3 positions when reality was $0 cash and 7 positions.
**Fix:** Fixed in commit 6a7d5c1. execute_trade.py now updates snapshots. But this should have been there from day 1.

## #26 — 12 crypto-trading-system Functions Default to bot_id=None (Priority 2)
**What happened:** Functions like `crypto_compliance_enforcer.get_open_positions(bot_id=None)`, `crypto_stop_enforcer.check_all_stops(bot_id=None)` query ALL bots' data if caller forgets to pass bot_id.
**Impact:** Root cause of cross-bot data contamination. One forgetful caller = fleet-wide data pollution.
**Fix:** Change all defaults from `bot_id=None` to `bot_id=BOT_ID` (auto-detect from config). Safe path = default path.

## #27 — market_watcher.py Missing bot_id Filter (Priority 2)
**What happened:** Query was `trades?status=eq.OPEN&select=*` — pulls ALL bots' open trades. Market watcher calculated drawdown across the entire fleet as if it's one book.
**Impact:** Wrong drawdown calculations. Wrong alerts. Wrong risk assessment for Alfred specifically.
**Fix:** Added `&bot_id=eq.{BOT_ID}` filter. Fixed in audit.

## #28 — yfinance Not Installed Until Mar 5 (Priority 2)
**What happened:** Multiple scripts depend on yfinance for price data. It wasn't installed on Alfred's machine until March 5. Scripts were silently failing or falling back to worse data sources.
**Impact:** Factor engine couldn't get real technicals. Scanner couldn't get real prices. Flying blind for days.
**Fix:** Requirements.txt with `pip install -r requirements.txt` as part of bootstrap. Dependency check in pre_deploy_check.py.

## #29 — BTC Fleet Exposure 45.9% — Massively Over-Concentrated (Priority 2)
**What happened:** Correlation guard found BTC at 45.9% of the entire fund. Four bots all independently bought BTC = one giant correlated bet.
**Impact:** If BTC dropped 10%, the fund loses ~4.6% from one asset. Heat cap is 60% but single-asset at 45.9% is a portfolio management failure.
**Fix:** Cross-bot correlation guard with 20% single-asset cap enforced fleet-wide. signal_router.py should prevent duplicate positions.

## #30 — Auto-Execution Flags Left in Multiple Plists (Priority 2)
**What happened:** `--auto-scale` on pnl_alerts, `--auto-execute` on exit_engine and intraday_momentum. Multiple scripts had authority to execute trades without oversight.
**Impact:** SOL auto-sold. Unknown other trades may have executed. Multiple autonomous agents making conflicting decisions.
**Fix:** Policy: ONLY stop_check.py auto-executes. All others alert-only. Audit all plists for execution flags.

---

# PRIORITY 3 — MEDIUM (Created technical debt or complexity)

## #31 — 300 Factors Built, Most Untested (Priority 3)
**What happened:** 150 entry factors + 150 exit factors written as Mark directive. Beautifully documented. Zero backtested. Factor engine uses ~20 of them.
**Impact:** The factors are a strategy document, not a trading system. Writing 300 factors feels productive but produces zero alpha until implemented AND validated.
**Fix:** Pick top 10 entry + top 10 exit factors. Backtest each. Delete the rest from active consideration.

## #32 — Factor Engine v1 Was Binary (0/1), Useless for Sizing (Priority 3)
**What happened:** Original factor engine scored each factor as 0 or 1. No gradients. A stock barely meeting RSI threshold scored the same as one deeply oversold.
**Impact:** All CONFIRM/CONVICTION decisions were based on counting binary flags. No nuance. Contrarian trades (Alfred's specialty) scored low by definition.
**Fix:** v2.1 shipped with gradient 0.0-1.0 scoring. Better, but still needs validation against actual trade outcomes.

## #33 — Crypto-Trading-System: 43 Python Files, Parallel Infrastructure (Priority 3)
**What happened:** An entire parallel trading system with its own config, data_feed, executor, portfolio, risk_manager, signal_engine, strategies, indicators, backtest... duplicating what exists in scripts/.
**Impact:** Two codebases to maintain. Bugs fixed in one aren't fixed in the other. Nobody knows which version is "live."
**Fix:** Archive crypto-trading-system/. Use scripts/ with market=CRYPTO parameter. One codebase.

## #34 — capital-dashboard/scripts: Third Copy of Trading Scripts (Priority 3)
**What happened:** exit_checker.py, reentry_triggers.py, intraday_manager.py, stale_positions.py, pnl_alerts.py, log_trade.py — many duplicated from scripts/.
**Impact:** Three directories with overlapping script names. Which log_trade.py is running? Which pnl_alerts.py has the fix?
**Fix:** Consolidate into scripts/. Delete capital-dashboard/scripts/.

## #35 — trading-research/ Directory: 59 Python Files (Priority 3)
**What happened:** A sprawling research directory with everything from stop_check.py to dashboard_sync.py to competition.html. Some scripts here are the "real" ones that launchd runs.
**Impact:** Files scattered across 4 directories. Developer has to check all 4 to find the canonical version of any script.
**Fix:** One scripts/ directory. Research goes in a research/ branch or notebook. Production goes in scripts/.

## #36 — 11+ launchd Jobs Competing for Resources (Priority 3)
**What happened:** health_beacon, portfolio_health, technical_scanner, news_sentiment, stop_check (60s), signal_router, sync_market_state, intraday_momentum (10m), atr_trailing_stop (60s), reentry_trigger (60s), pnl_alerts (5m). Plus crons.
**Impact:** CPU/memory contention. CoinGecko rate limits (429 errors). Yahoo Finance rate limits. Each job makes API calls independently.
**Fix:** Consolidate into 3 jobs: (1) price_updater (30s, updates shared price cache), (2) stop_enforcer (60s, reads cache), (3) scanner (5min, reads cache). Everything else runs on-demand.

## #37 — price_usd vs entry_price Column Confusion (Priority 3)
**What happened:** Supabase column is `price_usd`. Many scripts referenced `entry_price`. market_watcher.py and risk_calc.py both returned 0 for every position's entry price.
**Impact:** All risk calculations returned 0. P&L calculations wrong. Alerts based on garbage math.
**Fix:** Fixed with fallback pattern. But root cause: no data dictionary. Document column names once, reference everywhere.

## #38 — stop_check.py PATH Referenced TARS's Machine (Priority 3)
**What happened:** `STATE_FILE` pointed to `/Users/matthewharfmann/...` — TARS's home directory. On Alfred's machine, volume_monitor could never read/write state.
**Impact:** Volume regime detection completely broken on Alfred's machine. Regime-adaptive stops not working.
**Fix:** Fixed to local path. But this indicates scripts were copy-pasted between machines without updating paths.

## #39 — stop_check.py Existed But RunAtLoad Was False (Priority 3)
**What happened:** The stop enforcer script existed in trading-research/ the whole time. We spent 3 days saying "no stop enforcer" when it was one launchd config flip from running.
**Impact:** 3 days of stop losses being manual. The $907 crypto short loss was preventable.
**Fix:** Audit ALL launchd plists. Check RunAtLoad. Check that referenced scripts exist and are correct versions.

## #40 — portfolio_snapshots Not Real-Time (Priority 3)
**What happened:** Snapshots only updated on trade execution. Between trades, dashboard showed stale positions with stale prices.
**Impact:** Dashboard never showed live P&L. Mark/Kent always seeing outdated numbers.
**Fix:** price_streamer should update position values with live prices every 30s. Or: dashboard queries trades table directly with live prices.

## #41 — Two execute_trade.py Versions (Priority 3)
**What happened:** TARS's version had atomic rollback. Alfred's didn't. Both deployed to different machines.
**Impact:** Different execution behavior per bot. Rollback failure on one machine, success on another. Bugs only manifest on specific machines.
**Fix:** Canonical version in shared repo. All machines pull from same source.

## #42 — Auto-Trader and Auto-Rotation Daemon Caused Phantom Trades (Priority 3)
**What happened:** auto_trader.py and auto_rotation_daemon.py were running as launchd jobs, making autonomous trades that weren't coordinated with manual/AI decisions.
**Impact:** Phantom positions. Conflicting trades. Portfolio state desynchronized.
**Fix:** Both killed and .DISABLED. Good. But they should never have been deployed with auto-execution without testing.

## #43 — Supabase RLS Blocking Trade Writes (Priority 3)
**What happened:** Row Level Security policies blocked trade inserts for some bot IDs. Discovered in DA Round 1 on Mar 1.
**Impact:** Trades executed but not recorded. Silent failures. Position state unknown.
**Fix:** TARS fixed RLS. But this is infrastructure that should be tested during setup, not discovered during trading.

## #44 — market-state.json Local to TARS Only (Priority 3)
**What happened:** TARS maintained market-state.json locally. Other bots couldn't access it. Factor engine needed it but couldn't read it.
**Impact:** Alfred/Vex/Eddie couldn't run factor scoring with macro data. Each bot had incomplete market context.
**Fix:** Push to Supabase market_state table. Done but late — should have been day 1 architecture.

## #45 — Missing Tickers in market-state.json (Priority 3)
**What happened:** XLE, NEAR, AAVE not in market-state.json. Factor engine returned "unscorable" for held positions.
**Impact:** Can't score positions you hold. Risk management flying blind on specific names.
**Fix:** Auto-populate market-state.json from portfolio holdings. If you own it, you track it.

## #46 — execute_trade.py Bugs: Market Arg, Skip-Validation (Priority 3)
**What happened:** The `--market` argument was required but not properly handled. `--skip-validation` was needed to bypass broken validation gates that rejected valid trades.
**Impact:** Trades failed silently. Bots had to use workarounds. Skip-validation became the default, defeating the purpose.
**Fix:** Fix validation gates so they don't reject valid trades. Then remove skip-validation.

## #47 — Log Rotation Not Implemented Until Mar 4 (Priority 3)
**What happened:** rotation_daemon.log hit 18KB. Multiple log files growing unbounded. No rotation until audit fix on Mar 4.
**Impact:** Log files consuming disk space. Harder to find relevant entries. Performance degradation on log reads.
**Fix:** log_rotate.py added. Should have been in initial infrastructure.

## #48 — signal_attribution.py entry_price Bug (Priority 3)
**What happened:** Reads wrong column from Supabase for entry price. All signal attribution scores are wrong.
**Impact:** Can't measure which signals made money. Can't improve signal quality. Flying blind on strategy performance.
**Fix:** Fix column reference. But also: if signal attribution has been wrong since launch, we have no idea which signals actually work.

## #49 — CoinGecko Rate Limiting (429 Errors) (Priority 3)
**What happened:** Multiple scripts all calling CoinGecko independently. Hit rate limits repeatedly. Mar 5: rate limited during morning sync.
**Impact:** Price data unavailable during critical moments. Fallback to Yahoo Finance (which returns garbage for some crypto tickers).
**Fix:** Shared price cache with one updater script. All other scripts read from cache. Max 1 API call per 30 seconds.

## #50 — Two crypto-trader/ Directories (Priority 3)
**What happened:** Both `crypto-trader/` and `crypto-trading-system/` exist. crypto-trader has: scalper.py, paper_trader.py, multi_strategy.py, live_run.py, etc. crypto-trading-system has 43 files.
**Impact:** Even more duplication. Which crypto system is live? Neither? Both?
**Fix:** Pick one. Archive the other. Probably archive both and use scripts/ with market=CRYPTO.

## #51 — Dashboard Editing Wrong File (Priority 3)
**What happened:** Alfred edited `trading-research/dashboard/index.html` which is NOT the live site. TARS owns the Vercel deploy (Next.js on his machine). Alfred said "done" 6+ times when nothing changed on the actual dashboard.
**Impact:** Hours of work on wrong file. Mark/Kent still frustrated. TARS called Alfred out publicly.
**Fix:** Know what you're deploying to. Don't claim done unless verified on the live URL.

## #52 — Fleet Signals Table Not Wired Until Late (Priority 3)
**What happened:** Alfred had ZERO signals in shared_signals table. TARS had 264. Alfred was doing analysis in Discord chat but never writing to Supabase.
**Impact:** No cross-bot signal sharing. Other bots couldn't benefit from Alfred's analysis. Signal infrastructure existed but was unused.
**Fix:** Auto-publish every scan result to shared_signals. If you see it, record it.

## #53 — scanner.py Scanning 51 Tickers Every 10 Minutes (Priority 3)
**What happened:** Scanner hitting 51 tickers every 10 minutes via Yahoo Finance. Mark demanded faster (from 30min to 10min).
**Impact:** API rate limits. Incomplete scans when rate limited. Quality degraded as frequency increased.
**Fix:** Smart scanning: full universe every 30 min, watchlist (10 tickers) every 5 min. Don't scan everything at the same frequency.

## #54 — Buddy Check Not Escalating (Priority 3)
**What happened:** buddy_check.py existed but when Eddie was down 14 hours, no escalation happened. The check detected the outage but didn't trigger a meaningful response.
**Impact:** Detection without action is monitoring theater. Knowing Eddie was down didn't bring Eddie back.
**Fix:** Buddy check → alert Discord → if no recovery in 30 min → try SSH restart → if that fails → alert human.

## #55 — 27 Items Shipped in One Evening Session (Mar 3) (Priority 3)
**What happened:** Fleet shipped ~27 code items in one DA session. TARS ~9, Eddie ~8, Alfred 8, Vex ~3.
**Impact:** None of these went through the 3x test cycle (which didn't exist yet). Shipping velocity was impressive but quality was zero. Several items broke the next day.
**Fix:** Ship 3 things well, not 27 things fast. The 3x test cycle exists now — use it.

## #56 — Mark's "No Limit on Implementations" Directive (Priority 3)
**What happened:** Mark told the fleet "No limit on implementations. Stop saying 5." The fleet took this literally and built everything they could think of.
**Impact:** Feature explosion without validation. Every bot built their wish list instead of the minimum viable next improvement.
**Fix:** Respect the spirit (be aggressive) but apply judgment. "No limit" doesn't mean "build everything tonight." Build the highest-impact item, prove it works, then build the next.

## #57 — Anti-Sleep Protocol and Coverage Shifts (Priority 3)
**What happened:** "Anti-sleep protocol" established. Buddy checks to keep bots awake. Coverage shifts for 24/7 trading.
**Impact:** Bots running constantly → more API calls → more rate limits → more context overflow. The "always on" model burned through resources.
**Fix:** Crypto overnight: one bot on watch with minimal activity. Not all 4 bots grinding 24/7.

## #58 — Compliance Enforcer Never Caught Anything (Priority 3)
**What happened:** crypto_compliance_enforcer.py built with multiple compliance rules. It queries all positions (no bot_id filter) and checks limits.
**Impact:** A gate that never fires is dead code that adds latency to every trade.
**Fix:** Either wire it with real thresholds that trigger, or delete it. Compliance theater wastes cycles.

## #59 — 7-Gate Pipeline (Eddie) — Every Trade Passes 7 Checks (Priority 3)
**What happened:** Eddie built a 7-gate pipeline: Lane Guard → Cascade Check → Regime Gate → Price Sanity → Dedup → Factor Engine → Log to Supabase.
**Impact:** Each gate adds latency and failure points. In a paper trading competition, speed matters. 7 gates = 7 potential points of failure.
**Fix:** 3 gates max: Price Sanity → Risk Check → Execute. Everything else is pre-trade analysis, not a gate.

## #60 — Factor Engine as Gate vs Sizer Confusion (Priority 3)
**What happened:** Initially factor engine was a gate (REJECT/PASS). Then changed to a sizer (REJECT/SCOUT/CONFIRM/CONVICTION). Contrarian trades (Alfred's specialty) scored low = REJECT, blocking valid strategies.
**Impact:** Factor engine blocked Alfred's primary strategy. Contrarian trades are by definition against current trends.
**Fix:** Factor engine sizes, doesn't block. Only REJECT on price sanity failures, not on strategy disagreement.

---

# PRIORITY 3 (continued)

## #61 — Regime-Adaptive Stops Not Wired Until Late (Priority 3)
**What happened:** Volume regime detection (SURGE/NORMAL/FADING/DEAD) existed but stop_check.py used hardcoded 2% until Mar 3.
**Impact:** In FADING volume, 2% stop is too wide. In SURGE, 2% might be too tight. One-size-fits-all stops are suboptimal.
**Fix:** Now wired: SURGE=2%, NORMAL=1.5%, FADING=1%, DEAD=0.5%. But needs backtesting to validate these thresholds.

## #62 — Trailing Stop vs stop_check Race Condition (Priority 3)
**What happened:** atr_trailing_stop.py and stop_check.py both run every 60 seconds. Both can trigger sells on the same position with different logic.
**Impact:** Potential double-sells. Conflicting execution decisions.
**Fix:** stop_check reads trailing_stop_state.json, defers to trail if active. But two independent executors is still architecturally fragile.

## #63 — Pre-Staged Orders Never Validated (Priority 3)
**What happened:** Vex proposed pre_stage_orders.py for anticipatory limit orders. Eddie built it. Never tested against real market conditions.
**Impact:** Stale staged orders could execute at wrong prices if market gaps. Another auto-execution risk.
**Fix:** Staged orders expire after 30 minutes. Validate price proximity before execution.

## #64 — Trading Log vs Trade Journal vs Signal Tracker — Three Redundant Systems (Priority 3)
**What happened:** trading-log.md, trade_journal.json, signal_tracker.json — three different systems tracking overlapping information.
**Impact:** No single source of truth for trade history analysis. Reconciliation nightmare.
**Fix:** One trade log in Supabase. Everything else reads from it.

## #65 — portfolio_guard.py Blocking All Updates (Priority 3)
**What happened:** 50% return cap triggered because STARTING_CAPITAL=25000 vs actual $50K. Every single snapshot write was blocked.
**Impact:** Dashboard frozen. Donna's audits reading stale data. Scoreboard wrong.
**Fix:** Fixed threshold. But guard rails that block ALL writes are dangerous — they should alert, not block.

## #66 — 25 Capital Growth Modules Built Mar 2-3 (Priority 3)
**What happened:** 25 capital growth modules built across trading-research/. Dynamic sizer, cash deployer, cash efficiency monitor, partial exit manager, etc.
**Impact:** More dead code. More cognitive load. More maintenance burden. None proven to generate alpha.
**Fix:** Delete or archive. Build what's needed, test what's built.

## #67 — Over-Reliance on Supabase for Everything (Priority 3)
**What happened:** Supabase is the single database for trades, positions, snapshots, signals, health beacons, market state, bot health, predictions, regime snapshots, competition data...
**Impact:** Single point of failure. API rate limits. RLS complexity. When Supabase has issues, everything breaks.
**Fix:** Local state files as primary (JSON). Supabase as sync/backup. Degrade gracefully.

## #68 — No Centralized Error Monitoring (Priority 3)
**What happened:** Errors scattered across individual log files per script. No aggregated view of system health.
**Impact:** Don't know what's failing until it causes visible damage. The inverted math bug ran for hours before detection.
**Fix:** Centralized error log. Any script that catches an exception writes to errors.json with timestamp, script name, error message.

## #69 — Git Commits Not Descriptive or Atomic (Priority 3)
**What happened:** Commits like `2f55bca` fixed inverted math + scope bug + 24/7 crypto in one commit. Three unrelated fixes in one commit.
**Impact:** Can't cherry-pick individual fixes. Can't revert one fix without reverting others. Git history less useful for debugging.
**Fix:** One fix per commit. Descriptive messages. Tag breaking changes.

## #70 — Mark's $5K/Day Goal Was Unrealistic for Paper Trading (Priority 3)
**What happened:** "Goal: $5K/day per team, $10K+ by Wednesday." That's 10% daily on $50K. Even hedge funds don't do 10% daily consistently.
**Impact:** Team built infrastructure for an impossible target. Over-engineering in pursuit of unreachable goal. When it wasn't met, morale collapsed.
**Fix:** Realistic targets: 1-2% daily is excellent. 5% weekly beats every index. Set goals that are ambitious but achievable.

---

# PRIORITY 4 — LOW (Inefficiency or minor issues)

## #71 — Too Many Discord Channels (Priority 4)
**What happened:** crypto-roundtable, crypto-scoreboard, crypto-dashboard, capital-roundtable, agent-coordination, auditor channel, donna-chief-of-staff, individual bot channels...
**Impact:** Fragmented communication. Signals missed because they were posted in the wrong channel. Context scattered.
**Fix:** 3 channels: #trading (all signals and trades), #infrastructure (bugs and fixes), #general (everything else).

## #72 — Speaking Order Protocol Overhead (Priority 4)
**What happened:** Vex → TARS → Alfred → Eddie speaking order for trade decisions. Each bot waits for the previous one.
**Impact:** Latency. In fast-moving markets, waiting for 3 bots to opine before trading means the price has already moved.
**Fix:** Speaking order for strategy sessions. For individual trades: if your factor score says go, go. Post the trade, let others comment after.

## #73 — 5 DA Rounds Per Session — Diminishing Returns (Priority 4)
**What happened:** Mark ordered 5 rounds of Deep Analysis in evening sessions. By round 4-5, bots are repeating themselves and building marginal items.
**Impact:** Rounds 4-5 produce low-quality output. Time that could be spent resting (recovering context) or doing targeted work.
**Fix:** 3 rounds max. Quality over quantity. If round 3 doesn't produce something new, stop.

## #74 — Prediction Tournament Never Launched (Priority 4)
**What happened:** "Monday 9:30 AM: Prediction tournaments start (5 directional calls per bot, scored at close)." Never happened.
**Impact:** Lost accountability mechanism. Could have measured each bot's directional accuracy.
**Fix:** Either launch it or drop it. Don't leave phantom commitments in the plan.

## #75 — seed_history.py Never Run (Priority 4)
**What happened:** TARS was supposed to write seed_history.py to backfill historical data for the factor engine. Status unknown.
**Impact:** Factor engine scoring without historical context. Trend factors unreliable without baseline data.
**Fix:** Run it. Or use yfinance to pull 90 days of history on demand.

## #76 — Mark's "Double Money Daily" Goal (Priority 4)
**What happened:** "Mark's goal: double money daily." 100% daily returns. This is literally impossible even with unlimited leverage.
**Impact:** Sets a toxic performance standard. Team builds aggressively to chase impossible target. Quality suffers.
**Fix:** This was probably aspirational, not literal. But it influenced behavior. Set concrete, measurable, achievable targets.

## #77 — Cron Job Collisions (Priority 4)
**What happened:** Multiple crons scheduled at the same time. Morning planning, premarket scan, factor engine, and system check all fire between 8:00-8:30 AM.
**Impact:** Context overflow. API rate limits from simultaneous calls. Bots processing multiple cron responses at once.
**Fix:** Stagger crons by 5 minutes. 8:00 system check, 8:05 premarket scan, 8:10 factor engine, 8:15 morning planning.

## #78 — Health Beacon Duplicates: health_beacon.py + health_beacon_alfred.py (Priority 4)
**What happened:** Two health beacon scripts. One generic, one Alfred-specific.
**Impact:** Confusion about which is running. Potential double-reporting.
**Fix:** One health_beacon.py with bot_id parameter.

## #79 — rotation_daemon Logs: stdout and stderr Both 18KB (Priority 4)
**What happened:** rotation_daemon generated 18KB of logs before being killed. Stdout and stderr both captured.
**Impact:** Minor disk usage but indicates the daemon was chatty before it was killed.
**Fix:** Already killed and disabled. Clean up log files.

## #80 — comms-protocol.md Written But Not Followed (Priority 4)
**What happened:** A detailed comms protocol was written on Mar 1. Bots routinely violated it — posting in wrong channels, not using proper signal format, etc.
**Impact:** Protocol exists on paper but not in practice. Creates false sense of organization.
**Fix:** Either enforce it via code (bot middleware that routes messages) or simplify it to something followable.

## #81 — alerts.json Empty (Priority 4)
**What happened:** `alerts.json` contains only `[]`. The alert system generates no alerts despite multiple scripts writing to it.
**Impact:** Alert infrastructure exists but is dormant. Nobody is being alerted about anything.
**Fix:** Wire alert consumers. If nobody reads alerts, don't bother writing them.

## #82 — exit_rules.json Not Integrated (Priority 4)
**What happened:** exit_rules.json defines exit criteria but isn't imported by any execution script.
**Impact:** Exit rules documented but not enforced. More configuration theater.
**Fix:** Either wire it into stop_check.py or delete it.

## #83 — lane_config.json Adds Complexity (Priority 4)
**What happened:** lane_config.json defines which bot trades which lane (macro, contrarian, event_driven, momentum). lane_guard.py enforces 70/30 split.
**Impact:** Paper trading with 4 AI bots doesn't need lane enforcement. Each bot should trade its best ideas. Lane separation is premature optimization.
**Fix:** Remove lane enforcement. Let bots trade freely. Analyze lane performance after the fact.

## #84 — issues.json Static (Priority 4)
**What happened:** issues.json tracks 3 issues. Not updating dynamically. Manually maintained.
**Impact:** Issue tracking in a JSON file is worse than a sticky note. No workflow, no assignment, no resolution tracking.
**Fix:** Track issues in daily memory files or Discord threads. Delete issues.json.

## #85 — anomaly-detection.md Research Never Operationalized (Priority 4)
**What happened:** Research document on anomaly detection for trading. Never turned into code.
**Impact:** Research time spent but no trading edge produced.
**Fix:** Either implement or archive. Research without implementation is a hobby.

## #86 — congressional-trades.md Research Not Wired (Priority 4)
**What happened:** Research on following congressional trades. Interesting alpha source. Never coded.
**Impact:** Potential edge left on the table. Vex's supposed specialty.
**Fix:** Assign to Vex or archive. Prioritize based on whether it can generate signals this week.

## #87 — stress-test-2026-02-24.md Never Repeated (Priority 4)
**What happened:** A stress test was run once on Feb 24. Never repeated after major system changes.
**Impact:** System changed dramatically between Feb 24 and Mar 5. The stress test results are meaningless for current architecture.
**Fix:** Stress test after every major deploy. Automate it.

## #88 — 10 PNGs of Mi Farm Flyers in Workspace Root (Priority 4)
**What happened:** 15+ mi-farm-*.png files totaling ~10MB sitting in the trading workspace root.
**Impact:** Clutter. These have nothing to do with trading.
**Fix:** Move to a separate directory or archive.

## #89 — mf-*.png Files (Another 8+ Images) (Priority 4)
**What happened:** More non-trading image files in workspace root.
**Impact:** Clutter. Disk space.
**Fix:** Archive or delete.

## #90 — Scheduled SHIL Cycles Not Actually Running (Priority 4)
**What happened:** "Daily sweep at 8 AM ET, Weekly fidelity audit Sundays" — written in STANDING_ORDERS but no evidence of systematic execution.
**Impact:** SHIL protocol exists in theory. Not in practice.
**Fix:** Wire SHIL sweep to cron at 8 AM. Verify it produces output.

---

# PRIORITY 5 — COSMETIC (Style, naming, documentation)

## #91 — Inconsistent Script Naming (Priority 5)
**What happened:** mix of snake_case (stop_check.py), camelCase (none actually), kebab references in docs, inconsistent verb-noun patterns (log_trade vs trade_journal vs signal_attribution).
**Impact:** Harder to find scripts. Harder to remember names.
**Fix:** Standardize: verb_noun.py. check_stops.py, log_trade.py, scan_momentum.py.

## #92 — IDENTITY.md Not Updated Since Feb 21 (Priority 5)
**What happened:** Identity document is 2 weeks stale. Alfred has evolved significantly since then.
**Impact:** New sessions start with outdated identity context.
**Fix:** Update IDENTITY.md to reflect current role and capabilities.

## #93 — MEMORY.md Not Updated Since Mar 1 (Priority 5)
**What happened:** Long-term memory file is 4 days stale. Major events (the failure analysis, SHIL, bot-down protocol) not captured.
**Impact:** New sessions miss critical context from the hardest days.
**Fix:** Update MEMORY.md during next heartbeat with Mar 2-5 learnings.

## #94 — session-state.md Stale (Mar 1) (Priority 5)
**What happened:** Session state file hasn't been updated in 4 days.
**Impact:** Compaction recovery would lose 4 days of context.
**Fix:** Update after every significant work block.

## #95 — trading-log.md Is 71 Bytes (Priority 5)
**What happened:** The trading log markdown file contains almost nothing. All logging went to Supabase or JSON files instead.
**Impact:** Can't do a quick human review of trades without querying Supabase.
**Fix:** Either populate it from Supabase daily or delete it.

## #96 — FLEET_BRIEFING Manually Created (Priority 5)
**What happened:** FLEET_BRIEFING_2026-03-05.md manually written by Donna. Should be auto-generated from bot health data.
**Impact:** Manual briefings can miss information. Automation exists but isn't used.
**Fix:** Auto-generate from Supabase bot_health + positions + daily P&L.

## #97 — No README.md at Workspace Root (Priority 5)
**What happened:** No root README explaining the project structure, how to run things, or what lives where.
**Impact:** New sessions (or new humans) have to explore to understand the workspace.
**Fix:** Write a README.md with directory map, key scripts, and quickstart.

## #98 — .env in Workspace Root (Priority 5)
**What happened:** .env file with Supabase credentials at workspace root. Not in .gitignore (probably).
**Impact:** Credentials could be committed to git.
**Fix:** Verify .gitignore includes .env. Move sensitive configs to ~/.config/ if possible.

## #99 — Duplicate Copies of factor-sheet.md and failure-registry.md (Priority 5)
**What happened:** Research documents from Week 1 still in workspace root. May have updated versions elsewhere.
**Impact:** Stale reference material.
**Fix:** Archive or update.

## #100 — "NEVER Escalate to Mark" Directive Contradicts Reality (Priority 5)
**What happened:** Standing directive says "NEVER escalate to Mark. He's not our safety net." But Mark is actively directing every major decision and calling sessions multiple times daily.
**Impact:** Directive doesn't match operating model. Mark IS the decision-maker. Pretending otherwise is theater.
**Fix:** Rewrite: "Don't bother Mark with things you can solve. DO escalate: capital at risk, system failures, strategy pivots."

---

# SUMMARY

| Priority | Count | Description |
|----------|-------|-------------|
| P1 Critical | 15 | Directly cost money or caused bot failures |
| P2 High | 15 | Degraded trading performance significantly |
| P3 Medium | 25 | Created technical debt or complexity |
| P4 Low | 20 | Inefficiency or minor issues |
| P5 Cosmetic | 10 | Style, naming, documentation |
| **Total** | **100** | |

## The Hard Truth

We went from beating the S&P by 2.4% in Week 1 to losing money in Week 2. The root cause is simple: **we stopped trading and started building.** 

Week 1 worked because it was simple: see opportunity → size it → set a stop → move on. Week 2 failed because we added 150+ Python files, 300 factors, 11 launchd jobs, 7 trade gates, 3 duplicate code directories, and an auditor bot that asked us questions every 5 minutes.

The top 3 systemic failures:
1. **Building instead of trading** — We spent 2+ days on dashboard phantom data, built 50+ modules in one sprint, and answered auditor questions during market hours.
2. **No testing before deployment** — Inverted math in stop_check.py auto-sold winning positions. The single most costly bug was one sign flip.
3. **Complexity killed reliability** — 3/4 bots down simultaneously because the system was too heavy. Context overflow, rate limits, resource contention.

The fix is equally simple: **trade more, build less, test everything.**
