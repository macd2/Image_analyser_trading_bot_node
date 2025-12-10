-- Migration: 008_performance_indexes
-- Created: 2025-12-09
-- Description: Add performance indexes for dashboard queries
-- 
-- Run with: psql $DATABASE_URL -f 008_performance_indexes.sql
-- Or via Python migration runner

-- ============================================
-- 1. Indexes for trades table
-- ============================================

-- Speed up queries filtering by cycle_id (used in stats aggregation)
CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id);

-- Speed up JOINs with recommendations table
CREATE INDEX IF NOT EXISTS idx_trades_recommendation ON trades(recommendation_id);

-- Speed up ORDER BY created_at DESC (used in getRecentTrades)
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);

-- ============================================
-- 2. Composite index for runs table
-- ============================================

-- Speed up queries fetching latest run for an instance
CREATE INDEX IF NOT EXISTS idx_runs_instance_started ON runs(instance_id, started_at DESC);

-- ============================================
-- 3. Optional: Index for cycles table (if needed)
-- ============================================

-- Already have idx_cycles_run and idx_cycles_boundary

-- ============================================
-- 4. Index for recommendations table (if needed)
-- ============================================

-- Already have idx_rec_cycle and idx_rec_symbol

-- ============================================
-- 5. Index for trades status + dry_run (optional)
-- ============================================

-- Not needed at this time.

-- ============================================
-- 6. Index for trades run_id + status (optional)
-- ============================================

-- Already have idx_trades_run and idx_trades_status.
