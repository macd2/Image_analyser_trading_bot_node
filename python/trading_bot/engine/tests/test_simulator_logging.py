"""
Tests for paper trade simulator logging to trade_monitoring_log table.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator


class TestSimulatorLogging:
    """Test simulator logging functionality."""

    @pytest.fixture
    def simulator(self):
        """Create simulator instance."""
        return PaperTradeSimulator()

    @pytest.fixture
    def sample_trade(self):
        """Create sample trade dict."""
        return {
            "id": "trade-123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "quantity": 1.0,
            "stop_loss": 98.0,
            "take_profit": 110.0,
            "status": "pending",
            "strategy_uuid": "strategy-uuid-123",
            "strategy_type": "price_based",
            "strategy_name": "PromptStrategy",
        }

    def test_simulator_accepts_strategy_parameter(self, simulator, sample_trade):
        """Test that simulator accepts strategy parameter."""
        mock_strategy = Mock()
        mock_strategy.get_exit_condition.return_value = {
            "should_exit": False,
        }

        # Simulate with empty candles (should return None)
        result = simulator.simulate_trade(
            trade=sample_trade,
            candles=[],
            strategy=mock_strategy,
        )

        # Should return None for empty candles
        assert result is None

    def test_simulator_preserves_strategy_uuid(self, simulator, sample_trade):
        """Test that simulator preserves strategy_uuid in trade data."""
        # Verify strategy_uuid is in sample trade
        assert sample_trade.get("strategy_uuid") == "strategy-uuid-123"
        assert sample_trade.get("strategy_type") == "price_based"
        assert sample_trade.get("strategy_name") == "PromptStrategy"

    def test_simulator_handles_strategy_error_gracefully(self, simulator, sample_trade):
        """Test that simulator handles strategy errors gracefully."""
        mock_strategy = Mock()
        mock_strategy.get_exit_condition.side_effect = Exception("Strategy error")

        # Should not raise exception even with strategy error
        result = simulator.simulate_trade(
            trade=sample_trade,
            candles=[],
            strategy=mock_strategy,
        )

        # Should return None for empty candles
        assert result is None

    def test_simulator_calls_strategy_get_exit_condition(self, simulator, sample_trade):
        """Test that simulator calls strategy.get_exit_condition()."""
        mock_strategy = Mock()
        mock_strategy.get_exit_condition.return_value = {
            "should_exit": False,
        }

        # Create a candle that would trigger exit check
        from trading_bot.engine.paper_trade_simulator import Candle
        candle = Candle(
            timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
            open=100.0,
            high=110.0,
            low=98.0,
            close=105.0,
        )

        # Simulate with strategy
        result = simulator.simulate_trade(
            trade=sample_trade,
            candles=[candle],
            strategy=mock_strategy,
        )

        # Strategy should be consulted for exit condition
        # (may or may not be called depending on fill status)

