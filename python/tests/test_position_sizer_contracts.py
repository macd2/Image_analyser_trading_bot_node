"""Position Sizer Contract Tests"""

import pytest
from unittest.mock import Mock
from hypothesis import given, settings, strategies as st

from trading_bot.engine.position_sizer import PositionSizer


class TestPositionSizerContract:
    """Test position sizer contracts."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    @pytest.fixture
    def sizer(self, mock_executor):
        return PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=50.0,
            max_loss_usd=0.0,
            confidence_weighting=False,
            use_kelly_criterion=False,
        )

    def test_basic_long_trade(self, sizer):
        """Test case 1: Basic long trade with 1% risk."""
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=49000,
            wallet_balance=10000,
            confidence=0.75,
        )
        assert "error" not in result
        assert result["position_size"] > 0
        assert result["risk_amount"] > 0
        assert result["position_value"] >= 50.0

    def test_short_trade(self, sizer):
        """Test case 2: Short trade (SL > entry)."""
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=51000,
            wallet_balance=10000,
            confidence=0.75,
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_min_position_value(self, sizer):
        """Test case 3: Minimum position value enforced."""
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=49000,
            wallet_balance=10000,
            confidence=0.75,
        )
        assert result["position_value"] >= 50.0

    def test_max_loss_cap(self, mock_executor):
        """Test case 4: Max loss USD cap enforced."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=50.0,
            confidence_weighting=False,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=49000,
            wallet_balance=10000,
            confidence=0.75,
        )
        assert result["risk_amount"] <= 50.0

    def test_confidence_low(self, mock_executor):
        """Test case 5: Low confidence reduces position."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            confidence_weighting=True,
            low_conf_threshold=0.70,
            low_conf_weight=0.8,
            high_conf_threshold=0.85,
            high_conf_weight=1.2,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=49000,
            wallet_balance=10000,
            confidence=0.60,
        )
        assert result["confidence_weight"] == pytest.approx(0.8, rel=0.01)

    def test_confidence_high(self, mock_executor):
        """Test case 6: High confidence increases position."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            confidence_weighting=True,
            low_conf_threshold=0.70,
            low_conf_weight=0.8,
            high_conf_threshold=0.85,
            high_conf_weight=1.2,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=50000,
            stop_loss=49000,
            wallet_balance=10000,
            confidence=0.95,
        )
        assert result["confidence_weight"] == pytest.approx(1.2, rel=0.01)

    @given(
        entry_price=st.floats(min_value=100, max_value=100000),
        sl_offset=st.floats(min_value=1, max_value=10000),
        wallet_balance=st.floats(min_value=1000, max_value=1000000),
    )
    @settings(max_examples=30, suppress_health_check=[])
    def test_invariants(self, entry_price, sl_offset, wallet_balance):
        """Test invariants hold for any valid input."""
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        sizer = PositionSizer(
            order_executor=executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            confidence_weighting=False,
        )
        stop_loss = entry_price - sl_offset
        result = sizer.calculate_position_size(
            symbol="BTCUSDT",
            entry_price=entry_price,
            stop_loss=stop_loss,
            wallet_balance=wallet_balance,
            confidence=0.75,
        )
        assert "error" not in result
        assert result["position_value"] == pytest.approx(
            result["position_size"] * entry_price, rel=0.01
        )
        assert result["risk_percentage"] == pytest.approx(
            result["risk_amount"] / wallet_balance, rel=0.01
        )
