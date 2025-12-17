-- ===========================================
-- Migration 001: Tournament System Schema
-- Purpose: Find best performing prompt efficiently
-- ===========================================

-- Tournaments: Each tournament run to find the best prompt
CREATE TABLE IF NOT EXISTS tournaments (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, cancelled
    
    -- Configuration
    model TEXT NOT NULL,                     -- AI model used (gpt-4-vision, claude-3, etc.)
    elimination_pct INTEGER NOT NULL,        -- % of prompts eliminated each phase (e.g., 50)
    images_phase_1 INTEGER NOT NULL,         -- Images per prompt in phase 1
    images_phase_2 INTEGER NOT NULL,         -- Images per prompt in phase 2  
    images_phase_3 INTEGER NOT NULL,         -- Images per prompt in phase 3
    image_offset INTEGER DEFAULT 0,          -- Skip N most recent images
    selection_strategy TEXT DEFAULT 'random', -- random or sequential
    
    -- Symbols & Timeframes (JSON arrays)
    symbols_json TEXT NOT NULL,
    timeframes_json TEXT,
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_sec REAL,
    
    -- Results
    winner_prompt_name TEXT,
    winner_win_rate REAL,
    winner_avg_pnl REAL,
    total_api_calls INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tournament Phases: Each elimination round
CREATE TABLE IF NOT EXISTS tournament_phases (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    phase_number INTEGER NOT NULL,           -- 1, 2, 3, ...
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed
    
    -- Configuration for this phase
    images_per_prompt INTEGER NOT NULL,
    prompts_entering INTEGER NOT NULL,       -- How many prompts started this phase
    prompts_eliminated INTEGER DEFAULT 0,    -- How many were eliminated
    
    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    UNIQUE(tournament_id, phase_number)
);

-- Tournament Prompts: Track each prompt's journey through tournament
CREATE TABLE IF NOT EXISTS tournament_prompts (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
    prompt_name TEXT NOT NULL,
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'active',   -- active, eliminated, winner
    eliminated_in_phase INTEGER,             -- Phase number where eliminated (null if still active)
    final_rank INTEGER,                      -- Final ranking (1 = winner)
    
    -- Aggregate stats across all phases
    total_trades INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,
    total_holds INTEGER DEFAULT 0,
    cumulative_pnl REAL DEFAULT 0,
    
    UNIQUE(tournament_id, prompt_name)
);

-- Phase Results: Per-prompt performance in each phase
CREATE TABLE IF NOT EXISTS phase_results (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES tournament_phases(id) ON DELETE CASCADE,
    tournament_prompt_id INTEGER NOT NULL REFERENCES tournament_prompts(id) ON DELETE CASCADE,
    
    -- Performance metrics
    trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    holds INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_pnl REAL DEFAULT 0,
    
    -- Ranking in this phase
    rank_in_phase INTEGER,
    eliminated BOOLEAN DEFAULT FALSE,
    
    UNIQUE(phase_id, tournament_prompt_id)
);

-- Phase Images: Which images were used (for reproducibility)
CREATE TABLE IF NOT EXISTS phase_images (
    id SERIAL PRIMARY KEY,
    phase_id INTEGER NOT NULL REFERENCES tournament_phases(id) ON DELETE CASCADE,
    image_path TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    image_timestamp TIMESTAMP,
    selection_order INTEGER NOT NULL,
    
    UNIQUE(phase_id, image_path)
);

-- Individual Analyses: Each prompt's analysis of each image
CREATE TABLE IF NOT EXISTS tournament_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES tournament_phases(id) ON DELETE CASCADE,
    tournament_prompt_id INTEGER NOT NULL REFERENCES tournament_prompts(id) ON DELETE CASCADE,
    phase_image_id INTEGER NOT NULL REFERENCES phase_images(id) ON DELETE CASCADE,
    
    -- Analysis result
    recommendation TEXT,                     -- BUY, SELL, HOLD
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    
    -- Trade simulation result
    outcome TEXT,                            -- WIN, LOSS, EXPIRED, null for HOLD
    pnl_pct REAL,
    
    -- Timing & debug
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_response TEXT,
    error_message TEXT,
    
    UNIQUE(phase_id, tournament_prompt_id, phase_image_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tournaments_status ON tournaments(status);
CREATE INDEX IF NOT EXISTS idx_phases_tournament ON tournament_phases(tournament_id);
CREATE INDEX IF NOT EXISTS idx_prompts_tournament ON tournament_prompts(tournament_id);
CREATE INDEX IF NOT EXISTS idx_prompts_status ON tournament_prompts(status);
CREATE INDEX IF NOT EXISTS idx_results_phase ON phase_results(phase_id);
CREATE INDEX IF NOT EXISTS idx_analyses_phase ON tournament_analyses(phase_id);

