#!/usr/bin/env python3
"""
Migrate SQLite backtests.db from INTEGER ids to TEXT UUIDs.
SQLite doesn't support ALTER COLUMN, so we recreate tables.
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent.parent / "data" / "backtests.db"
BACKUP_PATH = DB_PATH.with_suffix('.db.backup_before_uuid')

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return
    
    # Backup first
    print(f"Backing up to {BACKUP_PATH}...")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    
    print("Migrating runs table to TEXT id...")
    
    # 1. Rename old table
    c.execute("ALTER TABLE runs RENAME TO runs_old")
    
    # 2. Create new table with TEXT id
    c.execute("""
        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            run_signature TEXT NOT NULL UNIQUE,
            started_at TEXT,
            finished_at TEXT,
            duration_sec REAL,
            charts_dir TEXT,
            selection_strategy TEXT,
            num_images INTEGER,
            prompts_json TEXT,
            symbols_json TEXT
        )
    """)
    
    # 3. Copy data with converted IDs
    c.execute("""
        INSERT INTO runs (id, run_signature, started_at, finished_at, duration_sec, 
                          charts_dir, selection_strategy, num_images, prompts_json, symbols_json)
        SELECT 'bt_' || CAST(strftime('%s', COALESCE(started_at, datetime('now'))) AS TEXT) || '_' || CAST(id AS TEXT),
               run_signature, started_at, finished_at, duration_sec,
               charts_dir, selection_strategy, num_images, prompts_json, symbols_json
        FROM runs_old
    """)
    
    # 4. Create mapping for FK updates
    c.execute("""
        CREATE TEMP TABLE id_mapping AS
        SELECT old.id as old_id, 
               'bt_' || CAST(strftime('%s', COALESCE(old.started_at, datetime('now'))) AS TEXT) || '_' || CAST(old.id AS TEXT) as new_id
        FROM runs_old old
    """)
    
    print("Migrating run_images...")
    c.execute("ALTER TABLE run_images RENAME TO run_images_old")
    c.execute("""
        CREATE TABLE run_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            timestamp TEXT,
            image_path TEXT NOT NULL,
            selection_order INTEGER,
            UNIQUE(run_id, image_path),
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    """)
    c.execute("""
        INSERT INTO run_images (run_id, symbol, timeframe, timestamp, image_path, selection_order)
        SELECT m.new_id, ri.symbol, ri.timeframe, ri.timestamp, ri.image_path, ri.selection_order
        FROM run_images_old ri
        JOIN id_mapping m ON ri.run_id = m.old_id
    """)
    
    print("Migrating analyses...")
    c.execute("ALTER TABLE analyses RENAME TO analyses_old")
    c.execute("""
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            prompt_name TEXT, prompt_version TEXT, prompt_hash TEXT,
            symbol TEXT, timeframe TEXT, timestamp TEXT, image_path TEXT,
            recommendation TEXT, confidence REAL, entry_price REAL, stop_loss REAL, 
            take_profit REAL, rr_ratio REAL, status TEXT, raw_response TEXT, 
            rationale TEXT, error_message TEXT, assistant_id TEXT, assistant_model TEXT,
            UNIQUE(run_id, prompt_name, image_path),
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    """)
    c.execute("""
        INSERT INTO analyses (run_id, prompt_name, prompt_version, prompt_hash, symbol, timeframe, 
                              timestamp, image_path, recommendation, confidence, entry_price, stop_loss, 
                              take_profit, rr_ratio, status, raw_response, rationale, error_message, 
                              assistant_id, assistant_model)
        SELECT m.new_id, a.prompt_name, a.prompt_version, a.prompt_hash, a.symbol, a.timeframe,
               a.timestamp, a.image_path, a.recommendation, a.confidence, a.entry_price, a.stop_loss,
               a.take_profit, a.rr_ratio, a.status, a.raw_response, a.rationale, a.error_message,
               a.assistant_id, a.assistant_model
        FROM analyses_old a
        LEFT JOIN id_mapping m ON a.run_id = m.old_id
        WHERE m.new_id IS NOT NULL
    """)
    
    print("Migrating trades...")
    c.execute("ALTER TABLE trades RENAME TO trades_old")
    c.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            prompt_name TEXT NOT NULL, prompt_version TEXT, prompt_hash TEXT,
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL, timestamp TEXT NOT NULL,
            direction TEXT NOT NULL, entry_price REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL,
            confidence REAL, rr_ratio REAL, outcome TEXT, duration_candles INTEGER,
            achieved_rr REAL, exit_price REAL, exit_candle_index INTEGER, entry_candle_index INTEGER,
            mfe_price REAL, mae_price REAL, mfe_percent REAL, mae_percent REAL,
            mfe_r REAL, mae_r REAL, image_path TEXT NOT NULL,
            realized_pnl_price REAL, realized_pnl_percent REAL,
            UNIQUE(run_id, prompt_name, image_path),
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    """)
    c.execute("""
        INSERT INTO trades (run_id, prompt_name, prompt_version, prompt_hash, symbol, timeframe,
                            timestamp, direction, entry_price, stop_loss, take_profit,
                            confidence, rr_ratio, outcome, duration_candles, achieved_rr,
                            exit_price, exit_candle_index, entry_candle_index,
                            mfe_price, mae_price, mfe_percent, mae_percent, mfe_r, mae_r,
                            image_path, realized_pnl_price, realized_pnl_percent)
        SELECT m.new_id, t.prompt_name, t.prompt_version, t.prompt_hash, t.symbol, t.timeframe,
               t.timestamp, t.direction, t.entry_price, t.stop_loss, t.take_profit,
               t.confidence, t.rr_ratio, t.outcome, t.duration_candles, t.achieved_rr,
               t.exit_price, t.exit_candle_index, t.entry_candle_index,
               t.mfe_price, t.mae_price, t.mfe_percent, t.mae_percent, t.mfe_r, t.mae_r,
               t.image_path, t.realized_pnl_price, t.realized_pnl_percent
        FROM trades_old t
        LEFT JOIN id_mapping m ON t.run_id = m.old_id
        WHERE m.new_id IS NOT NULL
    """)
    
    print("Migrating summaries...")
    c.execute("ALTER TABLE summaries RENAME TO summaries_old")
    c.execute("""
        CREATE TABLE summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            prompt_name TEXT NOT NULL,
            total_trades INTEGER, wins INTEGER, losses INTEGER, expired INTEGER,
            win_rate REAL, profit_factor REAL, expectancy REAL, avg_rr REAL,
            avg_confidence REAL, avg_duration REAL,
            UNIQUE(run_id, prompt_name),
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    """)
    c.execute("""
        INSERT INTO summaries (run_id, prompt_name, total_trades, wins, losses, expired,
                               win_rate, profit_factor, expectancy, avg_rr, avg_confidence, avg_duration)
        SELECT m.new_id, s.prompt_name, s.total_trades, s.wins, s.losses, s.expired,
               s.win_rate, s.profit_factor, s.expectancy, s.avg_rr, s.avg_confidence, s.avg_duration
        FROM summaries_old s
        LEFT JOIN id_mapping m ON s.run_id = m.old_id
        WHERE m.new_id IS NOT NULL
    """)

    # Drop old tables
    print("Cleaning up old tables...")
    c.execute("DROP TABLE runs_old")
    c.execute("DROP TABLE run_images_old")
    c.execute("DROP TABLE analyses_old")
    c.execute("DROP TABLE trades_old")
    c.execute("DROP TABLE summaries_old")

    conn.commit()

    # Verify
    c.execute("SELECT id FROM runs LIMIT 3")
    rows = c.fetchall()
    print(f"\nMigration complete! Sample IDs:")
    for r in rows:
        print(f"  {r[0]}")

    conn.close()
    print("\n✅ SQLite UUID migration successful!")

if __name__ == "__main__":
    migrate()

