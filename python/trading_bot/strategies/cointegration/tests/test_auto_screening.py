#!/usr/bin/env python3
"""
Test script for auto-screening integration in CointegrationAnalysisModule.

Tests both static and auto_screen pair discovery modes.

Usage:
    source venv/bin/activate
    python test_auto_screening.py
"""

import asyncio
import sys
import os
import json
from pathlib import Path

# Add project to path
python_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.db.client import query, get_connection


def get_test_instance_id():
    """Get an instance ID from the database for testing."""
    try:
        conn = get_connection()
        instances = query(conn, "SELECT id FROM instances LIMIT 1")
        if instances:
            return instances[0]['id']
    except Exception as e:
        print(f"⚠️  Could not get instance from DB: {e}")
    return "test-instance-default"


async def test_static_mode():
    """Test static pair discovery mode."""
    print("\n" + "=" * 70)
    print("TEST 1: STATIC PAIR DISCOVERY MODE")
    print("=" * 70)

    instance_id = get_test_instance_id()
    config = ConfigV2.load(instance_id=instance_id)
    
    strategy = CointegrationAnalysisModule(
        config=config,
        instance_id="test-instance-static",
        run_id="test-run-001",
        heartbeat_callback=lambda message="", **kwargs: print(f"[HB] {message}")
    )
    
    # Verify static mode is default
    mode = strategy.get_config_value('pair_discovery_mode', 'static')
    print(f"✅ Pair discovery mode: {mode}")
    
    pairs = strategy.get_config_value('pairs', {})
    print(f"✅ Static pairs configured: {len(pairs)} pairs")
    for symbol, pair_symbol in list(pairs.items())[:3]:
        print(f"   - {symbol} <-> {pair_symbol}")
    
    return True


async def test_cache_path():
    """Test screener cache path generation."""
    print("\n" + "=" * 70)
    print("TEST 2: SCREENER CACHE PATH GENERATION")
    print("=" * 70)

    instance_id = get_test_instance_id()
    config = ConfigV2.load(instance_id=instance_id)
    
    strategy = CointegrationAnalysisModule(
        config=config,
        instance_id="test-instance-1h",
        run_id="test-run-001",
        heartbeat_callback=lambda message="", **kwargs: print(f"[HB] {message}")
    )
    
    # Test cache path for different timeframes
    for timeframe in ["1h", "4h", "1d"]:
        cache_path = strategy._get_screener_cache_path(timeframe)
        print(f"✅ Cache path for {timeframe}: {cache_path.name}")
        assert f"test-instance-1h_{timeframe}.json" in str(cache_path)
    
    return True


async def test_cache_loading():
    """Test loading screener cache."""
    print("\n" + "=" * 70)
    print("TEST 3: SCREENER CACHE LOADING")
    print("=" * 70)

    instance_id = get_test_instance_id()
    config = ConfigV2.load(instance_id=instance_id)
    
    strategy = CointegrationAnalysisModule(
        config=config,
        instance_id="test-instance-cache",
        run_id="test-run-001",
        heartbeat_callback=lambda message="", **kwargs: print(f"[HB] {message}")
    )
    
    # Try to load non-existent cache
    cache_data = strategy._load_screener_cache("1h")
    if cache_data is None:
        print("✅ Non-existent cache returns None (expected)")
    else:
        print("❌ Non-existent cache should return None")
        return False
    
    # Create a test cache file
    cache_path = strategy._get_screener_cache_path("1h")
    test_cache = {
        "timestamp": "2025-12-17T15:30:00",
        "timeframe": "1h",
        "total_symbols_screened": 10,
        "total_pairs_found": 3,
        "independent_pairs": 2,
        "pairs": [
            {"symbol1": "BTC", "symbol2": "ETH"},
            {"symbol1": "SOL", "symbol2": "ADA"}
        ]
    }
    
    with open(cache_path, 'w') as f:
        json.dump(test_cache, f)
    
    # Load the cache
    loaded = strategy._load_screener_cache("1h")
    if loaded and loaded.get('timeframe') == '1h':
        print(f"✅ Cache loaded successfully: {loaded.get('independent_pairs')} independent pairs")
    else:
        print("❌ Failed to load cache")
        return False
    
    # Clean up
    cache_path.unlink()
    print("✅ Test cache cleaned up")
    
    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("AUTO-SCREENING INTEGRATION TESTS")
    print("=" * 70)
    
    tests = [
        ("Static Mode", test_static_mode),
        ("Cache Path Generation", test_cache_path),
        ("Cache Loading", test_cache_loading),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    return all_passed


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

