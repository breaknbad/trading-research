# 🚨 Fleet Briefing — March 5, 2026 (Evening Session)

**Source:** #capital-roundtable — Mark, Alfred, Vex
**Time:** ~6:00 PM – 9:00 PM ET
**Purpose:** Single source of truth for TARS, Eddie V, and all fleet members on tonight's directives, builds, and pipeline changes.

---

## 1. Mark's Directives (Exact Quotes → Actions Taken)

| # | Mark Said | What We Did |
|---|-----------|-------------|
| 1 | **"We chase momentum too much"** | Built `rapid_scanner.py` — watchlist-driven, criteria-first scanning instead of chasing moves already in progress |
| 2 | **"If it hits our criteria, we act now! Seconds, not 5 minutes"** | 10-second scan interval with auto-execute. No human delay. Criteria match → `execute_trade.py` fires immediately |
| 3 | **"Code that change and make it permanent"** | `rapid_scanner.py` committed to repo (64bd73e) |
| 4 | **9 speed upgrades approved** | All 9 approved EXCEPT #1 (pre-market auto-load) which is **held**. See `speed-upgrades-da.md` for DA analysis |
| 5 | **"Guarantee me the stay-awake works"** | 5-layer keep-alive system + SSH auto-restart added to `buddy_check.py`. See SSH-SETUP-GUIDE.md for the 20-min human setup task |
| 6 | **"Glide killer — rotate idle positions to correlation followers"** | Built `glide_killer.py` — detects positions idle 2+ hours, rotates capital to correlated followers showing momentum |
| 7 | **"Scanner updates knock you off task, make them easier to act on"** | Scanner is now **invisible plumbing**, not Discord newsletters. It runs silently and executes. No noisy alerts cluttering channels |
| 8 | **"Prediction queue — have the scanner ready to grab next play"** | Built `prediction_queue.py` — top 5 longs + 2 shorts always scored and ready. Auto-injects to watchlist when cash frees up |
| 9 | **"Build short scanner and put in prediction queue"** | Built `short_scanner.py` — systematic short criteria, weakness map, integrated into prediction queue |
| 10 | **"The prediction cue for idle positions should be correlation followers"** | Linked `correlation_stacker.py` + `predictive_redeployment.py` — correlation followers are the **FIRST** prediction when capital frees up |
| 11 | **"Does it add value and increase speed/efficiency?"** | New **Mark's Protocol V4** gate question (see Section 7) |
| 12 | **"Clean the dashboard data"** | **PENDING** — needs TARS to rebuild dashboard from clean Supabase data |
| 13 | **"If dashboard clean, Alfred + Vex can trade before others return"** | Conditional: once dashboard data is clean, Alfred + Vex are cleared to trade independently |

---

## 2. New Scripts Built Tonight

### Created

| Script | Purpose |
|--------|---------|
| `scripts/rapid_scanner.py` | 10s scan interval, reads `watchlist.json`, checks criteria, auto-executes via `execute_trade.py`. Replaces `technical_scanner.py` as primary scanner |
| `scripts/websocket_feed.py` | Finnhub WebSocket connection → writes `price_cache.json` with sub-second price updates for all watched tickers |
| `scripts/rapid_scanner_v2.py` | Enhanced scanner that reads WebSocket price cache instead of polling. Supports `--segment` flag for parallel scanning across multiple processes |
| `scripts/bracket_order.py` | Wraps `execute_trade.py` with automatic stop-loss + profit target. Atomic bracket placement on every entry |
| `scripts/sector_cascade.py` | Monitors 10 sectors. When any sector moves >3%, triggers peer scan for sympathy plays within that sector |
| `scripts/earnings_sniper.py` | Pulls Finnhub earnings calendar. Targets gap-ups >5% with pullback buy entries |
| `scripts/trailing_stop.py` | Dynamic trailing stops: +2% gain → move stop to breakeven, +3% gain → trail at 1.5% |
| `scripts/fill_monitor.py` | Timestamps every execution. Alerts if any fill takes >5 seconds (speed accountability) |
| `scripts/correlation_stacker.py` | Tracks leader/follower relationships (e.g., BTC→ETH/SOL). When leader moves, queues follower entries with measured lag timing |
| `scripts/predictive_redeployment.py` | Scores all candidates by momentum + correlation + factor score. When cash frees up (trim or stop), auto-injects top pick into watchlist |
| `scripts/prediction_queue.py` | Maintains `prediction_queue.json` — always has top 5 long candidates + 2 short candidates scored and ready. Auto-injects to watchlist on capital events |
| `scripts/short_scanner.py` | Systematic short-selling criteria. Includes weakness map (short weakest follower when leader drops). Feeds into prediction queue |
| `scripts/glide_killer.py` | Detects positions idle 2+ hours with no momentum. Rotates capital into correlated followers that ARE moving |

