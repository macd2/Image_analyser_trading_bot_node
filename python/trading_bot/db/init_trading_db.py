#!/usr/bin/env python3
"""
Initialize the new trading.db database with clean schema.
This replaces the fragmented bot.db, analysis_results.db, trade_states.db approach.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime, timezone

# Import centralized database client
from trading_bot.db.client import (
    get_connection,
    get_db_path,
    should_run_migrations,
    should_init_schema,
    should_seed_defaults
)


SCHEMA_SQL = """
-- 0. Instances (bot configurations - supports multiple bots with different settings)
CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY,           -- UUID for the instance
    name TEXT NOT NULL,            -- Human-readable name (e.g., "SOL-Aggressive")

    -- Configuration
    prompt_name TEXT,              -- Which prompt to use
    prompt_version TEXT,
    min_confidence REAL,
    max_leverage INTEGER,
    symbols TEXT,                  -- JSON array of symbols to trade
    timeframe TEXT,
    settings TEXT,                 -- JSON blob for other config

    -- Status
    is_active INTEGER DEFAULT 1,   -- Whether instance is enabled

    -- Timestamps
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_instances_active ON instances(is_active);
CREATE INDEX IF NOT EXISTS idx_instances_name ON instances(name);

-- 1. Runs (bot session tracking for audit trail)
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,           -- UUID for the run
    instance_id TEXT REFERENCES instances(id),  -- Links to parent instance

    -- Timing
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'stopped', 'crashed', 'completed')),
    stop_reason TEXT,

    -- Config snapshot at start (for reproducibility)
    timeframe TEXT,
    paper_trading INTEGER,
    min_confidence REAL,
    max_leverage INTEGER,
    symbols_watched TEXT,          -- JSON array of symbols being watched
    config_snapshot TEXT,          -- Full config JSON for complete reproducibility

    -- Aggregates (updated on cycle complete)
    total_cycles INTEGER DEFAULT 0,
    total_recommendations INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_instance ON runs(instance_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);

-- 1. Recommendations (analysis results)
CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    cycle_id TEXT REFERENCES cycles(id),  -- Links to parent cycle
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    recommendation TEXT NOT NULL CHECK (recommendation IN ('LONG', 'SHORT', 'HOLD')),
    confidence REAL NOT NULL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    reasoning TEXT,

    -- Audit fields
    chart_path TEXT,
    prompt_name TEXT NOT NULL,
    prompt_version TEXT,
    model_name TEXT DEFAULT 'gpt-4-vision-preview',
    raw_response TEXT,

    -- Timestamps
    analyzed_at TEXT NOT NULL,
    cycle_boundary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_rec_cycle ON recommendations(cycle_id);
CREATE INDEX IF NOT EXISTS idx_rec_symbol ON recommendations(symbol);
CREATE INDEX IF NOT EXISTS idx_rec_timeframe ON recommendations(timeframe);
CREATE INDEX IF NOT EXISTS idx_rec_boundary ON recommendations(cycle_boundary);
CREATE INDEX IF NOT EXISTS idx_rec_analyzed ON recommendations(analyzed_at);

-- 3. Trades (execution records)
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    recommendation_id TEXT REFERENCES recommendations(id),
    run_id TEXT REFERENCES runs(id),      -- Direct link to run for fast queries
    cycle_id TEXT REFERENCES cycles(id),  -- Direct link to cycle for fast queries

    -- Trade details
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('Buy', 'Sell')),
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    leverage INTEGER DEFAULT 1,

    -- Exchange data
    order_id TEXT,
    order_link_id TEXT,

    -- Status (updated by WebSocket)
    status TEXT DEFAULT 'pending' CHECK (status IN (
        'pending', 'submitted', 'new', 'partially_filled',
        'filled', 'cancelled', 'rejected', 'closed', 'error', 'paper_trade', 'failed'
    )),

    -- Fill data (from WebSocket execution stream)
    fill_price REAL,
    fill_quantity REAL,
    fill_time TEXT,

    -- Exit data
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,
    pnl_percent REAL,

    -- Audit
    timeframe TEXT,
    prompt_name TEXT,
    confidence REAL,
    rr_ratio REAL,
    dry_run INTEGER DEFAULT 0,
    rejection_reason TEXT,  -- Why trade was rejected (if status='rejected')

    -- Timestamps
    submitted_at TEXT,
    filled_at TEXT,
    closed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_order ON trades(order_id);
