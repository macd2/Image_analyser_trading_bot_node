"""
Integration tests for SL Adjustment feature.
Tests the complete flow: recommendation → adjustment → database recording.
"""

import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sqlite3
import json

from trading_bot.services.sl_adjuster import StopLossAdjuster
from trading_bot.db.client import get_connection, execute, query
import trading_bot.db.client as db_client


class TestSLAdjusterIntegration(unittest.TestCase):
    """Integration tests for SL adjustment with real database"""

    @classmethod
    def setUpClass(cls):
        """Set up test database"""
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        cls.db_path = cls.temp_db.name
        cls.temp_db.close()

        # Create schema
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()

        # Create recommendations table
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

        # Create sl_adjustments table
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
        # Patch DB_TYPE in the db_client module where it's used
        db_client.DB_TYPE = 'sqlite'

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.adjuster = StopLossAdjuster(self.conn)

    def tearDown(self):
        """Clean up after tests"""
        self.conn.close()

    def test_end_to_end_long_adjustment(self):
        """Test complete flow: adjust recommendation and record to DB"""
        recommendation = {
            'recommendation_id': 'rec_e2e_long',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 1.5,
            'trading.sl_adjustment_short_pct': 1.0,
        }

        # Apply adjustment
        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Verify adjustment was applied
        self.assertIsNotNone(adjustment_record)
        self.assertAlmostEqual(adjusted_rec['stop_loss'], 94.925, places=3)
        self.assertEqual(adjustment_record['adjustment_value'], 1.5)

        # Verify record was written to database
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM sl_adjustments WHERE recommendation_id = ?",
            (recommendation['recommendation_id'],)
        )
        db_record = cursor.fetchone()
        
        self.assertIsNotNone(db_record)
        self.assertEqual(db_record['recommendation_id'], 'rec_e2e_long')
        self.assertAlmostEqual(db_record['original_stop_loss'], 95.0, places=3)
        self.assertAlmostEqual(db_record['adjusted_stop_loss'], 94.925, places=3)
        self.assertEqual(db_record['adjustment_value'], 1.5)

    def test_end_to_end_short_adjustment(self):
        """Test complete flow for SHORT trade"""
        recommendation = {
            'recommendation_id': 'rec_e2e_short',
            'symbol': 'ETHUSDT',
            'recommendation': 'SHORT',
            'entry_price': 100.0,
            'stop_loss': 105.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 1.0,
            'trading.sl_adjustment_short_pct': 2.0,
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Verify adjustment
        self.assertIsNotNone(adjustment_record)
        self.assertAlmostEqual(adjusted_rec['stop_loss'], 105.1, places=3)

        # Verify database record
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM sl_adjustments WHERE recommendation_id = ?",
            (recommendation['recommendation_id'],)
        )
        db_record = cursor.fetchone()
        
        self.assertIsNotNone(db_record)
        self.assertAlmostEqual(db_record['adjusted_stop_loss'], 105.1, places=3)

    def test_traceability_query(self):
        """Test that we can trace adjustment back to recommendation"""
        # Insert recommendation
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO recommendations 
            (id, cycle_id, symbol, recommendation, entry_price, stop_loss, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('rec_trace', 'cyc_123', 'BTCUSDT', 'LONG', 100.0, 95.0, 0.85))
        self.conn.commit()

        # Apply adjustment
        recommendation = {
            'recommendation_id': 'rec_trace',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 1.5,
            'trading.sl_adjustment_short_pct': 1.5,
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Query to trace adjustment
        cursor.execute("""
            SELECT 
                r.id as rec_id,
                r.symbol,
                r.entry_price,
                r.stop_loss as original_sl,
                sa.original_stop_loss,
                sa.adjusted_stop_loss,
                sa.adjustment_value
            FROM recommendations r
            LEFT JOIN sl_adjustments sa ON r.id = sa.recommendation_id
            WHERE r.id = ?
        """, ('rec_trace',))
        
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result['rec_id'], 'rec_trace')
        self.assertEqual(result['symbol'], 'BTCUSDT')
        self.assertAlmostEqual(result['adjusted_stop_loss'], 94.925, places=3)


if __name__ == '__main__':
    unittest.main()