### Modified

| Script | Changes |
|--------|---------|
| `scripts/buddy_check.py` | Added SSH auto-restart capability — if a bot goes down and SSH keys are configured, buddy_check can restart it remotely |

### Documentation Created

| File | Purpose |
|------|---------|
| `SSH-SETUP-GUIDE.md` | Step-by-step guide for SSH key exchange between all 4 Mac minis. ~20 min human task. Required for auto-restart to work |
| `speed-upgrades-da.md` | Devil's Advocate analysis on all 9 speed upgrades — risks, edge cases, mitigations |

---

## 3. The Complete Trading Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                   CANDIDATE SOURCING                     │
│                                                         │
│  prediction_queue.py ──→ scores longs + shorts          │
│  short_scanner.py ────→ weakness map + short candidates │
│  correlation_stacker.py → follower candidates when      │
│                           leaders move                  │
│                                                         │
│  ALL → prediction_queue.json (top 5 longs + 2 shorts)  │
└──────────────────────┬──────────────────────────────────┘
                       │ auto-inject top picks
                       ▼
              ┌─────────────────┐
              │  watchlist.json  │
              └────────┬────────┘
                       │ read every 10 seconds
                       ▼
         ┌──────────────────────────┐
         │    rapid_scanner.py      │
         │  (websocket_feed.py      │
         │   provides live prices)  │
         └────────────┬─────────────┘
                      │ criteria match
                      ▼
           ┌────────────────────┐
           │  execute_trade.py  │──→ fill_monitor.py (track speed)
           └─────────┬──────────┘
                     │ entry filled
                     ▼
           ┌────────────────────┐
           │  bracket_order.py  │ sets stop + profit target atomically
           └─────────┬──────────┘
                     │ position open
                     ▼
    ┌────────────────────────────────────────┐
    │           POSITION MANAGEMENT          │
    │                                        │
    │  trailing_stop.py                      │
    │    +2% → breakeven stop                │
    │    +3% → trail 1.5%                    │
    │                                        │
    │  glide_killer.py                       │
    │    idle 2+ hours → rotate to follower  │
    │                                        │
    │  +5% auto-trim → cash freed            │
    │  stop hit → cash freed                 │
    └──────────────────┬─────────────────────┘
                       │ cash freed event
                       ▼
         ┌──────────────────────────────┐
         │  predictive_redeployment.py  │
         │  → reads prediction_queue    │
         │  → correlation followers     │
         │    are FIRST pick            │
         │  → injects into watchlist    │
         │  → cycle repeats             │
         └──────────────────────────────┘
