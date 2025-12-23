-- Migration: 015_spread_based_position_sizing
-- Created: 2025-12-23
-- Description: Add spread-based position sizing columns to recommendations table
--
-- Adds columns for:
-- 1. units_x: Quantity for main symbol (X) in spread-based trades
-- 2. units_y: Quantity for pair symbol (Y) in spread-based trades
-- 3. pair_entry_price: Entry price for pair symbol
--
-- These columns are populated by spread-based strategies (e.g., CointegrationAnalysisModule)
-- and used by the trading engine to calculate pair_qty for spread-based trades.
--
-- Run with: psql $DATABASE_URL -f 015_spread_based_position_sizing.sql

-- ============================================
-- RECOMMENDATIONS TABLE - Add spread-based position sizing
-- ============================================

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS units_x REAL;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS units_y REAL;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS pair_entry_price REAL;

-- Create indexes for spread-based queries
CREATE INDEX IF NOT EXISTS idx_rec_units_x ON recommendations(units_x) WHERE units_x IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rec_units_y ON recommendations(units_y) WHERE units_y IS NOT NULL;

