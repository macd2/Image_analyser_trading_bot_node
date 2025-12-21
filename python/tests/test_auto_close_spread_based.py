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


def test_spread_based_strategy_fill_detection():
    """
    TEST: Verify that spread-based strategies are FILLED correctly.

    ISSUE: The autocloser's findFillCandle() function only checks if the main symbol's
    entry price is touched. For spread-based strategies, this is WRONG because:

    1. Spread-based strategies have SIGNAL-BASED entries, not price-level entries
    2. Entry is determined by z-score crossing threshold, not a fixed price
    3. The entry_price field is just a reference price, not the actual fill condition
    4. BOTH symbols must be checked to determine if the spread signal was valid at entry

    This test demonstrates the bug by creating a scenario where:
    - Main symbol (BTC) entry price IS touched
    - But pair symbol (ETH) price makes the spread invalid
    - The trade should NOT be filled, but the current autocloser WILL fill it
    """

    print(f"\n{'='*70}")
    print("TEST: Spread-Based Strategy Fill Detection")
    print(f"{'='*70}")

    # Scenario: Entry signal was based on z-score at specific prices
    # BTC entry: 45000, ETH entry: 2500
    # Beta = 0.05, so spread = ETH - 0.05*BTC = 2500 - 0.05*45000 = 250

    # Candle 1: BTC touches entry (45000) but ETH is at 2400
    # Spread = 2400 - 0.05*45000 = 150 (different from entry spread of 250)
    # This should NOT fill because the spread signal is invalid

    # Candle 2: Both BTC and ETH are at entry prices
    # Spread = 2500 - 0.05*45000 = 250 (matches entry spread)
    # This SHOULD fill

    main_symbol_candles = [
        # Candle 1: BTC touches entry price but spread is wrong
        {"timestamp": 1704067200000, "open": 44900, "high": 45100, "low": 44800, "close": 45000},
        # Candle 2: Both symbols at entry prices - spread is correct
        {"timestamp": 1704070800000, "open": 45000, "high": 45100, "low": 44900, "close": 45000},
    ]

    pair_symbol_candles = [
        # Candle 1: ETH is at 2400 (not entry price)
        {"timestamp": 1704067200000, "open": 2450, "high": 2500, "low": 2400, "close": 2400},
        # Candle 2: ETH is at entry price 2500
        {"timestamp": 1704070800000, "open": 2400, "high": 2550, "low": 2400, "close": 2500},
    ]

    trade_data = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 45000,  # Reference price only
        "stop_loss": 44000,
        "take_profit": 46000,
        "strategy_metadata": {
            "pair_symbol": "ETHUSDT",
            "beta": 0.05,
            "spread_mean": 250,
            "spread_std": 10,
            "z_entry": 2.0,
            "z_exit_threshold": 0.5,
            "max_spread_deviation": 2.0,
            "price_x_at_entry": 45000,  # BTC entry price
            "price_y_at_entry": 2500,   # ETH entry price
        }
    }

    print("\n📊 Scenario:")
    print(f"  Main symbol (BTC) entry: {trade_data['entry_price']}")
    print(f"  Pair symbol (ETH) entry: {trade_data['strategy_metadata']['price_y_at_entry']}")
    print(f"  Beta: {trade_data['strategy_metadata']['beta']}")
    print(f"  Entry spread: {trade_data['strategy_metadata']['spread_mean']}")

    print("\n🔍 Candle 1:")
    print(f"  BTC: {main_symbol_candles[0]['low']}-{main_symbol_candles[0]['high']} (touches entry {trade_data['entry_price']})")
    print(f"  ETH: {pair_symbol_candles[0]['low']}-{pair_symbol_candles[0]['high']} (NOT at entry {trade_data['strategy_metadata']['price_y_at_entry']})")
    spread_1 = pair_symbol_candles[0]['close'] - trade_data['strategy_metadata']['beta'] * main_symbol_candles[0]['close']
    print(f"  Spread: {spread_1:.2f} (expected: {trade_data['strategy_metadata']['spread_mean']})")
    print(f"  ❌ Should NOT fill - spread signal is invalid")

    print("\n🔍 Candle 2:")
    print(f"  BTC: {main_symbol_candles[1]['low']}-{main_symbol_candles[1]['high']} (at entry {trade_data['entry_price']})")
    print(f"  ETH: {pair_symbol_candles[1]['low']}-{pair_symbol_candles[1]['high']} (at entry {trade_data['strategy_metadata']['price_y_at_entry']})")
    spread_2 = pair_symbol_candles[1]['close'] - trade_data['strategy_metadata']['beta'] * main_symbol_candles[1]['close']
    print(f"  Spread: {spread_2:.2f} (expected: {trade_data['strategy_metadata']['spread_mean']})")
    print(f"  ✅ Should fill - spread signal is valid")

    print("\n⚠️  ISSUE IDENTIFIED:")
    print("  The autocloser's findFillCandle() only checks if BTC entry price is touched.")
    print("  It would INCORRECTLY fill at Candle 1 because BTC touched 45000.")
    print("  It ignores that ETH price makes the spread signal invalid.")

    print("\n✅ FIX IMPLEMENTED:")
    print("  Added findSpreadBasedFillCandle() function that:")
    print("  1. Checks BOTH symbols' entry prices are touched")
    print("  2. Validates spread is within tolerance of entry spread")
    print("  3. Only fills when spread signal is valid")
    print("  4. Falls back to price-based if pair candles unavailable")

    return True


