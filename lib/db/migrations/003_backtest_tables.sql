-- Migration: 003_backtest_tables
-- Created: 2024-12-04
-- Description: Backtest tables (bt_ prefix) from backtests.db

CREATE TABLE IF NOT EXISTS bt_runs (
    id SERIAL PRIMARY KEY,
    run_signature TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_sec REAL,
    charts_dir TEXT,
    selection_strategy TEXT,
    num_images INTEGER,
    prompts_json JSONB,
    symbols_json JSONB
);

CREATE TABLE IF NOT EXISTS bt_run_images (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES bt_runs(id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    image_path TEXT NOT NULL,
    selection_order INTEGER NOT NULL,
    UNIQUE(run_id, image_path)
);
CREATE INDEX IF NOT EXISTS idx_bt_images_run ON bt_run_images(run_id);

CREATE TABLE IF NOT EXISTS bt_analyses (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES bt_runs(id),
    prompt_name TEXT NOT NULL,
    prompt_version TEXT,
    prompt_hash TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    image_path TEXT NOT NULL,
    recommendation TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    rr_ratio REAL,
    status TEXT,
    raw_response TEXT,
    rationale TEXT,
    error_message TEXT,
    assistant_id TEXT,
    assistant_model TEXT,
    UNIQUE(run_id, prompt_name, image_path)
);
CREATE INDEX IF NOT EXISTS idx_bt_analyses_run ON bt_analyses(run_id, prompt_name);

CREATE TABLE IF NOT EXISTS bt_trades (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES bt_runs(id),
    prompt_name TEXT NOT NULL,
    prompt_version TEXT,
    prompt_hash TEXT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    confidence REAL,
    rr_ratio REAL,
    outcome TEXT,
    duration_candles INTEGER,
    achieved_rr REAL,
    exit_price REAL,
    exit_candle_index INTEGER,
    entry_candle_index INTEGER,
    mfe_price REAL,
    mae_price REAL,
    mfe_percent REAL,
    mae_percent REAL,
    mfe_r REAL,
    mae_r REAL,
    realized_pnl_price REAL,
    realized_pnl_percent REAL,
    image_path TEXT NOT NULL,
    UNIQUE(run_id, prompt_name, image_path)
);
CREATE INDEX IF NOT EXISTS idx_bt_trades_run ON bt_trades(run_id, prompt_name);
CREATE INDEX IF NOT EXISTS idx_bt_trades_outcome ON bt_trades(outcome);

CREATE TABLE IF NOT EXISTS bt_summaries (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES bt_runs(id),
    prompt_name TEXT NOT NULL,
    total_trades INTEGER,
    wins INTEGER,
    losses INTEGER,
    expired INTEGER,
    win_rate REAL,
    profit_factor REAL,
    expectancy REAL,
    avg_rr REAL,
    avg_confidence REAL,
    avg_duration REAL,
    UNIQUE(run_id, prompt_name)
);

CREATE TABLE IF NOT EXISTS bt_tournament_runs (
    id SERIAL PRIMARY KEY,
    tournament_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT,
    random_seed INTEGER,
    config_json JSONB,
    phase_details_json JSONB,
    result_json JSONB,
    winner TEXT,
    win_rate REAL,
    avg_pnl REAL,
    total_api_calls INTEGER,
    duration_sec REAL
);

