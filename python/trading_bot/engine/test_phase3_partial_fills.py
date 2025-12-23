#!/usr/bin/env python3
"""
Tests for Phase 3: Partial Fill Handling with 1-Minute Timeout
Run with: python python/trading_bot/engine/test_phase3_partial_fills.py
"""

import sys
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Dict, Any, Optional

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock ExecutionRecord
@dataclass
class ExecutionRecord:
    exec_id: str
    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_value: float
    exec_fee: float
    exec_pnl: float
    exec_time: str
    is_maker: bool
    category: str = "linear"


class MockOrderExecutor:
    """Mock order executor for testing."""
    
    def __init__(self):
        self.calls = []
        self.close_position_result = {"status": "success"}
        self.cancel_order_result = {"status": "cancelled"}
    
    def close_position(self, symbol: str) -> Dict[str, Any]:
        self.calls.append({"method": "close_position", "symbol": symbol})
        return self.close_position_result
    
    def cancel_order(self, symbol: str, order_id: Optional[str] = None, 
                     order_link_id: Optional[str] = None) -> Dict[str, Any]:
        self.calls.append({
            "method": "cancel_order",
            "symbol": symbol,
            "order_id": order_id,
            "order_link_id": order_link_id
        })
        return self.cancel_order_result


class MockDatabase:
    """Mock database for testing."""

    def __init__(self):
        self.logs = []
        self.rowcount = 1

    def cursor(self):
        """Return self to support cursor() calls"""
        return self

    def execute(self, sql, params=None):
        """Mock execute method"""
        self.logs.append({
            "sql": sql,
            "params": params
        })
        return self

    def commit(self):
        """Mock commit method"""
        pass

    def rollback(self):
        """Mock rollback method"""
        pass

    def log_action(self, instance_id: str, run_id: str, trade_id: str,
                   symbol: str, action: str, details: str):
        self.logs.append({
            "instance_id": instance_id,
            "run_id": run_id,
            "trade_id": trade_id,
            "symbol": symbol,
            "action": action,
            "details": details
        })


def setup_spread_orders(monitor, instance_id, run_id, trade_id, order_id_x, order_id_y):
    """Helper to setup spread-based orders in monitor"""
    monitor.on_spread_based_orders_placed(
        instance_id=instance_id,
        run_id=run_id,
        trade_id=trade_id,
        symbol_x="BTCUSDT",
        symbol_y="ETHUSDT",
        qty_x=1.0,
        qty_y=-10.0,
        price_x=50000,
        price_y=3000,
        order_id_x=order_id_x,
        order_id_y=order_id_y
    )

    # Manually add orders to _order_state
    monitor._order_state[order_id_x] = {
        "instance_id": instance_id,
        "symbol": "BTCUSDT",
        "side": "Buy",
        "created_time": datetime.now(timezone.utc).isoformat(),
        "timeframe": "1h",
        "run_id": run_id,
        "trade_id": trade_id,
        "is_spread_based": True,
        "pair_symbol": "ETHUSDT",
        "order_id_x": order_id_x,
        "order_id_y": order_id_y,
    }
    monitor._order_state[order_id_y] = {
        "instance_id": instance_id,
        "symbol": "ETHUSDT",
        "side": "Sell",
        "created_time": datetime.now(timezone.utc).isoformat(),
        "timeframe": "1h",
        "run_id": run_id,
        "trade_id": trade_id,
        "is_spread_based": True,
        "pair_symbol": "BTCUSDT",
        "order_id_x": order_id_x,
        "order_id_y": order_id_y,
    }


def test_partial_fill_timeout_x_filled_y_unfilled():
    """Test: X leg fills, Y doesn't within 1 minute -> close X, cancel Y"""
    from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode

    executor = MockOrderExecutor()
    db = MockDatabase()
    monitor = EnhancedPositionMonitor(
        order_executor=executor,
        mode=MonitorMode.EVENT_DRIVEN,
        db_connection=db
    )

    # Setup spread-based orders
    setup_spread_orders(monitor, "test_instance", "test_run", "trade_123",
                       "order_x_123", "order_y_123")
    
    # X leg fills
    exec_x = ExecutionRecord(
        exec_id="exec_x_1",
        order_id="order_x_123",
        symbol="BTCUSDT",
        side="Buy",
        exec_price=50000,
        exec_qty=1.0,
        exec_value=50000,
        exec_fee=10,
        exec_pnl=0,
        exec_time="2024-01-01T10:00:00Z",
        is_maker=True
    )
    monitor.on_execution_update(exec_x, "test_instance", "test_run")
    
    # Verify X leg tracked
    order_info = monitor._order_state.get("order_x_123")
    assert order_info is not None, "Order X should be tracked"
    assert order_info.get("fill_price_x") == 50000, "X fill price should be recorded"
    assert order_info.get("first_leg_fill_time") is not None, "First fill time should be set"
    print("✅ X leg fill tracked correctly")
    
    # Simulate 61 seconds elapsed
    order_info["first_leg_fill_time"] = datetime.now(timezone.utc) - timedelta(seconds=61)
    
    # Trigger timeout check
    monitor._check_partial_fill_timeouts("test_instance", "test_run")
    
    # Verify recovery actions
    assert len(executor.calls) >= 2, "Should have close and cancel calls"
    close_call = next((c for c in executor.calls if c["method"] == "close_position"), None)
    cancel_call = next((c for c in executor.calls if c["method"] == "cancel_order"), None)
    
    assert close_call is not None, "Should close filled leg"
    assert close_call["symbol"] == "BTCUSDT", "Should close X leg"
    print("✅ Filled leg (X) closed via market order")
    
    assert cancel_call is not None, "Should cancel unfilled leg"
    assert cancel_call["symbol"] == "ETHUSDT", "Should cancel Y leg"
    print("✅ Unfilled leg (Y) cancelled")
    
    # Verify logging
    assert len(db.logs) > 0, "Should log recovery actions"
    print("✅ Recovery actions logged to database")


