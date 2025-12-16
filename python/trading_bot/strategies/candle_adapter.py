"""
CandleAdapter - Unified interface for getting candles from database or API.

Strategies use this instead of calling Bybit directly.
Handles caching and fallback to real API if needed.
Uses centralized database layer for both SQLite and PostgreSQL.
"""

from typing import List, Dict, Any, Optional
import logging
import os
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from env.local
load_dotenv('.env.local')

# Thread pool for blocking API calls
_executor = ThreadPoolExecutor(max_workers=5)


class CandleAdapter:
    """
    Unified interface for getting candles.

    Priority:
    1. Check database cache (klines table)
    2. If missing, fetch from Bybit API
    3. Cache the results for future use

    Uses centralized database layer that handles both SQLite and PostgreSQL.
    """

    def __init__(self, instance_id: Optional[str] = None):
        """
        Initialize candle adapter.

        Args:
            instance_id: Instance ID (for logging/context)
        """
        self.instance_id = instance_id
        self.logger = logging.getLogger(__name__)
        self._available_symbols = None
        self._symbols_fetched_at = 0

    async def _get_available_symbols(self) -> List[str]:
        """
        Get list of available symbols from Bybit.
        Caches the result for 24 hours.
        """
        current_time = time.time()
        # Refresh if not cached or cache is older than 24 hours
        if self._available_symbols is None or (current_time - self._symbols_fetched_at) > 24 * 3600:
            try:
                from prompt_performance.core.bybit_symbols import get_bybit_symbols_cached
                self._available_symbols = get_bybit_symbols_cached(category="linear")
                self._symbols_fetched_at = current_time
                self.logger.debug(f"Fetched {len(self._available_symbols)} available symbols from Bybit")
            except Exception as e:
                self.logger.warning(f"Failed to fetch available symbols: {e}")
                self._available_symbols = []
        return self._available_symbols or []

    async def symbol_exists(self, symbol: str) -> bool:
        """
        Check if a symbol exists on Bybit perpetual market.

        Args:
            symbol: Symbol to check (e.g., 'BTCUSDT', 'ETHUSDT')

        Returns:
            True if symbol exists, False otherwise
        """
        available = await self._get_available_symbols()
        return symbol in available

    def _timeframe_to_ms(self, timeframe: str) -> int:
        """Convert timeframe string to milliseconds."""
        timeframe_map = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "30m": 30 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
            "1w": 7 * 24 * 60 * 60 * 1000,
        }
        return timeframe_map.get(timeframe, 60 * 60 * 1000)  # Default to 1h

    def _normalize_candle(self, candle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize candle field names to standard format.

        Handles different candle formats from different sources:
        - Database: open_price, high_price, low_price, close_price, volume, turnover
        - Bybit API: open, high, low, close, volume, turnover

        Returns normalized candle with standard field names:
        - open, high, low, close, volume, turnover, timestamp
        """
        normalized = {}

        # Map all possible field names to standard names
        field_mappings = {
            'timestamp': ['timestamp', 'start_time', 'time'],
            'open': ['open', 'open_price'],
            'high': ['high', 'high_price'],
            'low': ['low', 'low_price'],
            'close': ['close', 'close_price'],
            'volume': ['volume', 'vol'],
            'turnover': ['turnover', 'quote_asset_volume'],
        }

        for standard_name, possible_names in field_mappings.items():
            for possible_name in possible_names:
                if possible_name in candle:
                    normalized[standard_name] = candle[possible_name]
                    break

        return normalized
    
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        use_cache: bool = True,
        min_candles: int = 10,
        prefer_source: str = "cache",
        cache_to_db: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get candles for a symbol/timeframe.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Timeframe (e.g., "1h", "4h")
            limit: Number of candles to return
            use_cache: Whether to use cached candles
            min_candles: Minimum number of candles required (default: 10)
            prefer_source: "cache" (prefer cached, fallback to API) or "api" (prefer API, fallback to cache)
            cache_to_db: Whether to cache fetched candles to database (default: True)

        Returns:
            List of candles with OHLCV data (or empty list if < min_candles)
        """
        print(f"[CandleAdapter] Fetching {symbol} {timeframe} (prefer_source={prefer_source})", flush=True)

        # Determine source priority based on prefer_source
        sources = []
        if prefer_source == "api":
            sources = ["api", "cache"]
        else:  # Default to "cache"
            sources = ["cache", "api"]

        for source in sources:
            print(f"[CandleAdapter] Trying source: {source}", flush=True)
            if source == "cache" and use_cache:
                try:
                    # Try to get from database using centralized layer
                    from trading_bot.db.client import get_connection, release_connection, query, get_table_name

                    conn = get_connection()
                    try:
                        # Get the latest candles for this symbol/timeframe
                        table_name = get_table_name('klines_store')
                        sql = f"""
                            SELECT * FROM {table_name}
                            WHERE symbol = ? AND timeframe = ?
                            ORDER BY start_time DESC
                            LIMIT ?
                        """
                        cached = query(conn, sql, (symbol, timeframe, limit))

                        if cached and len(cached) >= min_candles:
                            # Check if we got close to the requested limit
                            # If we got significantly fewer than requested, try API for more
                            if len(cached) >= limit * 0.8:  # Got at least 80% of requested
                                # Reverse to get chronological order
                                cached = list(reversed(cached))
                                print(f"[CandleAdapter] Got {len(cached)} candles from cache", flush=True)
                                self.logger.debug(
                                    f"Got {len(cached)} candles from cache for {symbol} {timeframe}",
                                    extra={"symbol": symbol, "instance_id": self.instance_id}
                                )
                                # Normalize candle field names
                                return [self._normalize_candle(c) for c in cached]
                            # If we got fewer than 80% of requested, try API for more
                        # If we got some but not enough, or got nothing, continue to next source
                    finally:
                        release_connection(conn)
                except Exception as e:
                    self.logger.warning(f"Failed to get cached candles: {e}")
                # Fall through to try API

            elif source == "api":
                # Fetch from API with rate limit handling
                try:
                    print(f"[CandleAdapter] Fetching from API...", flush=True)

                    # Try to use pybit directly (simpler than BybitAPIManager which needs full config)
                    from pybit.unified_trading import HTTP
                    import time

                    # Get API credentials from environment
                    api_key = os.getenv('BYBIT_API_KEY')
                    api_secret = os.getenv('BYBIT_API_SECRET')

                    if api_key and api_secret:
                        session = HTTP(api_key=api_key, api_secret=api_secret, testnet=False)
                    else:
                        # Fallback to public session (limited rate limit)
                        session = HTTP(testnet=False)

                    # Normalize symbol for Bybit
                    api_symbol = symbol if not symbol.endswith('.P') else symbol[:-2]

                    # Map timeframe to Bybit interval
                    interval_map = {
                        "1m": "1",
                        "5m": "5",
                        "15m": "15",
                        "30m": "30",
                        "1h": "60",
                        "4h": "240",
                        "1d": "D",
                        "1w": "W",
                    }
                    interval = interval_map.get(timeframe, "60")

                    # Run blocking API call in thread pool with rate limit handling
                    print(f"[CandleAdapter] Calling get_kline({api_symbol}, {interval})...", flush=True)

                    max_retries = 3
                    retry_count = 0
                    response = None

                    while retry_count < max_retries:
                        try:
                            response = await asyncio.get_event_loop().run_in_executor(
                                _executor,
                                lambda: session.get_kline(
                                    category="linear",
                                    symbol=api_symbol,
                                    interval=interval,
                                    limit=limit
                                )
                            )
                            break  # Success, exit retry loop
                        except Exception as e:
                            error_str = str(e)
                            # Check for rate limit error
                            if "10006" in error_str or "rate limit" in error_str.lower():
                                retry_count += 1
                                if retry_count < max_retries:
                                    wait_time = 2 ** retry_count  # Exponential backoff: 2, 4, 8 seconds
                                    print(f"[CandleAdapter] Rate limited, waiting {wait_time}s before retry {retry_count}/{max_retries}...", flush=True)
                                    await asyncio.sleep(wait_time)
                                else:
                                    print(f"[CandleAdapter] Rate limit exceeded after {max_retries} retries", flush=True)
                                    raise
                            else:
                                raise

                    if response is None:
                        print(f"[CandleAdapter] Failed to get response after retries", flush=True)
                        continue

                    print(f"[CandleAdapter] Got response: retCode={response.get('retCode')}", flush=True)

                    if response.get('retCode') == 0:
                        candles = response.get('result', {}).get('list', [])
                        print(f"[CandleAdapter] Got {len(candles)} candles from API", flush=True)
                        # Convert Bybit format to standard format
                        candles = [
                            {
                                'timestamp': int(c[0]),
                                'open': float(c[1]),
                                'high': float(c[2]),
                                'low': float(c[3]),
                                'close': float(c[4]),
                                'volume': float(c[5]),
                                'turnover': float(c[6]) if len(c) > 6 else 0,
                            }
                            for c in candles
                        ]
                    else:
                        candles = []
                        print(f"[CandleAdapter] API error: retCode={response.get('retCode')}", flush=True)

                    # Check minimum candles requirement
                    if candles and len(candles) < min_candles:
                        self.logger.warning(
                            f"Got {len(candles)} candles but minimum required is {min_candles} for {symbol} {timeframe}",
                            extra={"symbol": symbol, "instance_id": self.instance_id}
                        )
                        continue  # Try next source

                    # Cache for future use (async) - only if enabled
                    if candles and cache_to_db:
                        await self._cache_candles_async(symbol, timeframe, candles)

                    if candles:
                        self.logger.debug(
                            f"Fetched {len(candles)} candles from API for {symbol} {timeframe}",
                            extra={"symbol": symbol, "instance_id": self.instance_id}
                        )
                        # Normalize candle field names
                        return [self._normalize_candle(c) for c in candles]
                except Exception as e:
                    self.logger.warning(
                        f"Failed to get candles from API: {e}",
                        extra={"symbol": symbol, "instance_id": self.instance_id}
                    )

        # No candles found from any source
        return []
    
    def get_candles_since(
        self,
        symbol: str,
        timeframe: str,
        since_timestamp: int
    ) -> List[Dict[str, Any]]:
        """
        Get all candles since a specific timestamp.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            since_timestamp: Unix timestamp (milliseconds)
        
        Returns:
            List of candles since timestamp
        """
        if not self.candle_store:
            return []
        
        try:
            return self.candle_store.get_candles_since(symbol, timeframe, since_timestamp)
        except Exception as e:
            self.logger.error(
                f"Failed to get candles since {since_timestamp}: {e}",
                extra={"symbol": symbol, "instance_id": self.instance_id}
            )
            return []
    
    async def _cache_candles_async(self, symbol: str, timeframe: str, candles: List[Dict[str, Any]]) -> None:
        """Async wrapper for caching candles."""
        await asyncio.get_event_loop().run_in_executor(
            _executor,
            lambda: self.cache_candles(symbol, timeframe, candles)
        )

    def cache_candles(
        self,
        symbol: str,
        timeframe: str,
        candles: List[Dict[str, Any]]
    ) -> bool:
        """
        Manually cache candles using centralized database layer.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            candles: List of candles to cache

        Returns:
            True if successful
        """
        try:
            from trading_bot.db.client import get_connection, release_connection, execute, get_table_name

            # Convert to database format for caching
            db_candles = [
                {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'category': 'linear',
                    'start_time': c.get('timestamp', c.get('start_time')),
                    'open_price': c.get('open', c.get('open_price')),
                    'high_price': c.get('high', c.get('high_price')),
                    'low_price': c.get('low', c.get('low_price')),
                    'close_price': c.get('close', c.get('close_price')),
                    'volume': c.get('volume'),
                    'turnover': c.get('turnover'),
                }
                for c in candles
            ]

            from trading_bot.db.client import DB_TYPE

            conn = get_connection()
            try:
                table_name = get_table_name('klines_store')
                for candle in db_candles:
                    # Use different syntax for SQLite vs PostgreSQL
                    if DB_TYPE == 'postgres':
                        sql = f"""
                            INSERT INTO {table_name}
                            (symbol, timeframe, category, start_time, open_price, high_price, low_price, close_price, volume, turnover)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """
                    else:
                        sql = f"""
                            INSERT OR IGNORE INTO {table_name}
                            (symbol, timeframe, category, start_time, open_price, high_price, low_price, close_price, volume, turnover)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """

                    execute(conn, sql, (
                        candle['symbol'],
                        candle['timeframe'],
                        candle['category'],
                        candle['start_time'],
                        candle['open_price'],
                        candle['high_price'],
                        candle['low_price'],
                        candle['close_price'],
                        candle['volume'],
                        candle['turnover'],
                    ))
                return True
            finally:
                release_connection(conn)
        except Exception as e:
            self.logger.error(
                f"Failed to cache candles: {e}",
                extra={"symbol": symbol, "instance_id": self.instance_id}
            )
            return False

