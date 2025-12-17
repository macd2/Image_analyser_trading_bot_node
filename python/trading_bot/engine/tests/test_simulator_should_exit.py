"""
Tests for simulator using strategy.should_exit() method.

Verifies that the simulator correctly calls should_exit() and exits trades
at the right times for both price-based and spread-based strategies.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle


class TestSimulatorShouldExit:
    """Test simulator integration with strategy.should_exit()."""

    @pytest.fixture
    def simulator(self):
        """Create simulator instance."""
        return PaperTradeSimulator()

    @pytest.fixture
    def sample_candles(self):
        """Create sample candles."""
        base_time = int(datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        return [
            Candle(timestamp=base_time, open=100, high=102, low=99, close=100),
            Candle(timestamp=base_time + 60000, open=100, high=105, low=99, close=104),
            Candle(timestamp=base_time + 120000, open=104, high=106, low=103, close=105),
        ]

    def test_simulator_calls_should_exit_for_price_based(self, simulator, sample_candles):
        """Test simulator calls should_exit() for price-based strategy."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": {"reason": "tp_touched", "price": 105.0}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 105.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }

        result = simulator.simulate_trade(trade, sample_candles, mock_strategy)

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify trade was closed
        assert result is not None
        assert result["status"] == "closed"

    def test_simulator_calls_should_exit_for_spread_based(self, simulator, sample_candles):
        """Test simulator calls should_exit() for spread-based strategy."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": {
                "reason": "z_score_exit",
                "z_score": 2.5,
                "threshold": 2.0,
            }
        })

        trade = {
            "id": "trade_1",
            "symbol": "RENDER",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 105.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }

        result = simulator.simulate_trade(trade, sample_candles, mock_strategy)

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify trade was closed
        assert result is not None
        assert result["status"] == "closed"

    def test_simulator_stores_exit_details(self, simulator, sample_candles):
        """Test simulator stores exit_details from should_exit()."""
        exit_details = {
            "reason": "tp_touched",
            "price": 105.0,
            "tp": 105.0,
            "sl": 98.0,
            "distance_to_tp": 0.0,
            "distance_to_sl": 7.0,
        }

        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": exit_details
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 105.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }

        result = simulator.simulate_trade(trade, sample_candles, mock_strategy)

        # Verify exit_details are stored
        assert result is not None
        assert result["exit_details"] == exit_details
        assert result["exit_reason"] == "tp_touched"

    def test_simulator_handles_should_exit_error(self, simulator, sample_candles):
        """Test simulator handles errors from should_exit()."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(side_effect=Exception("Strategy error"))

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 105.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }

        # Should not raise exception
        result = simulator.simulate_trade(trade, sample_candles, mock_strategy)

        # Should return None or filled status (not closed)
        assert result is None or result["status"] == "filled"

    def test_simulator_no_exit_when_should_exit_false(self, simulator, sample_candles):
        """Test simulator doesn't exit when should_exit returns False."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": False,
            "exit_details": {"reason": "no_exit"}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 100.0,
            "take_profit": 105.0,
            "stop_loss": 98.0,
            "quantity": 1.0,
            "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        }

        result = simulator.simulate_trade(trade, sample_candles, mock_strategy)

        # Should be filled but not closed
        assert result is not None
        assert result["status"] == "filled"
        assert result["exit_price"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

