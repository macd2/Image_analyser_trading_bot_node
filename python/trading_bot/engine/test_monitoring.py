#!/usr/bin/env python3
"""
Tests for Position Monitor and Trade Tracker.
Run with: python -m trading_bot.engine.test_monitoring
"""

from trading_bot.engine.position_monitor import PositionMonitor, TighteningStep
from trading_bot.engine.trade_tracker import TradeTracker, TradeStatus
from trading_bot.core.state_manager import PositionState, OrderState, ExecutionRecord


class MockOrderExecutor:
    """Mock order executor for testing."""
    
    def __init__(self):
        self.calls = []
    
    def set_trading_stop(self, symbol, stop_loss=None, take_profit=None, position_idx=0):
        self.calls.append({
            "method": "set_trading_stop",
            "symbol": symbol,
            "stop_loss": stop_loss,
        })
        return {"status": "success"}


def test_position_monitor_tightening():
    """Test SL tightening logic."""
    executor = MockOrderExecutor()
    monitor = PositionMonitor(
        order_executor=executor,
        tightening_enabled=True,
        tightening_steps=[
            TighteningStep(threshold=2.0, sl_position=1.0),
            TighteningStep(threshold=3.0, sl_position=2.0),
        ],
    )
    
    # Initial position at entry
    position = PositionState(
        symbol="BTCUSDT",
        side="Buy",
        size=0.1,
        entry_price=50000,
        mark_price=50000,
        unrealised_pnl=0,
        leverage="10",
        stop_loss=49000,  # 1R risk = 1000
    )
    monitor.on_position_update(position)
    
    # No tightening yet
    assert len(executor.calls) == 0
    
    # Price moves to 2R profit (52000)
    position.mark_price = 52000
    position.unrealised_pnl = 200
    monitor.on_position_update(position)
    
    # Should trigger first tightening
    assert len(executor.calls) == 1
    assert executor.calls[0]["symbol"] == "BTCUSDT"
    # New SL should be at 1R profit = 51000
    assert executor.calls[0]["stop_loss"] == 51000
    
    # Price moves to 3R profit (53000)
    position.mark_price = 53000
    monitor.on_position_update(position)
    
    # Should trigger second tightening
    assert len(executor.calls) == 2
    # New SL should be at 2R profit = 52000
    assert executor.calls[1]["stop_loss"] == 52000
    
    print("✅ test_position_monitor_tightening passed")


def test_position_monitor_short():
    """Test tightening for short positions."""
    executor = MockOrderExecutor()
    monitor = PositionMonitor(
        order_executor=executor,
        tightening_steps=[
            TighteningStep(threshold=2.0, sl_position=1.0),
        ],
    )
    
    # Short position
    position = PositionState(
        symbol="ETHUSDT",
        side="Sell",
        size=1.0,
        entry_price=3000,
        mark_price=3000,
        unrealised_pnl=0,
        leverage="10",
        stop_loss=3100,  # 1R risk = 100
    )
    monitor.on_position_update(position)
    
    # Price drops to 2R profit (2800)
    position.mark_price = 2800
    monitor.on_position_update(position)
    
    # Should tighten SL
    assert len(executor.calls) == 1
    # New SL should be at 1R profit = 2900
    assert executor.calls[0]["stop_loss"] == 2900
    
    print("✅ test_position_monitor_short passed")


def test_trade_tracker_lifecycle():
    """Test trade lifecycle tracking."""
    tracker = TradeTracker()
    
    # Register trade
    trade = tracker.register_trade(
        trade_id="t1",
        symbol="BTCUSDT",
        side="Buy",
        entry_price=50000,
        quantity=0.1,
        order_id="o1",
    )
    
    assert trade.status == TradeStatus.SUBMITTED
    assert len(tracker.get_open_trades()) == 1
    
    # Order filled
    order = OrderState(
        order_id="o1",
        order_link_id="t1",
        symbol="BTCUSDT",
        side="Buy",
        order_type="Limit",
        price=50000,
        qty=0.1,
        status="Filled",
        filled_qty=0.1,
        avg_price=50000,
    )
    tracker.on_order_update(order)
    
    assert trade.status == TradeStatus.FILLED
    assert trade.fill_quantity == 0.1
    
    # Position closed with profit
    execution = ExecutionRecord(
        exec_id="e1",
        order_id="o1",
        symbol="BTCUSDT",
        side="Sell",
        exec_price=51000,
        exec_qty=0.1,
        exec_value=5100,
        exec_fee=2.55,
        exec_pnl=100,  # $100 profit
        exec_time="1234567890",
        is_maker=False,
    )
    tracker.on_execution(execution)
    
    assert trade.status == TradeStatus.CLOSED
    assert trade.pnl == 100
    assert trade.exit_price == 51000
    assert len(tracker.get_open_trades()) == 0
    
    print("✅ test_trade_tracker_lifecycle passed")


def run_all_tests():
    """Run all monitoring tests."""
    print("\n🧪 Running Monitoring tests...\n")
    
    test_position_monitor_tightening()
    test_position_monitor_short()
    test_trade_tracker_lifecycle()
    
    print("\n✅ All monitoring tests passed!\n")


if __name__ == "__main__":
    run_all_tests()

