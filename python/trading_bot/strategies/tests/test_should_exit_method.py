"""
Tests for should_exit() method in strategies.

Tests both price-based (PromptStrategy) and spread-based (CointegrationAnalysisModule)
exit logic to ensure correct exit decisions.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestPromptStrategyShouldExit:
    """Test PromptStrategy.should_exit() for price-based exit logic."""

    def test_should_exit_tp_touched_long(self):
        """Test TP touched for long position."""
        # Create a minimal strategy instance just for testing should_exit
        strategy = Mock(spec=PromptStrategy)
        strategy.should_exit = PromptStrategy.should_exit.__get__(strategy)

        trade = {
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = strategy.should_exit(trade, current_candle)

        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "tp_touched"
        assert result["exit_details"]["price"] == 105.5

    def test_should_exit_sl_touched_long(self):
        """Test SL touched for long position."""
        strategy = Mock(spec=PromptStrategy)
        strategy.should_exit = PromptStrategy.should_exit.__get__(strategy)
        strategy.logger = Mock()

        trade = {
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 97.5}

        result = strategy.should_exit(trade, current_candle)

        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "sl_touched"

    def test_should_exit_tp_touched_short(self):
        """Test TP touched for short position."""
        strategy = Mock(spec=PromptStrategy)
        strategy.should_exit = PromptStrategy.should_exit.__get__(strategy)
        strategy.logger = Mock()

        trade = {
            "entry_price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 95.0,
        }
        current_candle = {"close": 94.5}

        result = strategy.should_exit(trade, current_candle)

        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "tp_touched"

    def test_should_exit_no_exit(self):
        """Test no exit condition met."""
        strategy = Mock(spec=PromptStrategy)
        strategy.should_exit = PromptStrategy.should_exit.__get__(strategy)
        strategy.logger = Mock()

        trade = {
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 101.0}

        result = strategy.should_exit(trade, current_candle)

        assert result["should_exit"] is False
        assert result["exit_details"]["reason"] == "no_exit"

    def test_should_exit_missing_data(self):
        """Test handling of missing data."""
        strategy = Mock(spec=PromptStrategy)
        strategy.should_exit = PromptStrategy.should_exit.__get__(strategy)
        strategy.logger = Mock()

        trade = {
            "entry_price": 100.0,
            # Missing stop_loss and take_profit
        }
        current_candle = {"close": 101.0}

        result = strategy.should_exit(trade, current_candle)

        assert result["should_exit"] is False
        assert "error" in result["exit_details"]


class TestCointegrationShouldExit:
    """Test CointegrationAnalysisModule.should_exit() for spread-based exit logic."""

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

    @pytest.fixture
    def strategy(self, mock_config):
        """Create CointegrationAnalysisModule instance."""
        return CointegrationAnalysisModule(config=mock_config, instance_id="test-instance")

    def test_should_exit_z_score_crossed(self, strategy):
        """Test z-score exit when mean reversion occurs (z-score within threshold)."""
        trade = {
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }
        current_candle = {"close": 100.0}
        pair_candle = {"close": 101.5}  # spread = 101.5 - 1.0*100 = 1.5, z = (1.5 - 0) / 1.0 = 1.5

        result = strategy.should_exit(trade, current_candle, pair_candle)

        # z_score = (101.5 - 1.0*100 - 0.0) / 1.0 = 1.5
        # abs(1.5) <= 2.0, so should exit (mean reversion)
        assert result["should_exit"] is True
        assert result["exit_details"]["reason"] == "z_score_exit"

    def test_should_exit_z_score_not_crossed(self, strategy):
        """Test exit when z-score exceeds threshold (no mean reversion)."""
        trade = {
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }
        current_candle = {"close": 100.0}
        pair_candle = {"close": 105.0}  # spread = 105 - 1.0*100 = 5.0, z = 5.0

        result = strategy.should_exit(trade, current_candle, pair_candle)

        # z_score = (105.0 - 1.0*100 - 0.0) / 1.0 = 5.0
        # abs(5.0) > 2.0, so no exit (z-score still too extreme)
        assert result["should_exit"] is False
        assert result["exit_details"]["reason"] == "no_exit"

    def test_should_exit_missing_metadata(self, strategy):
        """Test handling of missing strategy metadata."""
        trade = {
            "strategy_metadata": {}  # Missing required fields
        }
        current_candle = {"close": 100.0}
        pair_candle = {"close": 150.0}

        result = strategy.should_exit(trade, current_candle, pair_candle)

        assert result["should_exit"] is False
        assert "error" in result["exit_details"]

    def test_should_exit_missing_candle_data(self, strategy):
        """Test handling of missing candle data."""
        trade = {
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }
        current_candle = {}  # Missing close price
        pair_candle = {"close": 150.0}

        result = strategy.should_exit(trade, current_candle, pair_candle)

        assert result["should_exit"] is False
        assert "error" in result["exit_details"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

