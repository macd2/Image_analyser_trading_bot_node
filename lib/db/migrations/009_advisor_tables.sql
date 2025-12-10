-- Migration: 009_advisor_tables
-- Created: 2025-12-09
-- Description: Add advisor service tables for technical analysis strategies and node-based architecture

-- ============================================
-- ADVISOR STRATEGIES
-- ============================================
CREATE TABLE IF NOT EXISTS advisor_strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    version TEXT NOT NULL,
    config_schema JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_advisor_strategies_name ON advisor_strategies(name);

-- ============================================
-- ADVISOR INSTANCE SETTINGS
-- ============================================
CREATE TABLE IF NOT EXISTS advisor_instance_settings (
    instance_id TEXT PRIMARY KEY REFERENCES instances(id) ON DELETE CASCADE,
    strategy_id TEXT REFERENCES advisor_strategies(id) ON DELETE SET NULL,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_advisor_instance_settings_strategy ON advisor_instance_settings(strategy_id);

-- ============================================
-- ADVISOR NODES (node-based architecture)
-- ============================================
CREATE TABLE IF NOT EXISTS advisor_nodes (
    id TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    strategy_id TEXT NOT NULL REFERENCES advisor_strategies(id) ON DELETE CASCADE,
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    execution_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_advisor_nodes_instance ON advisor_nodes(instance_id);
CREATE INDEX IF NOT EXISTS idx_advisor_nodes_strategy ON advisor_nodes(strategy_id);
CREATE INDEX IF NOT EXISTS idx_advisor_nodes_enabled ON advisor_nodes(enabled);

-- ============================================
-- ADVISOR LOGS (traceability)
-- ============================================
CREATE TABLE IF NOT EXISTS advisor_logs (
    id TEXT PRIMARY KEY,
    cycle_id TEXT REFERENCES cycles(id) ON DELETE SET NULL,
    instance_id TEXT REFERENCES instances(id) ON DELETE SET NULL,
    node_id TEXT REFERENCES advisor_nodes(id) ON DELETE SET NULL,
    operation TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_advisor_logs_cycle ON advisor_logs(cycle_id);
CREATE INDEX IF NOT EXISTS idx_advisor_logs_instance ON advisor_logs(instance_id);
CREATE INDEX IF NOT EXISTS idx_advisor_logs_node ON advisor_logs(node_id);
CREATE INDEX IF NOT EXISTS idx_advisor_logs_created ON advisor_logs(created_at);

-- ============================================
-- INSERT DEFAULT STRATEGIES
-- ============================================
INSERT INTO advisor_strategies (id, name, description, version, config_schema) VALUES
('alex_top_down', 'Alex Top-Down Analysis', 'Top-down analysis across timeframes with Area of Interest and Entry Signals', '1.0', '{"timeframes": {"type": "array", "items": {"type": "string"}, "default": ["1h", "4h", "1d"]}, "lookback_periods": {"type": "integer", "default": 20}, "indicators": {"type": "array", "items": {"type": "string"}, "default": ["RSI", "MACD", "EMA"]}}')
ON CONFLICT (id) DO NOTHING;

INSERT INTO advisor_strategies (id, name, description, version, config_schema) VALUES
('market_regime_check', 'Market Regime Detection', 'Higher timeframe bias, volume-validated candlestick patterns, market structure shift confirmation', '1.0', '{"timeframe": {"type": "string", "default": "4h"}, "volume_threshold": {"type": "number", "default": 1.5}, "pattern_lookback": {"type": "integer", "default": 10}}')
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- UPDATE INSTANCES SETTINGS SCHEMA (optional)
-- ============================================
-- Note: Advisor configuration can be stored in instances.settings JSONB field.
-- No schema change needed.