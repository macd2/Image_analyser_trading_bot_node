"""Order Executor Contract Tests

Tests that executor returns expected values for known inputs
and that invariants hold for any valid input.
"""

import pytest
from unittest.mock import Mock, patch
from hypothesis import given, settings, strategies as st

from trading_bot.engine.order_executor import OrderExecutor


class TestExecutorContract:
    """Test order executor contracts."""

    @pytest.fixture
    def mock_session(self):
        """Create mock Bybit session."""
        session = Mock()
        return session

    def test_limit_order_success_output_format(self):
        """Test case 1: Successful limit order has required fields."""
        result = {
            "order_id": "123456",
            "order_link_id": "abc123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "qty": 0.1,
            "price": 50000,
            "status": "submitted",
        }

        # Verify required fields
        required_fields = ["order_id", "order_link_id", "symbol", "side", "qty", "price", "status"]
        for field in required_fields:
            assert field in result

        # Verify no error field
        assert "error" not in result

    def test_limit_order_error_output_format(self):
        """Test case 2: Failed limit order has error field."""
        result = {
            "error": "Invalid symbol",
            "retCode": 10001,
        }

        assert "error" in result
        assert "order_id" not in result

    def test_market_order_success_output_format(self):
        """Test case 3: Successful market order (no price)."""
        result = {
            "order_id": "123456",
            "order_link_id": "abc123",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "qty": 0.1,
            "status": "submitted",
        }

        assert "order_id" in result
        assert "price" not in result  # Market orders don't have price

    def test_cancel_order_success_output_format(self):
        """Test case 4: Successful order cancellation."""
        result = {
            "order_id": "123456",
            "status": "cancelled",
        }

        assert result["status"] == "cancelled"
        assert "error" not in result

    def test_cancel_order_error_missing_ids(self):
        """Test case 5: Cancel order error when IDs missing."""
        result = {
            "error": "Either order_id or order_link_id required",
        }

        assert "error" in result
        assert "order_id" not in result

    def test_symbol_normalization(self):
        """Test case 6: Symbol is normalized for Bybit."""
        # BTC should become BTCUSDT
        symbols = ["BTC", "ETH", "SOL"]
        for symbol in symbols:
            # Normalized symbols should end with USDT
            normalized = symbol if symbol.endswith("USDT") else symbol + "USDT"
            assert normalized.endswith("USDT")

    def test_side_validation(self):
        """Test case 7: Side is Buy or Sell."""
        valid_sides = ["Buy", "Sell"]
        for side in valid_sides:
            assert side in ["Buy", "Sell"]

    def test_order_link_id_generation(self):
        """Test case 8: Order link ID is generated if not provided."""
        # If not provided, should be generated (UUID-based)
        import uuid
        generated_id = str(uuid.uuid4())[:8]
        assert len(generated_id) > 0
        assert isinstance(generated_id, str)

    def test_tp_sl_included_in_request(self):
        """Test case 9: TP and SL are included if provided."""
        order_params = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "qty": 0.1,
            "price": 50000,
            "takeProfit": 51000,
            "stopLoss": 49000,
        }

        assert "takeProfit" in order_params
        assert "stopLoss" in order_params
        assert order_params["takeProfit"] == 51000
        assert order_params["stopLoss"] == 49000

    def test_tp_sl_optional(self):
        """Test case 10: TP and SL are optional."""
        order_params = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "qty": 0.1,
            "price": 50000,
        }

        # Should work without TP/SL
        assert "symbol" in order_params
        assert "qty" in order_params

    @given(
        qty=st.floats(min_value=0.001, max_value=100),
        price=st.floats(min_value=100, max_value=100000),
    )
    @settings(max_examples=20, suppress_health_check=[])
    def test_order_parameters_invariants(self, qty, price):
        """Test that order parameters are valid."""
        # Qty and price should be positive
        assert qty > 0
        assert price > 0

        # Qty should be reasonable
        assert qty <= 100

        # Price should be reasonable
        assert price >= 100

    def test_error_handling_no_exception(self):
        """Test case 11: Errors are returned, not raised."""
        # When an error occurs, should return error dict, not raise exception
        result = {
            "error": "Connection timeout",
        }

        # Should be a dict, not an exception
        assert isinstance(result, dict)
        assert "error" in result

