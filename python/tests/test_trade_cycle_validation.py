"""
Tests for Trade Cycle Validation Module.

Tests that validation prevents silent failures and catches all missing/invalid data.
"""

import pytest
from python.trading_bot.core.trade_cycle_validator import (
    SignalValidator,
    TradeExecutionValidator,
    CycleValidator,
    TradeCycleValidationError,
)


class TestSignalValidator:
    """Test signal validation."""
    
    def test_valid_signal(self):
        """Valid signal should pass."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "confidence": 0.8,
        }
        is_valid, error = SignalValidator.validate_signal_for_execution(
            signal, "BTCUSDT", "cycle_123"
        )
        assert is_valid is True
        assert error is None
    
    def test_missing_required_field(self):
        """Missing required field should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            # Missing stop_loss
            "confidence": 0.8,
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        assert "stop_loss" in str(exc_info.value)
    
    def test_none_field_value(self):
        """None field value should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": None,  # None value
            "confidence": 0.8,
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        assert "cannot be None" in str(exc_info.value)
    
    def test_invalid_price_type(self):
        """Invalid price type should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": "100.0",  # String instead of float
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "confidence": 0.8,
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        assert "must be" in str(exc_info.value)
    
    def test_invalid_confidence(self):
        """Confidence outside 0-1 should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "confidence": 1.5,  # Invalid
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        assert "Confidence" in str(exc_info.value)
    
    def test_entry_equals_stop_loss(self):
        """Entry price equal to stop loss should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 100.0,  # Same as entry
            "confidence": 0.8,
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        assert "cannot equal" in str(exc_info.value)
    
    def test_spread_based_missing_fields(self):
        """Spread-based signal missing units should raise error."""
        signal = {
            "recommendation": "BUY",
            "entry_price": 100.0,
            "take_profit": 110.0,
            "stop_loss": 90.0,
            "confidence": 0.8,
            "strategy_type": "spread_based",
            # Missing units_x, units_y, pair_symbol
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            SignalValidator.validate_signal_for_execution(signal, "BTCUSDT", "cycle_123")
        error_msg = str(exc_info.value).lower()
        assert "spread" in error_msg or "units" in error_msg


class TestTradeExecutionValidator:
    """Test trade execution result validation."""
    
    def test_valid_execution_result(self):
        """Valid execution result should pass."""
        result = {
            "id": "trade_123",
            "status": "paper_trade",
            "symbol": "BTCUSDT",
        }
        is_valid, error = TradeExecutionValidator.validate_trade_execution_result(
            result, "BTCUSDT", "cycle_123"
        )
        assert is_valid is True
        assert error is None
    
    def test_missing_status(self):
        """Missing status should raise error."""
        result = {
            "id": "trade_123",
            "symbol": "BTCUSDT",
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            TradeExecutionValidator.validate_trade_execution_result(
                result, "BTCUSDT", "cycle_123"
            )
        assert "status" in str(exc_info.value)
    
    def test_invalid_status(self):
        """Invalid status should raise error."""
        result = {
            "id": "trade_123",
            "status": "invalid_status",
            "symbol": "BTCUSDT",
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            TradeExecutionValidator.validate_trade_execution_result(
                result, "BTCUSDT", "cycle_123"
            )
        assert "Invalid" in str(exc_info.value)
    
    def test_rejected_without_error_reason(self):
        """Rejected trade without error reason should raise error."""
        result = {
            "id": "trade_123",
            "status": "rejected",
            # Missing error field
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            TradeExecutionValidator.validate_trade_execution_result(
                result, "BTCUSDT", "cycle_123"
            )
        assert "error" in str(exc_info.value).lower()
    
    def test_successful_without_trade_id(self):
        """Successful trade without ID should raise error."""
        result = {
            "status": "paper_trade",
            # Missing id
        }
        with pytest.raises(TradeCycleValidationError) as exc_info:
            TradeExecutionValidator.validate_trade_execution_result(
                result, "BTCUSDT", "cycle_123"
            )
        assert "trade ID" in str(exc_info.value)


class TestCycleValidator:
    """Test cycle state validation."""
    
    def test_valid_cycle_state(self):
        """Valid cycle state should pass."""
        signals = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        is_valid, error = CycleValidator.validate_cycle_state(
            "cycle_123", signals, 5
        )
        assert is_valid is True
        assert error is None
    
    def test_more_signals_than_slots(self):
        """More signals than available slots should raise error."""
        signals = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        with pytest.raises(TradeCycleValidationError) as exc_info:
            CycleValidator.validate_cycle_state("cycle_123", signals, 1)
        assert "slots" in str(exc_info.value).lower()
    
    def test_invalid_cycle_id(self):
        """Invalid cycle ID should raise error."""
        signals = []
        with pytest.raises(TradeCycleValidationError) as exc_info:
            CycleValidator.validate_cycle_state(None, signals, 5)
        assert "cycle_id" in str(exc_info.value).lower()

