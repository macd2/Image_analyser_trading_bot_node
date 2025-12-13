"""
Full trading cycle test with SL adjustment.
Tests that the entire trading cycle works correctly with SL adjustment enabled.
"""

import unittest
import tempfile
import os
import sys
from unittest.mock import Mock, patch, MagicMock
import sqlite3
import json
from datetime import datetime, timezone

# Ensure DB_TYPE is set to sqlite for tests
os.environ['DB_TYPE'] = 'sqlite'

# Force reload of db.client module
if 'trading_bot.db.client' in sys.modules:
    del sys.modules['trading_bot.db.client']

from trading_bot.services.sl_adjuster import StopLossAdjuster
from trading_bot.db.client import get_connection, execute, query
import trading_bot.db.client as db_client


class TestSLAdjusterFullCycle(unittest.TestCase):
    """Full trading cycle test with SL adjustment"""

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        cls.db_path = cls.temp_db.name
        cls.temp_db.close()
        
        # Create schema
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        
        # Create all necessary tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id TEXT PRIMARY KEY,
                cycle_id TEXT,
                symbol TEXT,
                recommendation TEXT,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                confidence REAL,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sl_adjustments (
                id TEXT PRIMARY KEY,
                recommendation_id TEXT NOT NULL REFERENCES recommendations(id),
                original_stop_loss REAL,
                adjusted_stop_loss REAL,
                adjustment_type TEXT,
                adjustment_value REAL,
                reason TEXT,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                recommendation_id TEXT REFERENCES recommendations(id),
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT,
                created_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sl_adj_rec ON sl_adjustments(recommendation_id)
        """)
        
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        if os.path.exists(cls.db_path):
            os.unlink(cls.db_path)

    def setUp(self):
        """Set up test fixtures"""
        # Set DB_TYPE to sqlite for this test
        db_client.DB_TYPE = 'sqlite'

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.adjuster = StopLossAdjuster(self.conn)

    def tearDown(self):
        """Clean up after tests"""
        self.conn.close()

    def test_full_trading_cycle_with_adjustment(self):
        """Test complete trading cycle: recommendation → adjustment → trade execution"""
        # Step 1: Create a recommendation
        rec_id = 'rec_full_cycle_001'
        recommendation = {
            'recommendation_id': rec_id,
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 50000.0,
            'stop_loss': 49000.0,  # 1000 risk
            'take_profit': 52000.0,
            'confidence': 0.85,
        }
        
        # Insert recommendation into DB
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO recommendations 
            (id, symbol, recommendation, entry_price, stop_loss, take_profit, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (rec_id, 'BTCUSDT', 'LONG', 50000.0, 49000.0, 52000.0, 0.85, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        
        # Step 2: Apply SL adjustment
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 2.0,  # 2% wider
            'trading.sl_adjustment_short_pct': 1.5,
        }
        
        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )
        
        # Verify adjustment was applied
        self.assertIsNotNone(adjustment_record)
        self.assertEqual(adjusted_rec['recommendation'], 'LONG')
        self.assertEqual(adjusted_rec['entry_price'], 50000.0)
        
        # Risk = 50000 - 49000 = 1000
        # Adjustment = 1000 * 2% = 20
        # Adjusted SL = 49000 - 20 = 48980
        expected_adjusted_sl = 48980.0
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_adjusted_sl, places=2)
        
        # Step 3: Verify adjustment was recorded to DB
        cursor.execute(
            "SELECT * FROM sl_adjustments WHERE recommendation_id = ?",
            (rec_id,)
        )
        db_adjustment = cursor.fetchone()
        self.assertIsNotNone(db_adjustment)
        self.assertEqual(db_adjustment['original_stop_loss'], 49000.0)
        self.assertAlmostEqual(db_adjustment['adjusted_stop_loss'], expected_adjusted_sl, places=2)
        self.assertEqual(db_adjustment['adjustment_value'], 2.0)
        
        # Step 4: Simulate trade execution with adjusted SL
        trade_id = 'trade_001'
        cursor.execute("""
            INSERT INTO trades 
            (id, recommendation_id, symbol, direction, entry_price, stop_loss, take_profit, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (trade_id, rec_id, 'BTCUSDT', 'LONG', 50000.0, adjusted_rec['stop_loss'], 52000.0, 'OPEN', datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        
        # Step 5: Verify trade was created with adjusted SL
        cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        self.assertIsNotNone(trade)
        self.assertEqual(trade['symbol'], 'BTCUSDT')
        self.assertEqual(trade['direction'], 'LONG')
        self.assertAlmostEqual(trade['stop_loss'], expected_adjusted_sl, places=2)
        self.assertEqual(trade['status'], 'OPEN')
        
        # Step 6: Verify complete traceability
        cursor.execute("""
            SELECT 
                t.id as trade_id,
                r.stop_loss as original_rec_sl,
                sa.original_stop_loss,
                sa.adjusted_stop_loss,
                sa.adjustment_value,
                t.stop_loss as executed_sl
            FROM trades t
            LEFT JOIN recommendations r ON t.recommendation_id = r.id
            LEFT JOIN sl_adjustments sa ON r.id = sa.recommendation_id
            WHERE t.id = ?
        """, (trade_id,))
        
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result['trade_id'], trade_id)
        self.assertEqual(result['original_rec_sl'], 49000.0)
        self.assertEqual(result['original_stop_loss'], 49000.0)
        self.assertAlmostEqual(result['adjusted_stop_loss'], expected_adjusted_sl, places=2)
        self.assertEqual(result['adjustment_value'], 2.0)
        self.assertAlmostEqual(result['executed_sl'], expected_adjusted_sl, places=2)
        
        print("\n✅ Full Trading Cycle Test PASSED")
        print(f"  Original SL: {result['original_rec_sl']}")
        print(f"  Adjusted SL: {result['adjusted_stop_loss']}")
        print(f"  Executed SL: {result['executed_sl']}")
        print(f"  Adjustment: {result['adjustment_value']}%")


if __name__ == '__main__':
    unittest.main()

