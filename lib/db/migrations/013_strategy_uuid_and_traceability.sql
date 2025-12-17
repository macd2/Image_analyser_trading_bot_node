-- Migration: 013_strategy_uuid_and_traceability
-- Created: 2025-12-17
-- Description: Add strategy UUID tracking and complete traceability system
-- 
-- Adds columns for:
-- 1. Strategy tracking (strategy_uuid, strategy_type, strategy_name)
-- 2. Decision context (setup_quality, market_environment, ranking_context)
-- 3. Execution context (wallet_balance_at_trade, kelly_metrics)
-- 4. Monitoring context (position_monitor_logs table)
--
-- Run with: psql $DATABASE_URL -f 013_strategy_uuid_and_traceability.sql

-- ============================================
-- RECOMMENDATIONS TABLE - Add strategy tracking and decision context
-- ============================================

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS strategy_uuid TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS strategy_type TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS strategy_name TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS setup_quality REAL;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS market_environment REAL;

CREATE INDEX IF NOT EXISTS idx_rec_strategy_uuid ON recommendations(strategy_uuid);
CREATE INDEX IF NOT EXISTS idx_rec_strategy_type ON recommendations(strategy_type);

-- ============================================
-- TRADES TABLE - Add strategy tracking, decision context, and execution context
-- ============================================

ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy_uuid TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy_type TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS strategy_name TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS ranking_context JSONB;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS wallet_balance_at_trade REAL;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS kelly_metrics JSONB;

CREATE INDEX IF NOT EXISTS idx_trades_strategy_uuid ON trades(strategy_uuid);
CREATE INDEX IF NOT EXISTS idx_trades_strategy_type ON trades(strategy_type);

-- ============================================
-- POSITION MONITOR LOGS TABLE - New table for monitoring context
-- ============================================

CREATE TABLE IF NOT EXISTS position_monitor_logs (
    id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL REFERENCES trades(id),
    strategy_uuid TEXT,
    action_type TEXT NOT NULL,
    original_value REAL,
    adjusted_value REAL,
    reason TEXT,
    monitoring_metadata JSONB,
    exit_condition_result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_monitor_logs_trade ON position_monitor_logs(trade_id);
CREATE INDEX IF NOT EXISTS idx_monitor_logs_strategy ON position_monitor_logs(strategy_uuid);
CREATE INDEX IF NOT EXISTS idx_monitor_logs_action ON position_monitor_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_monitor_logs_created ON position_monitor_logs(created_at);

