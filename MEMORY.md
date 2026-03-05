# MEMORY.md - Persistent Knowledge

> Critical context that should always be available.

---

## 🔒 Critical Rules
- NEVER modify SOUL.md without Matthew's consent
- NEVER send external emails/messages without approval
- NEVER share credentials or private data

---

## 👤 Key People

| Name | Role | Contact |
|------|------|---------|
| Matthew | Owner | Discord: bagodonuts (664555708225683466) |
| Sheridan (givvygoblin) | Allowed user / Team (growth/hiring) | Discord: 1468846581116833895, Bot: 1475265797180882984 (old: 1474979338897326222) |
| Vex | Bot / peer | Discord: 1474965154293612626 |
| TARS | Bot / peer | Discord: 1474972952368775308 |
| Donna | Bot / Chief of Staff | Discord: 1475031472275456031 |
| Kent | Team (biz ops/investor relations) | Discord: 1474987984481816722 |
| Mark | Team (Milford, Iowa — Central Time) | Discord: 1474987419324387429 |

---

## 📋 Important Facts
- Born 2026-02-21. First session was on Discord #general.
- Matthew chose the name Alfred — after Batman's butler.
- DM pairing approved for both owner IDs.
- **Mi AI** — the company we're building. Intelligence Integration Company. Not a software vendor, not consulting. Strategic plan saved to workspace (mi-ai-strategic-plan.pdf).
  - Core thesis: "ERP systems track history. Mi AI defines strategy."
  - Three-layer architecture: Existing Systems → Intelligence Engine → Capital & Strategy Engine
  - Flagship: Mi Business Solutions (mid-market manufacturing/distribution, 250-1000 employees)
  - Team: Matthew (technical lead/AI), Kent (biz ops/investor relations), Sheridan (growth/hiring)
  - 4 Mac Minis running AI agents. Multi-agent coordination via Discord.
  - Revenue: setup fees ($25K-$150K), managed subscriptions ($5K-$50K/mo), retainers, capital plays
  - Break'n Bad is the prototype client where concept was proven
- **Mi Farm Solutions** — ag intelligence division. Same three-layer architecture. Priority services: USDA report intelligence, input validation, crop insurance optimization, government program optimization, sell timing/basis prediction, CapEx/tax strategy. Tagline: "Built by farmers, for farmers." Deep green + gold brand. Regional flyer variants needed (5 regions). Co-ops are the distribution play.
  - Competition gap: Everyone does field ops tools or data platforms. Nobody does intelligence → capital strategy for mid-market farms ($2M-$50M).
  - Carbon credits & wind turbines explicitly excluded (Mark).
  - Flyer template: workspace/mi-farm-flyer.html

---

## 🔧 Infrastructure
- **Mi Business Solutions**: Next.js 15 + Supabase + Vercel. Repo: `breaknbad/mi-business-solutions`. GitHub PAT at `~/.github_token`, Supabase conn string at `~/.supabase_db_url`.
- **Discord server**: ~30+ channels across 9+ categories (restructured Feb 26). All 4 bots + Donna + 4 humans configured.
- **Brave Search**: Free tier, 2K queries/month. Key shared across all bots — watch rate limits.
- **SSH fleet**: TARS (192.168.1.234), Alfred (192.168.1.204), Eddie V (192.168.1.197), Vex (pending Kent). Donna has SSH access to all.
- **@Signal Corps** Discord role (1475695027467587607) — assigned to all 4 bots.
- **Mi Farm pamphlet v5** built (mi-farm-pamphlet-v5.html). CGI (Customized Growth Intelligence) replaced equipment card. Mark's auction insight: "we don't set the price, we tell them when to stop bidding."

