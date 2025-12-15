-- Migration: Add position sizing metrics to trades table
-- Purpose: Store detailed position sizing calculations for audit trail and UI display
-- Date: 2025-12-15

-- Add new columns to trades table for position sizing metrics
ALTER TABLE trades ADD COLUMN IF NOT EXISTS position_size_usd REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS risk_amount_usd REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS risk_percentage REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS confidence_weight REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS risk_per_unit REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS sizing_method TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS risk_pct_used REAL;

-- Create index for sizing_method for filtering
CREATE INDEX IF NOT EXISTS idx_trades_sizing_method ON trades(sizing_method);

