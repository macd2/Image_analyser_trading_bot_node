#!/usr/bin/env python3
"""
Apply SQL migrations to PostgreSQL database.

Usage:
    python apply_postgres_migrations.py
    
Reads all .sql files from lib/db/migrations/ and applies them to PostgreSQL.
Tracks applied migrations in _migrations table.
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded environment from {env_path}")

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set in environment")
    sys.exit(1)

MIGRATIONS_DIR = Path(__file__).parent.parent / "lib" / "db" / "migrations"

def get_connection():
    """Get PostgreSQL connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)

def create_migrations_table(conn):
    """Create _migrations tracking table if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()

def get_applied_migrations(conn):
    """Get list of applied migrations."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM _migrations ORDER BY id")
    migrations = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return migrations

def get_pending_migrations():
    """Get list of pending migrations."""
    applied = set(get_applied_migrations(get_connection()))
    files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql')])
    return [f for f in files if f not in applied]

def apply_migration(conn, filename):
    """Apply a single migration."""
    filepath = MIGRATIONS_DIR / filename
    with open(filepath, 'r') as f:
        sql = f.read()
    
    print(f"Applying migration: {filename}")
    cursor = conn.cursor()
    
    try:
        cursor.execute(sql)
        cursor.execute("INSERT INTO _migrations (name) VALUES (%s)", (filename,))
        conn.commit()
        print(f"✅ Applied: {filename}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Failed to apply {filename}: {e}")
        raise
    finally:
        cursor.close()

def main():
    """Run all pending migrations."""
    conn = get_connection()
    
    # Create migrations table
    create_migrations_table(conn)
    
    # Get pending migrations
    pending = get_pending_migrations()
    
    if not pending:
        print("✅ No pending migrations")
        conn.close()
        return
    
    print(f"Found {len(pending)} pending migration(s)")
    print()
    
    for migration in pending:
        try:
            apply_migration(conn, migration)
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            conn.close()
            sys.exit(1)
    
    conn.close()
    print()
    print(f"✅ Successfully applied {len(pending)} migration(s)")

if __name__ == "__main__":
    main()

