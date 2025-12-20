#!/usr/bin/env python3
"""
Delete all trades and recommendations from the cointegration strategy.
Uses the centralized database client for SQLite/PostgreSQL compatibility.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env.local
env_path = Path(__file__).parent.parent / ".env.local"
load_dotenv(env_path)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from trading_bot.db.client import get_connection, release_connection, query, execute

def delete_cointegration_data():
    """Delete all cointegration strategy trades and recommendations."""
    conn = None
    try:
        conn = get_connection()

        # Step 1: Find all cointegration recommendations
        # Search for old format: raw_response contains {"strategy": "cointegration"
        print("🔍 Finding cointegration recommendations...")
        recs = query(conn, """
            SELECT id, symbol, strategy_name, strategy_type, raw_response
            FROM recommendations
            WHERE strategy_name = 'CointegrationAnalysisModule'
               OR strategy_type = 'spread_based'
               OR raw_response::text ILIKE ?
               OR raw_response::text ILIKE ?
        """, ('%"strategy": "cointegration"%', '%"strategy":"cointegration"%'))
        
        print(f"Found {len(recs)} cointegration recommendations")
        for rec in recs:
            print(f"  - {rec['symbol']}: {rec['id']}")
        
        if not recs:
            print("✅ No cointegration recommendations found")
            return
        
        # Step 2: Get all trades linked to these recommendations
        rec_ids = [rec['id'] for rec in recs]
        print(f"\n🔍 Finding trades linked to these recommendations...")
        
        trades = []
        for rec_id in rec_ids:
            trade_rows = query(conn, """
                SELECT id, symbol, side, entry_price 
                FROM trades 
                WHERE recommendation_id = ?
            """, (rec_id,))
            trades.extend(trade_rows)
        
        print(f"Found {len(trades)} trades linked to cointegration recommendations")
        for trade in trades:
            print(f"  - {trade['symbol']} {trade['side']}: {trade['id']}")
        
        # Step 3: Delete trades first (foreign key constraint)
        print(f"\n🗑️  Deleting {len(trades)} trades...")
        for trade in trades:
            execute(conn, "DELETE FROM trades WHERE id = ?", (trade['id'],))
        print(f"✅ Deleted {len(trades)} trades")
        
        # Step 4: Delete recommendations
        print(f"\n🗑️  Deleting {len(recs)} recommendations...")
        for rec in recs:
            execute(conn, "DELETE FROM recommendations WHERE id = ?", (rec['id'],))
        print(f"✅ Deleted {len(recs)} recommendations")
        
        # Step 5: Verify deletion
        print("\n✅ Verifying deletion...")
        remaining_recs = query(conn, """
            SELECT COUNT(*) as count FROM recommendations 
            WHERE strategy_name = 'CointegrationAnalysisModule' 
               OR strategy_type = 'spread_based'
        """)
        
        remaining_trades = query(conn, """
            SELECT COUNT(*) as count FROM trades 
            WHERE recommendation_id IN (
                SELECT id FROM recommendations 
                WHERE strategy_name = 'CointegrationAnalysisModule' 
                   OR strategy_type = 'spread_based'
            )
        """)
        
        print(f"Remaining cointegration recommendations: {remaining_recs[0]['count']}")
        print(f"Remaining cointegration trades: {remaining_trades[0]['count']}")
        
        if remaining_recs[0]['count'] == 0 and remaining_trades[0]['count'] == 0:
            print("\n✅ All cointegration trades and recommendations deleted successfully!")
        else:
            print("\n⚠️  Some records may still exist")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        if conn:
            release_connection(conn)

if __name__ == "__main__":
    delete_cointegration_data()

