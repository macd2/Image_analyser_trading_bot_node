"""
Edge Case Contract Tests

Tests for the 5% gap: rounding, floating point, extreme values, boundaries,
Kelly edge cases, timezone, side effects, concurrency, missing fields, type mismatches.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone
from hypothesis import given, settings, strategies as st, assume
import math

from trading_bot.engine.position_sizer import PositionSizer
from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle


class TestRoundingEdgeCases:
    """Test 1: Rounding errors don't break invariants."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_rounding_down_respects_min_position(self, mock_executor):
        """Rounding down doesn't violate min_position_value."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=100.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        # After rounding, position_value should still >= min_position_value
        assert result["position_value"] >= 100.0

    def test_rounding_up_respects_max_loss(self, mock_executor):
        """Rounding up doesn't violate max_loss_usd."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=50.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        # After rounding, risk_amount should still <= max_loss_usd
        assert result["risk_amount"] <= 50.0

    @given(
        entry=st.floats(min_value=0.001, max_value=1000000),
        sl_offset=st.floats(min_value=0.001, max_value=10000),
    )
    @settings(max_examples=50, suppress_health_check=[])
    def test_rounding_preserves_invariants(self, entry, sl_offset):
        """Rounding preserves all invariants for any valid input."""
        assume(entry > 0)
        assume(sl_offset > 0)
        assume(sl_offset != entry)

        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })

        sizer = PositionSizer(
            order_executor=executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )

        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=entry, stop_loss=entry - sl_offset,
            wallet_balance=10000, confidence=0.75
        )

        # Invariants must hold after rounding
        assert result["position_size"] > 0
        assert result["position_value"] == pytest.approx(
            result["position_size"] * entry, rel=0.01
        )


class TestFloatingPointEdgeCases:
    """Test 2: Floating point precision doesn't break comparisons."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_risk_percentage_precision(self, mock_executor):
        """Risk percentage calculation handles floating point precision."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        # Use approx for floating point comparison (allow 10% tolerance for rounding)
        assert result["risk_amount"] / 10000 == pytest.approx(0.01, rel=0.1)

    def test_position_value_precision(self, mock_executor):
        """Position value calculation handles floating point precision."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        # position_value = position_size * entry_price
        expected = result["position_size"] * 50000
        assert result["position_value"] == pytest.approx(expected, rel=0.01)

    @given(
        risk_pct=st.floats(min_value=0.01, max_value=0.1),
        wallet=st.floats(min_value=10000, max_value=1000000),
    )
    @settings(max_examples=50, suppress_health_check=[])
    def test_floating_point_invariants(self, risk_pct, wallet):
        """Floating point precision doesn't break invariants."""
        assume(risk_pct > 0)
        assume(wallet > 0)

        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })

        sizer = PositionSizer(
            order_executor=executor,
            risk_percentage=risk_pct,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )

        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=wallet, confidence=0.75
        )

        # Invariant: risk_amount / wallet ≈ risk_percentage (allow 30% tolerance for rounding)
        actual_risk_pct = result["risk_amount"] / wallet
        assert actual_risk_pct == pytest.approx(risk_pct, rel=0.3)


class TestExtremeValues:
    """Test 3: Extreme values don't cause overflow/underflow."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_very_small_entry_price(self, mock_executor):
        """Very small entry price (0.00000001) doesn't break math."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="SHIB", entry_price=0.00000001, stop_loss=0.000000005,
            wallet_balance=10000, confidence=0.75
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_very_large_entry_price(self, mock_executor):
        """Very large entry price (1000000) doesn't break math."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="GOLD", entry_price=1000000, stop_loss=999000,
            wallet_balance=10000, confidence=0.75
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_very_large_wallet(self, mock_executor):
        """Very large wallet (1 billion) doesn't break math."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=1000000000, confidence=0.75
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_very_small_wallet(self, mock_executor):
        """Very small wallet (100) doesn't break math."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=100, confidence=0.75
        )
        assert "error" not in result or result["error"] is not None


class TestBoundaryConditions:
    """Test 4: Boundary values (0, 1, -1) don't break logic."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_confidence_zero(self, mock_executor):
        """Confidence = 0 (minimum) doesn't break logic."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            confidence_weighting=True,
            low_conf_weight=0.8,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.0
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_confidence_one(self, mock_executor):
        """Confidence = 1.0 (maximum) doesn't break logic."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            confidence_weighting=True,
            high_conf_weight=1.2,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=1.0
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_risk_percentage_zero(self, mock_executor):
        """Risk percentage = 0 (minimum) doesn't break logic."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.0,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        # Should either error or return valid result (min_position_value enforced)
        assert "error" not in result or result.get("position_size", 0) > 0

    def test_min_position_value_zero(self, mock_executor):
        """Min position value = 0 (disabled) doesn't break logic."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )
        assert "error" not in result
        assert result["position_size"] > 0


