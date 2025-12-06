import logging
import time
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.config.settings_v2 import Config
from .database_utils import CandleStoreDatabase

logger = logging.getLogger(__name__)

class CandleFetcher:
    """Handles fetching and storing candles from Bybit API.

    Candles are stored permanently in the candle store database and NEVER deleted.
    """

    def __init__(self, config: Optional[Config] = None, use_testnet: bool = False):
        if config is None:
            # Look for config.yaml in the parent directory of prompt_performance
            import sys
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "config.yaml"
            # Fallback to default working-directory config if not found
            cfg_path_str = str(config_path if config_path.exists() else Path("config.yaml"))
            self.config = Config.from_yaml(cfg_path_str)
        else:
            self.config = config
        self.api_manager = BybitAPIManager(self.config, use_testnet=use_testnet)
        self.db = CandleStoreDatabase()

    def _infer_category_from_symbol(self, symbol: str) -> str:
        """Infer Bybit category from symbol."""
        symbol_upper = symbol.upper()

        if '.P' in symbol_upper:
            return 'linear'
        elif 'USD' in symbol_upper and not symbol_upper.endswith('USDT'):
            return 'inverse'
        else:
            return 'linear'  # Default

    def _normalize_symbol_for_api(self, symbol: str) -> str:
        """Normalize symbol for Bybit API (remove suffixes if needed)."""
        # Remove common suffixes for API compatibility
        symbol = symbol.upper()
        for suffix in ['.P', '.S']:
            if symbol.endswith(suffix):
                symbol = symbol[:-len(suffix)]
                break
        return symbol

    def _map_timeframe_to_interval(self, timeframe: str) -> str:
        """Map internal timeframe to Bybit API interval."""
        mapping = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '4h': '240',
            '1d': 'D',
            '1w': 'W'
        }
        return mapping.get(timeframe, '60')  # Default to 1h

    def _timeframe_to_ms(self, timeframe: str) -> int:
        mapping = {'1m': 60_000, '5m': 300_000, '15m': 900_000, '30m': 1_800_000, '1h': 3_600_000, '4h': 14_400_000, '1d': 86_400_000, '1w': 604_800_000}
        return mapping.get(timeframe, 3_600_000)


    def _fetch_candles_from_api(self, symbol: str, timeframe: str, start_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch candles from Bybit API with retry logic."""
        category = self._infer_category_from_symbol(symbol)
        api_symbol = self._normalize_symbol_for_api(symbol)
        interval = self._map_timeframe_to_interval(timeframe)

        logger.info(f"Fetching {limit} candles for {symbol} {timeframe} from {start_time} (category: {category}, interval: {interval})")

        # Bybit API parameters
        params = {
            'symbol': api_symbol,
            'interval': interval,
            'start': start_time,
            'limit': limit,
            'category': category
        }

        response = self.api_manager.get_kline(**params)

        if not response or response.get('retCode') != 0:
            logger.error(f"Failed to fetch candles: {response}")
            return []

        candles_data = response.get('result', {}).get('list', [])
        if not candles_data:
            logger.warning("No candles returned from API")
            return []

        # Parse candles from API response
        candles = []
        for candle_data in candles_data:
            try:
                # Bybit returns: [start_time, open, high, low, close, volume, turnover]
                candle = {
                    'start_time': int(candle_data[0]),
                    'open_price': float(candle_data[1]),
                    'high_price': float(candle_data[2]),
                    'low_price': float(candle_data[3]),
                    'close_price': float(candle_data[4]),
                    'volume': float(candle_data[5]),
                    'turnover': float(candle_data[6])
                }
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning(f"Failed to parse candle data: {candle_data}, error: {e}")
                continue

        logger.info(f"Successfully fetched {len(candles)} candles from API")
        return candles

    def fetch_and_cache_candles(self, symbol: str, timeframe: str, earliest_timestamp: int, max_historical: bool = False) -> bool:
        """Fetch missing candles and cache them. Returns True if successful."""
        # Check current cache state
        latest_cached = self.db.get_latest_candle_timestamp(symbol, timeframe)

        # If max_historical is True, fetch extensive historical data
        if max_historical:
            return self._fetch_maximum_historical_candles(symbol, timeframe)

        # If cache is empty or outdated, fetch new candles
        if latest_cached is None or latest_cached < earliest_timestamp:
            logger.info(f"Cache outdated for {symbol} {timeframe}. Latest cached: {latest_cached}, Need from: {earliest_timestamp}")

            # Fetch up to 1000 candles starting from earliest_timestamp
            candles = self._fetch_candles_from_api(symbol, timeframe, earliest_timestamp, limit=1000)

            if candles:
                category = self._infer_category_from_symbol(symbol)
                self.db.insert_candles(candles, symbol, timeframe, category)
                return True
            else:
                logger.warning(f"No candles fetched for {symbol} {timeframe}")
                return False
        else:
            logger.info(f"Cache is up to date for {symbol} {timeframe}. Latest: {latest_cached}")
            return True

    def _fetch_candles_backwards(self, symbol: str, timeframe: str, end_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch candles BEFORE end_time using the 'end' parameter."""
        category = self._infer_category_from_symbol(symbol)
        api_symbol = self._normalize_symbol_for_api(symbol)
        interval = self._map_timeframe_to_interval(timeframe)

        params = {
            'symbol': api_symbol,
            'interval': interval,
            'end': end_time,  # Use 'end' to fetch backwards
            'limit': limit,
            'category': category
        }

        response = self.api_manager.get_kline(**params)

        if not response or response.get('retCode') != 0:
            logger.error(f"Failed to fetch candles backwards: {response}")
            return []

        candles_data = response.get('result', {}).get('list', [])
        if not candles_data:
            return []

        candles = []
        for candle_data in candles_data:
            try:
                candle = {
                    'start_time': int(candle_data[0]),
                    'open_price': float(candle_data[1]),
                    'high_price': float(candle_data[2]),
                    'low_price': float(candle_data[3]),
                    'close_price': float(candle_data[4]),
                    'volume': float(candle_data[5]),
                    'turnover': float(candle_data[6])
                }
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning(f"Failed to parse candle data: {candle_data}, error: {e}")
                continue

        return candles

    def _fetch_maximum_historical_candles(self, symbol: str, timeframe: str) -> bool:
        """Fetch maximum historical candles for a symbol/timeframe combination."""
        import time

        logger.info(f"Fetching maximum historical candles for {symbol} {timeframe}")

        earliest_cached = self.db.get_earliest_candle_timestamp(symbol, timeframe)
        current_time = int(time.time() * 1000)
        category = self._infer_category_from_symbol(symbol)
        total_fetched = 0

        # Phase 1: Fetch historical data BACKWARDS from earliest cached point
        logger.info(f"Phase 1: Fetching historical data backwards for {symbol} {timeframe}")

        # Use earliest cached as end_time, or current time if no cache
        end_time = earliest_cached if earliest_cached else current_time
        max_iterations = 100
        iteration = 0

        while iteration < max_iterations:
            candles = self._fetch_candles_backwards(symbol, timeframe, end_time, limit=1000)

            if not candles:
                logger.info(f"No more historical candles to fetch for {symbol} {timeframe}")
                break

            self.db.insert_candles(candles, symbol, timeframe, category)
            total_fetched += len(candles)

            # Get earliest from this batch to continue backwards
            earliest_fetched = min(c['start_time'] for c in candles)

            # If we got less than limit, we've reached the end of available data
            if len(candles) < 1000:
                logger.info(f"Reached end of historical data for {symbol} {timeframe}")
                break

            # Move end_time backwards
            end_time = earliest_fetched - 1
            iteration += 1
            time.sleep(0.1)

        # Phase 2: Fetch newer data (forwards from latest cached point)
        logger.info(f"Phase 2: Fetching newer data for {symbol} {timeframe}")

        # Get updated latest timestamp after historical fetch
        latest_cached = self.db.get_latest_candle_timestamp(symbol, timeframe)

        if latest_cached is not None:
            # Start fetching from the latest cached timestamp + 1ms
            start_time = latest_cached + 1

            iteration = 0
            while iteration < max_iterations:
                # Fetch candles in batches starting from latest cached + 1ms
                candles = self._fetch_candles_from_api(symbol, timeframe, start_time, limit=1000)

                if not candles:
                    logger.info(f"No more newer candles to fetch for {symbol} {timeframe}")
                    break

                # Insert candles into database
                self.db.insert_candles(candles, symbol, timeframe, category)
                total_fetched += len(candles)

                # Get the latest timestamp from the fetched candles to continue forwards
                latest_fetched = max(candle['start_time'] for candle in candles)

                # If we're getting the same or older data, we've reached the limit
                if latest_fetched <= start_time:
                    break

                # Move start_time forwards to fetch newer candles
                start_time = latest_fetched + 1  # Add 1ms to avoid duplicates

                iteration += 1

                # Small delay to be respectful to the API
            time.sleep(0.1)
            logger.info(f"Successfully fetched {total_fetched} total candles for {symbol} {timeframe}")
            return True



    def fill_missing_candles(self, symbol: str, timeframe: str, max_gaps: int = 20) -> int:
        """Detect gaps in the cache and fetch candles to fill them.
        Returns the total number of candles newly inserted.
        """
        gaps = self.db.get_candle_gaps(symbol, timeframe)
        if not gaps:
            logger.info(f"No gaps detected for {symbol} {timeframe}")
            return 0

        category = self._infer_category_from_symbol(symbol)
        total_inserted = 0
        interval_ms = self._timeframe_to_ms(timeframe)

        for gap in gaps[:max_gaps]:
            start = int(gap["start_missing"])
            end = int(gap["end_missing"])
            logger.info(f"Filling gap for {symbol} {timeframe}: {start} -> {end}")

            # Fetch forward in batches until we pass 'end' or API returns empty
            safety = 0
            while start <= end and safety < 100:
                batch = self._fetch_candles_from_api(symbol, timeframe, start, limit=1000)
                if not batch:
                    break
                self.db.insert_candles(batch, symbol, timeframe, category)
                total_inserted += len(batch)
                last_ts = max(c['start_time'] for c in batch)
                if last_ts >= end:
                    break
                start = last_ts + interval_ms
                safety += 1

        logger.info(f"Inserted {total_inserted} candles while filling gaps for {symbol} {timeframe}")
        return total_inserted


    def get_candles_for_simulation(self, symbol: str, timeframe: str, start_timestamp: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get candles from cache for trade simulation.

        Auto-fetches missing data if:
        1. No cached candles exist for this symbol/timeframe
        2. Cached data doesn't cover the requested start_timestamp
        3. There are gaps in the data
        """
        import time

        # First try to get from cache
        candles = self.db.get_candles_after_timestamp(symbol, timeframe, start_timestamp, limit)

        # Check if we have enough data
        if candles:
            first_candle_ts = candles[0].get('start_time', 0)
            interval_ms = self._timeframe_to_ms(timeframe)
            # If first candle is within 2 intervals of requested time, data is valid
            if abs(first_candle_ts - start_timestamp) <= interval_ms * 2:
                return candles

        # Need to fetch missing data
        logger.info(f"Auto-fetching missing candles for {symbol} {timeframe} from {start_timestamp}")

        # Check earliest cached - if start_timestamp is before it, fetch backwards
        earliest_cached = self.db.get_earliest_candle_timestamp(symbol, timeframe)

        if earliest_cached is None or start_timestamp < earliest_cached:
            # Fetch backwards from earliest_cached or current time
            end_time = earliest_cached if earliest_cached else int(time.time() * 1000)
            category = self._infer_category_from_symbol(symbol)

            # Fetch in batches until we cover start_timestamp
            iteration = 0
            while iteration < 50 and (earliest_cached is None or start_timestamp < earliest_cached):
                batch = self._fetch_candles_backwards(symbol, timeframe, end_time, limit=1000)
                if not batch:
                    break
                self.db.insert_candles(batch, symbol, timeframe, category)
                earliest_fetched = min(c['start_time'] for c in batch)
                if len(batch) < 1000:
                    break  # No more data
                end_time = earliest_fetched - 1
                earliest_cached = earliest_fetched
                iteration += 1
                time.sleep(0.1)

        # Also fetch forward to fill any gaps
        self.fill_missing_candles(symbol, timeframe, max_gaps=5)

        # Try again from cache
        return self.db.get_candles_after_timestamp(symbol, timeframe, start_timestamp, limit)