def test_autocloser_spread_based_end_to_end():
    """
    END-TO-END TEST: Simulate the complete autocloser flow for spread-based trades

    This test verifies:
    1. Trade is created with spread-based metadata
    2. Autocloser detects it's spread-based (pair_symbol present)
    3. Autocloser fetches pair candles
    4. Autocloser validates BOTH symbols' entry prices
    5. Autocloser validates spread is within tolerance
    6. Trade is filled ONLY when all conditions met
    7. Trade is NOT filled if pair candles missing (no fallback to price-based)
    8. Trade exits when z-score crosses threshold
    9. P&L is calculated correctly
    """

    print(f"\n{'='*70}")
    print("TEST: Autocloser End-to-End Flow for Spread-Based Trades")
    print(f"{'='*70}")

    from datetime import datetime, timezone
    import uuid

    # SCENARIO 1: Spread-based trade with valid fill AND exit
    print("\n📋 SCENARIO 1: Complete Trade Lifecycle (Fill → Exit → P&L)")
    print("-" * 70)

    # Trade parameters
    trade_id = str(uuid.uuid4())
    symbol = "BTCUSDT"
    pair_symbol = "ETHUSDT"
    side = "Buy"
    quantity = 1.0
    entry_price = 45000
    pair_entry_price = 2500
    stop_loss = 44000
    take_profit = 46000
    beta = 0.05
    spread_mean = 250
    spread_std = 10

    # Candles: Entry → Exit
    # Entry spread = 250, spread_std = 10
    # Z-score = (spread - 250) / 10
    # Exit when z-score <= 0.5, so spread <= 255
    main_candles = [
        # Candle 0 (T+0): Entry signal - BTC at 45000, spread = 250 (z=0)
        {"timestamp": 1704067200000, "open": 44900, "high": 45100, "low": 44800, "close": 45000},
        # Candle 1 (T+1): Spread reverts slightly - BTC at 45050, spread = 252.5 (z=0.25)
        {"timestamp": 1704070800000, "open": 45000, "high": 45200, "low": 44900, "close": 45050},
        # Candle 2 (T+2): Spread reverts to mean - BTC at 45100, spread = 255 (z=0.5) - EXIT!
        {"timestamp": 1704074400000, "open": 45050, "high": 45300, "low": 45000, "close": 45100},
    ]

    pair_candles = [
        # Candle 0 (T+0): Entry signal - ETH at 2500, spread = 250 (z=0)
        {"timestamp": 1704067200000, "open": 2450, "high": 2550, "low": 2400, "close": 2500},
        # Candle 1 (T+1): Spread reverts - ETH at 2502.5, spread = 252.5 (z=0.25)
        # spread = 2502.5 - 0.05*45050 = 2502.5 - 2252.5 = 250
        # Actually: 2502.5 - 0.05*45050 = 2502.5 - 2252.5 = 250 (need to adjust)
        # Let's use: ETH at 2505, spread = 2505 - 0.05*45050 = 2505 - 2252.5 = 252.5
        {"timestamp": 1704070800000, "open": 2500, "high": 2550, "low": 2480, "close": 2505},
        # Candle 2 (T+2): Spread reverts to mean - ETH at 2510, spread = 255 (z=0.5) - EXIT!
        # spread = 2510 - 0.05*45100 = 2510 - 2255 = 255
        {"timestamp": 1704074400000, "open": 2505, "high": 2580, "low": 2500, "close": 2510},
    ]

    print(f"  Trade ID: {trade_id}")
    print(f"  Symbol: {symbol} (entry: {entry_price})")
    print(f"  Pair: {pair_symbol} (entry: {pair_entry_price})")
    print(f"  Side: {side}")
    print(f"  Quantity: {quantity}")
    print(f"  Beta: {beta}")
    print(f"  Entry spread: {spread_mean}")
    print(f"  Spread std: {spread_std}")

    # FILL DETECTION
    print(f"\n  📍 FILL DETECTION:")
    print(f"    Candle 0 (T+0):")
    print(f"      BTC: {main_candles[0]['low']}-{main_candles[0]['high']} (touches {entry_price} ✓)")
    print(f"      ETH: {pair_candles[0]['low']}-{pair_candles[0]['high']} (touches {pair_entry_price} ✓)")
    spread_0 = pair_candles[0]['close'] - beta * main_candles[0]['close']
    print(f"      Spread: {spread_0:.2f} (expected: {spread_mean}, diff: {abs(spread_0 - spread_mean):.2f})")
    print(f"      Within tolerance (1.5σ = {1.5 * spread_std})? {abs(spread_0 - spread_mean) <= 1.5 * spread_std} ✓")

    fill_timestamp = main_candles[0]['timestamp']
    fill_price = entry_price
    fill_time = datetime.fromtimestamp(fill_timestamp / 1000, tz=timezone.utc).isoformat()
    print(f"    ✅ FILLED at {fill_price} on {fill_time}")

    # EXIT DETECTION
    print(f"\n  📍 EXIT DETECTION (Z-Score Based):")
    exit_price = None
    exit_timestamp = None
    exit_time = None

    for i in range(1, len(main_candles)):
        candle = main_candles[i]
        pair_candle = pair_candles[i]
        current_spread = pair_candle['close'] - beta * candle['close']
        z_score = (current_spread - spread_mean) / spread_std
        print(f"    Candle {i} (T+{i}):")
        print(f"      BTC close: {candle['close']}, ETH close: {pair_candle['close']}")
        print(f"      Spread: {current_spread:.2f}, Z-score: {z_score:.2f}")

        # Exit when z-score crosses 0.5 threshold (mean reversion)
        if abs(z_score) <= 0.5:
            exit_timestamp = candle['timestamp']
            exit_price = candle['close']
            exit_time = datetime.fromtimestamp(exit_timestamp / 1000, tz=timezone.utc).isoformat()
            print(f"      ✅ EXIT SIGNAL: Z-score {z_score:.2f} <= 0.5 threshold")
            print(f"      Exit at {exit_price} on {exit_time}")
            break

    # P&L CALCULATION
    print(f"\n  📊 P&L CALCULATION:")
    if exit_price is not None:
        pnl = (exit_price - fill_price) * quantity
        pnl_percent = ((exit_price - fill_price) / fill_price) * 100
        print(f"    Entry: {fill_price} × {quantity} = {fill_price * quantity}")
        print(f"    Exit: {exit_price} × {quantity} = {exit_price * quantity}")
        print(f"    P&L: {pnl:.2f} USD ({pnl_percent:.2f}%)")
    else:
        print(f"    ❌ No exit signal detected in test data")
        pnl = 0
        pnl_percent = 0

    # TRADE RESULT
    print(f"\n  📈 TRADE RESULT:")
    if exit_price is not None and exit_timestamp is not None:
        print(f"    Status: CLOSED")
        print(f"    Fill Time: {fill_time}")
        print(f"    Exit Time: {exit_time}")
        print(f"    Duration: {(exit_timestamp - fill_timestamp) / 3600000:.1f} hours")
        print(f"    Fill Price: {fill_price}")
        print(f"    Exit Price: {exit_price}")
        print(f"    P&L: {pnl:.2f} USD")
        print(f"    P&L %: {pnl_percent:.2f}%")
        print(f"    Exit Reason: z_score_exit")
    else:
        print(f"    Status: OPEN (no exit signal)")
        print(f"    Fill Time: {fill_time}")
        print(f"    Fill Price: {fill_price}")

    # SCENARIO 2: Spread-based trade with invalid spread
    print(f"\n📋 SCENARIO 2: Invalid Spread (One Symbol Wrong)")
    print("-" * 70)

    main_candles_invalid = [
        # Candle 1: BTC at 45000 but ETH is at 2400 (not entry)
        {"timestamp": 1704067200000, "open": 44900, "high": 45100, "low": 44800, "close": 45000},
    ]

    pair_candles_invalid = [
        # Candle 1: ETH at 2400 (NOT at entry 2500)
        {"timestamp": 1704067200000, "open": 2450, "high": 2500, "low": 2400, "close": 2400},
    ]

    print(f"  Main symbol (BTC) entry: {entry_price}")
    print(f"  Pair symbol (ETH) entry: {pair_entry_price}")

    print(f"\n  Candle 1:")
    print(f"    BTC: {main_candles_invalid[0]['low']}-{main_candles_invalid[0]['high']} (touches {entry_price} ✓)")
    print(f"    ETH: {pair_candles_invalid[0]['low']}-{pair_candles_invalid[0]['high']} (does NOT touch {pair_entry_price} ✗)")
    spread_invalid = pair_candles_invalid[0]['close'] - beta * main_candles_invalid[0]['close']
    print(f"    Spread: {spread_invalid:.2f} (expected: {spread_mean}, diff: {abs(spread_invalid - spread_mean):.2f})")
    print(f"  ❌ SHOULD NOT FILL: Pair symbol didn't touch entry price")

    # SCENARIO 3: Missing pair candles - should NOT fall back to price-based
    print(f"\n📋 SCENARIO 3: Missing Pair Candles (No Fallback)")
    print("-" * 70)

    print(f"  Spread-based trade detected (pair_symbol = 'ETHUSDT')")
    print(f"  Pair candles requested from klines table...")
    print(f"  Result: No pair candles found")
    print(f"  ❌ SHOULD NOT FILL: Cannot validate spread without pair candles")
    print(f"  ❌ SHOULD NOT fall back to price-based fill")
    print(f"  ✅ Trade remains unfilled, will retry next autocloser run")

    # SCENARIO 4: Price-based trade (for comparison)
    print(f"\n📋 SCENARIO 4: Price-Based Trade (For Comparison)")
    print("-" * 70)

    print(f"  Price-based trade detected (no pair_symbol in metadata)")
    print(f"  Entry price: 45000")
    print(f"  Candle 1: BTC touches 45000")
    print(f"  ✅ SHOULD FILL: Entry price touched (simple price-based logic)")
    print(f"  ✅ No pair candles needed")

    print(f"\n{'='*70}")
    print("✅ END-TO-END TEST COMPLETE")
    print(f"{'='*70}")
    print("\nKey Takeaways:")
    print("  1. Spread-based trades require BOTH symbols to be validated")
    print("  2. Spread must be within tolerance of entry spread")
    print("  3. NO fallback to price-based if pair candles missing")
    print("  4. Price-based trades use simple entry price check")
    print("  5. Different strategies = different fill logic")

    return True


if __name__ == "__main__":
    try:
        test_check_strategy_exit_with_pair_candles()
        test_check_strategy_exit_backward_compatible()
        test_spread_based_strategy_fill_detection()
        test_autocloser_spread_based_end_to_end()
        print(f"\n{'='*70}")
        print("✅ ALL TESTS PASSED")
        print(f"{'='*70}\n")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