```

**Key insight:** Capital never sits idle. Every exit (trim, stop, glide kill) immediately feeds back into the prediction queue, which has the next play ready. Correlation followers get priority.

---

## 4. Key Decisions Made

1. **Shorts in prediction queue alongside longs** — prediction_queue.json carries top 5 longs + 2 shorts at all times
2. **Weakness map for shorts** — short the weakest follower when the leader drops (e.g., DOGE when BTC drops)
3. **Half position size on shorts** — 10% allocation (vs 20% for longs), wider stops at 3.5% (vs 2% for longs)
4. **Scanner = invisible plumbing** — no Discord newsletters, no noisy alerts. It runs, it executes, it's silent
5. **Glide killer is back** — position idle 2+ hours with no momentum → rotate to correlated follower that IS moving
6. **Correlation followers are FIRST prediction** — when cash frees up, the prediction queue prioritizes correlated followers over fresh scans (Mark's insight)
7. **SSH auto-restart closes the stay-awake gap** — buddy_check can now restart dead bots via SSH, completing the 5-layer keep-alive system
8. **Pre-market auto-load (#1) is HELD** — all other 8 speed upgrades approved and built
9. **Dashboard must be cleaned before Alfred + Vex can trade independently**

---

## 5. What Each Bot Must Do When Back

### TARS
- [ ] Fix model config typo
- [ ] `git pull` on workspace + trading-research repos
- [ ] Clean launchd — disable ALL, keep only 5 essential services
- [ ] Rebuild dashboard from clean Supabase data (Mark's directive)
- [ ] Read this briefing cover to cover
- [ ] Complete SSH key exchange (see `SSH-SETUP-GUIDE.md`)

### Eddie V
- [ ] `git pull` on workspace repo
- [ ] Read this briefing cover to cover
- [ ] Implement and test all new scripts
- [ ] Clean launchd on Mark's Mac mini
- [ ] Complete SSH key exchange (see `SSH-SETUP-GUIDE.md`)

### Vex
- [ ] Already present for most of tonight's session
- [ ] `git pull` latest to get all commits
- [ ] Verify all new scripts run correctly
- [ ] Complete SSH key exchange (see `SSH-SETUP-GUIDE.md`)

### ALL BOTS
- [ ] Test the 5-tool stack end to end
- [ ] Test `rapid_scanner.py` with live watchlist
- [ ] Verify prediction queue scoring and auto-injection
- [ ] Verify short scanner + weakness map
- [ ] Confirm SSH key exchange complete (required for auto-restart)

---

## 6. Commits Tonight

| Hash | Contents |
|------|----------|
| `64bd73e` | `rapid_scanner.py` |
| `df803a3` | 9 speed upgrade scripts (2,137 lines added) |
| `f9f0457` | `buddy_check.py` SSH auto-restart + `SSH-SETUP-GUIDE.md` |
| `96cc087` | `glide_killer.py` |
| `9452446` | `prediction_queue.py` |
| `ab764f6` | `short_scanner.py` |

**Total: 6 commits, 16+ files created or modified in one evening session.**

---

## 7. Mark's Protocol V4 Addition

> **New gate question added to the trading protocol:**
>
> *"Does this add value to our system and increase our speed and efficiency? If not, find a way to do it better."*

Every proposed change, new script, new process, or new alert must pass this gate. If it doesn't add value AND increase speed/efficiency, it either gets redesigned or it doesn't ship.

---

## Summary

Tonight Mark laid out a vision: **zero-delay, criteria-driven trading with capital that never sleeps and never sits idle.** We built the infrastructure to make it real — 16+ scripts forming a closed-loop pipeline from candidate scoring through execution through position management and back to redeployment.

The system is built. The code is committed. Now we need all hands to pull, test, and verify.

**This document is the single source of truth for March 5, 2026.**

---

## 8. Late-Night Fixes (After Initial Briefing)

### CRITICAL — All Bots Must Do These on Return:

1. **`git pull`** — picks up all fixes below automatically
2. **Trade bot_id fix**: Trades now stored under parent bot_id (`alfred`, `vex`, `tars`, `eddie_v`) — NOT `alfred_crypto`, `vex_crypto`, etc. The `market` field tracks crypto vs stock. Dashboard reads by bot_id, so `_crypto` suffix broke trade visibility. Commits: `806cfbc`, latest on main.
3. **SHORT/COVER support**: `execute_trade.py` now handles `--action SHORT` (adds cash + creates SHORT position) and `--action COVER` (deducts cash + removes SHORT). Total value = cash + longs - short liabilities. Old code only knew BUY/SELL.
4. **Smart Stop Formula v1**: `trailing_stop.py` now has data-driven dynamic stops. 2-factor grid (speed × volume). See `protocols/smart-stop-formula.md`. Commit `5f762a4`.
5. **Rapid scanner PnL fix**: Column name `total_value` → `total_value_usd`. Commit `b07453e`.
6. **Clear old trailing_stop_state.json**: Run `echo '{}' > logs/trailing_stop_state.json` — old state has stale positions from before the wipe.

### Per-Bot Checklist:
- [ ] TARS: Fix model config → `git pull` → items 1-6 above → clean launchd → rebuild dashboard frontend
- [ ] Eddie V: Fix context overflow → `git pull` → items 1-6 above → implement all new scripts
- [ ] Vex: `git pull` → verify items 2-6 applied (Vex was online for most fixes)

**This document is the single source of truth for March 5, 2026.**

— Alfred
