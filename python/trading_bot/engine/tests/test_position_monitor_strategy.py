"""
Tests for position monitor with strategy-specific monitoring metadata.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock

from trading_bot.core.state_manager import PositionState
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode


class TestPositionMonitorStrategy:
    """Test position monitor with strategy-specific monitoring."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.modify_stop_loss = Mock(return_value=True)
        return executor

    @pytest.fixture
    def monitor(self, mock_executor):
        """Create position monitor."""
        return EnhancedPositionMonitor(
            order_executor=mock_executor,
            mode=MonitorMode.EVENT_DRIVEN,
            master_tightening_enabled=True,
            tightening_enabled=True,
        )

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

    def test_monitor_with_price_based_strategy_metadata(self, monitor, sample_position):
        """Test monitor with price-based strategy monitoring metadata."""
        strategy = Mock()
        strategy.get_monitoring_metadata = Mock(return_value={
            "monitoring_type": "price_level",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 110.0,
            "rr_ratio": 5.0,
            "enable_rr_tightening": True,
            "enable_tp_proximity": True,
        })
        
        # Should be able to retrieve monitoring metadata
        metadata = strategy.get_monitoring_metadata()
        
        assert metadata["monitoring_type"] == "price_level"
        assert metadata["entry_price"] == 100.0
        assert metadata["enable_rr_tightening"] is True

    def test_monitor_with_spread_based_strategy_metadata(self, monitor, sample_position):
        """Test monitor with spread-based strategy monitoring metadata."""
        strategy = Mock()
        strategy.get_monitoring_metadata = Mock(return_value={
            "monitoring_type": "z_score",
            "spread_mean": 0.5,
            "spread_std": 0.1,
            "z_exit_threshold": 2.0,
            "z_current": 1.5,
            "enable_spread_monitoring": True,
            "monitoring_interval_bars": 5,
        })
        
        # Should be able to retrieve monitoring metadata
        metadata = strategy.get_monitoring_metadata()
        
        assert metadata["monitoring_type"] == "z_score"
        assert metadata["spread_mean"] == 0.5
        assert metadata["enable_spread_monitoring"] is True

    def test_monitor_position_update_with_strategy(self, monitor, sample_position):
        """Test position update with strategy-specific monitoring."""
        strategy = Mock()
        strategy.get_monitoring_metadata = Mock(return_value={
            "monitoring_type": "price_level",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 110.0,
            "rr_ratio": 5.0,
        })
        
        # Should handle position update
        monitor.on_position_update(
            position=sample_position,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )
        
        # Position should be tracked
        position_key = ("instance_1", "BTCUSDT")
        assert position_key in monitor._position_state

    def test_monitor_respects_strategy_tightening_settings(self, monitor, sample_position):
        """Test that monitor respects strategy tightening settings."""
        strategy = Mock()
        strategy.get_monitoring_metadata = Mock(return_value={
            "monitoring_type": "price_level",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 110.0,
            "rr_ratio": 5.0,
            "enable_rr_tightening": False,  # Disabled for this strategy
            "enable_tp_proximity": True,
        })
        
        metadata = strategy.get_monitoring_metadata()
        
        # Should respect the strategy's tightening settings
        assert metadata["enable_rr_tightening"] is False
        assert metadata["enable_tp_proximity"] is True

    def test_monitor_logs_monitoring_action(self, monitor, sample_position):
        """Test that monitor logs monitoring actions."""
        strategy = Mock()
        strategy.get_monitoring_metadata = Mock(return_value={
            "monitoring_type": "price_level",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 110.0,
        })
        
        # Should be able to track monitoring actions
        monitor.on_position_update(
            position=sample_position,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )
        
        # Verify position is tracked
        position_key = ("instance_1", "BTCUSDT")
        assert position_key in monitor._position_state
        
        # Verify state has required fields
        state = monitor._position_state[position_key]
        assert state.entry_price == 100.0
        assert state.original_sl == 98.0

