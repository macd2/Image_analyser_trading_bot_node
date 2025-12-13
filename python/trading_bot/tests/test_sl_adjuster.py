"""
Unit tests for StopLossAdjuster service.
Tests pre-execution SL adjustment functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from trading_bot.services.sl_adjuster import StopLossAdjuster


class TestStopLossAdjuster(unittest.TestCase):
    """Test cases for StopLossAdjuster"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_db = Mock()
        self.adjuster = StopLossAdjuster(self.mock_db)

    def test_adjustment_disabled(self):
        """Test that no adjustment happens when disabled"""
        recommendation = {
            'recommendation_id': 'rec_123',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'sl_adjustment': {'enabled': False}
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        self.assertEqual(adjusted_rec['stop_loss'], 95.0)
        self.assertIsNone(adjustment_record)

    def test_long_adjustment(self):
        """Test SL widening for LONG trades"""
        recommendation = {
            'recommendation_id': 'rec_123',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'sl_adjustment': {
                'enabled': True,
                'type': 'percentage',
                'long_adjustment': 1.5,
                'short_adjustment': 1.5,
            }
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Risk = 100 - 95 = 5
        # Adjustment = 5 * 1.5% = 0.075
        # Adjusted SL = 95 - 0.075 = 94.925
        expected_sl = 94.925
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_sl, places=3)
        self.assertIsNotNone(adjustment_record)
        self.assertEqual(adjustment_record['adjustment_value'], 1.5)

    def test_short_adjustment(self):
        """Test SL widening for SHORT trades"""
        recommendation = {
            'recommendation_id': 'rec_456',
            'symbol': 'ETHUSDT',
            'recommendation': 'SHORT',
            'entry_price': 100.0,
            'stop_loss': 105.0,
        }
        instance_settings = {
            'sl_adjustment': {
                'enabled': True,
                'type': 'percentage',
                'long_adjustment': 1.0,
                'short_adjustment': 2.0,
            }
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Risk = 105 - 100 = 5
        # Adjustment = 5 * 2.0% = 0.1
        # Adjusted SL = 105 + 0.1 = 105.1 (move UP for shorts)
        expected_sl = 105.1
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_sl, places=3)
        self.assertIsNotNone(adjustment_record)
        self.assertEqual(adjustment_record['adjustment_value'], 2.0)

    def test_no_adjustment_for_hold(self):
        """Test that HOLD signals don't get adjusted"""
        recommendation = {
            'recommendation_id': 'rec_789',
            'symbol': 'XRPUSDT',
            'recommendation': 'HOLD',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'sl_adjustment': {
                'enabled': True,
                'type': 'percentage',
                'long_adjustment': 1.5,
                'short_adjustment': 1.5,
            }
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        self.assertEqual(adjusted_rec['stop_loss'], 95.0)
        self.assertIsNone(adjustment_record)

    def test_zero_adjustment_value(self):
        """Test that zero adjustment value is skipped"""
        recommendation = {
            'recommendation_id': 'rec_000',
            'symbol': 'ADAUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'sl_adjustment': {
                'enabled': True,
                'type': 'percentage',
                'long_adjustment': 0,
                'short_adjustment': 0,
            }
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        self.assertEqual(adjusted_rec['stop_loss'], 95.0)
        self.assertIsNone(adjustment_record)

    def test_missing_entry_price(self):
        """Test handling of missing entry price"""
        recommendation = {
            'recommendation_id': 'rec_bad',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'stop_loss': 95.0,
        }
        instance_settings = {
            'sl_adjustment': {
                'enabled': True,
                'type': 'percentage',
                'long_adjustment': 1.5,
                'short_adjustment': 1.5,
            }
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        self.assertIsNone(adjustment_record)

    def test_flat_config_format_long(self):
        """Test SL adjustment with new flat config format (LONG)"""
        recommendation = {
            'recommendation_id': 'rec_flat',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 2.0,
            'trading.sl_adjustment_short_pct': 1.0,
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Risk = 100 - 95 = 5
        # Adjustment = 5 * 2.0% = 0.1
        # Adjusted SL = 95 - 0.1 = 94.9
        expected_sl = 94.9
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_sl, places=3)
        self.assertIsNotNone(adjustment_record)
        self.assertEqual(adjustment_record['adjustment_value'], 2.0)

    def test_flat_config_format_short(self):
        """Test SL adjustment with new flat config format (SHORT)"""
        recommendation = {
            'recommendation_id': 'rec_flat_short',
            'symbol': 'ETHUSDT',
            'recommendation': 'SHORT',
            'entry_price': 100.0,
            'stop_loss': 105.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': True,
            'trading.sl_adjustment_long_pct': 1.0,
            'trading.sl_adjustment_short_pct': 2.5,
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        # Risk = 105 - 100 = 5
        # Adjustment = 5 * 2.5% = 0.125
        # Adjusted SL = 105 + 0.125 = 105.125
        expected_sl = 105.125
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_sl, places=3)
        self.assertIsNotNone(adjustment_record)
        self.assertEqual(adjustment_record['adjustment_value'], 2.5)

    def test_flat_config_format_string_values(self):
        """Test SL adjustment with string values in flat config format"""
        recommendation = {
            'recommendation_id': 'rec_str',
            'symbol': 'BTCUSDT',
            'recommendation': 'LONG',
            'entry_price': 100.0,
            'stop_loss': 95.0,
        }
        instance_settings = {
            'trading.sl_adjustment_enabled': 'true',  # String instead of bool
            'trading.sl_adjustment_long_pct': '1.5',  # String instead of float
            'trading.sl_adjustment_short_pct': '1.5',
        }

        adjusted_rec, adjustment_record = self.adjuster.adjust_recommendation(
            recommendation, instance_settings
        )

        expected_sl = 94.925
        self.assertAlmostEqual(adjusted_rec['stop_loss'], expected_sl, places=3)
        self.assertIsNotNone(adjustment_record)


if __name__ == '__main__':
    unittest.main()

