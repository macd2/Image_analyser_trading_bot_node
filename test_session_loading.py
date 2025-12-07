#!/usr/bin/env python3
"""
Test script to verify TradingView session loading from database.
This uses the same data layer as the sourcer to diagnose session loading issues.
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'python'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv('.env.local')

from trading_bot.db.client import get_connection, query_one, query, DB_TYPE
from trading_bot.core.secrets_manager import SecretsManager


async def test_session_loading():
    """Test loading TradingView session from database."""
    print("=" * 80)
    print("TradingView Session Loading Test")
    print("=" * 80)
    
    # Get username from environment
    username = os.getenv('TRADINGVIEW_EMAIL', '')
    print(f"\n1. Environment Check:")
    print(f"   - TRADINGVIEW_EMAIL: {username}")
    print(f"   - DB_TYPE: {DB_TYPE}")
    print(f"   - DATABASE_URL: {'SET' if os.getenv('DATABASE_URL') else 'NOT SET'}")
    
    if not username:
        print("\n❌ ERROR: TRADINGVIEW_EMAIL not set in .env.local")
        return
    
    # Connect to database
    print(f"\n2. Database Connection:")
    try:
        conn = get_connection()
        print(f"   ✅ Connected to {DB_TYPE} database")
    except Exception as e:
        print(f"   ❌ Failed to connect: {e}")
        return
    
    # Check if table exists
    print(f"\n3. Table Check:")
    try:
        if DB_TYPE == 'postgres':
            table_check = query_one(conn, """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'tradingview_sessions'
                )
            """)
            print(f"   DEBUG: table_check = {table_check}, type = {type(table_check)}")
            # PostgreSQL returns RealDictRow, access by key name
            table_exists = table_check and table_check['exists']
            table_name = 'tradingview_sessions'
        else:
            table_check = query_one(conn, """
                SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'
            """)
            table_exists = bool(table_check)
            table_name = 'sessions'

        if table_exists:
            print(f"   ✅ Table '{table_name}' exists")
        else:
            print(f"   ❌ Table '{table_name}' does NOT exist")
            conn.close()
            return
    except Exception as e:
        print(f"   ❌ Error checking table: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return
    
    # List all sessions in database
    print(f"\n4. All Sessions in Database:")
    try:
        if DB_TYPE == 'postgres':
            rows = query(conn, """
                SELECT id, username, created_at, is_valid, LENGTH(encrypted_data) as data_length
                FROM tradingview_sessions
                ORDER BY created_at DESC
            """)
        else:
            rows = query(conn, """
                SELECT id, username, created_at, is_valid, LENGTH(encrypted_data) as data_length
                FROM sessions
                ORDER BY created_at DESC
            """)
        
        if rows:
            print(f"   Found {len(rows)} session(s):")
            for row in rows:
                if isinstance(row, dict):
                    print(f"   - ID: {row['id']}, User: {row['username']}, Valid: {row['is_valid']}, "
                          f"Created: {row['created_at']}, Size: {row['data_length']} bytes")
                else:
                    print(f"   - ID: {row[0]}, User: {row[1]}, Valid: {row[3]}, "
                          f"Created: {row[2]}, Size: {row[4]} bytes")
        else:
            print(f"   ❌ No sessions found in database")
    except Exception as e:
        print(f"   ❌ Error listing sessions: {e}")
        import traceback
        traceback.print_exc()
    
    # Query for specific user's session
    print(f"\n5. Query for User '{username}':")
    try:
        if DB_TYPE == 'postgres':
            row = query_one(conn, """
                SELECT id, username, created_at, is_valid, encrypted_data
                FROM tradingview_sessions
                WHERE username = ? AND is_valid = true
                ORDER BY created_at DESC LIMIT 1
            """, (username,))
        else:
            row = query_one(conn, """
                SELECT id, username, created_at, is_valid, encrypted_data
                FROM sessions
                WHERE username = ? AND is_valid = 1
                ORDER BY created_at DESC LIMIT 1
            """, (username,))
        
        if row:
            if isinstance(row, dict):
                print(f"   ✅ Found session: ID={row['id']}, Created={row['created_at']}, Valid={row['is_valid']}")
                encrypted_data = row['encrypted_data']
            else:
                print(f"   ✅ Found session: ID={row[0]}, Created={row[2]}, Valid={row[3]}")
                encrypted_data = row[4]
            
            # Try to decrypt
            print(f"\n6. Decryption Test:")
            try:
                secrets = SecretsManager()
                decrypted = secrets.decrypt(encrypted_data)
                session_data = json.loads(decrypted)
                
                print(f"   ✅ Successfully decrypted session data")
                print(f"   - Cookies: {len(session_data.get('cookies', []))}")
                print(f"   - User Agent: {session_data.get('user_agent', 'N/A')[:80]}...")
                print(f"   - Timestamp: {session_data.get('timestamp', 'N/A')}")
                print(f"   - Saved By: {session_data.get('saved_by', 'N/A')}")
                
                # Show first few cookie names
                cookies = session_data.get('cookies', [])
                if cookies:
                    print(f"\n   First 5 cookies:")
                    for i, cookie in enumerate(cookies[:5]):
                        print(f"   - {cookie.get('name')}: domain={cookie.get('domain')}, "
                              f"path={cookie.get('path')}, secure={cookie.get('secure', False)}")
                
            except Exception as e:
                print(f"   ❌ Decryption failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"   ❌ No valid session found for user '{username}'")
            
    except Exception as e:
        print(f"   ❌ Error querying session: {e}")
        import traceback
        traceback.print_exc()
    
    conn.close()
    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(test_session_loading())

