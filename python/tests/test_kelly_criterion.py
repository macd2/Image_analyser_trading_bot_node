"""
Tests for Kelly Criterion position sizing.
"""

import pytest
from trading_bot.engine.position_sizer import PositionSizer
from trading_bot.engine.order_executor import OrderExecutor


class MockOrderExecutor:
    """Mock OrderExecutor for testing."""
    
    def get_instrument_info(self, symbol: str):
        """Return mock instrument info."""
        return {
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001"
            }
        }


def test_kelly_criterion_disabled():
    """Test that Kelly is not used when disabled - uses configured risk percentage."""
    executor = MockOrderExecutor()
    configured_risk = 0.02  # 2% configured risk
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=configured_risk,
        use_kelly_criterion=False,
    )

    # Should use the configured risk percentage (not hardcoded 1%)
    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
    )

    assert result["sizing_method"] == "fixed"
    assert result["risk_pct_used"] == configured_risk  # Uses configured value


def test_kelly_criterion_insufficient_history():
    """Test Kelly fallback with insufficient trade history - uses configured risk."""
    executor = MockOrderExecutor()
    configured_risk = 0.015  # 1.5% configured risk
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=configured_risk,
        use_kelly_criterion=True,
        kelly_fraction=0.3,
        kelly_window=30,
    )

    # Only 5 trades - below minimum of 10
    trade_history = [
        {"pnl_percent": 1.5},
        {"pnl_percent": -1.0},
        {"pnl_percent": 2.0},
        {"pnl_percent": -0.5},
        {"pnl_percent": 1.0},
    ]

    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
        trade_history=trade_history,
    )

    # Should fallback to configured risk percentage
    assert result["sizing_method"] == "kelly"
    assert result["risk_pct_used"] == configured_risk  # Fallback to configured risk


def test_kelly_criterion_calculation():
    """Test Kelly Criterion calculation with valid trade history."""
    executor = MockOrderExecutor()
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=0.01,
        use_kelly_criterion=True,
        kelly_fraction=0.3,
        kelly_window=30,
    )
    
    # 20 trades: 60% win rate, avg win 2%, avg loss 1%
    trade_history = [
        {"pnl_percent": 2.0},   # Win
        {"pnl_percent": 2.1},   # Win
        {"pnl_percent": -1.0},  # Loss
        {"pnl_percent": 2.2},   # Win
        {"pnl_percent": -0.9},  # Loss
        {"pnl_percent": 1.9},   # Win
        {"pnl_percent": 2.0},   # Win
        {"pnl_percent": -1.1},  # Loss
        {"pnl_percent": 2.1},   # Win
        {"pnl_percent": -1.0},  # Loss
        {"pnl_percent": 2.0},   # Win
        {"pnl_percent": 2.2},   # Win
        {"pnl_percent": -0.95}, # Loss
        {"pnl_percent": 1.95},  # Win
        {"pnl_percent": 2.05},  # Win
        {"pnl_percent": -1.05}, # Loss
        {"pnl_percent": 2.1},   # Win
        {"pnl_percent": 2.0},   # Win
        {"pnl_percent": -1.0},  # Loss
        {"pnl_percent": 2.15},  # Win
    ]
    
    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
        trade_history=trade_history,
    )
    
    assert result["sizing_method"] == "kelly"
    # Kelly should be higher than fixed 1% due to positive win rate
    assert result["risk_pct_used"] > 0.01


def test_kelly_criterion_no_wins():
    """Test Kelly fallback when there are no wins - uses configured risk."""
    executor = MockOrderExecutor()
    configured_risk = 0.025  # 2.5% configured risk
    sizer = PositionSizer(
        order_executor=executor,
        risk_percentage=configured_risk,
        use_kelly_criterion=True,
    )

    # All losses
    trade_history = [
        {"pnl_percent": -1.0},
        {"pnl_percent": -1.5},
        {"pnl_percent": -0.8},
        {"pnl_percent": -1.2},
        {"pnl_percent": -0.9},
        {"pnl_percent": -1.1},
        {"pnl_percent": -1.0},
        {"pnl_percent": -1.3},
        {"pnl_percent": -0.7},
        {"pnl_percent": -1.0},
    ]

    result = sizer.calculate_position_size(
        symbol="BTCUSDT",
        entry_price=50000,
        stop_loss=49000,
        wallet_balance=10000,
        confidence=0.75,
        trade_history=trade_history,
    )

    # Should fallback to configured risk percentage
    assert result["risk_pct_used"] == configured_risk


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

