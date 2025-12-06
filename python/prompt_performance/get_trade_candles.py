#!/usr/bin/env python3
"""Fetch candles for trade verification from the candle store database."""
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_performance.core.database_utils import CandleStoreDatabase
from prompt_performance.core.candle_fetcher import CandleFetcher


def get_candles_for_trade(symbol: str, timeframe: str, timestamp_ms: int,
                          candles_before: int = 50, candles_after: int = 150) -> dict:
    """Get candles around a trade timestamp for chart display.

    Auto-fetches missing candles from the exchange API if not in cache.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        timeframe: Candle timeframe (e.g., 1h, 4h)
        timestamp_ms: Entry timestamp in milliseconds
        candles_before: Number of candles before the trade
        candles_after: Number of candles after the trade (default 150 for expired trades)

    Returns:
        Dict with candles array and metadata
    """
    db = CandleStoreDatabase()

    # Calculate time range based on timeframe
    timeframe_ms = {
        '1m': 60 * 1000,
        '3m': 3 * 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '30m': 30 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '2h': 2 * 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '6h': 6 * 60 * 60 * 1000,
        '12h': 12 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
        '1D': 24 * 60 * 60 * 1000,
    }.get(timeframe, 60 * 60 * 1000)  # Default to 1h

    start_ts = timestamp_ms - (candles_before * timeframe_ms)
    end_ts = timestamp_ms + (candles_after * timeframe_ms)

    # First try to get from cache
    candles = db.get_candles_between_timestamps(symbol, timeframe, start_ts, end_ts)

    # Check if we have enough candles before and after the signal
    expected_candles_before = candles_before
    expected_candles_after = candles_after
    candles_before_signal = [c for c in candles if c['start_time'] < timestamp_ms]
    candles_after_signal = [c for c in candles if c['start_time'] >= timestamp_ms]

    need_fetch = False
    fetch_status = 'cached'

    # Check if we need to fetch more candles
    if len(candles_before_signal) < expected_candles_before * 0.8:  # 80% threshold
        need_fetch = True
        sys.stderr.write(f"Not enough candles before signal: {len(candles_before_signal)}/{expected_candles_before}\n")

    if len(candles_after_signal) < expected_candles_after * 0.8:  # 80% threshold
        need_fetch = True
        sys.stderr.write(f"Not enough candles after signal: {len(candles_after_signal)}/{expected_candles_after}\n")

    # If we don't have enough candles, fetch them
    if need_fetch:
        try:
            sys.stderr.write(f"Fetching candles for {symbol} {timeframe}...\n")
            fetch_status = 'fetching'
            fetcher = CandleFetcher(use_testnet=False)
            # Fetch candles from start to end
            fetcher.fetch_and_cache_candles(
                symbol=symbol,
                timeframe=timeframe,
                earliest_timestamp=start_ts
            )
            # Re-query after fetch
            candles = db.get_candles_between_timestamps(symbol, timeframe, start_ts, end_ts)
            fetch_status = 'fetched'
            sys.stderr.write(f"Fetched {len(candles)} candles\n")
        except Exception as e:
            # Log error but continue with what we have
            fetch_status = 'error'
            sys.stderr.write(f"Warning: Failed to fetch additional candles: {e}\n")

    # Format for lightweight-charts
    formatted = []
    for c in candles:
        formatted.append({
            'time': c['start_time'] // 1000,  # Convert to seconds for lightweight-charts
            'open': float(c['open_price']),
            'high': float(c['high_price']),
            'low': float(c['low_price']),
            'close': float(c['close_price']),
            'volume': float(c.get('volume', 0))
        })

    return {
        'success': True,
        'symbol': symbol,
        'timeframe': timeframe,
        'entry_timestamp': timestamp_ms,
        'candles': formatted,
        'count': len(formatted)
    }


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(json.dumps({'error': 'Usage: get_trade_candles.py <symbol> <timeframe> <timestamp_ms>'}))
        sys.exit(1)
    
    symbol = sys.argv[1]
    timeframe = sys.argv[2]
    timestamp_ms = int(sys.argv[3])
    candles_before = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    candles_after = int(sys.argv[5]) if len(sys.argv) > 5 else 50
    
    result = get_candles_for_trade(symbol, timeframe, timestamp_ms, candles_before, candles_after)
    print(json.dumps(result))

