-- Migration: 004_tournament_and_settings
-- Created: 2024-12-04
-- Description: Tournament tables (tourn_ prefix) and app settings from bot.db

CREATE TABLE IF NOT EXISTS tourn_tournaments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    model TEXT NOT NULL,
    elimination_pct INTEGER NOT NULL,
    images_phase_1 INTEGER NOT NULL,
    images_phase_2 INTEGER NOT NULL,
    images_phase_3 INTEGER NOT NULL,
    image_offset INTEGER DEFAULT 0,
    selection_strategy TEXT DEFAULT 'random',
    symbols_json JSONB NOT NULL,
    timeframes_json JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_sec REAL,
    winner_prompt_name TEXT,
    winner_win_rate REAL,
    winner_avg_pnl REAL,
    total_api_calls INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tourn_phases (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tourn_tournaments(id) ON DELETE CASCADE,
    phase_number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    images_per_prompt INTEGER NOT NULL,
    prompts_entering INTEGER NOT NULL,
    prompts_eliminated INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE(tournament_id, phase_number)
);

CREATE TABLE IF NOT EXISTS tourn_prompts (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tourn_tournaments(id) ON DELETE CASCADE,
    prompt_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    eliminated_in_phase INTEGER,
    final_rank INTEGER,
    total_trades INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,
    total_holds INTEGER DEFAULT 0,
    cumulative_pnl REAL DEFAULT 0,
    UNIQUE(tournament_id, prompt_name)
);

CREATE TABLE IF NOT EXISTS tourn_phase_results (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES tourn_phases(id) ON DELETE CASCADE,
    tournament_prompt_id INTEGER NOT NULL REFERENCES tourn_prompts(id) ON DELETE CASCADE,
    trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    holds INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    rank_in_phase INTEGER,
    eliminated BOOLEAN DEFAULT FALSE,
    UNIQUE(phase_id, tournament_prompt_id)
);

CREATE TABLE IF NOT EXISTS tourn_phase_images (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES tourn_phases(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    image_timestamp TIMESTAMPTZ,
    selection_order INTEGER NOT NULL,
    UNIQUE(phase_id, image_path)
);

CREATE TABLE IF NOT EXISTS tourn_analyses (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES tourn_phases(id) ON DELETE CASCADE,
    tournament_prompt_id INTEGER NOT NULL REFERENCES tourn_prompts(id) ON DELETE CASCADE,
    phase_image_id INTEGER NOT NULL REFERENCES tourn_phase_images(id) ON DELETE CASCADE,
    recommendation TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    outcome TEXT,
    pnl_pct REAL,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    raw_response TEXT,
    error_message TEXT,
    UNIQUE(phase_id, tournament_prompt_id, phase_image_id)
);

-- App settings
CREATE TABLE IF NOT EXISTS app_settings (
    id SERIAL PRIMARY KEY,
    instance_id TEXT NOT NULL UNIQUE,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_app_settings_instance ON app_settings(instance_id);

CREATE TABLE IF NOT EXISTS app_migrations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

