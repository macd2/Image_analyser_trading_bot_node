"""Tests for strategy-specific settings loading in ConfigV2."""
import pytest
from unittest.mock import patch, MagicMock
from trading_bot.config.settings_v2 import ConfigV2, TradingConfig


class TestConfigStrategySettings:
    """Test strategy-specific settings loading."""

    def test_load_strategy_specific_settings_empty(self):
        """Test loading strategy-specific settings when none are configured."""
        db_config = {
            'trading.paper_trading': True,
            'trading.auto_approve_trades': False,
        }
        
        result = ConfigV2._load_strategy_specific_settings(db_config)
        
        assert result == {}

    def test_load_strategy_specific_settings_price_based(self):
        """Test loading price_based strategy-specific settings."""
        db_config = {
            'strategy_specific.price_based.enable_position_tightening': True,
            'strategy_specific.price_based.enable_sl_tightening': False,
            'strategy_specific.price_based.min_rr': 2.0,
        }
        
        result = ConfigV2._load_strategy_specific_settings(db_config)
        
        assert 'price_based' in result
        assert result['price_based']['enable_position_tightening'] is True
        assert result['price_based']['enable_sl_tightening'] is False
        assert result['price_based']['min_rr'] == 2.0

    def test_load_strategy_specific_settings_spread_based(self):
        """Test loading spread_based strategy-specific settings."""
        db_config = {
            'strategy_specific.spread_based.enable_spread_monitoring': True,
            'strategy_specific.spread_based.z_score_monitoring_interval': 120,
            'strategy_specific.spread_based.max_spread_deviation': 2.5,
        }
        
        result = ConfigV2._load_strategy_specific_settings(db_config)
        
        assert 'spread_based' in result
        assert result['spread_based']['enable_spread_monitoring'] is True
        assert result['spread_based']['z_score_monitoring_interval'] == 120
        assert result['spread_based']['max_spread_deviation'] == 2.5

    def test_load_strategy_specific_settings_multiple_strategies(self):
        """Test loading settings for multiple strategies."""
        db_config = {
            'strategy_specific.price_based.enable_position_tightening': True,
            'strategy_specific.price_based.min_rr': 1.5,
            'strategy_specific.spread_based.enable_spread_monitoring': False,
            'strategy_specific.spread_based.z_score_monitoring_interval': 60,
        }
        
        result = ConfigV2._load_strategy_specific_settings(db_config)
        
        assert 'price_based' in result
        assert 'spread_based' in result
        assert result['price_based']['enable_position_tightening'] is True
        assert result['price_based']['min_rr'] == 1.5
        assert result['spread_based']['enable_spread_monitoring'] is False
        assert result['spread_based']['z_score_monitoring_interval'] == 60

    def test_load_strategy_specific_settings_mixed_with_other_config(self):
        """Test that strategy-specific settings are extracted correctly from mixed config."""
        db_config = {
            'trading.paper_trading': True,
            'trading.min_rr': 1.0,
            'strategy_specific.price_based.enable_position_tightening': True,
            'strategy_specific.price_based.min_rr': 2.0,
            'bybit.use_testnet': False,
        }
        
        result = ConfigV2._load_strategy_specific_settings(db_config)
        
        # Should only extract strategy_specific keys
        assert 'price_based' in result
        assert result['price_based']['enable_position_tightening'] is True
        assert result['price_based']['min_rr'] == 2.0
        # Should not include other config keys
        assert 'trading' not in result
        assert 'bybit' not in result

