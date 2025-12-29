#!/usr/bin/env python3
"""
Systematic test for check_strategy_exit.py with real data from the dashboard.

This script:
1. Fetches real trade data from the database
2. Fetches real candles for both symbols
3. Calls check_strategy_exit.py with the exact same data as the auto-close route
4. Measures execution time and identifies bottlenecks
5. Tests with and without pair candles to isolate the issue

Usage:
  python3 test_strategy_exit_systematic.py [--trade-id TRADE_ID] [--verbose]
"""

import sys
import json
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from trading_bot.db.client import get_connection, query_one, query, release_connection


def get_real_trade_data(trade_id: str = None):
    """Fetch a real spread-based trade from the database."""
    conn = get_connection(timeout_seconds=10.0)
    try:
        # If no trade_id provided, find the most recent spread-based trade
        if not trade_id:
            sql = """
                SELECT * FROM trades 
                WHERE strategy_type = 'spread_based' 
                AND status IN ('filled', 'open')
                ORDER BY created_at DESC 
                LIMIT 1
            """
            trade = query_one(conn, sql)
        else:
            trade = query_one(conn, "SELECT * FROM trades WHERE id = ?", (trade_id,))
        
        if not trade:
            print("❌ No spread-based trades found in database")
            return None
        
        return trade
    finally:
        release_connection(conn)


def get_candles_for_symbol(symbol: str, timeframe: str, limit: int = 101):
    """Fetch real candles from the database."""
    conn = get_connection(timeout_seconds=10.0)
    try:
        sql = """
            SELECT 
                start_time as timestamp,
                open_price as open,
                high_price as high,
                low_price as low,
                close_price as close,
                volume
            FROM klines
            WHERE symbol = ? AND timeframe = ?
            ORDER BY start_time DESC
            LIMIT ?
        """
        candles = query(conn, sql, (symbol, timeframe, limit))
        # Reverse to get chronological order
        return list(reversed(candles))
    finally:
        release_connection(conn)


def run_check_strategy_exit(trade_id: str, strategy_name: str, candles: list, 
                            trade_data: dict, pair_candles: list = None, 
                            timeout: int = 120):
    """Run check_strategy_exit.py and measure execution time."""
    script_path = Path(__file__).parent / "check_strategy_exit.py"
    
    args = [
        sys.executable,
        str(script_path),
        trade_id,
        strategy_name,
        json.dumps(candles),
        json.dumps(trade_data),
    ]
    
    if pair_candles:
        args.append(json.dumps(pair_candles))
    
    print(f"\n{'='*70}")
    print(f"Running check_strategy_exit.py")
    print(f"{'='*70}")
    print(f"Trade ID: {trade_id}")
    print(f"Strategy: {strategy_name}")
    print(f"Candles: {len(candles)}")
    print(f"Pair candles: {len(pair_candles) if pair_candles else 'None'}")
    print(f"Timeout: {timeout}s")
    
    start_time = time.time()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start_time
        
        print(f"\n✅ Completed in {elapsed:.2f}s")
        print(f"Return code: {result.returncode}")
        
        if result.stderr:
            print(f"\nStderr:\n{result.stderr}")
        
        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
                print(f"\nResult:")
                print(json.dumps(output, indent=2))
                return output, elapsed
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON output: {e}")
                print(f"Stdout: {result.stdout}")
                return None, elapsed
        else:
            print(f"❌ Script failed with code {result.returncode}")
            print(f"Stdout: {result.stdout}")
            return None, elapsed
            
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"\n❌ TIMEOUT after {elapsed:.2f}s (limit: {timeout}s)")
        return None, elapsed


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Test check_strategy_exit.py systematically')
    parser.add_argument('--trade-id', help='Specific trade ID to test')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print("SYSTEMATIC TEST: check_strategy_exit.py")
    print(f"{'='*70}")
    
    # Get real trade data
    print("\n[1/4] Fetching trade data from database...")
    trade = get_real_trade_data(args.trade_id)
    if not trade:
        sys.exit(1)
    
    print(f"✅ Found trade: {trade['id']}")
    print(f"   Symbol: {trade['symbol']}")
    print(f"   Strategy: {trade.get('strategy_name', 'unknown')}")
    print(f"   Pair: {trade.get('pair_symbol', 'unknown')}")
    
    # Get candles
    print("\n[2/4] Fetching candles from database...")
    candles = get_candles_for_symbol(trade['symbol'], trade.get('timeframe', '1h'))
    print(f"✅ Fetched {len(candles)} candles for {trade['symbol']}")
    
    # Get pair candles
    print("\n[3/4] Fetching pair candles from database...")
    pair_symbol = trade.get('pair_symbol')
    pair_candles = None
    if pair_symbol:
        pair_candles = get_candles_for_symbol(pair_symbol, trade.get('timeframe', '1h'))
        print(f"✅ Fetched {len(pair_candles)} candles for {pair_symbol}")
    else:
        print("⚠️  No pair symbol found in trade data")
    
    # Prepare trade data
    trade_data = {
        'id': trade['id'],
        'symbol': trade['symbol'],
        'side': trade['side'],
        'entry_price': trade['entry_price'],
        'stop_loss': trade['stop_loss'],
        'take_profit': trade['take_profit'],
        'strategy_type': trade.get('strategy_type', 'unknown'),
        'strategy_metadata': json.loads(trade.get('strategy_metadata', '{}')) if isinstance(trade.get('strategy_metadata'), str) else trade.get('strategy_metadata', {}),
        'pair_symbol': pair_symbol,
    }
    
    # Test 1: With pair candles (normal case)
    print("\n[4/4] Testing with pair candles...")
    result1, time1 = run_check_strategy_exit(
        trade['id'],
        trade.get('strategy_name', 'CointegrationSpreadTrader'),
        candles,
        trade_data,
        pair_candles,
        timeout=120
    )
    
    # Test 2: Without pair candles (fallback case - will fetch from API)
    print("\n[5/4] Testing WITHOUT pair candles (will fetch from API)...")
    result2, time2 = run_check_strategy_exit(
        trade['id'],
        trade.get('strategy_name', 'CointegrationSpreadTrader'),
        candles,
        trade_data,
        pair_candles=None,
        timeout=120
    )
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"With pair candles:    {time1:.2f}s {'✅' if result1 else '❌'}")
    print(f"Without pair candles: {time2:.2f}s {'✅' if result2 else '❌'}")
    
    if time2 > time1 + 5:
        print(f"\n⚠️  API fetch is slow! Difference: {time2 - time1:.2f}s")
        print("   → Ensure pair candles are always passed to avoid API calls")
    
    return 0 if (result1 or result2) else 1


if __name__ == "__main__":
    sys.exit(main())

