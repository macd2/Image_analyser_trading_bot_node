import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path

# Ensure the parent directory is in the path for imports
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

# Import centralized database client
from trading_bot.db.client import (
    get_connection as get_db_connection,
    query,
    execute,
    get_table_name,
    DB_TYPE,
    should_run_migrations
)

logger = logging.getLogger(__name__)

def normalize_symbol(symbol: str) -> str:
    """Normalize symbol by removing .P suffix if present."""
    if symbol and symbol.endswith('.P'):
        return symbol[:-2]  # Remove .P suffix
    return symbol

class CandleStoreDatabase:
    """Database utility for managing candle store operations.

    This is a permanent store for historical candles fetched from Bybit API.
    Candles are NEVER deleted - only added to ensure we build up historical data over time.

    Uses centralized database layer to support both SQLite and PostgreSQL.
    """

    def __init__(self, db_path: Optional[str] = None):
        # db_path is only used for SQLite mode (ignored for PostgreSQL)
        if db_path is None:
            # Default to data/candle_store.db relative to project root (V2/prototype)
            db_path = str(Path(__file__).parent.parent.parent.parent / "data" / "candle_store.db")

        self.db_path = db_path
        self._ensure_database_exists()

    def _ensure_database_exists(self):
        """Create database and tables if they don't exist.

        For SQLite: Creates tables in candle_store.db
        For PostgreSQL: Tables should already exist (managed by Supabase)
        """
        # Only run migrations for SQLite (PostgreSQL is managed by Supabase)
        if not should_run_migrations():
            logger.info("✅ Using PostgreSQL - skipping candle store migrations (managed by Supabase)")
            return

        # SQLite: Create tables
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = self.get_connection()
        try:
            # Create klines_store table
            execute(conn, """
                CREATE TABLE IF NOT EXISTS klines_store (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    category TEXT NOT NULL,
                    start_time INTEGER NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume REAL NOT NULL,
                    turnover REAL NOT NULL,
                    UNIQUE(symbol, timeframe, start_time)
                )
            """, ())

            # Create prompt_hash_mappings table
            execute(conn, """
                CREATE TABLE IF NOT EXISTS prompt_hash_mappings (
                    prompt_hash TEXT PRIMARY KEY,
                    prompt_text TEXT NOT NULL,
                    timeframe TEXT,
                    symbol TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """, ())

            # Create indexes
            execute(conn, """
                CREATE INDEX IF NOT EXISTS idx_symbol_timeframe ON klines_store (symbol, timeframe)
            """, ())
            execute(conn, """
                CREATE INDEX IF NOT EXISTS idx_start_time ON klines_store (start_time)
            """, ())

            conn.commit()
            logger.info(f"✅ Candle store database initialized at {self.db_path}")
        finally:
            conn.close()

    def get_connection(self):
        """Get database connection using centralized client.

        For SQLite: Returns connection to candle_store.db
        For PostgreSQL: Returns connection to main database (klines table)
        """
        if DB_TYPE == 'postgres':
            # Use centralized connection for PostgreSQL
            return get_db_connection()
        else:
            # For SQLite, use separate candle_store.db
            import sqlite3
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn

    def get_latest_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Get the latest stored candle timestamp for a symbol/timeframe."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT MAX(start_time) FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (symbol, timeframe))
            if results and results[0].get('MAX(start_time)'):
                return results[0]['MAX(start_time)']
            # Try lowercase column name for PostgreSQL
            if results and results[0].get('max'):
                return results[0]['max']
            return None
        finally:
            conn.close()

    def get_earliest_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Get the earliest stored candle timestamp for a symbol/timeframe."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT MIN(start_time) FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (symbol, timeframe))
            if results and results[0].get('MIN(start_time)'):
                return results[0]['MIN(start_time)']
            # Try lowercase column name for PostgreSQL
            if results and results[0].get('min'):
                return results[0]['min']
            return None
        finally:
            conn.close()

    def insert_candles(self, candles: List[Dict[str, Any]], symbol: str, timeframe: str, category: str):
        """Insert candles into cache, skipping duplicates."""
        if not candles:
            return

        table_name = get_table_name('klines_store')

        # Sort candles by start_time ascending
        candles_sorted = sorted(candles, key=lambda x: x['start_time'])

        conn = self.get_connection()
        try:
            inserted_count = 0
            for candle in candles_sorted:
                try:
                    # Use INSERT OR IGNORE for SQLite, ON CONFLICT DO NOTHING for PostgreSQL
                    if DB_TYPE == 'postgres':
                        sql = f"""
                            INSERT INTO {table_name}
                            (symbol, timeframe, category, start_time, open_price, high_price,
                             low_price, close_price, volume, turnover)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT (symbol, timeframe, start_time) DO NOTHING
                        """
                    else:
                        sql = f"""
                            INSERT OR IGNORE INTO {table_name}
                            (symbol, timeframe, category, start_time, open_price, high_price,
                             low_price, close_price, volume, turnover)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """

                    params = (
                        symbol,
                        timeframe,
                        category,
                        candle['start_time'],
                        candle['open_price'],
                        candle['high_price'],
                        candle['low_price'],
                        candle['close_price'],
                        candle['volume'],
                        candle['turnover']
                    )

                    execute(conn, sql, params)
                    # Note: rowcount may not be reliable across databases for INSERT OR IGNORE
                    inserted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to insert candle for {symbol} {timeframe}: {e}")

            conn.commit()
            logger.info(f"Inserted {inserted_count} new candles for {symbol} {timeframe}")
        finally:
            conn.close()

    def get_candles_after_timestamp(self, symbol: str, timeframe: str, start_timestamp: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get candles after a specific timestamp, ordered by start_time ASC."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT * FROM {table_name}
            WHERE symbol = ? AND timeframe = ? AND start_time >= ?
            ORDER BY start_time ASC
            LIMIT ?
        """
        conn = self.get_connection()
        try:
            return query(conn, sql, (symbol, timeframe, start_timestamp, limit))
        finally:
            conn.close()

    def get_candle_count(self, symbol: str, timeframe: str) -> int:
        """Get total count of candles for a symbol/timeframe."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT COUNT(*) FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (symbol, timeframe))
            if results and results[0].get('COUNT(*)'):
                return results[0]['COUNT(*)']
            # Try lowercase column name for PostgreSQL
            if results and results[0].get('count'):
                return results[0]['count']
            return 0
        finally:
            conn.close()

    def store_prompt_hash_mapping(self, prompt_hash: str, prompt_text: str, timeframe: Optional[str] = None, symbol: Optional[str] = None):
        """Store a prompt hash to prompt text mapping with optional metadata."""
        normalized_symbol = normalize_symbol(symbol) if symbol else None

        # Use INSERT OR REPLACE for SQLite, ON CONFLICT for PostgreSQL
        if DB_TYPE == 'postgres':
            sql = """
                INSERT INTO prompt_hash_mappings
                (prompt_hash, prompt_text, timeframe, symbol, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT (prompt_hash) DO UPDATE SET
                    prompt_text = EXCLUDED.prompt_text,
                    timeframe = EXCLUDED.timeframe,
                    symbol = EXCLUDED.symbol,
                    created_at = CURRENT_TIMESTAMP
            """
        else:
            sql = """
                INSERT OR REPLACE INTO prompt_hash_mappings
                (prompt_hash, prompt_text, timeframe, symbol, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """

        conn = self.get_connection()
        try:
            execute(conn, sql, (prompt_hash, prompt_text, timeframe, normalized_symbol))
            conn.commit()
        finally:
            conn.close()

    def _timeframe_to_ms(self, timeframe: str) -> int:
        mapping = {"1m":60000, "5m":300000, "15m":900000, "30m":1800000, "1h":3600000, "4h":14400000, "1d":86400000, "1w":604800000}
        return mapping.get(timeframe, 3600000)

    def get_candle_gaps(self, symbol: str, timeframe: str) -> List[Dict[str, int]]:
        """Detect gaps in klines_store for given symbol/timeframe.
        Returns a list of dicts: {"start_missing": ts_ms, "end_missing": ts_ms} inclusive bounds.
        """
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT start_time FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
            ORDER BY start_time ASC
        """

        conn = self.get_connection()
        try:
            rows = query(conn, sql, (symbol, timeframe))
            if not rows:
                return []
            times = [r['start_time'] for r in rows]
        finally:
            conn.close()

        interval = self._timeframe_to_ms(timeframe)
        gaps: List[Dict[str, int]] = []
        prev = times[0]
        for t in times[1:]:
            if t - prev > interval:
                gap_start = prev + interval
                gap_end = t - interval
                if gap_start <= gap_end:
                    gaps.append({"start_missing": gap_start, "end_missing": gap_end})
            prev = t
        return gaps

    def get_prompt_text_by_hash(self, prompt_hash: str) -> Optional[str]:
        """Get the prompt text for a given hash."""
        sql = """
            SELECT prompt_text FROM prompt_hash_mappings
            WHERE prompt_hash = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (prompt_hash,))
            return results[0]['prompt_text'] if results else None
        finally:
            conn.close()

    def get_all_prompt_mappings(self) -> Dict[str, str]:
        """Get all prompt hash to text mappings."""
        sql = """
            SELECT prompt_hash, prompt_text FROM prompt_hash_mappings
            ORDER BY created_at
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, ())
            return {row['prompt_hash']: row['prompt_text'] for row in results}
        finally:
            conn.close()

    def get_prompt_metadata(self, prompt_hash: str) -> Optional[Dict[str, str]]:
        """Get metadata (timeframe, symbol) for a prompt hash."""
        sql = """
            SELECT timeframe, symbol FROM prompt_hash_mappings
            WHERE prompt_hash = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (prompt_hash,))
            if results:
                return {
                    'timeframe': results[0]['timeframe'],
                    'symbol': results[0]['symbol']
                }
            return None
        finally:
            conn.close()

    def get_available_symbols(self) -> List[str]:
        """Get all unique symbols available in the candle cache."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT DISTINCT symbol FROM {table_name}
            ORDER BY symbol
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, ())
            return [row['symbol'] for row in results]
        finally:
            conn.close()

    def get_available_timeframes(self, symbol: Optional[str] = None) -> List[str]:
        """Get all unique timeframes available in the candle cache, optionally filtered by symbol."""
        table_name = get_table_name('klines_store')

        if symbol:
            sql = f"""
                SELECT DISTINCT timeframe FROM {table_name}
                WHERE symbol = ?
                ORDER BY timeframe
            """
            params = (symbol,)
        else:
            sql = f"""
                SELECT DISTINCT timeframe FROM {table_name}
                ORDER BY timeframe
            """
            params = ()

        conn = self.get_connection()
        try:
            results = query(conn, sql, params)
            return [row['timeframe'] for row in results]
        finally:
            conn.close()

    def get_candles_between_timestamps(self, symbol: str, timeframe: str,
                                      start_timestamp: int, end_timestamp: int,
                                      limit: int = 5000) -> List[Dict[str, Any]]:
        """Get candles between two timestamps, ordered by start_time ASC."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT * FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
            AND start_time >= ? AND start_time <= ?
            ORDER BY start_time ASC
            LIMIT ?
        """
        conn = self.get_connection()
        try:
            return query(conn, sql, (symbol, timeframe, start_timestamp, end_timestamp, limit))
        finally:
            conn.close()

    def get_candle_date_range(self, symbol: str, timeframe: str) -> Optional[Dict[str, int]]:
        """Get the date range (earliest and latest timestamps) for a symbol/timeframe."""
        table_name = get_table_name('klines_store')
        sql = f"""
            SELECT MIN(start_time), MAX(start_time) FROM {table_name}
            WHERE symbol = ? AND timeframe = ?
        """
        conn = self.get_connection()
        try:
            results = query(conn, sql, (symbol, timeframe))
            if results:
                # Handle different column name formats
                min_val = results[0].get('MIN(start_time)') or results[0].get('min')
                max_val = results[0].get('MAX(start_time)') or results[0].get('max')
                if min_val and max_val:
                    return {
                        'earliest': min_val,
                        'latest': max_val
                    }
            return None
        finally:
            conn.close()
