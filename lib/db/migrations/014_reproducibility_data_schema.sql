-- Migration: 014_reproducibility_data_schema
-- Created: 2025-12-17
-- Description: Add reproducibility data capture schema
--
-- Adds columns for:
-- 1. Input snapshots (chart hash, model version, market data, config)
-- 2. Intermediate calculations (confidence components, setup quality, etc.)
-- 3. Reproducibility metadata (model params, prompt version, etc.)
--
-- Run with: psql $DATABASE_URL -f 014_reproducibility_data_schema.sql

-- ============================================
-- RECOMMENDATIONS TABLE - Add reproducibility columns
-- ============================================

-- Input snapshot: chart hash, model version, market data, strategy config
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS chart_hash TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS model_version TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS model_params JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS market_data_snapshot JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS strategy_config_snapshot JSONB;

-- Intermediate calculations: confidence components, setup quality, market environment
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS confidence_components JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS setup_quality_components JSONB;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS market_environment_components JSONB;

-- Reproducibility metadata
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS prompt_version TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS prompt_content TEXT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS validation_results JSONB;

-- Create indexes for reproducibility queries
CREATE INDEX IF NOT EXISTS idx_rec_chart_hash ON recommendations(chart_hash);
CREATE INDEX IF NOT EXISTS idx_rec_model_version ON recommendations(model_version);
CREATE INDEX IF NOT EXISTS idx_rec_prompt_version ON recommendations(prompt_version);

-- ============================================
-- TRADES TABLE - Add reproducibility columns
-- ============================================

-- Position sizing reproducibility
ALTER TABLE trades ADD COLUMN IF NOT EXISTS position_sizing_inputs JSONB;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS position_sizing_outputs JSONB;

-- Execution reproducibility
ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_parameters JSONB;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS execution_timestamp TIMESTAMPTZ;

-- Create indexes for reproducibility queries
CREATE INDEX IF NOT EXISTS idx_trades_execution_timestamp ON trades(execution_timestamp);

-- ============================================
-- POSITION MONITOR LOGS TABLE - Add reproducibility columns
-- ============================================

-- Monitoring reproducibility
ALTER TABLE position_monitor_logs ADD COLUMN IF NOT EXISTS adjustment_calculation JSONB;
ALTER TABLE position_monitor_logs ADD COLUMN IF NOT EXISTS exit_check_details JSONB;

-- Create indexes for reproducibility queries
CREATE INDEX IF NOT EXISTS idx_monitor_logs_adjustment ON position_monitor_logs(adjustment_calculation);

