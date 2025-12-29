"""
Database abstraction layer for Python

Supports both SQLite and PostgreSQL based on DB_TYPE env var.
This is the centralized database client that all Python code should use.

Usage:
    from trading_bot.db.client import get_connection, execute, query
    
    # Get a connection (auto-detects SQLite or PostgreSQL)
    conn = get_connection()
    
    # Execute a query (handles parameter placeholders automatically)
    execute(conn, "INSERT INTO trades (id, symbol) VALUES (?, ?)", ("123", "BTCUSDT"))
    
    # Query data
    rows = query(conn, "SELECT * FROM trades WHERE symbol = ?", ("BTCUSDT",))
"""

import os
import sqlite3
import time
from pathlib import Path
from typing import Any, List, Tuple, Optional, Union
from collections.abc import Mapping
import threading

# Database configuration
DB_TYPE = os.getenv('DB_TYPE', 'postgres')
DATABASE_URL = os.getenv('DATABASE_URL', '')

# PostgreSQL connection pool (singleton)
_pg_pool = None
_pg_pool_lock = threading.Lock()

# Unified data folder at project root: ./data/
# Path resolution: client.py -> db -> trading_bot -> python -> PROJECT_ROOT -> data
DB_DIR = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH = os.getenv('TRADING_DB_PATH', str(DB_DIR / "trading.db"))
if not Path(DB_PATH).is_absolute():
    # If relative path from env, resolve relative to project root
    DB_PATH = Path(__file__).parent.parent.parent.parent / DB_PATH
else:
    DB_PATH = Path(DB_PATH)

# Backtest database path (SQLite only - for PostgreSQL, uses same connection)
BACKTEST_DB_PATH = os.getenv('DATABASE_PATH', str(DB_DIR / "backtests.db"))


class UnifiedRow:
    """
    Unified row wrapper that supports both index and key access.
    Works consistently for both SQLite (sqlite3.Row) and PostgreSQL (RealDictRow).

    This allows code to use either row[0] or row['column_name'] syntax.
    """
    def __init__(self, row):
        self._row = row
        # Convert to dict for consistent access
        # Handle sqlite3.Row (has keys() method but is not a Mapping)
        if hasattr(row, 'keys') and callable(row.keys):
            # sqlite3.Row or dict-like object
            self._dict = {key: row[key] for key in row.keys()}
            # Convert values to tuple (not keys!) for index access
            self._tuple = tuple(row[key] for key in row.keys())
        elif isinstance(row, Mapping):
            self._dict = dict(row)
            self._tuple = tuple(row.values())
        else:
            # Fallback for tuple/list
            self._dict = {}
            self._tuple = tuple(row) if not isinstance(row, tuple) else row

    def __getitem__(self, key):
        """Support both index and key access."""
        if isinstance(key, int):
            # Index access: row[0], row[1], etc.
            if hasattr(self, '_tuple'):
                return self._tuple[key]
            # Convert dict to tuple for index access
            return list(self._dict.values())[key]
        else:
            # Key access: row['column_name']
            return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def get(self, key, default=None):
        """Dict-like get method."""
        return self._dict.get(key, default)

    def keys(self):
        """Return column names."""
        return self._dict.keys()

    def values(self):
        """Return column values."""
        return self._dict.values()

    def items(self):
        """Return (column, value) pairs."""
        return self._dict.items()

    def __repr__(self):
        return f"UnifiedRow({self._dict})"

    def __bool__(self):
        """Allow truthiness check."""
        return bool(self._dict)


