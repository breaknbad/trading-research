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
- **Discord server**: 27 channels across 9 categories. All 4 bots + 4 humans configured.
- **Brave Search**: Free tier, 2K queries/month. Key shared across all bots — watch rate limits.

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

## 📈 Trading Competition (Feb 2026)
- Paper trading competition starting Mon Feb 23. $25K per bot. Stocks + crypto.
- Alfred's lane: Congressional & Insider Flow
- GitHub repo: https://github.com/breaknbad/trading-research
- Dashboard: static site in repo, deployed to Vercel by TARS
- API keys: Alpha Vantage (~/.alpha_vantage_key), Finnhub (~/.finnhub_key)
- Updates to Mark at 10am CT, noon CT, 1hr before close
- Universal rules: 2% stop, 10% max position, -5% daily circuit breaker
- **Velocity/Volume Trigger Protocol v1.2** (updated Feb 26): Scout/Confirm/Conviction tiers. See `protocols/velocity-volume-triggers.md`.
  - SCOUT: 1.5% move + 1.5x RVOL, min 2/10 conviction (velocity+volume), min $1K size
  - CONFIRM: 3% + 2x RVOL, scout green, add equal, stop to breakeven
  - CONVICTION: 5%+ 3x RVOL + sector confirm, max 12%, trail 1.5%
  - **No trade caps.** No hourly limits. No time cutoffs. 10-min same-ticker cooldown only.
  - Kept: 2% stops, 10% max position, -5% circuit breaker, $500M market cap floor, 30% sector cap
  - Mark directive: "Cap risk, not activity. If there are 25 setups, be in 25."
- **Day 4 corrected standings (Feb 26 close):** Alfred $24,817 (-0.73%) | Vex ~$24,940 | Eddie ~$25,056 | TARS ~$24,302. Fund ~$99K, slightly negative overall.
- **Portfolio inflation bug resolved**: Phantom SQQQ sells + wrong short accounting formula. Fixed formula: Portfolio = Cash + Long_value - Short_obligation. `log_trade.py` now pre-validates positions before SELL/COVER.
- **Brave API budget:** 2K/month shared across all bots. CONSERVE.
- **Alfred overnight positions (Feb 26→27):** AAPL 4x@$272.28, AMZN 5x@$209, BBAI 100x@$3.50, CRM 13x@$192.21, GLD 2x@$476, MSFT 3x@$404.69, PLTR 9x@$135.63, XLP 7x@$80, SQQQ 14x@$70.74 (**SELL AT OPEN — inverse ETF rule**), SHORT NVDA 14x@$187.27, SHORT AMD 5x@$202.91. Cash: $18,533.

## 💡 Preferences
- Building this over time.

---

*Update this file when you learn something important that should persist.*
