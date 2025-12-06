#!/usr/bin/env python3
"""
Fix backtest data in PostgreSQL by clearing and re-migrating from SQLite.

The issue: bt_runs IDs in PostgreSQL don't match SQLite because they're timestamp-based
and were generated at different times. This causes foreign key violations.

Solution: Clear PostgreSQL backtest tables and re-migrate from SQLite.
"""

import os
import sys
from pathlib import Path

# Load environment
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from dotenv import load_dotenv
    # Script is in lib/db/, .env.local is in prototype/
    env_path = Path(__file__).parent.parent.parent / ".env.local"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment from {env_path}\n")
    else:
        print(f"⚠️  .env.local not found at {env_path}\n")
except ImportError:
    print("⚠️  python-dotenv not installed\n")

try:
    import psycopg2
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary")
    sys.exit(1)


def main():
    print("=" * 60)
    print("Fix Backtest Data - Clear PostgreSQL & Re-migrate")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will DELETE all backtest data from PostgreSQL")
    print("   and re-migrate from SQLite.")
    print()
    print("Tables to be cleared:")
    print("  - bt_trades")
    print("  - bt_analyses")
    print("  - bt_run_images")
    print("  - bt_summaries")
    print("  - bt_tournament_runs")
    print("  - bt_runs")
    print()
    
    response = input("Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    # Connect to PostgreSQL
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL not set")
        sys.exit(1)
    
    conn = psycopg2.connect(url)
    cursor = conn.cursor()
    
    print("\n🗑️  Clearing PostgreSQL backtest tables...")
    
    # Delete in reverse dependency order
    tables = [
        'bt_trades',
        'bt_analyses', 
        'bt_run_images',
        'bt_summaries',
        'bt_tournament_runs',
        'bt_runs'
    ]
    
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            count = cursor.rowcount
            print(f"  ✓ Deleted {count} rows from {table}")
        except Exception as e:
            print(f"  ⚠️  Error deleting from {table}: {e}")
    
    conn.commit()
    conn.close()
    
    print("\n✅ PostgreSQL backtest tables cleared")
    print("\n📦 Now run the migration script:")
    print("   python3 lib/db/migrate-to-postgres.py --tables bt_runs,bt_run_images,bt_analyses,bt_trades,bt_summaries,bt_tournament_runs")


if __name__ == "__main__":
    main()