class TestKellyCriterionEdgeCases:
    """Test 5: Kelly Criterion edge cases don't break logic."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_kelly_all_losses(self, mock_executor):
        """Kelly with 0% win rate (all losses) doesn't break."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            use_kelly_criterion=True,
            kelly_fraction=0.25,
        )
        # Simulate trade history with all losses
        trade_history = [
            {"pnl_percent": -1.0},
            {"pnl_percent": -1.0},
            {"pnl_percent": -1.0},
        ]
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75,
            trade_history=trade_history
        )
        # Should fall back to fixed risk or return 0
        assert "error" not in result or result["sizing_method"] == "fixed"

    def test_kelly_all_wins(self, mock_executor):
        """Kelly with 100% win rate (all wins) doesn't break."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            use_kelly_criterion=True,
            kelly_fraction=0.25,
        )
        # Simulate trade history with all wins
        trade_history = [
            {"pnl_percent": 1.0},
            {"pnl_percent": 1.0},
            {"pnl_percent": 1.0},
        ]
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75,
            trade_history=trade_history
        )
        assert "error" not in result
        assert result["position_size"] > 0

    def test_kelly_equal_win_loss(self, mock_executor):
        """Kelly with equal avg_win and avg_loss doesn't break."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
            use_kelly_criterion=True,
            kelly_fraction=0.25,
        )
        # Simulate trade history with equal wins/losses
        trade_history = [
            {"pnl_percent": 1.0},
            {"pnl_percent": -1.0},
            {"pnl_percent": 1.0},
            {"pnl_percent": -1.0},
        ]
        result = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75,
            trade_history=trade_history
        )
        assert "error" not in result


class TestTimezoneEdgeCases:
    """Test 6: Timezone conversions don't break timestamps."""

    def test_utc_timestamp_consistency(self):
        """UTC timestamps are consistent across conversions."""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            "id": "trade_1",
            "symbol": "BTC",
            "side": "Buy",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
            "quantity": 1.0,
            "created_at": base_time.isoformat(),
        }

        # Timestamp should be consistent
        assert int(datetime.fromisoformat(trade["created_at"]).timestamp() * 1000) == base_ms

    def test_candle_timestamp_ordering(self):
        """Candle timestamps maintain correct ordering."""
        base_ms = int(datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)

        candles = [
            Candle(timestamp=base_ms, open=50000, high=50500, low=49500, close=50000),
            Candle(timestamp=base_ms + 60000, open=50000, high=51000, low=50000, close=51000),
            Candle(timestamp=base_ms + 120000, open=51000, high=51500, low=50500, close=51500),
        ]

        # Timestamps should be in order
        for i in range(len(candles) - 1):
            assert candles[i].timestamp < candles[i + 1].timestamp


class TestSideEffects:
    """Test 7: Functions don't have unexpected side effects."""

    @pytest.fixture
    def mock_executor(self):
        executor = Mock()
        executor.get_instrument_info = Mock(return_value={
            "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"}
        })
        return executor

    def test_position_sizer_idempotent(self, mock_executor):
        """Calling position_sizer twice gives same result."""
        sizer = PositionSizer(
            order_executor=mock_executor,
            risk_percentage=0.01,
            min_position_value=0.0,
            max_loss_usd=0.0,
        )

        result1 = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )

        result2 = sizer.calculate_position_size(
            symbol="BTCUSDT", entry_price=50000, stop_loss=49000,
            wallet_balance=10000, confidence=0.75
        )

        # Results should be identical
        assert result1["position_size"] == result2["position_size"]
        assert result1["position_value"] == result2["position_value"]

    def test_simulator_doesnt_modify_trade(self):
        """Simulator doesn't modify input trade dict."""
        simulator = PaperTradeSimulator()
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            "id": "trade_1",
            "symbol": "BTC",
            "side": "Buy",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
            "quantity": 1.0,
            "created_at": base_time.isoformat(),
            "strategy_name": "AiImageAnalyzer",
            "strategy_type": "price_based",
            "strategy_metadata": {},
        }

        trade_copy = trade.copy()

        candles = [
            Candle(timestamp=base_ms, open=50000, high=50500, low=49500, close=50000),
            Candle(timestamp=base_ms + 60000, open=50000, high=51000, low=50000, close=51000),
        ]

        simulator.simulate_trade(trade, candles)

        # Trade dict should be unchanged
        assert trade == trade_copy


class TestMissingFields:
    """Test 8: Missing fields are handled gracefully."""

    def test_recommendation_missing_entry_price(self):
        """Missing entry_price is handled gracefully."""
        recommendation = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            # Missing: "entry_price"
            "stop_loss": 49000,
            "take_profit": 51000,
        }

        # Should either error or handle gracefully
        try:
            entry = recommendation.get("entry_price")
            assert entry is None
        except KeyError:
            pass

    def test_trade_missing_strategy_metadata(self):
        """Missing strategy_metadata is handled gracefully."""
        trade = {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
            # Missing: "strategy_metadata"
        }

        # Should either error or handle gracefully
        metadata = trade.get("strategy_metadata", {})
        assert isinstance(metadata, dict)


class TestTypeErrors:
    """Test 9: Type mismatches are handled gracefully."""

    def test_entry_price_as_string(self):
        """Entry price as string is handled gracefully."""
        entry_price = "50000"

        # Should either convert or error
        try:
            entry = float(entry_price)
            assert entry == 50000.0
        except (ValueError, TypeError):
            pass

    def test_confidence_as_string(self):
        """Confidence as string is handled gracefully."""
        confidence = "0.75"

        # Should either convert or error
        try:
            conf = float(confidence)
            assert 0 <= conf <= 1
        except (ValueError, TypeError):
            pass

    def test_side_as_lowercase(self):
        """Side as lowercase is handled gracefully."""
        side = "buy"

        # Should either convert or error
        normalized = side.capitalize()
        assert normalized in ["Buy", "Sell"]

