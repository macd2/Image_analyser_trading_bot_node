#!/usr/bin/env python3
"""
Fetch candles for bot trade charts from the candle store database.

COPIED FROM: python/prompt_performance/get_trade_candles.py
REASON: Bot-specific version with additional features:
  - Checks if candles are up-to-date for recent trades
  - Fetches missing/stale candles automatically
  - Returns fetch_status for loading indicators
  - Uses centralized DB client for SQLite/PostgreSQL switching
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Use centralized database client
from trading_bot.db.client import get_connection, release_connection, query, execute, get_table_name, DB_TYPE


def _convert_timeframe_to_bybit(timeframe: str) -> str:
    """Convert timeframe like '1h', '4h', '1d' to Bybit API format like '60', '240', 'D'."""
    mapping = {
        '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
        '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
        '1d': 'D', '1D': 'D', '1w': 'W', '1W': 'W', '1M': 'M'
    }
    return mapping.get(timeframe, '60')


def _get_symbol_precision(symbol: str) -> dict:
    """Get price precision (tick size) and qty precision from Bybit for a symbol.

    NOTE: This function is DISABLED to avoid slow API calls.
    We use smart defaults based on the symbol instead.
    """
    # Smart defaults based on symbol patterns
    # Most USDT pairs use 2-4 decimals, BTC pairs use more
    if 'BTC' in symbol or symbol.startswith('BTC'):
        price_decimals = 2
        tick_size = 0.01
    elif symbol.endswith('1000') or '1000' in symbol:
        # 1000PEPE, 1000SHIB etc - very small prices
        price_decimals = 6
        tick_size = 0.000001
    else:
        # Default for most USDT pairs
        price_decimals = 4
        tick_size = 0.0001

    return {
        'tickSize': tick_size,
        'priceDecimals': price_decimals,
        'qtyStep': 0.001,
        'qtyDecimals': 3
    }

    # OLD CODE - DISABLED DUE TO SLOW API CALLS (30+ seconds)
    # try:
    #     from pybit.unified_trading import HTTP
    #     session = HTTP(testnet=False)
    #     api_symbol = symbol if not symbol.endswith('.P') else symbol[:-2]
    #     response = session.get_instruments_info(category="linear", symbol=api_symbol)
    #     if response.get('retCode') == 0 and response.get('result', {}).get('list'):
    #         instrument = response['result']['list'][0]
    #         price_filter = instrument.get('priceFilter', {})
    #         lot_filter = instrument.get('lotSizeFilter', {})
    #         tick_size = price_filter.get('tickSize', '0.01')
    #         qty_step = lot_filter.get('qtyStep', '0.001')
    #         # Calculate decimal places...
    #         return {...}
    # except Exception as e:
    #     sys.stderr.write(f"Failed to get symbol precision: {e}\n")

    # Default fallback (never reached now)
    return {
        'tickSize': 0.01,
        'priceDecimals': 2,
        'qtyStep': 0.001,
        'qtyDecimals': 3
    }


def _get_candle_connection():
    """Get connection to candle database. Uses centralized client for PostgreSQL,
    separate candle_store.db for SQLite."""
    if DB_TYPE == 'postgres':
        return get_connection()
    else:
        # SQLite: use separate candle_store.db
        import sqlite3
        db_path = Path(__file__).parent.parent.parent.parent / "data" / "candle_store.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        # Ensure table exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS klines_store (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                category TEXT NOT NULL,
                start_time INTEGER NOT NULL,
                open_price REAL NOT NULL,
                high_price REAL NOT NULL,
                low_price REAL NOT NULL,
                close_price REAL NOT NULL,
                volume REAL NOT NULL,
                turnover REAL NOT NULL,
                UNIQUE(symbol, timeframe, start_time)
            )
        """)
        conn.commit()
        return conn


