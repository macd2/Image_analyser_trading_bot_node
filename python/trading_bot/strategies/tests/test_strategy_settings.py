"""
Tests for strategy-specific settings system.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestStrategySettings:
    """Test strategy-specific settings system."""

    @pytest.fixture
    def mock_config(self):
        """Create mock config."""
        config = Mock()
        config.openai.api_key = "test-key"
        config.bybit.api_key = "test-key"
        config.bybit.api_secret = "test-secret"
        config.bybit.recv_window = 5000
        config.bybit.testnet = False
        config.trading_view.username = "test"
        config.trading_view.password = "test"
        config.trading_view.watchlist_name = "test"
        config.trading_view.chart_save_path = "/tmp"
        return config

    def test_prompt_strategy_get_required_settings(self):
        """Test PromptStrategy.get_required_settings() returns correct schema."""
        settings = PromptStrategy.get_required_settings()
        
        # Verify all required settings are present
        assert "enable_position_tightening" in settings
        assert "enable_sl_tightening" in settings
        assert "rr_tightening_steps" in settings
        assert "min_rr" in settings
        
        # Verify schema structure
        assert settings["enable_position_tightening"]["type"] == "bool"
        assert settings["enable_position_tightening"]["default"] is True
        assert "description" in settings["enable_position_tightening"]

    def test_cointegration_strategy_get_required_settings(self):
        """Test CointegrationAnalysisModule.get_required_settings() returns correct schema."""
        settings = CointegrationAnalysisModule.get_required_settings()
        
        # Verify all required settings are present
        assert "enable_spread_monitoring" in settings
        assert "z_score_monitoring_interval" in settings
        assert "spread_reversion_threshold" in settings
        assert "max_spread_deviation" in settings
        assert "min_z_distance" in settings
        
        # Verify schema structure
        assert settings["enable_spread_monitoring"]["type"] == "bool"
        assert settings["z_score_monitoring_interval"]["type"] == "int"
        assert settings["spread_reversion_threshold"]["type"] == "float"

    def test_get_strategy_specific_settings_returns_defaults(self, mock_config):
        """Test get_strategy_specific_settings() returns defaults when no instance_id."""
        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartSourcer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartCleaner'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartAnalyzer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.BybitAPIManager'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.OpenAI'):
            strategy = PromptStrategy(config=mock_config)
            settings = strategy.get_strategy_specific_settings()

            # Should return defaults
            assert settings["enable_position_tightening"] is True
            assert settings["enable_sl_tightening"] is True
            assert settings["min_rr"] == 1.0

    def test_get_strategy_specific_settings_cointegration_defaults(self, mock_config):
        """Test CointegrationAnalysisModule defaults."""
        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'):
            strategy = CointegrationAnalysisModule(config=mock_config)
            settings = strategy.get_strategy_specific_settings()

            # Should return defaults
            assert settings["enable_spread_monitoring"] is True
            assert settings["z_score_monitoring_interval"] == 60
            assert settings["spread_reversion_threshold"] == 0.1
            assert settings["max_spread_deviation"] == 3.0

    def test_get_strategy_specific_settings_with_instance_id(self, mock_config):
        """Test get_strategy_specific_settings() loads from database."""
        import json

        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartSourcer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartCleaner'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.ChartAnalyzer'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.BybitAPIManager'), \
             patch('trading_bot.strategies.prompt.prompt_strategy.OpenAI'), \
             patch('trading_bot.db.client.get_connection') as mock_get_conn, \
             patch('trading_bot.db.client.release_connection') as mock_release_conn, \
             patch('trading_bot.db.client.query_one') as mock_query_one:

            # Mock database response
            mock_query_one.return_value = {
                'settings': json.dumps({
                    'strategy_specific': {
                        'price_based': {
                            'enable_position_tightening': False,
                            'min_rr': 2.0,
                        }
                    }
                })
            }

            strategy = PromptStrategy(config=mock_config, instance_id="test-instance")
            settings = strategy.get_strategy_specific_settings()

            # Should load from database
            assert settings["enable_position_tightening"] is False
            assert settings["min_rr"] == 2.0
            # Should still have defaults for missing settings
            assert settings["enable_sl_tightening"] is True

