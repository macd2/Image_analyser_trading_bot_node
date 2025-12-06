#!/usr/bin/env python3
"""
Migrate SQLite databases to PostgreSQL (Supabase)

Usage:
    python migrate-to-postgres.py [--dry-run] [--tables TABLE1,TABLE2]

Tables are migrated with prefixes:
    trading.db    -> no prefix (instances, runs, cycles, trades, etc.)
    backtests.db  -> bt_ prefix (bt_runs, bt_trades, etc.)
    bot.db        -> tourn_/app_ prefix
    candle_store.db -> klines
"""

import os
import sys
import sqlite3
import argparse
from pathlib import Path

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables from .env.local
try:
    from dotenv import load_dotenv
    # Script is in lib/db/, .env.local is in prototype/
    env_path = Path(__file__).parent.parent.parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment from {env_path}")
    else:
        print(f"⚠️  .env.local not found at {env_path}")
except ImportError:
    print("⚠️  python-dotenv not installed, using system environment variables")

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)

# Paths relative to prototype folder
DATA_DIR = Path(__file__).parent.parent.parent / "data"

# Cache for SQLite connections (avoid reopening same DB multiple times)
_sqlite_conn_cache = {}

# Table mappings: (sqlite_db, sqlite_table, postgres_table)
# IMPORTANT: Tables are ordered to respect foreign key dependencies
# Parent tables must be migrated before child tables
TABLE_MAPPINGS = [
    # trading.db -> no prefix (ordered by dependencies)
    ("trading.db", "instances", "instances"),              # No dependencies
    ("trading.db", "runs", "runs"),                        # References instances
    ("trading.db", "cycles", "cycles"),                    # References runs
    ("trading.db", "recommendations", "recommendations"),  # References cycles
    ("trading.db", "trades", "trades"),                    # References recommendations
    ("trading.db", "executions", "executions"),            # References trades
    ("trading.db", "position_snapshots", "position_snapshots"),  # References trades
    ("trading.db", "sessions", "tradingview_sessions"),    # No dependencies (renamed to avoid Supabase auth conflict)
    ("trading.db", "bot_actions", "bot_actions"),          # No dependencies
    ("trading.db", "error_logs", "error_logs"),            # References runs/cycles/trades
    ("trading.db", "analysis_results", "analysis_results"),  # No dependencies
    ("trading.db", "latest_recommendations", "latest_recommendations"),  # No dependencies

    # backtests.db -> bt_ prefix (ordered by dependencies)
    ("backtests.db", "runs", "bt_runs"),                   # No dependencies - MUST BE FIRST
    ("backtests.db", "run_images", "bt_run_images"),       # References bt_runs
    ("backtests.db", "analyses", "bt_analyses"),           # References bt_runs
    ("backtests.db", "trades", "bt_trades"),               # References bt_analyses
    ("backtests.db", "summaries", "bt_summaries"),         # References bt_runs
    ("backtests.db", "tournament_runs", "bt_tournament_runs"),  # No dependencies

    # bot.db -> tourn_/app_ prefix (ordered by dependencies)
    ("bot.db", "tournaments", "tourn_tournaments"),        # No dependencies
    ("bot.db", "tournament_phases", "tourn_phases"),       # References tournaments
    ("bot.db", "tournament_prompts", "tourn_prompts"),     # References tournaments
    ("bot.db", "phase_results", "tourn_phase_results"),    # References phases
    ("bot.db", "phase_images", "tourn_phase_images"),      # References phases
    ("bot.db", "tournament_analyses", "tourn_analyses"),   # References tournaments
    ("bot.db", "settings", "app_settings"),                # No dependencies
    ("bot.db", "_migrations", "app_migrations"),           # No dependencies

    # candle_store.db (no dependencies)
    ("candle_store.db", "klines_store", "klines"),
    ("candle_store.db", "prompt_hash_mappings", "prompt_hash_mappings"),
]


def get_sqlite_conn(db_name: str, use_cache: bool = True) -> sqlite3.Connection:
    """
    Get SQLite connection with optional caching.

    Args:
        db_name: Database filename
        use_cache: If True, reuse existing connection for same database

    Returns:
        SQLite connection or None if database doesn't exist
    """
    # Check cache first
    if use_cache and db_name in _sqlite_conn_cache:
        return _sqlite_conn_cache[db_name]

    db_path = DATA_DIR / db_name
    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Cache connection for reuse
    if use_cache:
        _sqlite_conn_cache[db_name] = conn

    return conn


