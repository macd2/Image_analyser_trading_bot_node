-- Migration: 005_klines_storage
-- Created: 2024-12-04
-- Description: Klines/candle storage from candle_store.db

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