def convert_numpy_types(params: Union[Tuple, List]) -> Union[Tuple, List]:
    """
    Convert numpy types to native Python types for database compatibility.

    Handles:
    - np.float64, np.float32 → float
    - np.int64, np.int32, np.int16, np.int8 → int
    - np.bool_ → bool
    - np.ndarray → list
    - Nested tuples/lists recursively

    Args:
        params: Query parameters (tuple or list)

    Returns:
        Parameters with numpy types converted to Python types
    """
    try:
        import numpy as np

        def convert_value(val):
            """Recursively convert a single value."""
            if val is None:
                return val

            # Handle numpy scalar types
            if isinstance(val, (np.floating, np.float64, np.float32)):
                return float(val)
            elif isinstance(val, (np.integer, np.int64, np.int32, np.int16, np.int8)):
                return int(val)
            elif isinstance(val, np.bool_):
                return bool(val)
            elif isinstance(val, np.ndarray):
                return val.tolist()
            # Handle nested tuples/lists
            elif isinstance(val, (tuple, list)):
                return type(val)(convert_value(v) for v in val)
            else:
                return val

        # Convert all parameters
        if isinstance(params, (tuple, list)):
            return type(params)(convert_value(p) for p in params)
        else:
            return convert_value(params)
    except ImportError:
        # numpy not available, return as-is
        return params


def get_boolean_value(value: bool) -> Union[bool, int]:
    """
    Get the correct boolean value for the current database type.

    SQLite: Returns 1 for True, 0 for False
    PostgreSQL: Returns True/False

    Args:
        value: Boolean value to convert

    Returns:
        Database-appropriate boolean value
    """
    if DB_TYPE == 'postgres':
        return value
    else:
        return 1 if value else 0


def get_boolean_comparison(column: str, value: bool) -> str:
    """
    Get SQL expression for boolean comparison that works with both SQLite and PostgreSQL.

    SQLite: column = 0 or column = 1
    PostgreSQL: column = false or column = true

    Args:
        column: Column name to compare
        value: Boolean value to compare against

    Returns:
        SQL comparison expression

    Example:
        get_boolean_comparison('dry_run', True) returns:
        - PostgreSQL: "dry_run = true"
        - SQLite: "dry_run = 1"
    """
    if DB_TYPE == 'postgres':
        return f"{column} = {str(value).lower()}"
    else:
        return f"{column} = {1 if value else 0}"


def get_db_path() -> Path:
    """Get the path to trading.db, creating directory if needed."""
    db_path = Path(DB_PATH) if isinstance(DB_PATH, str) else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_pg_pool():
    """
    Get or create PostgreSQL connection pool (singleton).
    Thread-safe connection pooling for multi-instance support.

    Returns:
        psycopg2.pool.ThreadedConnectionPool
    """
    global _pg_pool

    if _pg_pool is None:
        with _pg_pool_lock:
            # Double-check locking pattern
            if _pg_pool is None:
                from psycopg2 import pool
                from psycopg2 import extensions

                if not DATABASE_URL:
                    raise ValueError("DATABASE_URL not set for PostgreSQL mode")

                # Create a threaded connection pool
                # Pool sizing for multi-instance support:
                # - Each instance (TradingEngine + TradingCycle + EnhancedPositionMonitor) = 3 connections
                # - ErrorLogger gets 1 connection per error/warning logged
                # - minconn=5: Keep 5 connections ready for fast access
                # - maxconn=100: Support up to 30+ instances with logging overhead
                # Previous: maxconn=20 was too small (only supported ~6 instances)
                _pg_pool = pool.ThreadedConnectionPool(
                    minconn=5,
                    maxconn=100,
                    dsn=DATABASE_URL
                )

    return _pg_pool


def _get_pg_connection_with_timeout(timeout_seconds: float = 10.0):
    """
    Get a PostgreSQL connection from the pool with timeout.

    If pool is exhausted, waits up to timeout_seconds for a connection to become available.
    Raises TimeoutError if no connection available within timeout.

    Validates connections before returning to detect stale connections closed by server.

    Args:
        timeout_seconds: Maximum seconds to wait for a connection (default: 10)

    Returns:
        psycopg2.connection

    Raises:
        TimeoutError: If no connection available within timeout
        ValueError: If DATABASE_URL not set
    """
    import psycopg2.extras
    from psycopg2.pool import PoolError

    pool_obj = _get_pg_pool()
    start_time = time.time()

    # Try to get connection with timeout
    while True:
        try:
            # Try non-blocking first
            conn = pool_obj.getconn()
            conn.cursor_factory = psycopg2.extras.RealDictCursor

            # Validate connection is still alive (detect stale connections)
            # If connection was closed by server, this will raise an exception
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
            except Exception as e:
                # Connection is dead, return it to pool and try again
                pool_obj.putconn(conn, close=True)
                raise PoolError(f"Connection validation failed: {e}")

            return conn
        except PoolError:
            # Pool exhausted or connection invalid, check if we've exceeded timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"Connection pool exhausted: Could not get connection within {timeout_seconds}s. "
                    f"Pool size: {pool_obj.minconn}-{pool_obj.maxconn}. "
                    f"Consider increasing maxconn in database configuration."
                )
            # Wait a bit before retrying
            time.sleep(0.1)


