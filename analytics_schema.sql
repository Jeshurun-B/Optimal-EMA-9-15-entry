-- analytics_schema.sql
-- ═════════════════════════════════════════════════════════════════════════════
-- PURPOSE: Database schema for the EMA Crossover Analytics Dataset.
--          Run this SQL in your ANALYTICS Supabase project (separate from main).
--
-- TABLE: crossover_analytics
-- PURPOSE: Store trade outcome metrics for each crossover interval
-- ═════════════════════════════════════════════════════════════════════════════
-- Drop the crossover_analytics table and all its data

CREATE TABLE IF NOT EXISTS crossover_analytics (
    -- ═════════════════════════════════════════════════════════════════════════
    --                              PRIMARY KEYS
    -- ═════════════════════════════════════════════════════════════════════════
    
    id BIGSERIAL PRIMARY KEY,
    
    -- UTC timestamp of the crossover (ISO 8601 format)
    -- CRITICAL: This must EXACTLY match the main dataset's UTC format
    -- Example: "2026-05-01T10:30:00+00:00"
    crossover_utc TIMESTAMPTZ NOT NULL,
    
    -- Trading pair (e.g., "BTCUSDT", "ETHUSDT")
    symbol TEXT NOT NULL,
    
    
    -- ═════════════════════════════════════════════════════════════════════════
    --                              SIGNAL INFORMATION
    -- ═════════════════════════════════════════════════════════════════════════
    
    -- Signal direction: "LONG" or "SHORT"
    signal TEXT NOT NULL CHECK (signal IN ('LONG', 'SHORT')),
    
    -- Price at crossover (actual entry price)
    entry_price NUMERIC(20, 8) NOT NULL,
    
    
    -- ═════════════════════════════════════════════════════════════════════════
    --                              TRADE METRICS
    -- ═════════════════════════════════════════════════════════════════════════
    
    -- Optimal entry: Best possible entry price in the trade window
    -- LONG:  Lowest low BEFORE MFE peak
    -- SHORT: Highest high BEFORE MFE bottom
    optimal_entry NUMERIC(20, 8) NOT NULL,
    
    -- UTC timestamp when optimal entry occurred
    -- Critical for understanding timing: how long after crossover was best entry?
    optimal_entry_utc TIMESTAMPTZ NOT NULL,
    
    -- MFE (Maximum Favorable Excursion): Peak profit potential (%)
    -- LONG:  (highest high - entry) / entry × 100
    -- SHORT: (entry - lowest low) / entry × 100
    mfe_percent NUMERIC(10, 2) NOT NULL,
    
    -- MAE (Maximum Adverse Excursion): Worst drawdown (%)
    -- LONG:  (lowest low - entry) / entry × 100 (negative value)
    -- SHORT: (entry - highest high) / entry × 100 (negative value)
    mae_percent NUMERIC(10, 2) NOT NULL,
    
    -- Number of 15-minute candles in the trade window
    -- Example: 100 candles = 1,500 minutes = 25 hours
    trade_duration INTEGER NOT NULL,
    
    
    -- ═════════════════════════════════════════════════════════════════════════
    --                              EXIT INFORMATION
    -- ═════════════════════════════════════════════════════════════════════════
    
    -- UTC timestamp of next crossover (end of trade window)
    next_crossover_utc TIMESTAMPTZ NOT NULL,
    
    -- Price at next crossover (exit price)
    exit_price NUMERIC(20, 8) NOT NULL,
    
    -- Actual PnL from entry to exit (%)
    -- LONG:  (exit - entry) / entry × 100
    -- SHORT: (entry - exit) / entry × 100
    pnl_percent NUMERIC(10, 2) NOT NULL,
    
    
    -- ═════════════════════════════════════════════════════════════════════════
    --                              METADATA
    -- ═════════════════════════════════════════════════════════════════════════
    
    -- Auto-populated timestamp for when record was inserted
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    
    -- ═════════════════════════════════════════════════════════════════════════
    --                              CONSTRAINTS
    -- ═════════════════════════════════════════════════════════════════════════
    
    -- Prevent duplicate crossovers for same symbol
    CONSTRAINT unique_crossover UNIQUE (symbol, crossover_utc),
    
    -- Ensure next crossover is after current crossover
    CONSTRAINT valid_time_window CHECK (next_crossover_utc > crossover_utc),
    
    -- Ensure trade has minimum duration
    CONSTRAINT valid_duration CHECK (trade_duration >= 1)
);


-- ═════════════════════════════════════════════════════════════════════════════
--                              INDEXES FOR PERFORMANCE
-- ═════════════════════════════════════════════════════════════════════════════

-- Index on symbol for filtering queries (e.g., "show me all BTCUSDT trades")
CREATE INDEX idx_analytics_symbol ON crossover_analytics(symbol);

-- Index on crossover timestamp for chronological queries and merging
CREATE INDEX idx_analytics_crossover_utc ON crossover_analytics(crossover_utc);

-- Composite index for symbol + timestamp (most common query pattern)
CREATE INDEX idx_analytics_symbol_utc ON crossover_analytics(symbol, crossover_utc);

-- Index on signal type (for filtering LONG vs SHORT trades)
CREATE INDEX idx_analytics_signal ON crossover_analytics(signal);


-- ═════════════════════════════════════════════════════════════════════════════
--                              ROW LEVEL SECURITY (OPTIONAL)
-- ═════════════════════════════════════════════════════════════════════════════

-- Disable RLS for insert-only data collection pipeline
ALTER TABLE crossover_analytics DISABLE ROW LEVEL SECURITY;

-- Uncomment below if you need to enable RLS later for read access control
-- ALTER TABLE crossover_analytics ENABLE ROW LEVEL SECURITY;
-- 
-- CREATE POLICY "Allow public read access"
--   ON crossover_analytics
--   FOR SELECT
--   USING (true);


-- ═════════════════════════════════════════════════════════════════════════════
--                              COMMENTS (DOCUMENTATION)
-- ═════════════════════════════════════════════════════════════════════════════

COMMENT ON TABLE crossover_analytics IS 
'Analytics dataset for EMA crossover trades. Contains outcome metrics (optimal entry, MFE, MAE) for each crossover interval. Designed to merge with main signal dataset via UTC column.';

COMMENT ON COLUMN crossover_analytics.crossover_utc IS 
'UTC timestamp of EMA crossover. Primary key for merging with main dataset. MUST match exact UTC format from main database.';

COMMENT ON COLUMN crossover_analytics.optimal_entry IS 
'Best possible entry price that existed BEFORE the MFE peak. LONG = lowest low before highest high, SHORT = highest high before lowest low. Temporal constraint enforced: t(optimal_entry) < t(MFE).';

COMMENT ON COLUMN crossover_analytics.optimal_entry_utc IS 
'UTC timestamp when optimal entry price occurred. Shows timing window between crossover and best entry opportunity.';

COMMENT ON COLUMN crossover_analytics.mfe_percent IS 
'Maximum Favorable Excursion - peak profit potential from entry. Always positive for profitable moves.';

COMMENT ON COLUMN crossover_analytics.mae_percent IS 
'Maximum Adverse Excursion - worst drawdown from entry. Negative for drawdowns, positive for favorable moves.';

COMMENT ON COLUMN crossover_analytics.trade_duration IS 
'Number of 15-minute candles between this crossover and next. Example: 96 candles = 24 hours.';
