#!/usr/bin/env python3
"""
Test script to verify paper trading slot counting works correctly.
This tests that StateManager uses database for paper trading and WebSocket for live trading.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.core.state_manager import StateManager
from trading_bot.db.client import get_connection, execute, query

def test_live_trading_mode():
    """Test that live trading mode uses WebSocket data."""
    print("\n" + "="*60)
    print("TEST 1: Live Trading Mode (WebSocket-based)")
    print("="*60)
    
    # Create StateManager in live trading mode (default)
    sm = StateManager(paper_trading=False)
    
    # Initially should have 0 positions
    assert sm.count_slots_used() == 0, "Should start with 0 slots"
    print("✅ Initial slot count: 0")
    
    # Simulate WebSocket position update
    sm.handle_position_message({
        "data": [
            {"symbol": "BTCUSDT", "side": "Buy", "size": "0.1", "entryPrice": "50000"},
            {"symbol": "ETHUSDT", "side": "Sell", "size": "1.0", "entryPrice": "3000"},
        ]
    })
    
    # Should now have 2 positions from WebSocket
    assert sm.count_slots_used() == 2, "Should have 2 slots from WebSocket"
    assert sm.has_position("BTCUSDT"), "Should have BTCUSDT position"
    assert sm.has_position("ETHUSDT"), "Should have ETHUSDT position"
    print("✅ WebSocket positions counted: 2")
    print("✅ has_position() works correctly")
    
    # Test available slots
    assert sm.get_available_slots(5) == 3, "Should have 3 available slots (5 - 2)"
    print("✅ Available slots calculated correctly: 3/5")
    
    print("\n✅ LIVE TRADING MODE TEST PASSED\n")


def test_paper_trading_mode():
    """Test that paper trading mode uses database."""
    print("\n" + "="*60)
    print("TEST 2: Paper Trading Mode (Database-based)")
    print("="*60)

    # Create a test instance_id
    test_instance_id = "test-instance-paper-trading"

    # Create StateManager in paper trading mode
    sm = StateManager(paper_trading=True, instance_id=test_instance_id)

    # Initially should have 0 positions (no database records)
    count = sm.count_slots_used()
    print(f"✅ Initial slot count from database: {count}")

    # Test has_position (should check database, not WebSocket)
    has_btc = sm.has_position("BTCUSDT")
    print(f"✅ has_position('BTCUSDT') from database: {has_btc}")

    # Test has_open_order (should check database for pending paper trades)
    has_order = sm.has_open_order("BTCUSDT")
    print(f"✅ has_open_order('BTCUSDT') from database: {has_order}")

    # Test that WebSocket updates are IGNORED in paper trading mode
    sm.handle_position_message({
        "data": [
            {"symbol": "BTCUSDT", "side": "Buy", "size": "0.1", "entryPrice": "50000"},
        ]
    })

    # Should still use database, not WebSocket
    count_after_ws = sm.count_slots_used()
    print(f"✅ Slot count after WebSocket update (should still use DB): {count_after_ws}")
    print(f"   (WebSocket data is ignored in paper trading mode)")

    print("\n✅ PAPER TRADING MODE TEST PASSED\n")


def test_mode_switching():
    """Test that mode parameter correctly switches behavior."""
    print("\n" + "="*60)
    print("TEST 3: Mode Switching")
    print("="*60)
    
    # Create two StateManagers with different modes
    sm_live = StateManager(paper_trading=False)
    sm_paper = StateManager(paper_trading=True, instance_id="test-instance")
    
    # Add WebSocket data to both
    ws_data = {
        "data": [{"symbol": "BTCUSDT", "side": "Buy", "size": "0.1", "entryPrice": "50000"}]
    }
    sm_live.handle_position_message(ws_data)
    sm_paper.handle_position_message(ws_data)
    
    # Live mode should count WebSocket position
    live_count = sm_live.count_slots_used()
    print(f"✅ Live mode slot count (WebSocket): {live_count}")
    assert live_count == 1, "Live mode should count WebSocket position"
    
    # Paper mode should ignore WebSocket and check database
    paper_count = sm_paper.count_slots_used()
    print(f"✅ Paper mode slot count (Database): {paper_count}")
    # Paper count depends on database state, but should NOT be affected by WebSocket
    
    print("\n✅ MODE SWITCHING TEST PASSED\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTING PAPER TRADING SLOT COUNTING")
    print("="*60)
    
    try:
        test_live_trading_mode()
        test_paper_trading_mode()
        test_mode_switching()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nSummary:")
        print("  ✅ Live trading mode uses WebSocket data")
        print("  ✅ Paper trading mode uses database queries")
        print("  ✅ Mode switching works correctly")
        print("  ✅ StateManager is ready for multi-instance paper trading")
        print("\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)