CREATE INDEX IF NOT EXISTS idx_trades_rec ON trades(recommendation_id);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id);

-- 3. Cycles (trading cycle audit trail)
CREATE TABLE IF NOT EXISTS cycles (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),  -- Links to parent run
    timeframe TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    boundary_time TEXT NOT NULL,

    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'skipped')),
    skip_reason TEXT,

    -- Metrics
    charts_captured INTEGER DEFAULT 0,
    analyses_completed INTEGER DEFAULT 0,
    recommendations_generated INTEGER DEFAULT 0,
    trades_executed INTEGER DEFAULT 0,

    -- State at cycle start
    available_slots INTEGER,
    open_positions INTEGER,

    -- Timestamps
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cycles_run ON cycles(run_id);
CREATE INDEX IF NOT EXISTS idx_cycles_timeframe ON cycles(timeframe);
CREATE INDEX IF NOT EXISTS idx_cycles_boundary ON cycles(boundary_time);
CREATE INDEX IF NOT EXISTS idx_cycles_status ON cycles(status);

-- 4. Executions (WebSocket execution log for audit)
-- Note: Config is now stored per-instance in instances.settings JSON column
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    trade_id TEXT REFERENCES trades(id),
    order_id TEXT NOT NULL,

    -- Execution details (from WebSocket)
    exec_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT,
    exec_price REAL NOT NULL,
    exec_qty REAL NOT NULL,
    exec_value REAL,
    exec_fee REAL,
    exec_pnl REAL,
    exec_type TEXT,
    is_maker INTEGER,

    -- Timestamp
    exec_time TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exec_order ON executions(order_id);
CREATE INDEX IF NOT EXISTS idx_exec_trade ON executions(trade_id);
CREATE INDEX IF NOT EXISTS idx_exec_symbol ON executions(symbol);

-- 6. Position snapshots (for historical tracking)
CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT,
    size REAL,
    entry_price REAL,
    mark_price REAL,
    unrealised_pnl REAL,
    take_profit REAL,
    stop_loss REAL,
    leverage TEXT,

    -- Snapshot metadata
    snapshot_reason TEXT,
    snapshot_time TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshot_symbol ON position_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_snapshot_time ON position_snapshots(snapshot_time);

-- Error log trail (WARNING, ERROR, CRITICAL, and INFO for monitor actions)
CREATE TABLE IF NOT EXISTS error_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('WARNING', 'ERROR', 'CRITICAL', 'INFO')),

    -- Correlation IDs
    run_id TEXT,
    cycle_id TEXT,
    trade_id TEXT,
    symbol TEXT,

    -- Error details
    component TEXT,           -- 'sourcer', 'analyzer', 'cycle', 'executor', 'position_monitor'
    event TEXT,               -- 'login_failed', 'capture_failed', 'analysis_error', 'sl_tightened', etc.
    message TEXT NOT NULL,

    -- Debug context (JSON)
    stack_trace TEXT,
    context TEXT,             -- JSON with relevant debugging data

    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_error_run ON error_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_error_cycle ON error_logs(cycle_id);