def _get_candles_from_db(symbol: str, timeframe: str, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    """Get candles from database using centralized client for PostgreSQL."""
    conn = _get_candle_connection()
    try:
        # Normalize symbol (remove .P suffix if present)
        norm_symbol = symbol[:-2] if symbol.endswith('.P') else symbol

        # Table name differs: 'klines' for PostgreSQL, 'klines_store' for SQLite
        table_name = get_table_name('klines_store')

        rows = query(conn, f"""
            SELECT symbol, timeframe, category, start_time, open_price, high_price,
                   low_price, close_price, volume, turnover
            FROM {table_name}
            WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
            ORDER BY start_time ASC
            LIMIT 5000
        """, (norm_symbol, timeframe, start_ts, end_ts))

        candles = []
        for row in rows:
            candles.append({
                'symbol': row['symbol'],
                'timeframe': row['timeframe'],
                'category': row['category'],
                'start_time': row['start_time'],
                'open_price': row['open_price'],
                'high_price': row['high_price'],
                'low_price': row['low_price'],
                'close_price': row['close_price'],
                'volume': row['volume'],
                'turnover': row['turnover']
            })
        return candles
    finally:
        release_connection(conn)


def _insert_candles_to_db(candles: List[Dict[str, Any]], symbol: str, timeframe: str, category: str):
    """Insert candles into database using centralized client for PostgreSQL."""
    conn = _get_candle_connection()
    try:
        # Normalize symbol
        norm_symbol = symbol[:-2] if symbol.endswith('.P') else symbol

        # Table name differs: 'klines' for PostgreSQL, 'klines_store' for SQLite
        table_name = get_table_name('klines_store')

        for c in candles:
            try:
                execute(conn, f"""
                    INSERT INTO {table_name} (symbol, timeframe, category, start_time, open_price,
                                       high_price, low_price, close_price, volume, turnover)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (symbol, timeframe, start_time) DO NOTHING
                """, (
                    norm_symbol, timeframe, category, c['start_time'],
                    c['open_price'], c['high_price'], c['low_price'], c['close_price'],
                    c.get('volume', 0), c.get('turnover', 0)
                ))
            except Exception:
                pass  # Ignore duplicates
        conn.commit()
    finally:
        release_connection(conn)


def get_candles_for_trade(symbol: str, timeframe: str, timestamp_ms: int,
                          candles_before: int = 50, candles_after: int = 150) -> dict:
    """Get candles around a trade timestamp for chart display.

    Auto-fetches missing candles from the exchange API if not in cache.
    Uses centralized DB client for SQLite/PostgreSQL switching.

    Args:
        symbol: Trading pair (e.g., BTCUSDT)
        timeframe: Candle timeframe (e.g., 1h, 4h)
        timestamp_ms: Entry timestamp in milliseconds
        candles_before: Number of candles before the trade
        candles_after: Number of candles after the trade (default 150 for expired trades)

    Returns:
        Dict with candles array and metadata
    """
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

    # Get candles from database using centralized client
    candles = _get_candles_from_db(symbol, timeframe, start_ts, end_ts)

    # Check if we have enough candles before the signal
    expected_candles_before = candles_before
    candles_before_signal = [c for c in candles if c['start_time'] < timestamp_ms]
    candles_after_signal = [c for c in candles if c['start_time'] >= timestamp_ms]

    need_fetch = False
    fetch_status = 'cached'

    # Only check for candles BEFORE the signal - we show whatever exists after
    if len(candles_before_signal) < expected_candles_before * 0.8:  # 80% threshold
        need_fetch = True
        sys.stderr.write(f"Not enough candles before signal: {len(candles_before_signal)}/{expected_candles_before}\n")

    # For recent trades, check if candles are up-to-date
    # But DON'T require a specific number of candles after - just show what exists
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if candles and timestamp_ms > now_ms - (24 * 60 * 60 * 1000):  # Trade within last 24h
        latest_candle_time = max(c['start_time'] for c in candles) if candles else 0
        time_since_latest = now_ms - latest_candle_time
        max_age_ms = 2 * timeframe_ms  # Allow 2 candle periods of staleness

        if time_since_latest > max_age_ms:
            need_fetch = True
            sys.stderr.write(f"Candles are stale: {time_since_latest // 60000}min old\n")

    # If we don't have enough candles, fetch them directly from Bybit API
    if need_fetch or len(candles) < 10:
        try:
            sys.stderr.write(f"Fetching candles for {symbol} {timeframe} directly from Bybit...\n")
            fetch_status = 'fetching'

            # Fetch candles directly using backward fetch to get data around the trade time
            from pybit.unified_trading import HTTP
            session = HTTP(testnet=False)

            # Fetch candles ending at end_ts (to get candles before the trade)
            api_symbol = symbol if not symbol.endswith('.P') else symbol[:-2]

            response = session.get_kline(
                category="linear",
                symbol=api_symbol,
                interval=_convert_timeframe_to_bybit(timeframe),
                end=end_ts,
                limit=candles_before + candles_after + 10
            )

            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                fetched_candles = []
                # Bybit returns candles in reverse chronological order (newest first)
                # We need to reverse them to get oldest first
                for kline in reversed(response['result']['list']):
                    fetched_candles.append({
                        'start_time': int(kline[0]),
                        'open_price': float(kline[1]),
                        'high_price': float(kline[2]),
                        'low_price': float(kline[3]),
                        'close_price': float(kline[4]),
                        'volume': float(kline[5]) if len(kline) > 5 else 0,
                        'turnover': float(kline[6]) if len(kline) > 6 else 0
                    })

                # Cache these candles for future use using centralized client
                if fetched_candles:
                    # IMPORTANT: Filter out incomplete candles (current timeframe still forming)
                    # A candle is incomplete if it started within the current timeframe period
                    import time
                    now_ms = int(time.time() * 1000)
                    timeframe_ms_map = {
                        '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000, '30m': 1800000,
                        '1h': 3600000, '2h': 7200000, '4h': 14400000, '6h': 21600000, '12h': 43200000,
                        '1d': 86400000, '1w': 604800000, '1M': 2592000000
                    }
                    timeframe_ms_val = timeframe_ms_map.get(timeframe, 3600000)

                    # Filter out candles that started within the current timeframe period
                    filtered_candles = [c for c in fetched_candles if (now_ms - c['start_time']) >= timeframe_ms_val]

                    if len(filtered_candles) < len(fetched_candles):
                        sys.stderr.write(f"Filtered out {len(fetched_candles) - len(filtered_candles)} incomplete candle(s) before caching\n")

                    try:
                        category = 'linear'
                        _insert_candles_to_db(filtered_candles, symbol, timeframe, category)
                    except Exception as cache_err:
                        sys.stderr.write(f"Cache error (non-fatal): {cache_err}\n")

                    # Merge filtered candles with cached ones (NEVER overwrite, only add new)
                    # Create a dict of cached candles by time
                    cached_by_time = {c['start_time']: c for c in candles}

                    # Count new candles added
                    new_candles_count = 0
                    for fc in fetched_candles:
                        if fc['start_time'] not in cached_by_time:
                            # Only add if this timestamp doesn't exist
                            cached_by_time[fc['start_time']] = fc
                            new_candles_count += 1
                        # If timestamp exists, keep the cached version (never overwrite)

                    # Convert back to sorted list
                    candles = sorted(cached_by_time.values(), key=lambda x: x['start_time'])
                    fetch_status = 'fetched'
                    sys.stderr.write(f"Fetched {len(fetched_candles)} candles from Bybit, filtered to {len(filtered_candles)}, added {new_candles_count} new, total now {len(cached_by_time)}\n")
            else:
                sys.stderr.write(f"Bybit API error: {response.get('retMsg', 'Unknown error')}\n")
                fetch_status = 'error'
        except Exception as e:
            # Log error but continue with what we have
            fetch_status = 'error'
            sys.stderr.write(f"Warning: Failed to fetch candles: {e}\n")

    # Format for lightweight-charts and deduplicate by time
    # Use dict to deduplicate by time (keep first valid entry, never overwrite)
    candles_by_time = {}
    for c in candles:
        time_key = c['start_time'] // 1000  # Convert to seconds for lightweight-charts

        # Skip if we already have a candle for this time (never overwrite)
        if time_key in candles_by_time:
            sys.stderr.write(f"Warning: Duplicate candle at {time_key}, keeping existing\n")
            continue

        # Validate candle data
        try:
            open_price = float(c['open_price'])
            high_price = float(c['high_price'])
            low_price = float(c['low_price'])
            close_price = float(c['close_price'])
            volume = float(c.get('volume', 0))

            # Check for invalid values
            if not all(isinstance(p, float) and p > 0 for p in [open_price, high_price, low_price, close_price]):
                sys.stderr.write(f"Warning: Invalid candle prices at {time_key}: O={open_price} H={high_price} L={low_price} C={close_price}\n")
                continue

            # Validate OHLC relationships
            if not (low_price <= min(open_price, close_price) and max(open_price, close_price) <= high_price):
                sys.stderr.write(f"Warning: Invalid OHLC relationship at {time_key}: O={open_price} H={high_price} L={low_price} C={close_price}\n")
                continue

            candles_by_time[time_key] = {
                'time': time_key,
                'open': open_price,
                'high': high_price,
                'low': low_price,
                'close': close_price,
                'volume': volume
            }
        except (ValueError, TypeError) as e:
            sys.stderr.write(f"Warning: Failed to parse candle at {time_key}: {e}\n")
            continue

    # Sort by time to ensure correct order
    formatted = sorted(candles_by_time.values(), key=lambda x: x['time'])

    # Filter out incomplete candles (current candle still forming)
    # A candle is incomplete if it started within the current timeframe period
    import time
    now_ms = int(time.time() * 1000)
    timeframe_ms = {
        '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000, '30m': 1800000,
        '1h': 3600000, '2h': 7200000, '4h': 14400000, '6h': 21600000, '12h': 43200000,
        '1d': 86400000, '1w': 604800000, '1M': 2592000000
    }.get(timeframe, 3600000)

    # Keep only candles that started more than one timeframe ago
    formatted_filtered = [c for c in formatted if (now_ms - (c['time'] * 1000)) >= timeframe_ms]

    if len(formatted_filtered) < len(formatted):
        sys.stderr.write(f"Filtered out {len(formatted) - len(formatted_filtered)} incomplete candle(s) (still forming)\n")

    formatted = formatted_filtered

    # Log candle data for debugging
    if formatted:
        sys.stderr.write(f"Formatted {len(formatted)} candles\n")
        sys.stderr.write(f"First candle: time={formatted[0]['time']}, O={formatted[0]['open']}, H={formatted[0]['high']}, L={formatted[0]['low']}, C={formatted[0]['close']}\n")
        sys.stderr.write(f"Last candle: time={formatted[-1]['time']}, O={formatted[-1]['open']}, H={formatted[-1]['high']}, L={formatted[-1]['low']}, C={formatted[-1]['close']}\n")

        # Check for gaps in the time series
        if len(formatted) > 1:
            gaps = []
            for i in range(1, len(formatted)):
                time_diff = formatted[i]['time'] - formatted[i-1]['time']
                expected_diff = timeframe_ms // 1000  # Expected time difference in seconds
                if time_diff > expected_diff * 1.5:  # Allow 50% tolerance
                    gaps.append((formatted[i-1]['time'], formatted[i]['time'], time_diff))

            if gaps:
                sys.stderr.write(f"Found {len(gaps)} gaps in candle data:\n")
                for gap in gaps[:5]:  # Log first 5 gaps
                    sys.stderr.write(f"  Gap between {gap[0]} and {gap[1]} ({gap[2]}s)\n")

    # Get symbol precision for price formatting
    precision = _get_symbol_precision(symbol)

    return {
        'success': True,
        'symbol': symbol,
        'timeframe': timeframe,
        'entry_timestamp': timestamp_ms,
        'candles': formatted,
        'count': len(formatted),
        'fetch_status': fetch_status,
        'precision': precision
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