def test_partial_fill_timeout_y_filled_x_unfilled():
    """Test: Y leg fills, X doesn't within 1 minute -> close Y, cancel X"""
    from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode

    executor = MockOrderExecutor()
    db = MockDatabase()
    monitor = EnhancedPositionMonitor(
        order_executor=executor,
        mode=MonitorMode.EVENT_DRIVEN,
        db_connection=db
    )

    # Setup spread-based orders
    setup_spread_orders(monitor, "test_instance", "test_run", "trade_456",
                       "order_x_456", "order_y_456")
    
    # Y leg fills
    exec_y = ExecutionRecord(
        exec_id="exec_y_1",
        order_id="order_y_456",
        symbol="ETHUSDT",
        side="Sell",
        exec_price=3000,
        exec_qty=10.0,
        exec_value=30000,
        exec_fee=6,
        exec_pnl=0,
        exec_time="2024-01-01T10:00:00Z",
        is_maker=True
    )
    monitor.on_execution_update(exec_y, "test_instance", "test_run")
    
    # Verify Y leg tracked
    order_info = monitor._order_state.get("order_y_456")
    assert order_info is not None, "Order Y should be tracked"
    assert order_info.get("fill_price_y") == 3000, "Y fill price should be recorded"
    print("✅ Y leg fill tracked correctly")
    
    # Simulate 61 seconds elapsed
    order_info["first_leg_fill_time"] = datetime.now(timezone.utc) - timedelta(seconds=61)
    
    # Trigger timeout check
    monitor._check_partial_fill_timeouts("test_instance", "test_run")

    # Verify recovery actions
    close_call = next((c for c in executor.calls if c["method"] == "close_position"), None)
    cancel_call = next((c for c in executor.calls if c["method"] == "cancel_order"), None)

    assert close_call is not None, "Should close filled leg"
    assert close_call["symbol"] == "ETHUSDT", "Should close Y leg"
    print("✅ Filled leg (Y) closed via market order")

    assert cancel_call is not None, "Should cancel unfilled leg"
    assert cancel_call["symbol"] == "BTCUSDT", "Should cancel X leg"
    print("✅ Unfilled leg (X) cancelled")


def test_both_legs_filled_no_timeout():
    """Test: Both legs fill before timeout -> no recovery needed"""
    from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode

    executor = MockOrderExecutor()
    db = MockDatabase()
    monitor = EnhancedPositionMonitor(
        order_executor=executor,
        mode=MonitorMode.EVENT_DRIVEN,
        db_connection=db
    )

    # Setup spread-based orders
    setup_spread_orders(monitor, "test_instance", "test_run", "trade_789",
                       "order_x_789", "order_y_789")
    
    # X leg fills
    exec_x = ExecutionRecord(
        exec_id="exec_x_2",
        order_id="order_x_789",
        symbol="BTCUSDT",
        side="Buy",
        exec_price=50000,
        exec_qty=1.0,
        exec_value=50000,
        exec_fee=10,
        exec_pnl=0,
        exec_time="2024-01-01T10:00:00Z",
        is_maker=True
    )
    monitor.on_execution_update(exec_x, "test_instance", "test_run")
    
    # Y leg fills (before timeout)
    exec_y = ExecutionRecord(
        exec_id="exec_y_2",
        order_id="order_y_789",
        symbol="ETHUSDT",
        side="Sell",
        exec_price=3000,
        exec_qty=10.0,
        exec_value=30000,
        exec_fee=6,
        exec_pnl=0,
        exec_time="2024-01-01T10:00:05Z",
        is_maker=True
    )
    monitor.on_execution_update(exec_y, "test_instance", "test_run")
    
    # Verify both legs filled
    order_info = monitor._order_state.get("order_x_789")
    assert order_info.get("both_filled") is True, "Both legs should be marked as filled"
    print("✅ Both legs filled before timeout")
    
    # Trigger timeout check (should do nothing)
    monitor._check_partial_fill_timeouts("test_instance", "test_run")
    
    # Verify no recovery actions
    close_calls = [c for c in executor.calls if c["method"] == "close_position"]
    cancel_calls = [c for c in executor.calls if c["method"] == "cancel_order"]
    
    assert len(close_calls) == 0, "Should not close any positions"
    assert len(cancel_calls) == 0, "Should not cancel any orders"
    print("✅ No recovery actions taken (both legs filled)")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("PHASE 3: PARTIAL FILL HANDLING TESTS")
    print("="*60 + "\n")
    
    try:
        print("Test 1: X fills, Y doesn't -> close X, cancel Y")
        print("-" * 60)
        test_partial_fill_timeout_x_filled_y_unfilled()
        print()
        
        print("Test 2: Y fills, X doesn't -> close Y, cancel X")
        print("-" * 60)
        test_partial_fill_timeout_y_filled_x_unfilled()
        print()
        
        print("Test 3: Both legs fill before timeout -> no recovery")
        print("-" * 60)
        test_both_legs_filled_no_timeout()
        print()
        
        print("="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        sys.exit(0)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

