-- Migration: 010_sl_adjustments
-- Created: 2025-12-13
-- Description: Add stop loss adjustment tracking table for pre-execution SL modifications

-- ============================================
-- SL ADJUSTMENTS TABLE
-- ============================================
-- Tracks all stop loss adjustments applied before trade execution.
-- Links to recommendations via recommendation_id for full audit trail.
-- Separate from post-execution tightening (which uses error_logs).

CREATE TABLE IF NOT EXISTS sl_adjustments (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,

    -- Original values from recommendation
    original_stop_loss REAL,

    -- Adjusted values after applying adjustment
    adjusted_stop_loss REAL,

    -- Adjustment details
    adjustment_type TEXT NOT NULL DEFAULT 'percentage',  -- 'percentage', 'fixed', etc.
    adjustment_value REAL NOT NULL,  -- e.g., 1.5 for 1.5% wider
    reason TEXT,  -- e.g., 'config_adjustment', 'manual_override'

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups by recommendation
CREATE INDEX IF NOT EXISTS idx_sl_adj_rec ON sl_adjustments(recommendation_id);

-- Index for audit trail queries
CREATE INDEX IF NOT EXISTS idx_sl_adj_created ON sl_adjustments(created_at);

-- ============================================
-- TRACEABILITY NOTES
-- ============================================
-- To trace adjustment for a trade:
--   trade → recommendation_id → sl_adjustments
--
-- Full SL journey query:
--   SELECT 
--       t.id as trade_id,
--       r.stop_loss as original_rec_sl,
--       sa.original_stop_loss,
--       sa.adjusted_stop_loss,
--       sa.adjustment_value,
--       t.stop_loss as executed_sl,
--       el.message as tightening_event
--   FROM trades t
--   LEFT JOIN recommendations r ON t.recommendation_id = r.id
--   LEFT JOIN sl_adjustments sa ON r.id = sa.recommendation_id
--   LEFT JOIN error_logs el ON t.id = el.trade_id 
--       AND el.event = 'sl_tightened'
--   WHERE t.id = ?
--   ORDER BY el.created_at;