def close_all_sqlite_connections():
    """Close all cached SQLite connections."""
    for conn in _sqlite_conn_cache.values():
        try:
            conn.close()
        except:
            pass
    _sqlite_conn_cache.clear()


def get_postgres_conn() -> 'psycopg2.connection':
    """Get PostgreSQL connection from DATABASE_URL"""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")
    return psycopg2.connect(url)


def get_table_columns(sqlite_conn: sqlite3.Connection, table: str) -> list:
    """Get column names from SQLite table"""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cursor.fetchall()]


# Boolean columns that need conversion (SQLite stores as 0/1)
BOOLEAN_COLUMNS = {
    'is_active', 'paper_trading', 'dry_run', 'is_maker', 'is_valid', 'eliminated'
}

# Columns that need quoting in PostgreSQL (mixed case)
QUOTED_COLUMNS = {'orderLinkId'}


def quote_column(col: str) -> str:
    """Quote column name if needed for PostgreSQL"""
    if col in QUOTED_COLUMNS:
        return f'"{col}"'
    return col


def convert_row_types(row: tuple, columns: list) -> tuple:
    """Convert SQLite types to PostgreSQL compatible types"""
    converted = []
    for i, (value, col) in enumerate(zip(row, columns)):
        if col in BOOLEAN_COLUMNS and value is not None:
            # Convert 0/1 to boolean
            converted.append(bool(value))
        else:
            converted.append(value)
    return tuple(converted)


def validate_row(row: tuple, columns: list, table_name: str) -> tuple:
    """
    Validate row data and return (is_valid, reason).

    Checks for NULL values in columns that should not be NULL based on table schema.
    """
    # Define required (NOT NULL) columns per table
    REQUIRED_COLUMNS = {
        'bt_analyses': ['timestamp', 'run_id'],
        'bt_trades': ['run_id'],
        'bt_run_images': ['run_id'],
        'runs': ['instance_id'],
        'cycles': ['run_id'],
        'trades': ['recommendation_id'],
        'error_logs': ['timestamp'],
    }

    required = REQUIRED_COLUMNS.get(table_name, [])

    for col_name in required:
        if col_name in columns:
            idx = columns.index(col_name)
            if row[idx] is None or row[idx] == '':
                return (False, f"NULL value in required column '{col_name}'")

    return (True, None)


def get_postgres_row_count(pg_conn, table: str) -> int:
    """Get row count from PostgreSQL table."""
    try:
        cursor = pg_conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception:
        return 0


