#!/usr/bin/env python3
"""
Debug test for AlexAnalysisModule - check candle fetching.
"""

import sys
sys.path.insert(0, '/home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node/python')

from trading_bot.strategies.candle_adapter import CandleAdapter

def test_candle_fetch():
    """Test fetching candles from database."""
    print("\n" + "="*80)
    print("CANDLE ADAPTER - DEBUG TEST")
    print("="*80)
    
    adapter = CandleAdapter(instance_id="debug-test")
    
    symbols = ["AAVEUSDT", "CAKEUSDT"]
    timeframes = ["1h", "4h", "1d"]
    
    for symbol in symbols:
        print(f"\n{symbol}:")
        for tf in timeframes:
            print(f"  Fetching {tf}...", end=" ", flush=True)
            try:
                candles = adapter.get_candles(
                    symbol=symbol,
                    timeframe=tf,
                    limit=200,
                    use_cache=True,
                    min_candles=50
                )
                print(f"✓ Got {len(candles)} candles")
            except Exception as e:
                print(f"✗ Error: {e}")


if __name__ == "__main__":
    test_candle_fetch()