def get_connection(timeout_seconds: float = 10.0):
    """
    Get a database connection.
    Auto-detects SQLite or PostgreSQL based on DB_TYPE env var.

    For PostgreSQL: Returns a connection from the connection pool with timeout
    For SQLite: Returns a new connection (SQLite handles concurrency internally)

    Args:
        timeout_seconds: For PostgreSQL, max seconds to wait for a connection (default: 10)

    Returns:
        sqlite3.Connection or psycopg2.connection

    Raises:
        TimeoutError: For PostgreSQL if no connection available within timeout

    IMPORTANT: For PostgreSQL, you MUST call release_connection() when done to return
    the connection to the pool. Use the context manager pattern or try/finally.
    """
    if DB_TYPE == 'postgres':
        # Use timeout wrapper to prevent indefinite blocking
        return _get_pg_connection_with_timeout(timeout_seconds)
    else:
        conn = sqlite3.connect(str(get_db_path()))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def release_connection(conn):
    """
    Release a database connection back to the pool (PostgreSQL only).
    For SQLite, this closes the connection.

    For PostgreSQL: If connection is in a failed state, closes it instead of returning to pool.

    Args:
        conn: Database connection to release
    """
    if conn is None:
        return

    if DB_TYPE == 'postgres':
        pool = _get_pg_pool()
        try:
            # Check if connection is in a failed transaction state
            # If so, close it instead of returning to pool
            if conn.status != 1:  # 1 = OK, other values = failed/closed
                pool.putconn(conn, close=True)
            else:
                pool.putconn(conn)
        except Exception as e:
            # If we can't check status, close the connection to be safe
            import logging
            logging.getLogger(__name__).warning(f"Error releasing connection: {e}, closing instead")
            try:
                pool.putconn(conn, close=True)
            except:
                pass
    else:
        conn.close()


