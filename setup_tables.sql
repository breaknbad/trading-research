-- Run this in Supabase SQL Editor to create missing tables
-- URL: https://supabase.com/dashboard/project/vghssoltipiajiwzhkyn/sql/new

CREATE TABLE IF NOT EXISTS trailing_stop_state (
    id BIGSERIAL PRIMARY KEY,
    bot_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    high_watermark REAL NOT NULL,
    trail_active BOOLEAN DEFAULT FALSE,
    activated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bot_id, ticker)
);

CREATE TABLE IF NOT EXISTS cash_deploy_alerts (
    id BIGSERIAL PRIMARY KEY,
    bot_id TEXT NOT NULL,
    cash_pct REAL NOT NULL,
    cash_usd REAL NOT NULL,
    suggested_tickers JSONB,
    alert_type TEXT DEFAULT 'idle_cash',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS but allow service role full access (already default)
ALTER TABLE trailing_stop_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_deploy_alerts ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role full access" ON trailing_stop_state FOR ALL USING (true);
CREATE POLICY "Service role full access" ON cash_deploy_alerts FOR ALL USING (true);
