#!/usr/bin/env python3
"""Test UnifiedRow supports both index and key access."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'python'))

from dotenv import load_dotenv
load_dotenv('.env.local')

from trading_bot.db.client import get_connection, query_one

print("Testing UnifiedRow - supports both index and key access")
print("=" * 80)

conn = get_connection()

# Test with a simple query
row = query_one(conn, """
    SELECT 'test_value' as test_column, 123 as test_number, true as test_bool
""")

print(f"\nRow type: {type(row)}")
print(f"Row repr: {row}")

print("\n1. Key access (dict-like):")
print(f"   row['test_column'] = {row['test_column']}")
print(f"   row['test_number'] = {row['test_number']}")
print(f"   row['test_bool'] = {row['test_bool']}")

print("\n2. Index access (tuple-like):")
print(f"   row[0] = {row[0]}")
print(f"   row[1] = {row[1]}")
print(f"   row[2] = {row[2]}")

print("\n3. Dict methods:")
print(f"   row.get('test_column') = {row.get('test_column')}")
print(f"   row.get('missing', 'default') = {row.get('missing', 'default')}")
print(f"   'test_column' in row = {'test_column' in row}")
print(f"   'missing' in row = {'missing' in row}")

print("\n4. Iteration:")
print(f"   keys() = {list(row.keys())}")
print(f"   values() = {list(row.values())}")
print(f"   items() = {list(row.items())}")

print("\n✅ UnifiedRow works with both index and key access!")
print("=" * 80)

conn.close()