def get_backtest_connection():
    """
    Get a database connection for backtest operations.
    For PostgreSQL: uses the same connection as get_connection() (all tables in one DB)
    For SQLite: uses backtests.db instead of trading.db

    Returns:
        sqlite3.Connection or psycopg2.connection
    """
    if DB_TYPE == 'postgres':
        # PostgreSQL: same database, different table names (handled by get_table_name)
        return get_connection()
    else:
        # SQLite: separate backtests.db file
        backtest_path = Path(BACKTEST_DB_PATH)
        backtest_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(backtest_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        return conn


def convert_placeholders(sql: str, params: Tuple) -> Tuple[str, Tuple]:
    """
    Convert SQLite placeholders (?) to PostgreSQL placeholders (%s).

    For PostgreSQL: Replaces all ? with %s. psycopg2 handles parameter escaping automatically.
    For SQLite: Returns SQL and params unchanged.

    Args:
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        Tuple of (converted_sql, params)
    """
    # Validate input types
    if not isinstance(sql, str):
        raise TypeError(f"sql must be a string, got {type(sql).__name__}: {sql}")
    if not isinstance(params, (tuple, list)):
        raise TypeError(f"params must be a tuple or list, got {type(params).__name__}: {params}")

    if DB_TYPE == 'postgres':
        # Replace ? with %s for PostgreSQL
        # psycopg2 will handle parameter escaping automatically
        # We do NOT need to escape % characters - psycopg2 handles that
        converted_sql = sql.replace('?', '%s')
        return (converted_sql, params)
    else:
        return (sql, params)


def execute(conn, sql: str, params: Tuple = (), auto_commit: bool = True) -> int:
    """
    Execute an INSERT/UPDATE/DELETE query.
    Automatically handles parameter placeholder conversion and transaction management.
    Converts numpy types to native Python types for database compatibility.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters
        auto_commit: If True, automatically commit on success and rollback on error

    Returns:
        Number of affected rows
    """
    # Convert numpy types to Python types
    params = convert_numpy_types(params)

    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()

    try:
        cursor.execute(converted_sql, converted_params)

        if auto_commit:
            conn.commit()

        if DB_TYPE == 'postgres':
            return cursor.rowcount
        else:
            return cursor.rowcount
    except Exception as e:
        if auto_commit:
            try:
                conn.rollback()
            except Exception as rollback_error:
                # If rollback fails, connection is likely dead
                import logging
                logging.getLogger(__name__).error(f"Rollback failed: {rollback_error}")
        raise  # Re-raise the exception after rollback


def query(conn, sql: str, params: Tuple = ()) -> List[UnifiedRow]:
    """
    Execute a SELECT query and return all rows.
    Automatically handles parameter placeholder conversion.
    Converts numpy types to native Python types for database compatibility.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        List of UnifiedRow objects (support both index and key access)
    """
    # Convert numpy types to Python types
    params = convert_numpy_types(params)

    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    rows = cursor.fetchall()
    return [UnifiedRow(row) for row in rows] if rows else []


def query_one(conn, sql: str, params: Tuple = ()) -> Optional[UnifiedRow]:
    """
    Execute a SELECT query and return one row.
    Automatically handles parameter placeholder conversion.
    Converts numpy types to native Python types for database compatibility.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        UnifiedRow object (supports both index and key access) or None
    """
    # Convert numpy types to Python types
    params = convert_numpy_types(params)

    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    row = cursor.fetchone()
    return UnifiedRow(row) if row else None


def get_table_columns(conn, table_name: str) -> set:
    """
    Get set of column names for a table.
    Works with both SQLite and PostgreSQL.

    Args:
        conn: Database connection
        table_name: Name of the table

    Returns:
        Set of column names
    """
    cursor = conn.cursor()

    if DB_TYPE == 'postgres':
        # PostgreSQL: Use information_schema
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))
        rows = cursor.fetchall()
        # Handle dict cursor vs tuple cursor
        if rows and hasattr(rows[0], 'get'):
            return {row.get('column_name') or row['column_name'] for row in rows}
        return {row[0] for row in rows}
    else:
        # SQLite: Use PRAGMA table_info
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cursor.fetchall()}


def get_timestamp_type() -> str:
    """
    Get the appropriate timestamp type for the current database.

    Returns:
        'TIMESTAMP' for PostgreSQL, 'DATETIME' for SQLite
    """
    return 'TIMESTAMP' if DB_TYPE == 'postgres' else 'DATETIME'


def get_table_name(logical_name: str) -> str:
    """
    Get the actual table name for the current database.
    Handles table name differences between SQLite and PostgreSQL.

    Args:
        logical_name: Logical table name (e.g., 'klines_store', 'sessions', 'tournament_runs')

    Returns:
        Actual table name for the current database
    """
    # Table name mappings for PostgreSQL (Supabase managed)
    # SQLite uses local table names, PostgreSQL uses prefixed names
    table_mappings = {
        'klines_store': 'klines',  # PostgreSQL uses 'klines', SQLite uses 'klines_store'
        'sessions': 'tradingview_sessions',  # PostgreSQL uses 'tradingview_sessions', SQLite uses 'sessions'
        # Backtest tables: SQLite uses unprefixed names, PostgreSQL uses bt_ prefix
        'tournament_runs': 'bt_tournament_runs',
        'runs': 'bt_runs',
        'run_images': 'bt_run_images',
        'analyses': 'bt_analyses',
        'trades': 'bt_trades',
        'summaries': 'bt_summaries',
    }

    if DB_TYPE == 'postgres' and logical_name in table_mappings:
        return table_mappings[logical_name]
    return logical_name


