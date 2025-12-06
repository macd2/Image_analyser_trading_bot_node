-- Migration: 002_remaining_tables
-- Created: 2024-12-04
-- Description: Executions, sessions, error_logs, and other trading tables

CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    trade_id TEXT REFERENCES trades(id),
    order_id TEXT NOT NULL,
    exec_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT,
    exec_price REAL NOT NULL,
    exec_qty REAL NOT NULL,
    exec_value REAL,
    exec_fee REAL,
    exec_pnl REAL,
    exec_type TEXT,
    is_maker BOOLEAN,
    exec_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_exec_trade ON executions(trade_id);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT,
    size REAL,
    entry_price REAL,
    mark_price REAL,
    unrealised_pnl REAL,
    take_profit REAL,
    stop_loss REAL,
    leverage TEXT,
    snapshot_reason TEXT,
    snapshot_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    encrypted_data TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_valid BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS bot_actions (
    id TEXT PRIMARY KEY,
    cycle_id TEXT,
    action_type TEXT NOT NULL,
    action_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_logs (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    level TEXT NOT NULL,
    run_id TEXT,
    cycle_id TEXT,
    trade_id TEXT,
    symbol TEXT,
    component TEXT,
    event TEXT,
    message TEXT NOT NULL,
    stack_trace TEXT,
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_error_run ON error_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_error_level ON error_logs(level);

CREATE TABLE IF NOT EXISTS analysis_results (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL NOT NULL,
    summary TEXT,
    evidence TEXT,
    support_level REAL,
    resistance_level REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    direction TEXT,
    rr REAL,
    risk_factors JSONB,
    analysis_data JSONB,
    analysis_prompt TEXT,
    timestamp TIMESTAMPTZ,
    image_path TEXT,
    market_condition TEXT,
    market_direction TEXT,
    prompt_id TEXT,
    market_data JSONB
);
CREATE INDEX IF NOT EXISTS idx_ar_symbol_tf ON analysis_results(symbol, timeframe);

CREATE TABLE IF NOT EXISTS latest_recommendations (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence REAL NOT NULL,
    summary TEXT,
    support_level REAL,
    resistance_level REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    direction TEXT,
    rr REAL,
    risk_factors JSONB,
    analysis_data JSONB,
    timestamp TIMESTAMPTZ,
    image_path TEXT,
    market_condition TEXT,
    market_direction TEXT,
    prompt_id TEXT,
    market_data JSONB
);

