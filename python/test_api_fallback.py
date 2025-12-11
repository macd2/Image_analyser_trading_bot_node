#!/usr/bin/env python3
"""
Test CandleAdapter with API fallback.
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.strategies.candle_adapter import CandleAdapter


async def test_api_fallback():
    """Test API fallback for symbols not in cache."""
    print("\n" + "="*70)
    print("CANDLE ADAPTER - API FALLBACK TEST")
    print("="*70)
    
    adapter = CandleAdapter(instance_id="api-test")
    
    # Test 1: Symbol in cache (should use cache)
    print("\n📥 Test 1: CAKEUSDT (in cache, prefer_source='cache')")
    candles = adapter.get_candles(
        symbol="CAKEUSDT",
        timeframe="1h",
        limit=50,
        use_cache=True,
        min_candles=10,
        prefer_source="cache"
    )
    print(f"   Got {len(candles)} candles from cache")
    if candles:
        print(f"   First: {candles[0]}")
        print(f"   Last:  {candles[-1]}")
    
    # Test 2: Symbol not in cache (should use API)
    print("\n📥 Test 2: SNXUSDT (not in cache, prefer_source='api')")
    candles = adapter.get_candles(
        symbol="SNXUSDT",
        timeframe="1h",
        limit=50,
        use_cache=True,
        min_candles=10,
        prefer_source="api"
    )
    print(f"   Got {len(candles)} candles from API")
    if candles:
        print(f"   First: {candles[0]}")
        print(f"   Last:  {candles[-1]}")
    
    # Test 3: Prefer API even if in cache
    print("\n📥 Test 3: CAKEUSDT (in cache, prefer_source='api')")
    candles = adapter.get_candles(
        symbol="CAKEUSDT",
        timeframe="1h",
        limit=50,
        use_cache=True,
        min_candles=10,
        prefer_source="api"
    )
    print(f"   Got {len(candles)} candles from API")
    if candles:
        print(f"   First: {candles[0]}")
        print(f"   Last:  {candles[-1]}")


async def main():
    """Main entry point."""
    try:
        await test_api_fallback()
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

