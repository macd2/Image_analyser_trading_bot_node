-- ============================================
-- UNIFIED POSTGRESQL SCHEMA FOR TRADING BOT
-- ============================================
-- Consolidates: trading.db, bot.db, backtests.db, candle_store.db
--
-- Table prefixes to avoid naming conflicts:
--   (none)     = live trading tables (from trading.db)
--   bt_        = backtest tables (from backtests.db)
--   tourn_     = tournament tables (from bot.db)
--   app_       = app settings (from bot.db)
-- ============================================

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

CREATE TABLE IF NOT EXISTS sl_adjustments (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL REFERENCES recommendations(id),

    -- Original values from recommendation
    original_stop_loss REAL,

    -- Adjusted value
    adjusted_stop_loss REAL NOT NULL,

    -- Adjustment details
    adjustment_type TEXT NOT NULL,
    adjustment_value REAL NOT NULL,
    reason TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sl_adj_rec ON sl_adjustments(recommendation_id);

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


-- ============================================
-- 2. BACKTEST TABLES (from backtests.db) - bt_ prefix
-- ============================================

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


-- ============================================
-- 3. TOURNAMENT TABLES (from bot.db) - tourn_ prefix
-- ============================================

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

-- ============================================
-- 4. APP SETTINGS (from bot.db) - app_ prefix
-- ============================================

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

-- ============================================
-- 5. CANDLE STORE (from candle_store.db)
-- ============================================

CREATE TABLE IF NOT EXISTS klines (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    category TEXT NOT NULL,
    start_time BIGINT NOT NULL,
    open_price REAL NOT NULL,
    high_price REAL NOT NULL,
    low_price REAL NOT NULL,
    close_price REAL NOT NULL,
    volume REAL NOT NULL,
    turnover REAL NOT NULL,
    UNIQUE(symbol, timeframe, start_time)
);
CREATE INDEX IF NOT EXISTS idx_klines_symbol_tf ON klines(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_klines_time ON klines(start_time);

CREATE TABLE IF NOT EXISTS prompt_hash_mappings (
    prompt_hash TEXT PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    timeframe TEXT,
    symbol TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);