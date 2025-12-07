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
from pathlib import Path
from typing import Any, List, Tuple, Optional, Union
from collections.abc import Mapping

# Database configuration
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
DATABASE_URL = os.getenv('DATABASE_URL', '')

# Unified data folder at project root: ./data/
# Path resolution: client.py -> db -> trading_bot -> python -> PROJECT_ROOT -> data
DB_DIR = Path(__file__).parent.parent.parent.parent / "data"
DB_PATH = os.getenv('TRADING_DB_PATH', str(DB_DIR / "trading.db"))
if not Path(DB_PATH).is_absolute():
    # If relative path from env, resolve relative to project root
    DB_PATH = Path(__file__).parent.parent.parent.parent / DB_PATH
else:
    DB_PATH = Path(DB_PATH)


class UnifiedRow:
    """
    Unified row wrapper that supports both index and key access.
    Works consistently for both SQLite (sqlite3.Row) and PostgreSQL (RealDictRow).

    This allows code to use either row[0] or row['column_name'] syntax.
    """
    def __init__(self, row):
        self._row = row
        # Convert to dict for consistent access
        if isinstance(row, Mapping):
            self._dict = dict(row)
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


def get_db_path() -> Path:
    """Get the path to trading.db, creating directory if needed."""
    db_path = Path(DB_PATH) if isinstance(DB_PATH, str) else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection():
    """
    Get a database connection.
    Auto-detects SQLite or PostgreSQL based on DB_TYPE env var.
    
    Returns:
        sqlite3.Connection or psycopg2.connection
    """
    if DB_TYPE == 'postgres':
        import psycopg2
        import psycopg2.extras
        
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not set for PostgreSQL mode")
        
        conn = psycopg2.connect(DATABASE_URL)
        # Use RealDictCursor for dict-like row access (similar to sqlite3.Row)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(str(get_db_path()))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def convert_placeholders(sql: str, params: Tuple) -> Tuple[str, Tuple]:
    """
    Convert SQLite placeholders (?) to PostgreSQL placeholders (%s).

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
        converted_sql = sql.replace('?', '%s')
        return (converted_sql, params)
    else:
        return (sql, params)


def execute(conn, sql: str, params: Tuple = (), auto_commit: bool = True) -> int:
    """
    Execute an INSERT/UPDATE/DELETE query.
    Automatically handles parameter placeholder conversion and transaction management.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters
        auto_commit: If True, automatically commit on success and rollback on error

    Returns:
        Number of affected rows
    """
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
            conn.rollback()
        raise  # Re-raise the exception after rollback


def query(conn, sql: str, params: Tuple = ()) -> List[UnifiedRow]:
    """
    Execute a SELECT query and return all rows.
    Automatically handles parameter placeholder conversion.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        List of UnifiedRow objects (support both index and key access)
    """
    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    rows = cursor.fetchall()
    return [UnifiedRow(row) for row in rows] if rows else []


def query_one(conn, sql: str, params: Tuple = ()) -> Optional[UnifiedRow]:
    """
    Execute a SELECT query and return one row.
    Automatically handles parameter placeholder conversion.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        UnifiedRow object (supports both index and key access) or None
    """
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
        logical_name: Logical table name (e.g., 'klines_store', 'sessions')

    Returns:
        Actual table name for the current database
    """
    # Table name mappings for PostgreSQL (Supabase managed)
    table_mappings = {
        'klines_store': 'klines',  # PostgreSQL uses 'klines', SQLite uses 'klines_store'
        'sessions': 'tradingview_sessions',  # PostgreSQL uses 'tradingview_sessions', SQLite uses 'sessions'
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
]

