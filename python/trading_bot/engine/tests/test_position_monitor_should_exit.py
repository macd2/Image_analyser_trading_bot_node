"""
Tests for position monitor using strategy.should_exit() method.

Verifies that the position monitor correctly calls should_exit() and
handles exit decisions for both price-based and spread-based strategies.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode


class TestPositionMonitorShouldExit:
    """Test position monitor integration with strategy.should_exit()."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.set_trading_stop = Mock(return_value={})
        return executor

    @pytest.fixture
    def monitor(self, mock_executor):
        """Create position monitor instance."""
        return EnhancedPositionMonitor(
            order_executor=mock_executor,
            mode=MonitorMode.EVENT_DRIVEN,
            master_tightening_enabled=True,
        )

    def test_check_strategy_exit_price_based(self, monitor):
        """Test check_strategy_exit() for price-based strategy."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": {"reason": "tp_touched", "price": 105.0}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify exit result
        assert result is not None
        assert result["should_exit"] is True
        assert result["exit_reason"] == "tp_touched"

    def test_check_strategy_exit_spread_based(self, monitor):
        """Test check_strategy_exit() for spread-based strategy."""
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
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }
        current_candle = {"close": 100.0}
        pair_candle = {"close": 150.0}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            pair_candle=pair_candle,
            strategy=mock_strategy,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify exit result
        assert result is not None
        assert result["should_exit"] is True
        assert result["exit_reason"] == "z_score_exit"

    def test_check_strategy_exit_no_exit(self, monitor):
        """Test check_strategy_exit() when no exit condition met."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": False,
            "exit_details": {"reason": "no_exit"}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 101.0}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Should return None when no exit
        assert result is None

    def test_check_strategy_exit_no_strategy(self, monitor):
        """Test check_strategy_exit() without strategy."""
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=None,
        )

        # Should return None when no strategy
        assert result is None

    def test_check_strategy_exit_handles_error(self, monitor):
        """Test check_strategy_exit() handles errors gracefully."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(side_effect=Exception("Strategy error"))

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        # Should not raise exception
        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Should return None on error
        assert result is None

    def test_check_strategy_exit_stores_exit_details(self, monitor):
        """Test check_strategy_exit() stores exit_details."""
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
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Verify exit_details are stored
        assert result is not None
        assert result["exit_details"] == exit_details


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

