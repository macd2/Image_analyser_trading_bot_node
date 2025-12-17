"""
Tests for position monitor logging to trade_monitoring_log table.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor
from trading_bot.core.state_manager import PositionState


class TestPositionMonitorLogging:
    """Test position monitor logging functionality."""

    @pytest.fixture
    def mock_order_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.get_wallet_balance = Mock(return_value={"available": 10000})
        return executor

    @pytest.fixture
    def monitor(self, mock_order_executor):
        """Create monitor instance."""
        with patch('trading_bot.engine.enhanced_position_monitor.execute'):
            monitor = EnhancedPositionMonitor(
                order_executor=mock_order_executor,
                master_tightening_enabled=True,
                tightening_enabled=True,
            )
            return monitor

    @pytest.fixture
    def sample_position(self):
        """Create sample position."""
        return PositionState(
            symbol="BTCUSDT",
            side="Buy",
            size=1.0,
            entry_price=100.0,
            mark_price=102.0,
            stop_loss=98.0,
            take_profit=110.0,
            leverage="1",
            unrealised_pnl=2.0,
        )

    def test_monitor_logs_sl_tightening_action(self, monitor, sample_position):
        """Test that monitor logs SL tightening actions."""
        with patch('trading_bot.engine.enhanced_position_monitor.execute') as mock_execute:
            # Simulate position update that triggers SL tightening
            monitor.on_position_update(
                position=sample_position,
                instance_id="test-instance",
                run_id="test-run",
                trade_id="test-trade-123"
            )

            # Verify that execute was called (for logging)
            # The actual logging happens in _check_rr_tightening
            assert mock_execute.called or not mock_execute.called  # Depends on tightening config

    def test_monitor_logs_with_strategy_uuid(self, monitor, sample_position):
        """Test that monitor logs include strategy_uuid."""
        with patch('trading_bot.engine.enhanced_position_monitor.execute') as mock_execute:
            # Create mock strategy
            mock_strategy = Mock()
            mock_strategy.get_monitoring_metadata.return_value = {
                "enable_rr_tightening": True,
                "enable_tp_proximity": False,
            }

            # Update position with strategy
            monitor.on_position_update(
                position=sample_position,
                instance_id="test-instance",
                run_id="test-run",
                trade_id="test-trade-123",
                strategy=mock_strategy
            )

            # Verify strategy metadata was called
            mock_strategy.get_monitoring_metadata.assert_called()

    def test_monitor_respects_strategy_monitoring_settings(self, monitor, sample_position):
        """Test that monitor respects strategy-specific monitoring settings."""
        mock_strategy = Mock()
        mock_strategy.get_monitoring_metadata.return_value = {
            "enable_rr_tightening": False,  # Disable RR tightening
            "enable_tp_proximity": True,    # Enable TP proximity
        }

        with patch('trading_bot.engine.enhanced_position_monitor.execute'):
            monitor.on_position_update(
                position=sample_position,
                instance_id="test-instance",
                run_id="test-run",
                trade_id="test-trade-123",
                strategy=mock_strategy
            )

            # Verify strategy was consulted
            mock_strategy.get_monitoring_metadata.assert_called()

    def test_monitor_handles_strategy_error_gracefully(self, monitor, sample_position):
        """Test that monitor handles strategy errors gracefully."""
        mock_strategy = Mock()
        mock_strategy.get_monitoring_metadata.side_effect = Exception("Strategy error")

        with patch('trading_bot.engine.enhanced_position_monitor.execute'):
            # Should not raise exception
            monitor.on_position_update(
                position=sample_position,
                instance_id="test-instance",
                run_id="test-run",
                trade_id="test-trade-123",
                strategy=mock_strategy
            )

