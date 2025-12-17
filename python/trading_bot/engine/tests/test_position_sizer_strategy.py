"""
Tests for position sizer with strategy-specific risk metrics.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock

from trading_bot.engine.position_sizer import PositionSizer


class TestPositionSizerStrategy:
    """Test position sizer with strategy-specific risk calculation."""

    @pytest.fixture
    def mock_order_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.get_wallet_balance = Mock(return_value={"available": 10000})
        executor.get_instrument_info = Mock(return_value={
            "min_qty": 0.001,
            "max_qty": 1000,
            "qty_step": 0.001,
        })
        return executor

    @pytest.fixture
    def position_sizer(self, mock_order_executor):
        """Create position sizer."""
        return PositionSizer(
            order_executor=mock_order_executor,
            risk_percentage=2.0,
            min_position_value=0,
            max_loss_usd=1000,
            confidence_weighting=False,
            use_kelly_criterion=False,
        )

    def test_calculate_position_size_with_price_based_strategy(self, position_sizer):
        """Test position sizing with price-based strategy."""
        strategy = Mock()
        strategy.calculate_risk_metrics = Mock(return_value={
            "risk_per_unit": 100.0,
            "reward_per_unit": 150.0,
            "risk_reward_ratio": 1.5,
        })
        
        result = position_sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=100.0,
            stop_loss=95.0,
            wallet_balance=10000,
            confidence=0.8,
            strategy=strategy,
        )
        
        # Should call strategy's calculate_risk_metrics
        strategy.calculate_risk_metrics.assert_called_once()
        
        # Should have position size calculated
        assert "position_size" in result
        assert result["position_size"] > 0
        assert "error" not in result

    def test_calculate_position_size_with_spread_based_strategy(self, position_sizer):
        """Test position sizing with spread-based strategy."""
        strategy = Mock()
        strategy.calculate_risk_metrics = Mock(return_value={
            "z_distance_to_sl": 2.5,
            "z_distance_to_tp": 3.0,
            "spread_volatility": 0.05,
            "risk_per_unit": 50.0,  # Spread-based risk
        })
        
        result = position_sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=100.0,
            stop_loss=95.0,
            wallet_balance=10000,
            confidence=0.8,
            strategy=strategy,
        )
        
        # Should call strategy's calculate_risk_metrics
        strategy.calculate_risk_metrics.assert_called_once()
        
        # Should have position size calculated
        assert "position_size" in result
        assert result["position_size"] > 0
        assert "error" not in result

    def test_calculate_position_size_without_strategy_fallback(self, position_sizer):
        """Test position sizing without strategy (fallback)."""
        result = position_sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=100.0,
            stop_loss=95.0,
            wallet_balance=10000,
            confidence=0.8,
            strategy=None,
        )
        
        # Should use fallback calculation
        assert "position_size" in result
        assert result["position_size"] > 0
        assert "error" not in result

    def test_calculate_position_size_strategy_error_handling(self, position_sizer):
        """Test position sizing when strategy returns error."""
        strategy = Mock()
        strategy.calculate_risk_metrics = Mock(return_value={
            "error": "Invalid signal for spread-based strategy"
        })
        
        result = position_sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=100.0,
            stop_loss=95.0,
            wallet_balance=10000,
            confidence=0.8,
            strategy=strategy,
        )
        
        # Should propagate error
        assert "error" in result
        assert "Invalid signal" in result["error"]

    def test_calculate_position_size_respects_risk_percentage(self, position_sizer):
        """Test that position sizing respects configured risk percentage."""
        strategy = Mock()
        strategy.calculate_risk_metrics = Mock(return_value={
            "risk_per_unit": 100.0,
            "reward_per_unit": 150.0,
            "risk_reward_ratio": 1.5,
        })

        result = position_sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=100.0,
            stop_loss=95.0,
            wallet_balance=10000,
            confidence=0.8,
            strategy=strategy,
        )

        # Should have calculated position size
        assert "position_size" in result
        assert result["position_size"] > 0
        # Risk amount should be positive
        assert result["risk_amount"] > 0
        # Should not have error
        assert "error" not in result

