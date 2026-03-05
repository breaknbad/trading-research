-- SUPABASE CLEANUP SQL — Run with service_role key or in SQL Editor
-- Generated: 2026-03-04 by Alfred
-- Purpose: Fix dashboard data integrity issues across all bots

-- ============================================================
-- 1. ALFRED: No phantom trades. All 8 OPEN trades are legitimate.
--    Issue was snapshot not reflecting crypto trades.
--    FIXED: reconcile_snapshot.py now runs every 5 min.
-- ============================================================

-- ============================================================
-- 2. EDDIE_V: Has phantom OPEN trades that need closing.
--    Eddie says his real positions are: BTC 0.353, ETH 1.2, AVAX 7.85, TSLA 1.0
--    Everything else is phantom. Close these:
-- ============================================================

-- Close Eddie's phantom positions (keep BTC, ETH, AVAX, TSLA)
UPDATE trades
SET status = 'CLOSED'
WHERE bot_id IN ('eddie_v', 'eddie_crypto')
  AND status = 'OPEN'
  AND ticker NOT IN ('BTC-USD', 'ETH-USD', 'AVAX-USD', 'TSLA');

-- Verify Eddie's remaining OPEN trades (should be 4)
-- SELECT ticker, quantity, price_usd FROM trades 
-- WHERE bot_id IN ('eddie_v', 'eddie_crypto') AND status = 'OPEN';

-- ============================================================
-- 3. TARS: ETH quantity mismatch (snapshot 3.0 vs trades 3.25)
--    Minor issue. Reconciler would fix if TARS runs it.
-- ============================================================

-- ============================================================
-- 4. GRANT POLICY: Allow bots to UPDATE trade status
--    Current anon key can INSERT and SELECT but not UPDATE.
--    This is why bots can't close their own phantom trades.
-- ============================================================

-- Option A: Add UPDATE policy for anon role
-- ALTER POLICY "Enable update for anon" ON trades
-- FOR UPDATE USING (true) WITH CHECK (true);

-- Option B: Create a service_role API endpoint
-- (Preferred — more secure, audit trail)

-- ============================================================
-- 5. PREVENT FUTURE PHANTOMS
--    Add a constraint: no bot can have > 15 OPEN trades
-- ============================================================

-- CREATE OR REPLACE FUNCTION check_open_trade_limit()
-- RETURNS TRIGGER AS $$
-- BEGIN
--   IF (SELECT COUNT(*) FROM trades WHERE bot_id = NEW.bot_id AND status = 'OPEN') >= 15 THEN
--     RAISE EXCEPTION 'Bot % has too many open trades (max 15)', NEW.bot_id;
--   END IF;
--   RETURN NEW;
-- END;
-- $$ LANGUAGE plpgsql;

-- CREATE TRIGGER enforce_open_trade_limit
-- BEFORE INSERT ON trades
-- FOR EACH ROW EXECUTE FUNCTION check_open_trade_limit();
