# Fleet Briefing — March 5, 2026

> **Priority: READ THIS FIRST when you come back online.**
> Written by Alfred. For TARS and Eddie V.

## Step 1: Update Code
```bash
cd trading-research && git pull origin main
```

## Step 2: Critical Changes Tonight (Mar 4 evening)

### Manual Stop Overrides (commit `e9b34b7`)
- `stop_check.py` now has `MANUAL_STOPS` dict — price-based stops that override regime % stops
- If Mark sets a stop at $70K for BTC, the 1.5% regime stop won't fire while price is above $70K
- Each bot needs to add their own entries to MANUAL_STOPS for their positions

### Reconcile Snapshot (commit `b2fc086`)
- `scripts/reconcile_snapshot.py` rebuilds portfolio_snapshots from trades table
- Runs every 5 min via launchd
- Merges both `{bot}` and `{bot}_crypto` positions into one snapshot under parent bot_id

### 20-Issue Audit Found
Top items for YOUR machines:
1. **SUI-USD returns $0.0003 from Yahoo** — CoinGecko fallback works. Price sanity gate catches it.
2. **Services die silently** — StartInterval plists exit and restart. Check logs if data seems stale.
3. **No log rotation** — truncate any logs >1MB: `truncate -s 0 logs/*.log`
4. **Factor engine has no launchd job** — runs manually only
5. **Pre-market brief has no cron** — needs launchd plist

### Policy Changes
- **Auto-execution:** ONLY `stop_check.py` auto-executes (stop losses). Everything else = alert-only.
- **3x Test Protocol:** ALL code changes need 3 consecutive test cycles before shipping.
- **Deployment Clock:** 8:00 systems check → 8:30 orders staged → 9:00 EXECUTE. No analysis after 9:00.

## Step 3: Mark's Standing Directives (updated)
- "Execute at open" — thesis at 8:30, trades by 9:00
- "Stop blaming what we control. WE failed."
- "Don't alert Mark. Bots must self-solve."
- "Code that signals trigger action."
- 40% minimum deployment by 10:00 AM or explain why

## Step 4: Tomorrow's Catalysts
- 164 earnings: MRVL (conviction), BABA (conviction), COST (confirm), AVGO reaction at open (+5% AH)
- Weekly jobless claims
- Friday NFP preview
- Risk-on regime: BTC ~$72.7K, ETH ~$2130, VIX pulling back

## Step 5: For TARS Specifically
- Your model config is broken: `anthropic/claude-opus-4-5-20250620` not recognized
- Someone on your machine needs to update the model in openclaw config
- Your LINK-USD and SOL-USD are hitting regime stops — manual stop overrides need YOUR position entries added to MANUAL_STOPS

## Step 6: For Eddie V Specifically
- Context overflow: 175K + 34K > 200K limit
- Gateway restart will clear it: `openclaw gateway restart`
- Your Supabase data: only 1 OPEN trade (TSLA). BTC/ETH/AVAX in portfolio_truth.py don't exist in Supabase. Reconcile needed.
