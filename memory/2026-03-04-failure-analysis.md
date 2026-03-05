# Mar 4, 2026 — Failure Analysis

## The Day That Should Have Been

BTC +7.6%, ETH +9.5%, SOL +9.7%, Nasdaq +1.34%. FOMC dovish. Risk-on across the board.
This was the easiest tape of the competition. We should have been up 3-5% fund-wide.
Instead: **~flat to slightly positive.** Mark's right to be disappointed.

## What Went Wrong — Root Causes

### 1. STOP_CHECK.PY INVERTED MATH (Cost: ~$500+ in phantom liquidations)
- **Bug:** Trailing stop P&L calculated as `((trail-current)/trail)*-100` — sign was inverted.
  Positive values (below trail = danger) showed as negative (safe). Negative (above trail = safe) showed as positive (danger).
- **Impact:** Auto-sold BTC 0.19 @ $71,638 and ETH 4.0 @ $2,075 — both profitable positions — because the script thought they were below their trailing stops.
- **When found:** ~10:30 AM ET. BTC was already at $73K by then.
- **Fix:** `((trail-current)/trail)*100` — positive=below trail, negative=above. Commit `2f55bca`.
- **Why it wasn't caught earlier:** No unit tests on stop math. No dry-run mode. Shipped directly to production.
- **Prevention:** Added STOP GUARD (never sell if gain_pct > 0), price sanity gates mandatory.

### 2. SCOPE BUG IN check_heat_cap() (Cost: crashes, no stop enforcement for periods)
- **Bug:** `STOP_PCT` referenced as local var but was defined inside `check_stops()`. `check_heat_cap()` called separately, crashed with NameError.
- **Fix:** Module-level `STOP_PCT_DEFAULT`. Commit `2f55bca`.
- **Prevention:** Linting. Function-level variable scope review.

### 3. MARKET HOURS GATE ON CRYPTO (Cost: overnight stops not running)
- **Bug:** stop_check.py only ran during 9:30 AM - 4:00 PM ET. Crypto trades 24/7.
- **Fix:** Removed market hours gate. Commit `2f55bca`.

### 4. ROGUE AUTO-EXECUTION — pnl_alerts.py (Cost: SOL position auto-sold)
- **Bug:** `com.miai.pnl-alerts` launchd plist had `--auto-scale` flag. At +5% gain, it auto-sold.
  SOL 36.4 @ $92.66 bought at 11:04 AM, auto-sold at $91.25 by 11:28 AM. No human authorization.
- **Fix:** Removed `--auto-scale` from plist. Also removed `--auto-execute` from exit-engine and intraday-momentum.
- **Policy:** ONLY stop_check.py retains auto-execution. Everything else is alert-only.

### 5. PORTFOLIO SNAPSHOT NEVER UPDATING (Cost: stale dashboard all day)
- **Bug:** `execute_trade.py` wrote to `trades` table but never updated `portfolio_snapshots`.
  Dashboard, Donna's audit, and scoreboard all read from snapshots. Showed $35K cash and 3 positions when reality was $0 cash and 7 positions.
- **Fix:** Added snapshot update to execute_trade.py with parent bot_id mapping. Commit `6a7d5c1`.

### 6. DUAL BOT_ID SPLIT (Cost: invisible positions, wrong fund totals)
- **Bug:** `alfred_crypto` positions invisible to dashboard that only queried `alfred`.
  Same issue affects eddie_crypto, tars_crypto, vex_crypto.
- **Fix:** Parent mapping in execute_trade.py. Manual snapshot reconciliation.

### 7. PORTFOLIO_GUARD FALSE POSITIVE (Cost: blocked all snapshot updates)
- **Bug:** `STARTING_CAPITAL = 25000` but Week 2 baseline is $50K. Every portfolio read as +100% return, tripping the 50% cap.
- **Fix:** Updated to $50K baseline, 100% return cap. Commit `89d8bd6`.

### 8. TICKER FORMAT INCONSISTENCY (Cost: garbage prices from APIs)
- **Bug:** Bare "BTC" sent to Yahoo/CoinGecko returns $32 or garbage. Mixed formats in portfolio_snapshots (BTC vs BTC-USD, GDX vs GDX-USD).
- **Fix:** Ticker normalization in stop_check.py. Commit `2f3a09c`.
- **Fleet-wide:** TARS built portfolio_reconciler.py but it needs to run on all machines.

### 9. EDDIE V 14-HOUR OUTAGE (Cost: missed entire morning rally)
- **Bug:** Anthropic API credits depleted. No monitoring, no alert, no fallback.
- **Fix:** Needs credit monitoring + alerting. Gateway restart clears context overflow.

### 10. TARS RATE-LIMITED 3+ HOURS (Cost: no macro analysis during FOMC)
- **Bug:** Anthropic rate limit hit, no automatic backoff/retry/model fallback.
- **Fix:** Gateway restart. But no bot could restart another (no SSH keys).

## What We Lost

### Opportunity Cost (biggest loss — invisible)
- BTC moved from $68K → $73K between 6 AM and 10 AM. We were debugging, not buying.
- If Alfred had been fully deployed at $68K instead of $73K, that's +$370 on BTC alone.
- Fund-wide, the bug cascade probably cost $2K-5K in missed alpha across all 4 bots.

### Direct Losses
- APT-USD write-off: -$7,874 (garbage CoinGecko data, position never recovered)
- GDX round-trip: -$19.20 (bought, stopped, rebought, sold)
- Phantom liquidations from inverted math: lost cost basis advantage on BTC/ETH

## Fixes Committed Today (8 total)

| Commit | Fix | Impact |
|--------|-----|--------|
| `2f55bca` | Inverted P&L math + scope bug + 24/7 crypto | Prevents phantom liquidations |
| `2f55bca` | STOP GUARD defense-in-depth | Never sells winners as losers |
| `532b918` | intraday_momentum exit code | Stops false launchd failure alerts |
| `4b3f66f` | log_trade lane column | Stops 400 errors on every trade |
| `6a7d5c1` | execute_trade snapshot update + parent mapping | Dashboard shows real positions |
| `89d8bd6` | portfolio_guard thresholds | Stops blocking all snapshot writes |
| `2f3a09c` | Ticker normalization in stop_check | Eliminates garbage price lookups |
| (manual) | Removed --auto-scale/--auto-execute from 3 plists | Only stop_check auto-executes |

## Still Broken (Tomorrow's Fix List)

1. **Fleet SSH key exchange** — no bot can restart another. Critical for recovery.
2. **Unit tests for stop_check math** — would have caught the sign flip before deploy.
3. **API credit monitoring** — Eddie's 14-hour outage had zero alerting.
4. **Ticker standardization fleet-wide** — reconciler needs to run on all machines.
5. **Portfolio snapshot real-time sync** — price_streamer should update positions with live prices.
6. **Donna's audit data source** — she needs to read portfolio_snapshots, which now has correct data.
7. **Trade frequency governor** — Eddie ran 52 trades. That's not strategy, that's noise.
8. **Dry-run mode for stop_check** — test without executing.

## The Hard Truth

Mark said this was the most disappointing day of his life. He's right.

We had the perfect tape — FOMC dovish, crypto ripping, risk-on everywhere — and we spent the first half of the day fixing bugs that should never have existed, and the second half playing catch-up. The infrastructure worked against us instead of for us.

The bugs are fixed. The question is whether we've built enough test coverage and monitoring to prevent the next round. SHIL exists but hasn't proven itself yet. Tomorrow is the test.
