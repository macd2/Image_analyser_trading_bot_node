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
from trading_bot.db.client import get_connection, query, execute, get_table_name, DB_TYPE


def _convert_timeframe_to_bybit(timeframe: str) -> str:
    """Convert timeframe like '1h', '4h', '1d' to Bybit API format like '60', '240', 'D'."""
    mapping = {
        '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
        '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
        '1d': 'D', '1D': 'D', '1w': 'W', '1W': 'W', '1M': 'M'
    }
    return mapping.get(timeframe, '60')


def _get_symbol_precision(symbol: str) -> dict:
    """Get price precision (tick size) and qty precision from Bybit for a symbol."""
    try:
        from pybit.unified_trading import HTTP
        session = HTTP(testnet=False)

        api_symbol = symbol if not symbol.endswith('.P') else symbol[:-2]

        response = session.get_instruments_info(
            category="linear",
            symbol=api_symbol
        )

        if response.get('retCode') == 0 and response.get('result', {}).get('list'):
            instrument = response['result']['list'][0]
            price_filter = instrument.get('priceFilter', {})
            lot_filter = instrument.get('lotSizeFilter', {})

            tick_size = price_filter.get('tickSize', '0.01')
            qty_step = lot_filter.get('qtyStep', '0.001')

            # Calculate decimal places from tick size
            tick_size_str = str(tick_size)
            if '.' in tick_size_str:
                price_decimals = len(tick_size_str.split('.')[1].rstrip('0')) or 0
            else:
                price_decimals = 0

            qty_step_str = str(qty_step)
            if '.' in qty_step_str:
                qty_decimals = len(qty_step_str.split('.')[1].rstrip('0')) or 0
            else:
                qty_decimals = 0

            return {
                'tickSize': float(tick_size),
                'priceDecimals': price_decimals,
                'qtyStep': float(qty_step),
                'qtyDecimals': qty_decimals
            }
    except Exception as e:
        sys.stderr.write(f"Failed to get symbol precision: {e}\n")

    # Default fallback
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
        conn.close()


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
        conn.close()


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

    # Check if candles are up-to-date (for recent trades)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if candles and timestamp_ms > now_ms - (24 * 60 * 60 * 1000):  # Trade within last 24h
        latest_candle_time = max(c['start_time'] for c in candles)
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
                for kline in response['result']['list']:
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
                    try:
                        category = 'linear'
                        _insert_candles_to_db(fetched_candles, symbol, timeframe, category)
                    except Exception as cache_err:
                        sys.stderr.write(f"Cache error (non-fatal): {cache_err}\n")

                    # Use the fetched candles directly (sorted by time ascending)
                    candles = sorted(fetched_candles, key=lambda x: x['start_time'])
                    fetch_status = 'fetched'
                    sys.stderr.write(f"Fetched {len(candles)} candles from Bybit\n")
            else:
                sys.stderr.write(f"Bybit API error: {response.get('retMsg', 'Unknown error')}\n")
                fetch_status = 'error'
        except Exception as e:
            # Log error but continue with what we have
            fetch_status = 'error'
            sys.stderr.write(f"Warning: Failed to fetch candles: {e}\n")

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

