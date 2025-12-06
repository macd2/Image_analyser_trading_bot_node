import sqlite3
import logging
import sys
from typing import List, Dict, Any, Optional
from pathlib import Path

# Ensure the parent directory is in the path for imports
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

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
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to data/candle_store.db relative to project root (V2/prototype)
            db_path = str(Path(__file__).parent.parent.parent.parent / "data" / "candle_store.db")

        self.db_path = db_path
        self._ensure_database_exists()

    def _ensure_database_exists(self):
        """Create database and tables if they don't exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create klines_store table (renamed from klines_store)
            cursor.execute("""
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
                );
            """)

            # Create prompt_hash_mappings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prompt_hash_mappings (
                    prompt_hash TEXT PRIMARY KEY,
                    prompt_text TEXT NOT NULL,
                    timeframe TEXT,
                    symbol TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_timeframe ON klines_store (symbol, timeframe);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_start_time ON klines_store (start_time);
            """)

            conn.commit()
            logger.info(f"✅ Candle store database initialized at {self.db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(self.db_path)

    def get_latest_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Get the latest stored candle timestamp for a symbol/timeframe."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(start_time) FROM klines_store
                WHERE symbol = ? AND timeframe = ?
            """, (symbol, timeframe))
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_earliest_candle_timestamp(self, symbol: str, timeframe: str) -> Optional[int]:
        """Get the earliest stored candle timestamp for a symbol/timeframe."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(start_time) FROM klines_store
                WHERE symbol = ? AND timeframe = ?
            """, (symbol, timeframe))
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def insert_candles(self, candles: List[Dict[str, Any]], symbol: str, timeframe: str, category: str):
        """Insert candles into cache, skipping duplicates."""
        if not candles:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Sort candles by start_time ascending
            candles_sorted = sorted(candles, key=lambda x: x['start_time'])

            inserted_count = 0
            for candle in candles_sorted:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO klines_store
                        (symbol, timeframe, category, start_time, open_price, high_price,
                         low_price, close_price, volume, turnover)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
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
                    ))
                    if cursor.rowcount > 0:
                        inserted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to insert candle for {symbol} {timeframe}: {e}")

            conn.commit()
            logger.info(f"Inserted {inserted_count} new candles for {symbol} {timeframe}")

    def get_candles_after_timestamp(self, symbol: str, timeframe: str, start_timestamp: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get candles after a specific timestamp, ordered by start_time ASC."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM klines_store
                WHERE symbol = ? AND timeframe = ? AND start_time >= ?
                ORDER BY start_time ASC
                LIMIT ?
            """, (symbol, timeframe, start_timestamp, limit))

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_candle_count(self, symbol: str, timeframe: str) -> int:
        """Get total count of candles for a symbol/timeframe."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM klines_store
                WHERE symbol = ? AND timeframe = ?
            """, (symbol, timeframe))
            result = cursor.fetchone()
            return result[0] if result else 0

    def store_prompt_hash_mapping(self, prompt_hash: str, prompt_text: str, timeframe: Optional[str] = None, symbol: Optional[str] = None):
        """Store a prompt hash to prompt text mapping with optional metadata."""
        normalized_symbol = normalize_symbol(symbol) if symbol else None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO prompt_hash_mappings
                (prompt_hash, prompt_text, timeframe, symbol, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (prompt_hash, prompt_text, timeframe, normalized_symbol),
            )
            conn.commit()

    def _timeframe_to_ms(self, timeframe: str) -> int:
        mapping = {"1m":60000, "5m":300000, "15m":900000, "30m":1800000, "1h":3600000, "4h":14400000, "1d":86400000, "1w":604800000}
        return mapping.get(timeframe, 3600000)

    def get_candle_gaps(self, symbol: str, timeframe: str) -> List[Dict[str, int]]:
        """Detect gaps in klines_store for given symbol/timeframe.
        Returns a list of dicts: {"start_missing": ts_ms, "end_missing": ts_ms} inclusive bounds.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT start_time FROM klines_store
                WHERE symbol = ? AND timeframe = ?
                ORDER BY start_time ASC
                """,
                (symbol, timeframe),
            )
            rows = cursor.fetchall()
            if not rows:
                return []
            times = [r[0] for r in rows]

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prompt_text FROM prompt_hash_mappings
                WHERE prompt_hash = ?
            """, (prompt_hash,))
            result = cursor.fetchone()
            return result[0] if result else None

    def get_all_prompt_mappings(self) -> Dict[str, str]:
        """Get all prompt hash to text mappings."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT prompt_hash, prompt_text FROM prompt_hash_mappings
                ORDER BY created_at
            """)
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_prompt_metadata(self, prompt_hash: str) -> Optional[Dict[str, str]]:
        """Get metadata (timeframe, symbol) for a prompt hash."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timeframe, symbol FROM prompt_hash_mappings
                WHERE prompt_hash = ?
            """, (prompt_hash,))
            result = cursor.fetchone()
            if result:
                return {
                    'timeframe': result[0],
                    'symbol': result[1]
                }
            return None

    def get_available_symbols(self) -> List[str]:
        """Get all unique symbols available in the candle cache."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT symbol FROM klines_store
                ORDER BY symbol
            """)
            results = cursor.fetchall()
            return [row[0] for row in results]

    def get_available_timeframes(self, symbol: Optional[str] = None) -> List[str]:
        """Get all unique timeframes available in the candle cache, optionally filtered by symbol."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute("""
                    SELECT DISTINCT timeframe FROM klines_store
                    WHERE symbol = ?
                    ORDER BY timeframe
                """, (symbol,))
            else:
                cursor.execute("""
                    SELECT DISTINCT timeframe FROM klines_store
                    ORDER BY timeframe
                """)
            results = cursor.fetchall()
            return [row[0] for row in results]

    def get_candles_between_timestamps(self, symbol: str, timeframe: str,
                                      start_timestamp: int, end_timestamp: int,
                                      limit: int = 5000) -> List[Dict[str, Any]]:
        """Get candles between two timestamps, ordered by start_time ASC."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM klines_store
                WHERE symbol = ? AND timeframe = ?
                AND start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
                LIMIT ?
            """, (symbol, timeframe, start_timestamp, end_timestamp, limit))

            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_candle_date_range(self, symbol: str, timeframe: str) -> Optional[Dict[str, int]]:
        """Get the date range (earliest and latest timestamps) for a symbol/timeframe."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(start_time), MAX(start_time) FROM klines_store
                WHERE symbol = ? AND timeframe = ?
            """, (symbol, timeframe))
            result = cursor.fetchone()
            if result and result[0] and result[1]:
                return {
                    'earliest': result[0],
                    'latest': result[1]
                }
            return None