def get_boolean_value(value: bool) -> Union[bool, str]:
    """
    Get the appropriate boolean value for the current database.

    Args:
        value: Python boolean value

    Returns:
        For PostgreSQL: returns the boolean as-is
        For SQLite: returns the boolean as-is (SQLite accepts both)

    Note: This function exists for clarity but both databases now accept
    Python boolean values directly. Use this for explicit conversions if needed.
    """
    return value


def should_run_migrations() -> bool:
    """
    Check if database migrations should be run.

    Returns:
        True for SQLite (local migrations needed)
        False for PostgreSQL (managed by Supabase)
    """
    return DB_TYPE != 'postgres'


def should_init_schema() -> bool:
    """
    Check if schema initialization should be run.

    Returns:
        True for SQLite (local schema needed)
        False for PostgreSQL (managed by Supabase)
    """
    return DB_TYPE != 'postgres'


def should_seed_defaults() -> bool:
    """
    Check if default data seeding should be run.

    Returns:
        True for SQLite (local defaults needed)
        False for PostgreSQL (managed by Supabase)
    """
    return DB_TYPE != 'postgres'


def normalize_sql(sql: str) -> str:
    """
    Normalize SQL for the current database type.
    Converts SQLite-specific syntax to PostgreSQL-compatible syntax.

    This is the centralized place for handling SQL dialect differences.

    Args:
        sql: SQL query string (can contain DATETIME, etc.)

    Returns:
        Normalized SQL for the current database type
    """
    if DB_TYPE == 'postgres':
        # Replace DATETIME with TIMESTAMP for PostgreSQL
        sql = sql.replace('DATETIME', 'TIMESTAMP')
    return sql


def safe_execute(conn, sql: str, params: Tuple = (), rollback_on_error: bool = True) -> int:
    """
    Execute SQL with automatic error handling and transaction management.
    For PostgreSQL, automatically rolls back on error to prevent
    'InFailedSqlTransaction' errors.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters
        rollback_on_error: Whether to rollback on error (PostgreSQL only)

    Returns:
        Number of affected rows

    Raises:
        Exception: Re-raises the original exception after rollback
    """
    try:
        return execute(conn, sql, params)
    except Exception as e:
        if DB_TYPE == 'postgres' and rollback_on_error:
            conn.rollback()
        raise


def add_column_if_missing(conn, table_name: str, column_name: str, column_type: str, default_value: str = None) -> bool:
    """
    Add a column to a table if it doesn't exist.
    Works with both SQLite and PostgreSQL.

    Args:
        conn: Database connection
        table_name: Name of the table
        column_name: Name of the column to add
        column_type: SQL type of the column (e.g., 'TEXT', 'REAL', 'INTEGER')
        default_value: Optional default value (SQL expression)

    Returns:
        True if column was added, False if it already existed
    """
    existing_columns = get_table_columns(conn, table_name)

    if column_name in existing_columns:
        return False

    cursor = conn.cursor()

    # Normalize the column type (e.g., DATETIME -> TIMESTAMP for PostgreSQL)
    column_type = normalize_sql(column_type)

    if default_value:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default_value}"
    else:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"

    try:
        cursor.execute(sql)
        return True
    except Exception as e:
        # Rollback on error for PostgreSQL
        if DB_TYPE == 'postgres':
            conn.rollback()
        raise


__all__ = [
    'get_connection',
    'release_connection',
    'get_backtest_connection',
    'get_db_path',
    'execute',
    'query',
    'query_one',
    'convert_placeholders',
    'get_table_columns',
    'add_column_if_missing',
    'get_timestamp_type',
    'get_table_name',
    'get_boolean_value',
    'should_run_migrations',
    'should_init_schema',
    'should_seed_defaults',
    'normalize_sql',
    'safe_execute',
    'DB_TYPE',
    'BACKTEST_DB_PATH',
]

