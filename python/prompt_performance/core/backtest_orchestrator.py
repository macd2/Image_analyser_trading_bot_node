import logging
import sys
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Ensure the parent directory is in the path for imports
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from .data_loader import AnalysisDataLoader
from .candle_fetcher import CandleFetcher
from .trade_simulator import TradeSimulator
from .metrics_aggregator import MetricsAggregator
from .database_utils import CandleStoreDatabase

logger = logging.getLogger(__name__)

class BacktestOrchestrator:
    """Main orchestrator for the prompt performance backtest system."""

    def __init__(self, use_testnet: bool = False):
        self.data_loader = AnalysisDataLoader()
        self.candle_fetcher = CandleFetcher(use_testnet=use_testnet)
        self.trade_simulator = TradeSimulator()
        self.metrics_aggregator = MetricsAggregator()
        self.db = CandleStoreDatabase()

    def run_backtest(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Run the complete backtest process.

        Args:
            limit: Optional limit on number of analysis records to process

        Returns:
            Summary of backtest results
        """
        start_time = datetime.now()
        logger.info("Starting prompt performance backtest")

        try:
            # Step 1: Load and filter analysis records
            logger.info("Step 1: Loading and filtering analysis records")
            records = self.data_loader.load_filtered_records(limit=limit)

            if not records:
                return {
                    'success': False,
                    'error': 'No valid analysis records found',
                    'total_records': 0
                }

            # Step 2: Group records by symbol/timeframe
            logger.info("Step 2: Grouping records by symbol/timeframe")
            grouped_records = self.data_loader.group_records_by_symbol_timeframe(records)

            # Step 3: Pre-populate maximum historical data for all symbol/timeframe combinations
            logger.info("Step 3: Pre-populating maximum historical data")
            self._populate_maximum_historical_data(grouped_records)

            # Step 4: Process each group
            all_trade_results = []
            total_groups = len(grouped_records)
            processed_groups = 0

            # Parallelize group processing similar to run_autotrader image analysis
            def process_group(symbol: str, timeframe: str, group_records_local: list) -> list:
                # Get earliest timestamp for this group
                earliest_timestamp = self.data_loader.get_earliest_timestamp_in_group(group_records_local)
                if earliest_timestamp is None:
                    logger.warning(f"No valid timestamps for group {symbol}_{timeframe}, skipping")
                    return []

                # Filter records based on available candle data
                earliest_candle = self.db.get_earliest_candle_timestamp(symbol, timeframe)
                if earliest_candle is None:
                    logger.warning(f"No candle data available for {symbol} {timeframe}, skipping group")
                    return []

                valid_records = [
                    r for r in group_records_local
                    if self._record_timestamp_to_ms(r['timestamp']) >= earliest_candle
                ]
                if not valid_records:
                    logger.info(f"No records with sufficient candle data for {symbol} {timeframe}, skipping")
                    return []

                # Get candles for simulation starting at earliest valid record
                simulation_start = min(self._record_timestamp_to_ms(r['timestamp']) for r in valid_records)
                candles = self.candle_fetcher.get_candles_for_simulation(symbol, timeframe, simulation_start)
                if not candles:
                    logger.warning(f"No candles available for simulation in {symbol} {timeframe}, skipping")
                    return []

                logger.info(f"Simulating {len(valid_records)} trades for {symbol} {timeframe}")
                return self.trade_simulator.simulate_multiple_trades(valid_records, candles)

            # Choose worker count (env BACKTEST_MAX_WORKERS, default 4, capped by total groups)
            import os
            max_workers_env = os.getenv("BACKTEST_MAX_WORKERS")
            try:
                max_workers = int(max_workers_env) if max_workers_env else 4
            except Exception:
                max_workers = 4
            max_workers = max(1, min(max_workers, total_groups))

            from concurrent.futures import ThreadPoolExecutor, as_completed
            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for group_key, group_records in grouped_records.items():
                    symbol, timeframe = group_key.split('_', 1)
                    logger.info(f"Queueing group: {symbol} {timeframe} ({len(group_records)} records)")
                    futures.append(executor.submit(process_group, symbol, timeframe, group_records))

                for fut in as_completed(futures):
                    try:
                        trade_results = fut.result()
                        if trade_results:
                            all_trade_results.extend(trade_results)
                    except Exception as e:
                        logger.error(f"Group processing failed: {e}")
                    finally:
                        processed_groups += 1
                        logger.info(f"Processed groups: {processed_groups}/{total_groups}")

            # Step 8: Generate reports
            if all_trade_results:
                logger.info("Generating performance reports")
                self.metrics_aggregator.generate_report(all_trade_results)

                # Calculate summary statistics
                total_trades = len(all_trade_results)
                wins = sum(1 for r in all_trade_results if r['outcome'] == 'win')
                losses = sum(1 for r in all_trade_results if r['outcome'] == 'loss')
                expired = sum(1 for r in all_trade_results if r['outcome'] == 'expired')

                win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                summary = {
                    'success': True,
                    'total_trades': total_trades,
                    'wins': wins,
                    'losses': losses,
                    'expired': expired,
                    'win_rate': round(win_rate, 4),
                    'duration_seconds': round(duration, 2),
                    'groups_processed': processed_groups,
                    'total_groups': total_groups
                }

                logger.info(f"Backtest completed successfully: {summary}")
                return summary
            else:
                return {
                    'success': False,
                    'error': 'No trade simulations were successful',
                    'total_trades': 0
                }

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_trades': 0
            }

    def _populate_maximum_historical_data(self, grouped_records: Dict[str, List]) -> None:
        """Pre-populate maximum historical data for all symbol/timeframe combinations."""
        logger.info("Pre-populating maximum historical data for all symbol/timeframe combinations")

        processed_combinations = set()

        for group_key, group_records in grouped_records.items():
            symbol, timeframe = group_key.split('_', 1)

            # Skip if we've already processed this combination
            if (symbol, timeframe) in processed_combinations:
                continue

            processed_combinations.add((symbol, timeframe))

            try:
                logger.info(f"Ensuring maximum historical data for {symbol} {timeframe}")
                # Use max_historical=True to fetch maximum available historical data
                success = self.candle_fetcher.fetch_and_cache_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    earliest_timestamp=0,  # Will be ignored when max_historical=True
                    max_historical=True
                )

                if success:
                    logger.info(f"✅ Successfully populated maximum historical data for {symbol} {timeframe}")
                else:
                    logger.warning(f"❌ Failed to populate historical data for {symbol} {timeframe}")

            except Exception as e:
                logger.error(f"Error populating historical data for {symbol} {timeframe}: {e}")
                continue

        logger.info(f"Completed pre-population of historical data for {len(processed_combinations)} symbol/timeframe combinations")

    def _record_timestamp_to_ms(self, timestamp) -> int:
        """Convert record timestamp to milliseconds."""
        if isinstance(timestamp, str):
            # Parse ISO string
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except ValueError:
                return 0
        elif isinstance(timestamp, (int, float)):
            # Assume already in ms if > 1e10, otherwise convert from seconds
            if timestamp > 1e10:
                return int(timestamp)
            else:
                return int(timestamp * 1000)
        else:
            return 0

    def run_backtest_with_prompt_hash(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Run the complete backtest process using prompt hash analysis.

        Args:
            limit: Optional limit on number of analysis records to process

        Returns:
            Summary of backtest results
        """
        start_time = datetime.now()
        logger.info("Starting prompt performance backtest with prompt hash analysis")

        try:
            # Step 1: Load and filter analysis records for prompt hash
            logger.info("Step 1: Loading and filtering analysis records for prompt hash")
            records = self.data_loader.load_filtered_records_for_prompt_hash(limit=limit)

            if not records:
                return {
                    'success': False,
                    'error': 'No valid analysis records found for prompt hash analysis',
                    'total_records': 0
                }

            # Step 2: Group records by symbol/timeframe
            logger.info("Step 2: Grouping records by symbol/timeframe")
            grouped_records = self.data_loader.group_records_by_symbol_timeframe(records)

            # Step 3: Pre-populate maximum historical data for all symbol/timeframe combinations
            logger.info("Step 3: Pre-populating maximum historical data")
            self._populate_maximum_historical_data(grouped_records)

            # Step 4: Process each group (parallel)
            all_trade_results = []
            total_groups = len(grouped_records)
            processed_groups = 0

            def process_group(symbol: str, timeframe: str, group_records_local: list) -> list:
                # Get earliest timestamp for this group
                earliest_timestamp = self.data_loader.get_earliest_timestamp_in_group(group_records_local)
                if earliest_timestamp is None:
                    logger.warning(f"No valid timestamps for group {symbol}_{timeframe}, skipping")
                    return []

                # Filter records based on available candle data
                earliest_candle = self.db.get_earliest_candle_timestamp(symbol, timeframe)
                if earliest_candle is None:
                    logger.warning(f"No candle data available for {symbol} {timeframe}, skipping group")
                    return []

                valid_records = [
                    r for r in group_records_local
                    if self._record_timestamp_to_ms(r['timestamp']) >= earliest_candle
                ]
                if not valid_records:
                    logger.info(f"No records with sufficient candle data for {symbol} {timeframe}, skipping")
                    return []

                # Get candles for simulation starting at earliest valid record
                simulation_start = min(self._record_timestamp_to_ms(r['timestamp']) for r in valid_records)
                candles = self.candle_fetcher.get_candles_for_simulation(symbol, timeframe, simulation_start)
                if not candles:
                    logger.warning(f"No candles available for simulation in {symbol} {timeframe}, skipping")
                    return []

                logger.info(f"Simulating {len(valid_records)} trades for {symbol} {timeframe} with prompt hash")
                return self.trade_simulator.simulate_multiple_trades_with_prompt_hash(valid_records, candles)

            import os
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers_env = os.getenv("BACKTEST_MAX_WORKERS")
            try:
                max_workers = int(max_workers_env) if max_workers_env else 4
            except Exception:
                max_workers = 4
            max_workers = max(1, min(max_workers, total_groups))

            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for group_key, group_records in grouped_records.items():
                    symbol, timeframe = group_key.split('_', 1)
                    logger.info(f"Queueing group: {symbol} {timeframe} ({len(group_records)} records)")
                    futures.append(executor.submit(process_group, symbol, timeframe, group_records))

                for fut in as_completed(futures):
                    try:
                        trade_results = fut.result()
                        if trade_results:
                            all_trade_results.extend(trade_results)
                    except Exception as e:
                        logger.error(f"Group processing failed: {e}")
                    finally:
                        processed_groups += 1
                        logger.info(f"Processed groups: {processed_groups}/{total_groups}")

            # Step 8: Generate reports for prompt hash
            if all_trade_results:
                logger.info("Generating performance reports for prompt hash analysis")
                self.metrics_aggregator.generate_report_for_prompt_hash(all_trade_results)

                # Generate combination analysis
                logger.info("Generating combination analysis")
                top_combinations = self.metrics_aggregator.get_top_performing_combinations(all_trade_results, top_n=50)
                if top_combinations:
                    self.metrics_aggregator.write_combination_analysis_csv(top_combinations)
                    logger.info(f"Generated analysis for {len(top_combinations)} combinations")

                # Calculate summary statistics
                total_trades = len(all_trade_results)
                wins = sum(1 for r in all_trade_results if r['outcome'] == 'win')
                losses = sum(1 for r in all_trade_results if r['outcome'] == 'loss')
                expired = sum(1 for r in all_trade_results if r['outcome'] == 'expired')

                win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                summary = {
                    'success': True,
                    'total_trades': total_trades,
                    'wins': wins,
                    'losses': losses,
                    'expired': expired,
                    'win_rate': round(win_rate, 4),
                    'duration_seconds': round(duration, 2),
                    'groups_processed': processed_groups,
                    'total_groups': total_groups,
                    'analysis_type': 'prompt_hash'
                }

                logger.info(f"Prompt hash backtest completed successfully: {summary}")
                return summary
            else:
                return {
                    'success': False,
                    'error': 'No trade simulations were successful for prompt hash analysis',
                    'total_trades': 0
                }

        except Exception as e:
            logger.error(f"Prompt hash backtest failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_trades': 0
            }