-- Migration: 001_initial_schema
-- Created: 2024-12-04
-- Description: Initial unified PostgreSQL schema for trading bot
-- 
-- Run with: psql $DATABASE_URL -f 001_initial_schema.sql
-- Or via Python migration runner

-- ============================================
-- 1. LIVE TRADING TABLES (from trading.db)
-- ============================================

CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt_name TEXT,
    prompt_version TEXT,
    min_confidence REAL,
    max_leverage INTEGER,
    symbols TEXT,
    timeframe TEXT,
    settings JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_instances_active ON instances(is_active);
CREATE INDEX IF NOT EXISTS idx_instances_name ON instances(name);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    instance_id TEXT REFERENCES instances(id),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running',
    stop_reason TEXT,
    timeframe TEXT,
    paper_trading BOOLEAN,
    min_confidence REAL,
    max_leverage INTEGER,
    symbols_watched TEXT,
    config_snapshot JSONB,
    total_cycles INTEGER DEFAULT 0,
    total_recommendations INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_instance ON runs(instance_id);

CREATE TABLE IF NOT EXISTS cycles (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    timeframe TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    boundary_time TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'running',
    skip_reason TEXT,
    charts_captured INTEGER DEFAULT 0,
    analyses_completed INTEGER DEFAULT 0,
    recommendations_generated INTEGER DEFAULT 0,
    trades_executed INTEGER DEFAULT 0,
    available_slots INTEGER,
    open_positions INTEGER,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cycles_run ON cycles(run_id);
CREATE INDEX IF NOT EXISTS idx_cycles_boundary ON cycles(boundary_time);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    cycle_id TEXT REFERENCES cycles(id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL NOT NULL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    reasoning TEXT,
    chart_path TEXT,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT,
    model_name TEXT DEFAULT 'gpt-4-vision-preview',
    raw_response TEXT,
    analyzed_at TIMESTAMPTZ NOT NULL,
    cycle_boundary TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rec_symbol ON recommendations(symbol);
CREATE INDEX IF NOT EXISTS idx_rec_cycle ON recommendations(cycle_id);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT REFERENCES recommendations(id),
    run_id TEXT REFERENCES runs(id),
    cycle_id TEXT REFERENCES cycles(id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    leverage INTEGER DEFAULT 1,
    order_id TEXT UNIQUE,
    order_link_id TEXT,
    "orderLinkId" TEXT,
    status TEXT DEFAULT 'pending',
    fill_price REAL,
    fill_quantity REAL,
    fill_time TIMESTAMPTZ,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    pnl_percent REAL,
    timeframe TEXT,
    prompt_name TEXT,
    confidence REAL,
    rr_ratio REAL,
    risk_reward_ratio REAL,
    dry_run BOOLEAN DEFAULT FALSE,
    submitted_at TIMESTAMPTZ,
    filled_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    state TEXT DEFAULT 'trade',
    avg_exit_price REAL,
    closed_size REAL,
    placed_by TEXT DEFAULT 'BOT',
    alteration_details TEXT,
    order_type TEXT DEFAULT 'Limit',
    last_tightened_milestone REAL,
    rejection_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id);