CREATE INDEX IF NOT EXISTS idx_error_level ON error_logs(level);
CREATE INDEX IF NOT EXISTS idx_error_timestamp ON error_logs(timestamp);
"""


def run_migrations(conn) -> None:
    """Run database migrations for existing databases BEFORE schema init."""
    # Skip migrations for PostgreSQL - schema is managed externally (Supabase)
    if not should_run_migrations():
        print("📦 PostgreSQL mode - skipping SQLite migrations")
        return

    cursor = conn.cursor()

    # Check if recommendations table exists first
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recommendations'")
    if cursor.fetchone():
        # Migration 1: Add cycle_id to recommendations if missing
        try:
            cursor.execute("SELECT cycle_id FROM recommendations LIMIT 1")
        except sqlite3.OperationalError:
            print("🔄 Migration: Adding cycle_id column to recommendations...")
            cursor.execute("ALTER TABLE recommendations ADD COLUMN cycle_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_rec_cycle ON recommendations(cycle_id)")
            conn.commit()
            print("✅ Migration complete: cycle_id added to recommendations")

    # Check if runs table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
    if cursor.fetchone():
        # Migration 2: Add instance_id to runs if missing
        try:
            cursor.execute("SELECT instance_id FROM runs LIMIT 1")
        except sqlite3.OperationalError:
            print("🔄 Migration: Adding instance_id column to runs...")
            cursor.execute("ALTER TABLE runs ADD COLUMN instance_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_instance ON runs(instance_id)")
            conn.commit()
            print("✅ Migration complete: instance_id added to runs")

    # Check if trades table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
    if cursor.fetchone():
        # Migration 3: Add run_id to trades if missing
        try:
            cursor.execute("SELECT run_id FROM trades LIMIT 1")
        except sqlite3.OperationalError:
            print("🔄 Migration: Adding run_id column to trades...")
            cursor.execute("ALTER TABLE trades ADD COLUMN run_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id)")
            conn.commit()
            print("✅ Migration complete: run_id added to trades")

        # Migration 4: Add cycle_id to trades if missing
        try:
            cursor.execute("SELECT cycle_id FROM trades LIMIT 1")
        except sqlite3.OperationalError:
            print("🔄 Migration: Adding cycle_id column to trades...")
            cursor.execute("ALTER TABLE trades ADD COLUMN cycle_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id)")
            conn.commit()
            print("✅ Migration complete: cycle_id added to trades")

    cursor.close()


def init_schema(conn) -> None:
    """Initialize the database schema."""
    # Run migrations FIRST for existing databases
    run_migrations(conn)

    # Skip schema init for PostgreSQL - schema is managed externally (Supabase)
    if not should_init_schema():
        print("📦 PostgreSQL mode - skipping schema init (managed by Supabase)")
        return

    # Then run CREATE TABLE IF NOT EXISTS statements (SQLite only)
    conn.executescript(SCHEMA_SQL)

    # Add advisor tables
    conn.executescript("""
    -- ============================================
    -- ADVISOR STRATEGIES
    -- ============================================
    CREATE TABLE IF NOT EXISTS advisor_strategies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        version TEXT NOT NULL,
        config_schema TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_advisor_strategies_name ON advisor_strategies(name);

    -- ============================================
    -- ADVISOR INSTANCE SETTINGS
    -- ============================================
    CREATE TABLE IF NOT EXISTS advisor_instance_settings (
        instance_id TEXT PRIMARY KEY REFERENCES instances(id) ON DELETE CASCADE,
        strategy_id TEXT REFERENCES advisor_strategies(id) ON DELETE SET NULL,
        config TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_advisor_instance_settings_strategy ON advisor_instance_settings(strategy_id);

    -- ============================================
    -- ADVISOR NODES (node-based architecture)
    -- ============================================
    CREATE TABLE IF NOT EXISTS advisor_nodes (
        id TEXT PRIMARY KEY,
        instance_id TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
        strategy_id TEXT NOT NULL REFERENCES advisor_strategies(id) ON DELETE CASCADE,
        config TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER DEFAULT 1,
        execution_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
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
        input_data TEXT,
        output_data TEXT,
        duration_ms INTEGER,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_advisor_logs_cycle ON advisor_logs(cycle_id);
    CREATE INDEX IF NOT EXISTS idx_advisor_logs_instance ON advisor_logs(instance_id);
    CREATE INDEX IF NOT EXISTS idx_advisor_logs_node ON advisor_logs(node_id);
    CREATE INDEX IF NOT EXISTS idx_advisor_logs_created ON advisor_logs(created_at);
    """)

    conn.commit()


def seed_default_config(conn) -> None:
    """Seed default config values if they don't exist."""
    # Skip for PostgreSQL - config is managed externally
    if not should_seed_defaults():
        print("📦 PostgreSQL mode - skipping default config seed")
        return

    defaults = [
        # Trading settings (symbols come from TradingView watchlist, not configured here)
        ("trading.timeframe", "1h", "string", "trading", "Trading timeframe"),
        ("trading.paper_trading", "true", "boolean", "trading", "Paper trading mode"),
        ("trading.auto_approve_trades", "true", "boolean", "trading", "Auto approve trades"),
        ("trading.min_confidence_threshold", "0.75", "number", "trading", "Minimum confidence score"),
        ("trading.min_rr", "1.5", "number", "trading", "Minimum risk-reward ratio"),
        ("trading.risk_percentage", "0.01", "number", "trading", "Risk per trade (1%)"),
        ("trading.max_loss_usd", "10.0", "number", "trading", "Maximum loss per trade USD"),
        ("trading.leverage", "2", "number", "trading", "Default leverage"),
        ("trading.max_concurrent_trades", "3", "number", "trading", "Maximum concurrent trades"),

        # Bybit settings
        ("bybit.use_testnet", "false", "boolean", "bybit", "Use testnet"),
        ("bybit.recv_window", "30000", "number", "bybit", "Receive window (ms)"),
        ("bybit.max_retries", "5", "number", "bybit", "Maximum API retries"),

        # OpenAI settings
        ("openai.model", "gpt-4.1-mini", "string", "openai", "OpenAI model"),
        ("openai.assistant_id", "asst_m11ds7XhdYfN7voO0pRvgbul", "string", "openai", "OpenAI assistant ID"),
    ]

    for key, value, type_, category, description in defaults:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO config (key, value, type, category, description)
                VALUES (?, ?, ?, ?, ?)
            """, (key, value, type_, category, description))
        except Exception:
            pass

    # Seed default advisor strategies
    try:
        conn.execute("""
            INSERT OR IGNORE INTO advisor_strategies (id, name, description, version, config_schema)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'alex_top_down',
            'Alex Top-Down Analysis',
            'Top-down analysis across timeframes with Area of Interest and Entry Signals',
            '1.0',
            '{"timeframes": {"type": "array", "items": {"type": "string"}, "default": ["1h", "4h", "1d"]}, "lookback_periods": {"type": "integer", "default": 20}, "indicators": {"type": "array", "items": {"type": "string"}, "default": ["RSI", "MACD", "EMA"]}}'
        ))

        conn.execute("""
            INSERT OR IGNORE INTO advisor_strategies (id, name, description, version, config_schema)
            VALUES (?, ?, ?, ?, ?)
        """, (
            'market_regime_check',
            'Market Regime Detection',
            'Higher timeframe bias, volume-validated candlestick patterns, market structure shift confirmation',
            '1.0',
            '{"timeframe": {"type": "string", "default": "4h"}, "volume_threshold": {"type": "number", "default": 1.5}, "pattern_lookback": {"type": "integer", "default": 10}}'
        ))
    except Exception as e:
        print(f"Warning: Failed to seed advisor strategies: {e}")

    conn.commit()


def init_database():
    """Initialize the database and return connection."""
    conn = get_connection()
    init_schema(conn)
    seed_default_config(conn)
    return conn


if __name__ == "__main__":
    print(f"Initializing trading.db at {get_db_path()}...")
    conn = init_database()
    print("✅ Schema created successfully!")
    
    # Verify tables
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"📊 Tables created: {tables}")
    conn.close()

