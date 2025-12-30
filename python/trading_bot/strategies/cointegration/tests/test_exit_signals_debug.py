#!/usr/bin/env python3
"""
DEBUG TEST: Exit Signal Generation with Real Candle Data

This test debugs why CointegrationSpreadTrader is not producing exit signals.
Uses real candle data from the database to trace through the exit logic step-by-step.

Key debugging points:
1. Load real trade from database (OGUSDT pair)
2. Fetch real candle data for both symbols
3. Manually calculate z-scores at each candle
4. Trace through should_exit() logic
5. Identify where exit signals are being missed
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

# Load .env.local BEFORE importing anything else
# Path: test file is at python/trading_bot/strategies/cointegration/tests/
# Project root is 5 levels up
env_file = Path(__file__).parent.parent.parent.parent.parent.parent / '.env.local'
print(f"Loading env from: {env_file}")
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value
    print(f"✅ Loaded .env.local")
else:
    print(f"❌ .env.local not found at {env_file}")

print(f"DB_TYPE: {os.environ.get('DB_TYPE')}")
db_url = os.environ.get('DATABASE_URL', 'NOT SET')
print(f"DATABASE_URL: {db_url[:50] if db_url != 'NOT SET' else 'NOT SET'}...")

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

from trading_bot.db.client import get_connection, query_one, query, release_connection
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_exit_signals_with_real_data():
    """Debug exit signals using real trade and candle data."""
    
    print("\n" + "=" * 100)
    print("DEBUG TEST: Exit Signal Generation with Real Candle Data")
    print("=" * 100)
    
    # [1] Load the problematic trade from database
    print("\n[1] Loading trade from database...")
    conn = get_connection()
    try:
        trade = query_one(
            conn,
            """SELECT id, symbol, strategy_metadata, entry_price, filled_at, side
               FROM trades
               WHERE id = ?""",
            ("3660703e-f95a-4fca-a8e2-ec3844124186_1d451353",)
        )

        if not trade:
            print("❌ Trade not found")
            return False

        print(f"✅ Trade found: {trade['symbol']}")
        print(f"   Entry price: {trade['entry_price']}")
        print(f"   Filled at: {trade['filled_at']}")
        print(f"   Side: {trade['side']}")
        
        # [2] Parse strategy metadata
        print("\n[2] Parsing strategy metadata...")
        metadata = trade.get('strategy_metadata', {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        print(f"   Beta: {metadata.get('beta')}")
        print(f"   Spread mean: {metadata.get('spread_mean')}")
        print(f"   Spread std: {metadata.get('spread_std')}")
        print(f"   Z-exit threshold: {metadata.get('z_exit_threshold')}")
        print(f"   Pair symbol: {metadata.get('pair_symbol')}")
        print(f"   Max spread deviation: {metadata.get('max_spread_deviation')}")
        
        # [3] Fetch candle data for both symbols
        print("\n[3] Fetching candle data...")
        main_symbol = trade['symbol']
        pair_symbol = metadata.get('pair_symbol')
        
        main_candles = query(
            conn,
            """SELECT start_time as timestamp, open_price as open, high_price as high,
                      low_price as low, close_price as close
               FROM klines
               WHERE symbol = ?
               ORDER BY start_time DESC
               LIMIT 1000""",
            (main_symbol,)
        )

        pair_candles = query(
            conn,
            """SELECT start_time as timestamp, open_price as open, high_price as high,
                      low_price as low, close_price as close
               FROM klines
               WHERE symbol = ?
               ORDER BY start_time DESC
               LIMIT 1000""",
            (pair_symbol,)
        )
        
        print(f"✅ Fetched {len(main_candles)} candles for {main_symbol}")
        print(f"✅ Fetched {len(pair_candles)} candles for {pair_symbol}")
        
        # [4] Reverse to chronological order
        main_candles = list(reversed(main_candles))
        pair_candles = list(reversed(pair_candles))
        
        # [5] Calculate z-scores and trace exit logic
        print("\n[4] Tracing z-score calculations and exit logic...")
        print("-" * 100)
        
        beta = metadata.get('beta')
        spread_mean = metadata.get('spread_mean')
        spread_std = metadata.get('spread_std')
        z_exit_threshold = metadata.get('z_exit_threshold')
        
        exit_found = False
        for i, (main_candle, pair_candle) in enumerate(zip(main_candles, pair_candles)):
            current_price = main_candle['close']
            pair_price = pair_candle['close']
            
            spread = pair_price - beta * current_price
            z_score = (spread - spread_mean) / spread_std if spread_std > 0 else 0
            
            threshold_crossed = abs(z_score) <= z_exit_threshold
            
            if i % 50 == 0 or threshold_crossed:  # Print every 50 candles or when threshold crossed
                print(f"Candle {i}: Main={current_price:.4f}, Pair={pair_price:.4f}")
                print(f"  Spread={spread:.4f}, Z-score={z_score:.4f}, Threshold={z_exit_threshold}")
                print(f"  |Z| <= Threshold? {threshold_crossed}")
                
                if threshold_crossed:
                    print(f"  ✅ EXIT SIGNAL FOUND!")
                    exit_found = True
                    break
        
        if not exit_found:
            print("\n❌ NO EXIT SIGNAL FOUND in entire candle history")
            print("\nDEBUG INFO:")
            print(f"  Z-exit threshold: {z_exit_threshold}")
            print(f"  Looking for: |z_score| <= {z_exit_threshold}")
            print(f"  Total candles checked: {len(main_candles)}")
        
        return exit_found
        
    finally:
        release_connection(conn)


def test_should_exit_method_with_real_data():
    """Test the actual should_exit() method with real trade and candle data."""

    print("\n" + "=" * 100)
    print("TEST: should_exit() Method with Real Data")
    print("=" * 100)

    conn = get_connection()
    try:
        # Load the trade
        trade = query_one(
            conn,
            """SELECT id, symbol, strategy_metadata, entry_price, filled_at, side
               FROM trades
               WHERE id = ?""",
            ("3660703e-f95a-4fca-a8e2-ec3844124186_1d451353",)
        )

        if not trade:
            print("❌ Trade not found")
            return False

        print(f"\n[1] Trade loaded: {trade['symbol']}")

        # Parse metadata
        metadata = trade.get('strategy_metadata', {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        pair_symbol = metadata.get('pair_symbol')

        # Fetch candles
        main_candles = query(
            conn,
            """SELECT start_time as timestamp, open_price as open, high_price as high,
                      low_price as low, close_price as close
               FROM klines
               WHERE symbol = ?
               ORDER BY start_time DESC
               LIMIT 1000""",
            (trade['symbol'],)
        )

        pair_candles = query(
            conn,
            """SELECT start_time as timestamp, open_price as open, high_price as high,
                      low_price as low, close_price as close
               FROM klines
               WHERE symbol = ?
               ORDER BY start_time DESC
               LIMIT 1000""",
            (pair_symbol,)
        )

        main_candles = list(reversed(main_candles))
        pair_candles = list(reversed(pair_candles))

        print(f"[2] Candles loaded: {len(main_candles)} main, {len(pair_candles)} pair")

        # Initialize strategy
        print(f"\n[3] Initializing CointegrationAnalysisModule...")
        strategy = CointegrationAnalysisModule(config={})

        # Test should_exit() at different candle points
        print(f"\n[4] Testing should_exit() method...")
        print("-" * 100)

        exit_found = False
        for i, (main_candle, pair_candle) in enumerate(zip(main_candles, pair_candles)):
            # Create a candle dict in the format expected by should_exit()
            current_candle = {
                "timestamp": main_candle['timestamp'],
                "open": main_candle['open'],
                "high": main_candle['high'],
                "low": main_candle['low'],
                "close": main_candle['close'],
            }

            pair_candle_dict = {
                "timestamp": pair_candle['timestamp'],
                "open": pair_candle['open'],
                "high": pair_candle['high'],
                "low": pair_candle['low'],
                "close": pair_candle['close'],
            }

            # Call should_exit()
            result = strategy.should_exit(
                trade=trade,
                current_candle=current_candle,
                pair_candle=pair_candle_dict
            )

            if i % 50 == 0 or result.get('should_exit'):
                print(f"Candle {i}: should_exit={result.get('should_exit')}")
                if result.get('exit_details'):
                    details = result['exit_details']
                    print(f"  Reason: {details.get('reason')}")
                    if 'z_score' in details:
                        print(f"  Z-score: {details.get('z_score'):.4f}")

                if result.get('should_exit'):
                    print(f"  ✅ EXIT SIGNAL FOUND!")
                    exit_found = True
                    break

        if not exit_found:
            print(f"\n❌ NO EXIT SIGNAL from should_exit() method")

        return exit_found

    finally:
        release_connection(conn)


if __name__ == "__main__":
    # Run both tests
    print("\n" + "=" * 100)
    print("RUNNING BOTH TESTS")
    print("=" * 100)

    test1_success = test_exit_signals_with_real_data()
    test2_success = test_should_exit_method_with_real_data()

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Test 1 (Manual z-score calculation): {'✅ PASS' if test1_success else '❌ FAIL'}")
    print(f"Test 2 (should_exit() method): {'✅ PASS' if test2_success else '❌ FAIL'}")

    sys.exit(0 if (test1_success and test2_success) else 1)