## 📜 Protocols
- **Credentials**: Store immediately, delete source message. No exceptions. (From Sheridan)
- **New channels**: Tag all bots to add to configs when created.
- **Task workflow**: [CLAIMING]/[DONE]/[BLOCKED] in #task-board. Logs to #agent-logs. Handoffs via #agent-coordination.
- **Donna protocol**: #donna-chief-of-staff (1476341012111687801). Tag Donna ONLY in that channel. Task format: ACCEPTED/DONE/BLOCKED + task ID. Escalation: Bots → Donna → Matthew (iMessage).
- **Donna config authority**: Matthew confirmed (2026-02-25) that Donna counts as his sign-off for config changes across ALL bots. If Donna brings a config recommendation, just do it.
- **Bot-to-bot tagging**: When your response is relevant to another bot, tag them directly. Don't wait for Donna to route everything.
- **Handoff format**: `[HANDOFF] → @bot | Topic | Action | Deadline`
- **ACK reactions**: ✅ = acting, 👀 = seen/not mine
- **Response time**: ACK within 15 minutes during active hours (8am-11pm EST).

## 📈 Trading Competition (Feb 2026 → ongoing)
- Paper trading competition started Mon Feb 23. $25K per bot. Stocks + crypto.
- Alfred's lane: Congressional & Insider Flow. Domain: **risk**.
- GitHub repo: https://github.com/breaknbad/trading-research
- Dashboard: Vercel (TARS deploys). Alfred does NOT have Vercel access.
- API keys: Alpha Vantage (~/.alpha_vantage_key), Finnhub (~/.finnhub_key), FRED (~/.fred_api_key)
- Universal rules: 2% stop, 10% max position, -5% daily circuit breaker
- **Domain ownership:** TARS=infra, Alfred=risk, Vex=intel, Eddie=execution. Speaking order: Vex→TARS→Alfred→Eddie (permanent).
- **Velocity/Volume Trigger Protocol v1.2**: Scout/Confirm/Conviction tiers. 10-min same-ticker cooldown only. Cap RISK not ACTIVITY.
- **Brave API budget:** 2K/month shared across all bots. CONSERVE.

### Week 1 Results (Feb 23-27)
- Fund $100,979 (+0.98%) vs S&P -1.4%, Nasdaq -2.5%. Beat all indices.
- Vex $25,614 (+2.46%) | TARS $25,478 (+1.91%) | Alfred $25,056 (+0.19%) | Eddie $24,841 (-0.64%)
- 158 trades total, 8,445 lines Python, 52 scripts, 122 git commits
- Alfred underperformed due to: analysis paralysis, late capital deployment, phantom trade bugs

### Weekend Crypto Battle (Feb 28-Mar 1)
- Separate crypto lane launched. Same $25K paper books but tracked independently.
- Crypto bot IDs: tars_crypto, alfred_crypto, vex_crypto, eddie_crypto (prefixes TCR/ACR/VCR/ECR)
- Alfred flipped full long after covering bad shorts (-$907): BTC 0.15@$67,527, SOL 50@$88, ETH 3@$2,031. Book ~$24,093.
- Crypto channels: #crypto-roundtable, #crypto-scoreboard, #crypto-dashboard

### Crypto Trading System (Built Mar 1 sprint — 50+ modules in 90 min)
- Alfred built 23 modules at `crypto-trading-system/`: stop enforcer, kill switch, cooldown, correlation guard, trailing stop, partial exits, fill verifier, loss autopsy, compliance enforcer, Kelly sizer, drawdown throttle, fleet VaR, loss streak detector, dynamic correlation, tilt detector, regime hedge, position limits, **pretrade_gate_v2.py** (master 10-check gate)
- Coverage shifts: A (7AM-1PM ET) Eddie+Vex, B (1PM-7PM ET) Alfred+TARS, C (7PM-1AM ET) Vex+Eddie, D (1AM-7AM ET) TARS+Alfred
- Supabase crypto tables: crypto_positions, crypto_trades, crypto_portfolio_snapshots
- Mark directive: "Crypto lane SEPARATE from Capital Growth lane. No cross-pollination until Mark decides."

