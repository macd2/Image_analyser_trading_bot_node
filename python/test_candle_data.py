#!/usr/bin/env python3
"""
Test script to verify candle data processing and formatting.
Tests the get_trade_candles_bot_control.py functions.
"""
import sys
import json
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.utils.get_trade_candles_bot_control import get_candles_for_trade

def test_candle_formatting():
    """Test that candles are properly formatted and deduplicated."""
    # Test with a recent trade (will fetch from API if needed)
    symbol = "BTCUSDT"
    timeframe = "1h"
    # Use a timestamp from a few hours ago
    import time
    timestamp_ms = int((time.time() - 3600 * 3) * 1000)  # 3 hours ago
    
    print(f"Testing candle fetch for {symbol} {timeframe} at {timestamp_ms}")
    
    result = get_candles_for_trade(symbol, timeframe, timestamp_ms, candles_before=20, candles_after=10)
    
    print(f"\nResult: {json.dumps(result, indent=2)}")
    
    # Verify candles are sorted
    candles = result.get('candles', [])
    if len(candles) > 1:
        for i in range(1, len(candles)):
            if candles[i]['time'] <= candles[i-1]['time']:
                print(f"ERROR: Candles not sorted! {candles[i-1]['time']} >= {candles[i]['time']}")
                return False
        print(f"✓ Candles are properly sorted ({len(candles)} candles)")
    
    # Verify no duplicates
    times = [c['time'] for c in candles]
    if len(times) != len(set(times)):
        print(f"ERROR: Found duplicate timestamps!")
        return False
    print(f"✓ No duplicate timestamps")
    
    # Verify OHLC relationships
    for i, c in enumerate(candles):
        if not (c['low'] <= min(c['open'], c['close']) and max(c['open'], c['close']) <= c['high']):
            print(f"ERROR: Invalid OHLC at candle {i}: O={c['open']} H={c['high']} L={c['low']} C={c['close']}")
            return False
    print(f"✓ All OHLC relationships valid")
    
    # Check for gaps
    if len(candles) > 1:
        gaps = 0
        for i in range(1, len(candles)):
            time_diff = candles[i]['time'] - candles[i-1]['time']
            expected_diff = 3600  # 1h in seconds
            if time_diff > expected_diff * 1.5:
                gaps += 1
        if gaps > 0:
            print(f"⚠ Found {gaps} gaps in candle data (may be normal for recent trades)")
        else:
            print(f"✓ No significant gaps in candle data")
    
    return True

if __name__ == '__main__':
    try:
        success = test_candle_formatting()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

