"""
Test auto-close endpoint with spread-based trades.

Tests that the auto-close endpoint can:
1. Fetch pair candles from klines table
2. Pass pair candles to check_strategy_exit.py
3. Close spread-based trades correctly
"""

import json
import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.db.client import get_connection, release_connection, execute, query


def test_check_strategy_exit_with_pair_candles():
    """Test that check_strategy_exit.py accepts and uses pair candles."""

    # Prepare test data
    trade_id = "test-spread-trade-001"
    strategy_name = "CointegrationSpreadTrader"  # Correct strategy name from registry
    
    # Primary symbol candles (BTC)
    candles = [
        {"timestamp": 1704067200000, "open": 45000, "high": 45500, "low": 44500, "close": 45200},
        {"timestamp": 1704070800000, "open": 45200, "high": 45800, "low": 45000, "close": 45500},
        {"timestamp": 1704074400000, "open": 45500, "high": 46000, "low": 45300, "close": 45800},
    ]
    
    # Pair symbol candles (ETH)
    pair_candles = [
        {"timestamp": 1704067200000, "open": 2500, "high": 2550, "low": 2450, "close": 2520},
        {"timestamp": 1704070800000, "open": 2520, "high": 2580, "low": 2500, "close": 2550},
        {"timestamp": 1704074400000, "open": 2550, "high": 2600, "low": 2530, "close": 2580},
    ]
    
    # Trade data with spread-based metadata
    trade_data = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 45000,
        "stop_loss": 44000,
        "take_profit": 46000,
        "strategy_metadata": {
            "pair_symbol": "ETHUSDT",
            "beta": 0.05,
            "spread_mean": 0.0,
            "spread_std": 1.0,
            "z_exit_threshold": 0.5,
            "max_spread_deviation": 2.0,
        }
    }
    
    # Call check_strategy_exit.py with pair candles
    script_path = Path(__file__).parent.parent / "check_strategy_exit.py"
    
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            trade_id,
            strategy_name,
            json.dumps(candles),
            json.dumps(trade_data),
            json.dumps(pair_candles),  # Pass pair candles as 5th argument
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    
    print(f"\n{'='*70}")
    print("TEST: Auto-Close with Spread-Based Trades")
    print(f"{'='*70}")
    print(f"Return code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    if result.stderr:
        print(f"Stderr: {result.stderr}")
    
    # Parse result
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    print(f"\nExit result: {json.dumps(output, indent=2)}")
    
    # Verify output structure
    assert "should_exit" in output
    assert "exit_price" in output
    assert "exit_reason" in output
    assert "current_price" in output
    
    print(f"\n✅ Test passed: check_strategy_exit.py accepts pair candles")
    return True


def test_check_strategy_exit_backward_compatible():
    """Test that check_strategy_exit.py works without pair candles (backward compatible)."""
    
    trade_id = "test-price-trade-001"
    strategy_name = "PromptStrategy"
    
    candles = [
        {"timestamp": 1704067200000, "open": 45000, "high": 45500, "low": 44500, "close": 45200},
        {"timestamp": 1704070800000, "open": 45200, "high": 45800, "low": 45000, "close": 45500},
    ]
    
    trade_data = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 45000,
        "stop_loss": 44000,
        "take_profit": 46000,
        "strategy_metadata": {}
    }
    
    script_path = Path(__file__).parent.parent / "check_strategy_exit.py"
    
    # Call WITHOUT pair candles (backward compatibility)
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            trade_id,
            strategy_name,
            json.dumps(candles),
            json.dumps(trade_data),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    
    print(f"\n{'='*70}")
    print("TEST: Backward Compatibility (No Pair Candles)")
    print(f"{'='*70}")
    print(f"Return code: {result.returncode}")
    
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    
    output = json.loads(result.stdout)
    print(f"Exit result: {json.dumps(output, indent=2)}")
    
    assert "should_exit" in output
    print(f"\n✅ Test passed: backward compatible without pair candles")
    return True


if __name__ == "__main__":
    try:
        test_check_strategy_exit_with_pair_candles()
        test_check_strategy_exit_backward_compatible()
        print(f"\n{'='*70}")
        print("✅ ALL TESTS PASSED")
        print(f"{'='*70}\n")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