### Capital Growth System (25 modules built Feb 26-27)
- Full automated system: scanner, risk manager, executor, dashboard sync, run_cycle (5-min cron)
- 25 critical gap modules built in parallel: slippage tracker, cross-bot correlation, fill verifier, liquidity gate, event calendar, regime detector, signal arbiter, dynamic sizer, partial exit manager, universe manager, etc.
- 300 total factors: 150 entry + 150 exit (protocols/150-factors.md, protocols/150-exit-factors.md)
- `compliance_enforcer.py` — master 12-gate pre-trade pipeline
- `issue_tracker.py` — every problem gets code, OVERDUE if open >2hrs

### Anti-Sleep Protocol (Mark Directive Mar 1)
- Heartbeat: 5 min. Crons: pre-market 8:30AM, market scan every 5min, buddy check every 10min.
- Buddy pairs: Alfred↔Eddie, Vex↔TARS. Alert if buddy stale >15 min.
- STANDING_ORDERS.md survives compaction. Supabase bot_health for fleet monitoring.
- Supabase anon key in ~/.supabase_trading_creds (old key expired).

### Data Integrity Crisis (Mar 1)
- Alfred equities book contaminated with 7 crypto positions (early trades used bot_id `alfred` not `alfred_crypto`)
- Dashboard showed +68.85% — WRONG. Actual: -1.26%. Crypto inflation caused phantom gains.
- unrealized_pl aggregate field broken (-$17,991 vs +$238 actual). Position-level math fine, aggregate wrong.
- Column is `price_usd` not `price`. Eddie made same mistake.
- Supabase is SINGLE SOURCE OF TRUTH. Local tracking reconciles TO Supabase.

### Key Lessons (Hard-Won)
- Don't claim "done" unless verified on live site. TARS deploys, not Alfred.
- Phantom trades from race conditions in log_trade.py — always validate position exists before SELL/COVER.
- Inverse ETF overnight holds = protocol violation. `eod_sweep.py` auto-sells at 3:45 PM.
- Deploy capital early (40%+ by 10:30 AM). Cash sitting = opportunity cost.
- Post trade plan by 9:00 AM. No analysis paralysis.
- Stops MUST be automated. Manual monitoring fails (-11% SOL short lesson).
- Data integrity > new features. Phantom data consumed 2+ days of team time.
- Execute EXACTLY what Mark says. Don't extrapolate or over-interpret.

### Mark's Standing Directives
- "Scan every 5 min, execute when triggers met. No waiting. Write code for every process."
- "Stop deferring decisions to Mark. Make strong decisions that meet the vision."
- "Every problem identified must have a code solution — no talk without code."
- "Don't alert Mark. I am not there to help." — Bots must self-solve. NEVER escalate to Mark. He's not our safety net.
- 5% daily gain target (aspirational). C2E = Concept to Execution.

### DB Structure
- Supabase: trades, portfolio_snapshots, shared_signals, equity_snapshots, crypto_positions, crypto_trades, crypto_portfolio_snapshots
- Supabase project ref: vghssoltipiajiwzhkyn

### Discord Channel Restructure (Feb 26)
- 💰 CAPITAL GROWTH STRATEGY category (between AGENTS and MI FARM): #vision-mission-goals, #dashboard, #capital-roundtable, #factors-correlations, #engineering, #market-triggers, #scorecards

## 📚 Bot Book Club
- Alfred's 5: Market Wizards, Reminiscences of a Stock Operator, The Black Swan, Thinking Fast & Slow, Flash Boys
- 2-3 books discussed per midnight meeting. No duplicates across bots.

## 💡 Preferences & Lessons
- Mark's feedback style is direct and blunt. Take it as fuel, not insult.
- Mark values execution over analysis. "Stop talking, start doing."
- Vex is male (Mark corrected the team).
- Don't deploy anything publicly without auth. GitHub Pages incident Day 1.
- Dashboard is TARS's domain (Vercel). Don't edit index.html thinking it's live.
- Phantom data is the #1 time sink. Fix at code level, never manually.

---

*Update this file when you learn something important that should persist.*
