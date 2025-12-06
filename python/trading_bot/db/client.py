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
    if DB_TYPE == 'postgres':
        # Replace ? with %s for PostgreSQL
        converted_sql = sql.replace('?', '%s')
        return (converted_sql, params)
    else:
        return (sql, params)


def execute(conn, sql: str, params: Tuple = ()) -> int:
    """
    Execute an INSERT/UPDATE/DELETE query.
    Automatically handles parameter placeholder conversion.
    
    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters
        
    Returns:
        Number of affected rows
    """
    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    
    if DB_TYPE == 'postgres':
        return cursor.rowcount
    else:
        return cursor.rowcount


def query(conn, sql: str, params: Tuple = ()) -> List[Any]:
    """
    Execute a SELECT query and return all rows.
    Automatically handles parameter placeholder conversion.
    
    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters
        
    Returns:
        List of rows (as dicts or sqlite3.Row objects)
    """
    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    return cursor.fetchall()


def query_one(conn, sql: str, params: Tuple = ()) -> Optional[Any]:
    """
    Execute a SELECT query and return one row.
    Automatically handles parameter placeholder conversion.

    Args:
        conn: Database connection
        sql: SQL query with ? placeholders
        params: Query parameters

    Returns:
        Single row (as dict or sqlite3.Row object) or None
    """
    converted_sql, converted_params = convert_placeholders(sql, params)
    cursor = conn.cursor()
    cursor.execute(converted_sql, converted_params)
    return cursor.fetchone()


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
    'normalize_sql',
    'safe_execute',
    'DB_TYPE',
]

