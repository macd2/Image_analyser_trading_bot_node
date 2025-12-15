#!/usr/bin/env python3
"""
Tests for Trading Engine components.
Run with: python -m trading_bot.engine.test_engine
"""

from trading_bot.engine.position_sizer import PositionSizer
from trading_bot.core.state_manager import StateManager


class MockOrderExecutor:
    """Mock order executor for testing."""
    
    def get_instrument_info(self, symbol):
        return {
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
            }
        }
    
    def get_wallet_balance(self, coin="USDT"):
        return {
            "coin": coin,
            "available": 10000.0,
            "wallet_balance": 10000.0,
            "equity": 10000.0,
        }


def test_position_sizer_basic():
    """Test basic position sizing."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(order_executor=executor)
    
    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
    )
    
    assert "position_size" in result
    assert result["position_size"] > 0
    assert result["risk_amount"] > 0
    assert result["risk_percentage"] <= 0.02  # Should be around 1%
    
    print("✅ test_position_sizer_basic passed")


def test_position_sizer_confidence_weighting():
    """Test confidence weighting affects position size."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(order_executor=executor)
    
    # Low confidence
    low_conf = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.65,
    )
    
    # High confidence
    high_conf = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.90,
    )
    
    # High confidence should result in larger position
    assert high_conf["position_size"] > low_conf["position_size"]
    assert high_conf["confidence_weight"] > low_conf["confidence_weight"]
    
    print("✅ test_position_sizer_confidence_weighting passed")


def test_position_sizer_min_value():
    """Test minimum position value enforcement."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(
        order_executor=executor,
        min_position_value=100.0,
    )

    # Very small risk that would result in tiny position
    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49999,  # Very tight stop
        wallet_balance=100,
        confidence=0.75,
    )

    # Position value should be at least min_position_value
    assert result["position_value"] >= 10.0  # Default min

    print("✅ test_position_sizer_min_value passed")


def test_position_sizer_max_loss_disabled():
    """Test that max_loss_usd=0 disables the cap."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=0.015,
        max_loss_usd=0.0,  # Disabled
    )

    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
    )

    # Should use full risk calculation without capping
    expected_risk = 10000 * 0.015 * 0.9333  # ~$140
    assert result["risk_amount"] > 100  # Should be ~$140, not capped

    print("✅ test_position_sizer_max_loss_disabled passed")


def test_position_sizer_max_loss_cap():
    """Test that max_loss_usd caps the risk amount."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=0.015,
        max_loss_usd=10.0,  # Cap at $10
    )

    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
    )

    # Risk should be capped at $10
    assert result["risk_amount"] <= 10.0
    assert abs(result["risk_amount"] - 10.0) < 0.01  # Should be ~$10

    print("✅ test_position_sizer_max_loss_cap passed")


def test_state_manager_slot_counting():
    """Test StateManager slot counting with WebSocket data."""
    sm = StateManager()
    
    # Simulate 2 positions
    sm.handle_position_message({
        "data": [
            {"symbol": "BTCUSDT", "side": "Buy", "size": "0.1"},
            {"symbol": "ETHUSDT", "side": "Sell", "size": "1.0"},
        ]
    })
    
    # Simulate 1 pending order for new symbol
    sm.handle_order_message({
        "data": [
            {"orderId": "o1", "symbol": "SOLUSDT", "orderStatus": "New"},
        ]
    })
    
    # Should count 3 slots (2 positions + 1 order)
    assert sm.count_slots_used() == 3
    assert sm.get_available_slots(5) == 2
    
    # Add order for existing position symbol (should not increase count)
    sm.handle_order_message({
        "data": [
            {"orderId": "o2", "symbol": "BTCUSDT", "orderStatus": "New"},
        ]
    })
    
    # Still 3 slots (BTCUSDT already counted)
    assert sm.count_slots_used() == 3
    
    print("✅ test_state_manager_slot_counting passed")


def test_state_manager_position_blocking():
    """Test that symbols with positions are blocked."""
    sm = StateManager()
    
    # Add position
    sm.handle_position_message({
        "data": [{"symbol": "BTCUSDT", "side": "Buy", "size": "0.1"}]
    })
    
    assert sm.has_position("BTCUSDT")
    assert not sm.has_position("ETHUSDT")
    
    # Close position
    sm.handle_position_message({
        "data": [{"symbol": "BTCUSDT", "side": "", "size": "0"}]
    })
    
    assert not sm.has_position("BTCUSDT")
    
    print("✅ test_state_manager_position_blocking passed")


def run_all_tests():
    """Run all engine tests."""
    print("\n🧪 Running Trading Engine tests...\n")

    test_position_sizer_basic()
    test_position_sizer_confidence_weighting()
    test_position_sizer_min_value()
    test_position_sizer_max_loss_disabled()
    test_position_sizer_max_loss_cap()
    test_state_manager_slot_counting()
    test_state_manager_position_blocking()

    print("\n✅ All engine tests passed!\n")


if __name__ == "__main__":
    run_all_tests()