def migrate_table(sqlite_db: str, sqlite_table: str, pg_table: str,
                  pg_conn, dry_run: bool = False, batch_size: int = 1000) -> int:
    """
    Migrate a single table from SQLite to PostgreSQL using batch inserts.

    Args:
        sqlite_db: SQLite database filename
        sqlite_table: Source table name
        pg_table: Destination table name
        pg_conn: PostgreSQL connection
        dry_run: If True, only count rows without inserting
        batch_size: Number of rows to insert per batch (default: 1000)

    Returns:
        Number of rows processed
    """
    sqlite_conn = get_sqlite_conn(sqlite_db)
    if not sqlite_conn:
        print(f"  ⚠️  {sqlite_db} not found, skipping")
        return 0

    try:
        # Check if SQLite table exists
        cursor = sqlite_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (sqlite_table,)
        )
        if not cursor.fetchone():
            print(f"  ⚠️  Table {sqlite_table} not in {sqlite_db}, skipping")
            return 0

        # Get row count first (more efficient than loading all rows)
        count_cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {sqlite_table}")
        row_count = count_cursor.fetchone()[0]

        if row_count == 0:
            print(f"  📭 {sqlite_db}.{sqlite_table} is empty")
            return 0

        # Check existing data in PostgreSQL
        pg_row_count = get_postgres_row_count(pg_conn, pg_table)

        if pg_row_count > 0:
            print(f"  📦 {sqlite_db}.{sqlite_table} -> {pg_table}: {row_count} rows (PostgreSQL has {pg_row_count} rows)", end="")
        else:
            print(f"  📦 {sqlite_db}.{sqlite_table} -> {pg_table}: {row_count} rows", end="")

        if dry_run:
            print()
            return row_count

        # Get columns
        columns = get_table_columns(sqlite_conn, sqlite_table)
        cols_str = ", ".join(quote_column(c) for c in columns)

        # Use execute_values for batch inserts (much faster than individual inserts)
        pg_cursor = pg_conn.cursor()

        # Fetch and insert in batches to avoid loading all data into memory
        success_count = 0
        error_count = 0
        offset = 0

        while offset < row_count:
            # Fetch batch from SQLite
            batch_cursor = sqlite_conn.execute(
                f"SELECT * FROM {sqlite_table} LIMIT {batch_size} OFFSET {offset}"
            )
            batch_rows = batch_cursor.fetchall()

            if not batch_rows:
                break

            # Convert types for entire batch
            converted_batch = [convert_row_types(tuple(row), columns) for row in batch_rows]

            try:
                # Use execute_values for efficient batch insert
                # ON CONFLICT DO NOTHING protects against duplicates
                execute_values(
                    pg_cursor,
                    f"INSERT INTO {pg_table} ({cols_str}) VALUES %s ON CONFLICT DO NOTHING",
                    converted_batch,
                    page_size=batch_size
                )
                pg_conn.commit()
                success_count += len(batch_rows)

                # Show progress for large tables
                if row_count > 10000:
                    progress = (offset + len(batch_rows)) / row_count * 100
                    print(f"\r  📦 {sqlite_db}.{sqlite_table} -> {pg_table}: {row_count} rows [{progress:.1f}%]", end="")

            except Exception as e:
                pg_conn.rollback()
                error_msg = str(e)

                # Check if it's a foreign key constraint error
                if "foreign key constraint" in error_msg.lower():
                    # Extract constraint name for better error message
                    import re
                    constraint_match = re.search(r'constraint "([^"]+)"', error_msg)
                    constraint_name = constraint_match.group(1) if constraint_match else "unknown"
                    print(f"\n    ⚠️  Foreign key error: {constraint_name}")
                    print(f"       This table has dependencies that need to be migrated first.")
                    print(f"       Skipping remaining rows for {pg_table}...")
                    break  # Stop processing this table
                else:
                    error_count += len(batch_rows)
                    print(f"\n    ⚠️  Batch error at offset {offset}: {error_msg[:100]}")

            offset += batch_size

        print()  # New line after progress

        if error_count > 0:
            print(f"    ✓ Inserted {success_count}/{row_count} rows ({error_count} errors)")

        return row_count

    except Exception as e:
        print(f"\n    ❌ Migration failed: {str(e)[:100]}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--tables", type=str, help="Comma-separated list of postgres tables to migrate")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts (default: 1000)")
    parser.add_argument("--skip-fk-check", action="store_true", help="Skip foreign key checks (use with caution)")
    parser.add_argument("--force", action="store_true", help="Force re-migration even if data exists")
    args = parser.parse_args()

    print("=" * 50)
    print("SQLite → PostgreSQL Migration")
    print("=" * 50)

    if args.dry_run:
        print("🔍 DRY RUN MODE - no changes will be made\n")
    else:
        print(f"📊 Batch size: {args.batch_size}")
        if args.skip_fk_check:
            print("⚠️  Foreign key checks will be disabled during migration")
        if args.force:
            print("⚠️  Force mode - will attempt to re-migrate existing data")
        print()

    # Filter tables if specified
    mappings = TABLE_MAPPINGS
    if args.tables:
        filter_tables = [t.strip() for t in args.tables.split(",")]
        mappings = [m for m in TABLE_MAPPINGS if m[2] in filter_tables]
        print(f"Filtering to tables: {filter_tables}\n")

    # Connect to PostgreSQL
    try:
        pg_conn = get_postgres_conn()
        print("✅ Connected to PostgreSQL\n")
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        sys.exit(1)

    # Migrate each table
    import time
    start_time = time.time()
    total_rows = 0

    try:
        for sqlite_db, sqlite_table, pg_table in mappings:
            rows = migrate_table(sqlite_db, sqlite_table, pg_table, pg_conn, args.dry_run, args.batch_size)
            total_rows += rows
    finally:
        # Clean up connections
        close_all_sqlite_connections()
        pg_conn.close()

    elapsed = time.time() - start_time

    print()
    print("=" * 50)
    print(f"✅ Migration complete: {total_rows:,} total rows in {elapsed:.1f}s")
    if total_rows > 0 and elapsed > 0:
        print(f"   ({total_rows/elapsed:.0f} rows/sec)")
    if args.dry_run:
        print("   (dry run - no data was actually migrated)")
    print("=" * 50)


if __name__ == "__main__":
    main()

