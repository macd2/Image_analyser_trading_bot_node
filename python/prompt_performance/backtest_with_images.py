#!/usr/bin/env python3
"""
Image-Based Backtest System

Tests prompts using historical chart images and real AI analysis.
Allows testing ANY prompt (including new ones) by analyzing actual chart images.

Quick start (from repo root):
    python - << 'PY'
    from prompt_performance.backtest_with_images import ImageBacktester, PROMPT_REGISTRY
    bt = ImageBacktester(max_workers_prompts=3)  # or set env BACKTEST_MAX_WORKERS_PROMPTS=3
    res = bt.backtest_with_images(
        prompts=list(PROMPT_REGISTRY.keys()),  # all registered prompts
        symbols=['AVAXUSDT'],                  # change to your symbol(s)
        num_images=3,                          # newest 3 images per symbol
        verbose=False,
    )
    print(res)
    PY
"""

import sys
import re
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from collections import defaultdict

# Global cancel signal for cooperative stopping of backtests
CANCEL_EVENT = threading.Event()

def request_cancel() -> None:
    """Signal any running backtest to stop ASAP."""
    try:
        CANCEL_EVENT.set()
    except Exception:
        pass

def clear_cancel() -> None:
    """Clear cancel signal before starting a new backtest."""
    try:
        CANCEL_EVENT.clear()
    except Exception:
        pass

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trading_bot.core.analyzer import ChartAnalyzer
from trading_bot.core.prompts.analyzer_prompt import (
    code_nova_improoved_based_on_analyzis,
    get_analyzer_prompt_hybrid_ultimate,
    get_analyzer_prompt_improved_v28_short_fix,
    get_analyzer_prompt_optimized_v26_grok_fineTune,
    get_analyzer_prompt_trade_playbook_v1,
)
from prompt_performance.core.candle_fetcher import CandleFetcher
from prompt_performance.core.trade_simulator import TradeSimulator
from prompt_performance.core.backtest_store import BacktestStore
from prompt_performance.core.raw_output_logger import RawOutputLogger

from trading_bot.config.settings_v2 import Config
import openai

logger = logging.getLogger(__name__)


# Prompt registry - maps short names to actual functions
PROMPT_REGISTRY = {
    'code_nova': code_nova_improoved_based_on_analyzis,
    'hybrid': get_analyzer_prompt_hybrid_ultimate,
    'v28_short_fix': get_analyzer_prompt_improved_v28_short_fix,
    'grok_fineTune': get_analyzer_prompt_optimized_v26_grok_fineTune,
    'trade_playbook_v1': get_analyzer_prompt_trade_playbook_v1,
}


class ImageInfo:
    """Container for parsed image information."""

    def __init__(self, filepath: Path, symbol: str, timeframe: str, timestamp: datetime):
        self.filepath = filepath
        self.symbol = symbol
        self.timeframe = timeframe
        self.timestamp = timestamp
        self.timestamp_ms = int(timestamp.timestamp() * 1000)

    def __repr__(self):
        return f"ImageInfo({self.symbol}, {self.timeframe}, {self.timestamp})"


class ImageSelector:
    """Handles image discovery, parsing, and filtering."""

    # Filename pattern: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.png
    # Symbol can be alphanumeric (e.g., BTCUSDT, 1000PEPEUSDT)
    FILENAME_PATTERN = re.compile(
        r'^(?P<symbol>[A-Z0-9]+)_'
        r'(?P<timeframe>\d+[mhd])_'
        r'(?P<date>\d{8})_'
        r'(?P<time>\d{6})'
        r'\.png$'
    )

    def __init__(self, charts_dir: str = "data/charts/.backup"):
        self.charts_dir = Path(charts_dir)
        if not self.charts_dir.exists():
            raise ValueError(f"Charts directory not found: {charts_dir}")

    def parse_filename(self, filename: str) -> Optional[ImageInfo]:
        """Parse image filename to extract metadata."""
        match = self.FILENAME_PATTERN.match(filename)
        if not match:
            return None

        try:
            symbol = match.group('symbol')
            timeframe = match.group('timeframe')
            date_str = match.group('date')
            time_str = match.group('time')

            # Parse timestamp
            timestamp_str = f"{date_str}_{time_str}"
            timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

            filepath = self.charts_dir / filename

            return ImageInfo(filepath, symbol, timeframe, timestamp)

        except Exception as e:
            logger.warning(f"Failed to parse filename {filename}: {e}")
            return None

    def discover_images(self, symbols: Optional[List[str]] = None) -> List[ImageInfo]:
        """Discover all valid images in charts directory."""
        images = []

        for filepath in self.charts_dir.glob("*.png"):
            image_info = self.parse_filename(filepath.name)

            if image_info is None:
                continue

            # Filter by symbols if provided
            if symbols and image_info.symbol not in symbols:
                continue

            images.append(image_info)

        return images

    def filter_by_date_range(
        self,
        images: List[ImageInfo],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[ImageInfo]:
        """Filter images by date range."""
        if not start_date and not end_date:
            return images

        filtered = []

        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        # Set end_dt to end of day
        if end_dt:
            end_dt = end_dt.replace(hour=23, minute=59, second=59)

        for img in images:
            if start_dt and img.timestamp < start_dt:
                continue
            if end_dt and img.timestamp > end_dt:
                continue
            filtered.append(img)

        return filtered

    def limit_per_symbol(
        self,
        images: List[ImageInfo],
        num_images: int,
        offset: int = 0,
    ) -> List[ImageInfo]:
        """Limit number of images per symbol (newest first), with optional offset.
        Offset skips the N newest images before taking num_images per symbol.
        """
        # Group by symbol
        by_symbol = defaultdict(list)
        for img in images:
            by_symbol[img.symbol].append(img)

        # Sort each symbol's images by timestamp (newest first)
        for symbol in by_symbol:
            by_symbol[symbol].sort(key=lambda x: x.timestamp, reverse=True)

        # Take per-symbol window applying offset
        limited = []
        start = max(0, int(offset)) if offset else 0
        end = start + int(num_images)
        for symbol, imgs in by_symbol.items():
            limited.extend(imgs[start:end])

        return limited

    def select_images(
        self,
        symbols: List[str],
        num_images: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        offset: int = 0,
        timeframes: Optional[List[str]] = None,
    ) -> List[ImageInfo]:
        """
        Select images based on criteria.

        Args:
            symbols: List of symbols to include
            num_images: Number of images per symbol (newest first)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            offset: Skip this many newest images per symbol before taking num_images

        Returns:
            List of selected ImageInfo objects
        """
        # Validate: at least one filter must be provided
        if num_images is None and start_date is None and end_date is None:
            raise ValueError(
                "At least one of num_images, start_date, or end_date must be provided"
            )

        # Discover all images for symbols
        images = self.discover_images(symbols=symbols)

        if not images:
            raise ValueError(f"No images found for symbols: {symbols}")

        # Apply timeframe filter first (if provided)
        if timeframes:
            tset = {str(tf).lower() for tf in timeframes}
            images = [img for img in images if str(img.timeframe).lower() in tset]

        # Apply date range filter
        if start_date or end_date:
            images = self.filter_by_date_range(images, start_date, end_date)

        # Apply num_images limit with offset (per symbol) on the filtered set
        if num_images is not None:
            images = self.limit_per_symbol(images, num_images, offset=offset)

        # Sort by timestamp (newest first) for consistent ordering
        images.sort(key=lambda x: x.timestamp, reverse=True)

        return images


class PromptAnalyzer:
    """Manages prompt loading and AI analysis."""

    def __init__(self, config: Config, verbose_prompts: bool = False, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None, candle_fetcher: Optional['CandleFetcher'] = None):
        self.config = config
        self.openai_client = openai.OpenAI(api_key=config.openai.api_key)
        self.analyzer = ChartAnalyzer(self.openai_client, config)
        self.verbose_prompts = verbose_prompts
        self.progress_callback = progress_callback
        self.candle_fetcher = candle_fetcher

    @staticmethod
    def get_prompt_function_static(prompt_name: str) -> Callable:
        """Static version of get_prompt_function for use without instance.

        Resolve a prompt function by name.

        Priority:
        1) PROMPT_REGISTRY (stable short names)
        2) Any function in trading_bot.core.prompts.analyzer_prompt (dynamic)
        """
        # 1) Known short names
        if prompt_name in PROMPT_REGISTRY:
            return PROMPT_REGISTRY[prompt_name]

        # 2) Dynamic lookup from analyzer_prompt
        try:
            import inspect
            from trading_bot.core.prompts import analyzer_prompt as ap
            # Exclude helpers/private
            funcs = {
                name: fn for name, fn in inspect.getmembers(ap, inspect.isfunction)
                if not name.startswith('_') and name != 'get_market_data'
            }
            if prompt_name in funcs:
                return funcs[prompt_name]
        except Exception as e:
            logger.debug(f"Dynamic prompt lookup failed for {prompt_name}: {e}")

        raise ValueError(
            f"Unknown prompt: {prompt_name}. Available short names: {list(PROMPT_REGISTRY.keys())}. "
            f"Also ensure a function named '{prompt_name}' exists in analyzer_prompt.py."
        )

    def get_prompt_function(self, prompt_name: str) -> Callable:
        """Resolve a prompt function by name.

        Priority:
        1) PROMPT_REGISTRY (stable short names)
        2) Any function in trading_bot.core.prompts.analyzer_prompt (dynamic)
        """
        return self.get_prompt_function_static(prompt_name)

    def analyze_image(
        self,
        image_info: ImageInfo,
        prompt_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze image with specified prompt using real AI.

        This uses the EXACT same code path as live analyzer.

        NOTE: For historical backtesting, we use 'N/A' for market data
        (funding rate, long/short ratio) since historical values are not
        available. However, we DO provide the last_close_price from cached
        candle data so the AI has a price reference for the image timestamp.
        """
        try:
            # Get prompt function
            prompt_func = self.get_prompt_function(prompt_name)

            # Get the last close price from candle data for the image timestamp
            # This gives the AI a price reference to avoid hallucinating wrong prices
            last_close_price: Any = 'N/A'
            if self.candle_fetcher:
                try:
                    # Get candles at/before the image timestamp
                    candles = self.candle_fetcher.db.get_candles_after_timestamp(
                        symbol=image_info.symbol,
                        timeframe=image_info.timeframe,
                        start_timestamp=image_info.timestamp_ms,
                        limit=1
                    )
                    if candles and len(candles) > 0:
                        last_close_price = candles[0].get('close_price', 'N/A')
                except Exception as e:
                    logger.debug(f"Could not fetch last close price: {e}")

            # Create market data context with N/A values for historical backtest
            # We can't get historical funding rates or long/short ratios
            market_data = {
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'mid_price': 'N/A',  # Will be extracted from current data
                'bid_price': 'N/A',
                'ask_price': 'N/A',
                'last_close_price': last_close_price,  # From cached candle data
                'last_price': last_close_price,  # Alias for prompts that use last_price
                'funding_rate': 'N/A',
                'long_short_ratio': 'N/A'
            }

            # Get prompt data
            prompt_data = prompt_func(market_data)

            # Get assistant model name for display
            assistant_model = 'N/A'
            try:
                assistant_id = self.config.openai.assistant.assistants.get('analyzer', '')
                if assistant_id:
                    asst_obj = self.analyzer.client.beta.assistants.retrieve(assistant_id)
                    assistant_model = getattr(asst_obj, 'model', 'N/A')
            except Exception:
                pass

            # Note: Prompt display event is now emitted in _process_image_with_prompt
            # before cache check, so it shows even for cached analyses

            # Analyze chart using custom_prompt_data parameter
            # This is the EXACT same path as live analyzer
            # Pass skip_market_data=True to avoid fetching current market data
            result = self.analyzer.analyze_chart_with_assistant(
                image_path=str(image_info.filepath),
                target_timeframe=image_info.timeframe,
                custom_prompt_data=prompt_data,
                skip_market_data=True  # Don't fetch current market data for historical backtest
            )

            # Check for errors or skipped
            if result.get('error') or result.get('skipped'):
                logger.warning(
                    f"Analysis failed for {image_info.filepath.name} "
                    f"with {prompt_name}: {result.get('error') or 'skipped'}"
                )
                return None

            # Add metadata
            result['prompt_name'] = prompt_name
            result['prompt_version'] = prompt_data['version']['name']
            result['image_path'] = str(image_info.filepath)
            result['image_timestamp'] = image_info.timestamp.isoformat()
            result['image_timestamp_ms'] = image_info.timestamp_ms

            return result

        except Exception as e:
            logger.error(
                f"Error analyzing {image_info.filepath.name} "
                f"with {prompt_name}: {e}",
                exc_info=True
            )
            return None


class ResultsAggregator:
    """Calculates metrics and generates reports."""

    def __init__(self):
        self.trades = []
        self.analyses = []
        self._lock = threading.Lock()

    def add_trade(self, trade_data: Dict[str, Any]):
        """Add a trade result."""
        with self._lock:
            self.trades.append(trade_data)

    def add_analysis(self, analysis_data: Dict[str, Any]):
        """Add an analysis record (includes HOLDs and errors)."""
        with self._lock:
            self.analyses.append(analysis_data)

    def calculate_metrics(self, prompt_name: str) -> Dict[str, Any]:
        """Calculate metrics for a specific prompt."""
        prompt_trades = [t for t in self.trades if t['prompt_name'] == prompt_name]

        if not prompt_trades:
            return {
                'prompt_name': prompt_name,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'expired': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'expectancy': 0.0,
                'avg_rr': 0.0,
                'avg_confidence': 0.0,
                'avg_duration': 0.0
            }

        total = len(prompt_trades)
        wins = len([t for t in prompt_trades if t['outcome'] == 'win'])
        losses = len([t for t in prompt_trades if t['outcome'] == 'loss'])
        expired = len([t for t in prompt_trades if t['outcome'] == 'expired'])

        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0

        # Calculate profit factor
        total_profit = sum(t['rr_ratio'] for t in prompt_trades if t['outcome'] == 'win')
        total_loss = len([t for t in prompt_trades if t['outcome'] == 'loss'])
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0

        # Calculate expectancy
        avg_win = total_profit / wins if wins > 0 else 0.0
        avg_loss = 1.0  # Normalized to 1R
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        # Average metrics
        avg_rr = sum(t['rr_ratio'] for t in prompt_trades) / total
        avg_confidence = sum(t['confidence'] for t in prompt_trades) / total
        avg_duration = sum(t['duration_candles'] for t in prompt_trades) / total

        return {
            'prompt_name': prompt_name,
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'expired': expired,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'avg_rr': avg_rr,
            'avg_confidence': avg_confidence,
            'avg_duration': avg_duration
        }

    def get_all_metrics(self, prompt_names: List[str]) -> List[Dict[str, Any]]:
        """Get metrics for all prompts."""
        return [self.calculate_metrics(name) for name in prompt_names]

    def get_trades(self) -> List[Dict[str, Any]]:
        """Get all trade data."""
        return self.trades

    def get_analyses(self) -> List[Dict[str, Any]]:
        """Get all analysis records."""
        return self.analyses


class ImageBacktester:
    """Main orchestrator for image-based backtesting."""

    def __init__(
        self,
        charts_dir: str = "data/charts/.backup",
        output_dir: str = "prompt_performance",
        db_path: Optional[str] = None,
        max_workers_prompts: Optional[int] = None,
        max_workers_images: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        verbose_prompts: bool = False,
    ):
        self.charts_dir = charts_dir
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.config = Config.from_yaml()
        self.image_selector = ImageSelector(charts_dir)
        self.candle_fetcher = CandleFetcher(use_testnet=False)
        self.prompt_analyzer = PromptAnalyzer(self.config, verbose_prompts=verbose_prompts, progress_callback=progress_callback, candle_fetcher=self.candle_fetcher)
        self.trade_simulator = TradeSimulator()
        self.results_aggregator = ResultsAggregator()
        self.raw_output_logger = RawOutputLogger()
        # Parallelism settings
        env_workers_prompts = os.getenv("BACKTEST_MAX_WORKERS_PROMPTS")
        self.max_workers_prompts = max_workers_prompts or (int(env_workers_prompts) if env_workers_prompts else 4)
        env_workers_images = os.getenv("BACKTEST_MAX_WORKERS_IMAGES")
        self.max_workers_images = max_workers_images or (int(env_workers_images) if env_workers_images else 1)
        # Persistent store for runs/results
        self.backtest_store = BacktestStore(db_path=db_path)
        self._current_run_id: Optional[int] = None
        # Fallback buffers if DB temporarily locked; flushed at end of run
        self._pending_analyses: List[Dict[str, Any]] = []
        self._pending_trades: List[Dict[str, Any]] = []
        # Progress callback for real-time updates
        self.progress_callback = progress_callback
        self._progress_lock = threading.Lock()

    def _emit_progress(self, update: Dict[str, Any]) -> None:
        """Emit progress update via callback if configured."""
        if self.progress_callback:
            try:
                with self._progress_lock:
                    self.progress_callback(update)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

    def _get_current_metrics(self) -> Dict[str, Any]:
        """Get current aggregated metrics."""
        trades = self.results_aggregator.get_trades()
        total_trades = len(trades)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
            }

        wins = len([t for t in trades if t.get('outcome') == 'win'])
        losses = len([t for t in trades if t.get('outcome') == 'loss'])
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0.0
        total_pnl = sum(t.get('realized_pnl_percent', 0) for t in trades)

        return {
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
        }

    def backtest_with_images(
        self,
        prompts: List[str],
        symbols: List[str],
        num_images: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        offset: int = 0,
        verbose: bool = False,
        timeframes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest using historical chart images.

        Args:
            prompts: List of prompt names to test (short or full function names). Will be normalized to full function names.
            symbols: List of symbols to test
            num_images: Number of images per symbol (newest first)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            offset: Skip this many newest images per symbol before taking num_images
            verbose: Enable verbose logging

        Returns:
            Dictionary with results and metrics
        """
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)

        start_time = datetime.now()

        # Print header
        self._print_header(prompts, symbols, num_images, start_date, end_date)

        # Early cancel check
        if CANCEL_EVENT.is_set():
            raise RuntimeError("Cancelled")

        # Select images
        logger.info("Selecting images...")
        images = self.image_selector.select_images(
            symbols=symbols,
            num_images=num_images,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            timeframes=timeframes,
        )

        logger.info(f"Selected {len(images)} images")

        # Initialize persistent run in store
        image_paths = [str(img.filepath) for img in images]
        run_signature = BacktestStore.compute_signature(
            image_paths=image_paths,
            prompts=prompts,
            symbols=symbols,
            num_images=num_images or len(images),
            charts_dir=self.charts_dir,
        )
        run_info = self.backtest_store.create_or_get_run(
            run_signature=run_signature,
            started_at=start_time.isoformat(),
            charts_dir=self.charts_dir,
            selection_strategy="newest_per_symbol",
            num_images=num_images or len(images),
            prompts=prompts,
            symbols=symbols,
        )
        self._current_run_id = run_info.run_id
        # Persist selected images (stable order = current list order)
        self.backtest_store.add_run_images(
            self._current_run_id,
            [
                {
                    "symbol": img.symbol,
                    "timeframe": img.timeframe,
                    "timestamp": img.timestamp.isoformat(),
                    "image_path": str(img.filepath),
                    "selection_order": idx + 1,
                }
                for idx, img in enumerate(images)
            ],
        )

        # Start raw output logging
        self.raw_output_logger.start_run(
            run_id=self._current_run_id,
            config={
                'prompts': prompts,
                'symbols': symbols,
                'num_images': num_images or len(images),
                'start_date': start_date,
                'end_date': end_date,
                'offset': offset,
                'timeframes': timeframes,
                'charts_dir': self.charts_dir,
                'total_images_selected': len(images),
                'max_workers_prompts': self.max_workers_prompts,
                'max_workers_images': self.max_workers_images,
            }
        )

        # Group images by symbol for organized processing
        images_by_symbol = defaultdict(list)
        for img in images:
            images_by_symbol[img.symbol].append(img)

        # Normalize prompts to full function names (consistent DB usage)
        normalized_prompts: List[str] = []
        for p in prompts:
            try:
                fn = self.prompt_analyzer.get_prompt_function(p)
                normalized_prompts.append(fn.__name__)
            except Exception:
                # If not resolvable via registry/dynamic lookup, keep as-is
                normalized_prompts.append(p)

        # Process each symbol
        total_processed = 0
        total_images = len(images)

        if CANCEL_EVENT.is_set():
            raise RuntimeError("Cancelled")

        # Emit initial progress
        self._emit_progress({
            'type': 'start',
            'run_id': self._current_run_id,
            'total_images': total_images,
            'total_prompts': len(normalized_prompts),
            'symbols': list(images_by_symbol.keys()),
        })

        for symbol in sorted(images_by_symbol.keys()):
            symbol_images = images_by_symbol[symbol]
            logger.info(f"\nProcessing {symbol} ({len(symbol_images)} images)...")

            # Parallelize across images per symbol (optional)
            if self.max_workers_images and self.max_workers_images > 1:
                from concurrent.futures import ThreadPoolExecutor as _ImgExecutor
                with _ImgExecutor(max_workers=self.max_workers_images) as img_executor:
                    img_futures = [img_executor.submit(self._process_single_image, image_info, normalized_prompts, total_processed + idx)
                                   for idx, image_info in enumerate(symbol_images)]
                    # Cooperative cancel: stop queued futures and exit
                    if CANCEL_EVENT.is_set():
                        try:
                            img_executor.shutdown(cancel_futures=True)
                        except Exception:
                            pass
                        raise RuntimeError("Cancelled")
                    for idx, f in enumerate(img_futures):
                        if CANCEL_EVENT.is_set():
                            try:
                                img_executor.shutdown(cancel_futures=True)
                            except Exception:
                                pass
                            raise RuntimeError("Cancelled")
                        try:
                            f.result()
                            total_processed += 1
                        except Exception:
                            pass
            else:
                for i, image_info in enumerate(symbol_images, 1):
                    if CANCEL_EVENT.is_set():
                        raise RuntimeError("Cancelled")
                    total_processed += 1
                    print(f"\n  [{i}/{len(symbol_images)}] {image_info.filepath.name}")
                    print(f"    Progress: {total_processed}/{total_images} images ({100*total_processed/total_images:.1f}%)")
                    self._process_single_image(image_info, normalized_prompts, total_processed)

        # Calculate metrics
        logger.info("\nCalculating metrics...")
        metrics = self.results_aggregator.get_all_metrics(normalized_prompts)

        # Save results
        logger.info("Saving results...")
        self._save_results(metrics)

        # Finalize run in store (no per-run summaries per requirements)
        if self._current_run_id is not None:
            try:
                finished_at = datetime.now().isoformat()
                duration_sec = (datetime.now() - start_time).total_seconds()
                self.backtest_store.complete_run(self._current_run_id, finished_at=finished_at, duration_sec=duration_sec)
            except Exception:
                pass
        # Best-effort flush of any pending rows that failed earlier due to lock contention
        if self._current_run_id is not None and (self._pending_analyses or self._pending_trades):
            import time as _time
            for _ in range(3):
                if not self._pending_analyses and not self._pending_trades:
                    break
                # Flush analyses
                if self._pending_analyses:
                    to_flush = list(self._pending_analyses)
                    self._pending_analyses.clear()
                    for row in to_flush:
                        try:
                            self.backtest_store.add_analysis(self._current_run_id, row)
                        except Exception:
                            self._pending_analyses.append(row)
                # Flush trades
                if self._pending_trades:
                    to_flush_t = list(self._pending_trades)
                    self._pending_trades.clear()
                    for row in to_flush_t:
                        try:
                            self.backtest_store.add_trade(self._current_run_id, row)
                        except Exception:
                            self._pending_trades.append(row)
                if self._pending_analyses or self._pending_trades:
                    _time.sleep(0.3)
            if self._pending_analyses or self._pending_trades:
                logger.warning(f"Unflushed pending rows after retries: analyses={len(self._pending_analyses)}, trades={len(self._pending_trades)}")

        # Post-flush verification: ensure all in-memory rows are persisted to DB; attempt repair if needed
        ver: Optional[Dict[str, Any]] = None
        if self._current_run_id is not None:
            try:
                ver = self._verify_persistence_and_repair()
                if ver.get("verification_ok"):
                    logger.info(
                        f"DB OK: trades {ver.get('db_trades')}/{ver.get('expected_trades')}, analyses {ver.get('db_analyses')}/{ver.get('expected_analyses')}"
                    )
                else:
                    logger.warning(
                        f"DB repaired: +{ver.get('repaired_trades')} trades, +{ver.get('repaired_analyses')} analyses; final trades {ver.get('db_trades')}/{ver.get('expected_trades')}, analyses {ver.get('db_analyses')}/{ver.get('expected_analyses')}"
                    )
            except Exception:
                logger.warning("Persistence verification step failed (continuing)")

        # Cleanup OpenAI Assistant threads created by this backtest (best-effort)
        try:
            handler = getattr(self.prompt_analyzer.analyzer, 'assistant_handler', None)
            if handler is not None:
                agent_id = ''
                try:
                    agent_id = getattr(self.config.openai.assistant, 'assistants', {}).get('analyzer', '')
                except Exception:
                    agent_id = ''
                if agent_id:
                    deleted = handler.cleanup_threads_for_agent(agent_id)
                    logger.info(f"Assistant thread cleanup done: deleted={deleted} for agent={agent_id}")
                else:
                    deleted = handler.cleanup_all_threads()
                    logger.info(f"Assistant thread cleanup (all agents): deleted={deleted}")
        except Exception:
            pass


        # No per-run summary printing per requirements
        duration = (datetime.now() - start_time).total_seconds()

        # Emit completion progress
        final_metrics = self._get_current_metrics()
        self._emit_progress({
            'type': 'complete',
            'run_id': self._current_run_id,
            'total_images': total_images,
            'duration_seconds': duration,
            'metrics': final_metrics,
        })

        # End raw output logging with summary
        self.raw_output_logger.end_run(summary={
            'total_images': total_images,
            'total_trades': len(self.results_aggregator.get_trades()),
            'total_analyses': len(self.results_aggregator.get_analyses()),
            'duration_seconds': duration,
            'metrics': final_metrics,
            'verification': ver or {}
        })

        return {
            'success': True,
            'metrics': metrics,
            'total_images': total_images,
            'total_trades': len(self.results_aggregator.get_trades()),
            'duration_seconds': duration,
            'verification_ok': bool(ver.get('verification_ok') if ver else False),
            'verification': ver or {}
        }

    def _process_single_image(self, image_info: ImageInfo, normalized_prompts: List[str], progress_index: int = 0) -> None:
        """Process one image by running all prompts (optionally in parallel)."""
        if CANCEL_EVENT.is_set():
            return
        # Log to make parallelism visible in console
        try:
            ts_str = image_info.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            ts_str = str(image_info.timestamp)
        logger.info(f"→ Start image {image_info.symbol} {image_info.timeframe} {ts_str} with {len(normalized_prompts)} prompts (img_workers={self.max_workers_images}, prompt_workers={self.max_workers_prompts})")

        # Emit progress update for this image
        self._emit_progress({
            'type': 'image_start',
            'run_id': self._current_run_id,
            'image_index': progress_index,
            'image_filename': image_info.filepath.name,
            'symbol': image_info.symbol,
            'timeframe': image_info.timeframe,
            'timestamp': ts_str,
        })

        if self.max_workers_prompts and self.max_workers_prompts > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers_prompts) as executor:
                futures = [executor.submit(self._process_image_with_prompt, image_info, prompt_name)
                           for prompt_name in normalized_prompts]
                if CANCEL_EVENT.is_set():
                    try:
                        executor.shutdown(cancel_futures=True)
                    except Exception:
                        pass
                    return
                for f in futures:
                    if CANCEL_EVENT.is_set():
                        try:
                            executor.shutdown(cancel_futures=True)
                        except Exception:
                            pass
                        return
                    try:
                        f.result()
                    except Exception:
                        pass
        else:
            for prompt_name in normalized_prompts:
                if CANCEL_EVENT.is_set():
                    return
                self._process_image_with_prompt(image_info, prompt_name)

        # Emit progress update after image completes
        current_metrics = self._get_current_metrics()
        self._emit_progress({
            'type': 'image_complete',
            'run_id': self._current_run_id,
            'image_index': progress_index,
            'image_filename': image_info.filepath.name,
            'metrics': current_metrics,
        })


    def _process_image_with_prompt(self, image_info: ImageInfo, prompt_name: str):
        """Process a single image with a single prompt."""
        if CANCEL_EVENT.is_set():
            return

        # Emit prompt display event BEFORE cache check (so user sees what's being analyzed)
        if self.prompt_analyzer.verbose_prompts and self.prompt_analyzer.progress_callback:
            try:
                # Get prompt function and generate prompt text
                prompt_func = self.prompt_analyzer.get_prompt_function(prompt_name)
                market_data = {
                    'symbol': image_info.symbol,
                    'timeframe': image_info.timeframe,
                    'mid_price': 'N/A',
                    'bid_price': 'N/A',
                    'ask_price': 'N/A',
                    'last_close_price': 'N/A',
                    'funding_rate': 'N/A',
                    'long_short_ratio': 'N/A'
                }
                prompt_data = prompt_func(market_data)
                prompt_text = prompt_data.get('prompt', '')

                # Get assistant model
                assistant_model = 'N/A'
                try:
                    assistant_id = self.prompt_analyzer.config.openai.assistant.assistants.get('analyzer', '')
                    if assistant_id:
                        asst_obj = self.prompt_analyzer.analyzer.client.beta.assistants.retrieve(assistant_id)
                        assistant_model = getattr(asst_obj, 'model', 'N/A')
                except Exception:
                    pass

                # Emit the event
                self.prompt_analyzer.progress_callback({
                    'type': 'prompt_display',
                    'prompt_name': prompt_name,
                    'prompt_text': prompt_text,
                    'image_filename': image_info.filepath.name,
                    'model': assistant_model,
                    'prompt_length': len(prompt_text),
                    'symbol': image_info.symbol,
                    'timeframe': image_info.timeframe
                })

                logger.info(f"\n{'='*80}\nPROMPT SENT TO AI ({prompt_name}):\n{'='*80}\n{prompt_text}\n{'='*80}")
                print(f"\n{'='*80}")
                print(f"📝 PROMPT SENT TO AI ({prompt_name}):")
                print(f"{'='*80}")
                print(f"Image: {image_info.filepath.name}")
                print(f"Model: {assistant_model}")
                print(f"Prompt length: {len(prompt_text)} characters")
                print(f"First 500 chars:\n{prompt_text[:500]}...")
                print(f"{'='*80}\n")
            except Exception as e:
                logger.debug(f"Failed to emit prompt display event: {e}")

        # Check store to avoid re-analyzing the same prompt+image+model (save API cost)
        cached = None
        try:
            image_filename = image_info.filepath.name
            # try to determine intended assistant_model from prompt metadata
            try:
                prompt_func = self.prompt_analyzer.get_prompt_function(prompt_name)
                prompt_meta = prompt_func({
                    'symbol': image_info.symbol,
                    'timeframe': image_info.timeframe,
                    'mid_price': 'N/A',
                    'bid_price': 'N/A',
                    'ask_price': 'N/A',
                    'last_close_price': 'N/A',
                    'funding_rate': 'N/A',
                    'long_short_ratio': 'N/A'
                })
                intended_model = (
                    prompt_meta.get('assistant_model')
                    or prompt_meta.get('model')
                    or (prompt_meta.get('version', {}) or {}).get('model')
                )
            except Exception:
                intended_model = None
            if self.backtest_store is not None and self.backtest_store.has_cached_analysis(
                prompt_name=prompt_name,
                image_filename=image_filename,
                assistant_model=intended_model,
                require_non_error=True,
            ):
                cached = self.backtest_store.get_cached_analysis(
                    prompt_name=prompt_name,
                    image_filename=image_filename,
                    assistant_model=intended_model,
                )
        except Exception:
            cached = None

        if cached is not None:
            # Reuse cached analysis result
            recommendation = (cached.get('recommendation') or '')
            confidence = cached.get('confidence') or 0.0
            analysis_row = {
                'prompt_name': prompt_name,
                'prompt_version': cached.get('prompt_version', 'unknown'),
                'symbol': cached.get('symbol', image_info.symbol),
                'timeframe': cached.get('timeframe', image_info.timeframe),
                'timestamp': cached.get('timestamp', image_info.timestamp.isoformat()),
                'image_path': cached.get('image_path', str(image_info.filepath)),
                'recommendation': recommendation,
                'confidence': confidence,
                'entry_price': cached.get('entry_price'),
                'stop_loss': cached.get('stop_loss'),
                'take_profit': cached.get('take_profit'),
                'rr_ratio': cached.get('rr_ratio'),
                'status': 'signal' if recommendation and recommendation.lower() in ['buy', 'sell'] else 'hold',
                'raw_response': cached.get('raw_response'),
                'rationale': cached.get('rationale'),
                'error_message': cached.get('error_message'),
                'assistant_id': cached.get('assistant_id'),
                'assistant_model': cached.get('assistant_model')
            }
            self.results_aggregator.add_analysis(analysis_row)
            if self._current_run_id is not None:
                try:
                    self.backtest_store.add_analysis(self._current_run_id, analysis_row)
                except Exception:
                    # Defer to end-of-run flush to avoid losing data on temporary locks
                    self._pending_analyses.append(analysis_row)

            # HOLD -> no simulation
            if recommendation.lower() not in ['buy', 'sell']:
                print(f"    ⏸️  {prompt_name}: SKIPPED - Already analyzed (conf: {confidence:.2f})")
                return

            # Use cached values to simulate trade
            candles = self.candle_fetcher.get_candles_for_simulation(
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                start_timestamp=image_info.timestamp_ms
            )
            if not candles:
                # Try to fetch and cache missing candles starting from image timestamp
                self.candle_fetcher.fetch_and_cache_candles(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    earliest_timestamp=image_info.timestamp_ms
                )
                # Retry after fetch
                candles = self.candle_fetcher.get_candles_for_simulation(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    start_timestamp=image_info.timestamp_ms
                )
                if not candles:
                    print(f"    ⚠️  {prompt_name}: No candles available (cached)")
                    return

            trade_record = {
                'recommendation': recommendation,
                'entry_price': cached.get('entry_price'),
                'stop_loss': cached.get('stop_loss'),
                'take_profit': cached.get('take_profit'),
                'timestamp': image_info.timestamp.isoformat(),
                'symbol': image_info.symbol,
                'normalized_timeframe': image_info.timeframe
            }
            simulation = self.trade_simulator.simulate_trade(trade_record, candles)

            trade_data = {
                'prompt_name': prompt_name,
                'prompt_version': cached.get('prompt_version', 'unknown'),
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'timestamp': image_info.timestamp.isoformat(),
                'recommendation': recommendation,
                'entry_price': cached.get('entry_price'),
                'stop_loss': cached.get('stop_loss'),
                'take_profit': cached.get('take_profit'),
                'confidence': confidence,
                'rr_ratio': cached.get('rr_ratio', 0),
                'outcome': simulation['outcome'],
                'duration_candles': simulation['duration_candles'],
                'achieved_rr': simulation.get('achieved_rr', 0),
                'exit_price': simulation.get('exit_price'),
                'exit_candle_index': simulation.get('exit_candle_index'),
                'entry_candle_index': simulation.get('entry_candle_index'),
                'mfe_price': simulation.get('mfe_price'),
                'mae_price': simulation.get('mae_price'),
                'mfe_percent': simulation.get('mfe_percent'),
                'mae_percent': simulation.get('mae_percent'),
                'mfe_r': simulation.get('mfe_r'),
                'mae_r': simulation.get('mae_r'),
                'realized_pnl_price': simulation.get('realized_pnl_price'),
                'realized_pnl_percent': simulation.get('realized_pnl_percent'),
                'image_path': str(image_info.filepath)
            }
            self.results_aggregator.add_trade(trade_data)
            if self._current_run_id is not None:
                try:
                    self.backtest_store.add_trade(self._current_run_id, trade_data)
                except Exception:
                    self._pending_trades.append(trade_data)

            outcome_emoji = {'win':'✅','loss':'❌','expired':'⏱️'}.get(simulation['outcome'], '❓')
            self._print_trade_block(
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                prompt_name=prompt_name,
                recommendation=recommendation,
                entry=trade_record['entry_price'],
                sl=trade_record['stop_loss'],
                tp=trade_record['take_profit'],
                confidence=confidence,
                outcome=simulation['outcome'],
                cached_note=f"Note: {outcome_emoji} Cached - Already analyzed"
            )
            return

        try:
            # Analyze image
            analysis = self.prompt_analyzer.analyze_image(image_info, prompt_name)

            # Log raw output to file
            if analysis is None:
                # Log failed analysis
                self.raw_output_logger.log_analysis(
                    prompt_name=prompt_name,
                    image_name=image_info.filepath.name,
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    timestamp=image_info.timestamp.isoformat(),
                    raw_output="Analysis returned None",
                    error="Analysis failed - returned None"
                )
            else:
                # Log successful analysis with complete raw output
                self.raw_output_logger.log_analysis(
                    prompt_name=prompt_name,
                    image_name=image_info.filepath.name,
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    timestamp=image_info.timestamp.isoformat(),
                    raw_output=analysis.get('raw_response') or analysis.get('raw_text') or str(analysis),
                    analysis_result=analysis
                )

            # Always log an analysis record (even if failed or HOLD)
            if analysis is None:
                # Try to extract prompt version metadata without incurring analysis again
                try:
                    prompt_func = self.prompt_analyzer.get_prompt_function(prompt_name)
                    prompt_meta = prompt_func({
                        'symbol': image_info.symbol,
                        'timeframe': image_info.timeframe,
                        'mid_price': 'N/A',
                        'bid_price': 'N/A',
                        'ask_price': 'N/A',
                        'last_close_price': 'N/A',
                        'funding_rate': 'N/A',
                        'long_short_ratio': 'N/A'
                    })
                    prompt_version = prompt_meta.get('version', {}).get('name', 'unknown')
                except Exception:
                    prompt_version = 'unknown'

                err_row = {
                    'prompt_name': prompt_name,
                    'prompt_version': prompt_version,
                    'symbol': image_info.symbol,
                    'timeframe': image_info.timeframe,
                    'timestamp': image_info.timestamp.isoformat(),
                    'image_path': str(image_info.filepath),
                    'recommendation': None,
                    'confidence': None,
                    'entry_price': None,
                    'stop_loss': None,
                    'take_profit': None,
                    'rr_ratio': None,
                    'status': 'error'
                }
                self.results_aggregator.add_analysis(err_row)
                if self._current_run_id is not None:
                    try:
                        self.backtest_store.add_analysis(self._current_run_id, err_row)
                    except Exception:
                        self._pending_analyses.append(err_row)
                print(f"    ⚠️  {prompt_name}: Analysis failed")
                return

            recommendation = analysis.get('recommendation', '')
            confidence = analysis.get('confidence', 0)

            # Record analysis result including HOLDs
            analysis_row = {
                'prompt_name': prompt_name,
                'prompt_version': analysis.get('prompt_version', 'unknown'),
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'timestamp': image_info.timestamp.isoformat(),
                'image_path': str(image_info.filepath),
                'recommendation': recommendation,
                'confidence': confidence,
                'entry_price': analysis.get('entry_price'),
                'stop_loss': analysis.get('stop_loss'),
                'take_profit': analysis.get('take_profit'),
                'rr_ratio': analysis.get('risk_reward_ratio'),
                'status': 'signal' if recommendation and recommendation.lower() in ['buy', 'sell'] else 'hold',
                'raw_response': analysis.get('raw_response') or analysis.get('raw_text'),
                'rationale': analysis.get('rationale'),
                'error_message': None,
                'assistant_id': analysis.get('assistant_id'),
                'assistant_model': analysis.get('assistant_model')
            }
            self.results_aggregator.add_analysis(analysis_row)
            # Persist analysis to store (append-only; ignores duplicates)
            if self._current_run_id is not None:
                try:
                    self.backtest_store.add_analysis(self._current_run_id, analysis_row)
                except Exception as _:
                    pass

            # Check if HOLD
            if recommendation.lower() not in ['buy', 'sell']:
                print(f"    ⏸️  {prompt_name}: HOLD (confidence: {confidence:.2f})")
                return

            # Fetch candles for simulation (auto-fetch on cache miss)
            candles = self.candle_fetcher.get_candles_for_simulation(
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                start_timestamp=image_info.timestamp_ms
            )
            if not candles:
                # Try to fetch and cache missing candles starting from image timestamp
                self.candle_fetcher.fetch_and_cache_candles(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    earliest_timestamp=image_info.timestamp_ms
                )
                # Retry after fetch
                candles = self.candle_fetcher.get_candles_for_simulation(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    start_timestamp=image_info.timestamp_ms
                )
                if not candles:
                    print(f"    ⚠️  {prompt_name}: No candles available")
                    return

            # Simulate trade
            trade_record = {
                'recommendation': analysis['recommendation'],
                'entry_price': analysis['entry_price'],
                'stop_loss': analysis['stop_loss'],
                'take_profit': analysis['take_profit'],
                'timestamp': image_info.timestamp.isoformat(),
                'symbol': image_info.symbol,
                'normalized_timeframe': image_info.timeframe
            }

            simulation = self.trade_simulator.simulate_trade(trade_record, candles)

            # Store result
            trade_data = {
                'prompt_name': prompt_name,
                'prompt_version': analysis.get('prompt_version', 'unknown'),
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'timestamp': image_info.timestamp.isoformat(),
                'recommendation': analysis['recommendation'],
                'entry_price': analysis['entry_price'],
                'stop_loss': analysis['stop_loss'],
                'take_profit': analysis['take_profit'],
                'confidence': analysis.get('confidence', 0),
                'rr_ratio': analysis.get('risk_reward_ratio', 0),
                'outcome': simulation['outcome'],
                'duration_candles': simulation['duration_candles'],
                'achieved_rr': simulation.get('achieved_rr', 0),
                'exit_price': simulation.get('exit_price'),
                'exit_candle_index': simulation.get('exit_candle_index'),
                'entry_candle_index': simulation.get('entry_candle_index'),
                'mfe_price': simulation.get('mfe_price'),
                'mae_price': simulation.get('mae_price'),
                'mfe_percent': simulation.get('mfe_percent'),
                'mae_percent': simulation.get('mae_percent'),
                'mfe_r': simulation.get('mfe_r'),
                'mae_r': simulation.get('mae_r'),
                'realized_pnl_price': simulation.get('realized_pnl_price'),
                'realized_pnl_percent': simulation.get('realized_pnl_percent'),
                'image_path': str(image_info.filepath)
            }

            self.results_aggregator.add_trade(trade_data)
            # Persist trade to store (append-only; ignores duplicates)
            if self._current_run_id is not None:
                try:
                    self.backtest_store.add_trade(self._current_run_id, trade_data)
                except Exception as _:
                    self._pending_trades.append(trade_data)

            # Print result
            outcome_emoji = {
                'win': '✅',
                'loss': '❌',
                'expired': '⏱️'
            }.get(simulation['outcome'], '❓')

            self._print_trade_block(
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                prompt_name=prompt_name,
                recommendation=recommendation,
                entry=analysis['entry_price'],
                sl=analysis['stop_loss'],
                tp=analysis['take_profit'],
                confidence=analysis.get('confidence', 0),
                outcome=simulation['outcome']
            )

        except Exception as e:
            # Log exception to raw output file
            self.raw_output_logger.log_analysis(
                prompt_name=prompt_name,
                image_name=image_info.filepath.name,
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                timestamp=image_info.timestamp.isoformat(),
                raw_output=str(e),
                error=f"Exception during processing: {e}"
            )

            logger.error(
                f"Error processing {image_info.filepath.name} with {prompt_name}: {e}",
                exc_info=True
            )
            print(f"    ❌ {prompt_name}: Error - {e}")

            # Store error in database
            error_row = {
                'prompt_name': prompt_name,
                'prompt_version': 'unknown',
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'timestamp': image_info.timestamp.isoformat(),
                'image_path': str(image_info.filepath),
                'recommendation': None,
                'confidence': None,
                'entry_price': None,
                'stop_loss': None,
                'take_profit': None,
                'rr_ratio': None,
                'status': 'error',
                'raw_response': None,
                'rationale': None,
                'error_message': str(e),
                'assistant_id': None,
                'assistant_model': None
            }
            self.results_aggregator.add_analysis(error_row)
            if self._current_run_id is not None:
                try:
                    self.backtest_store.add_analysis(self._current_run_id, error_row)
                except Exception:
                    pass

    def _print_trade_block(self,
                           symbol: str,
                           timeframe: str,
                           prompt_name: str,
                           recommendation: str,
                           entry: Optional[float],
                           sl: Optional[float],
                           tp: Optional[float],
                           confidence: Optional[float],
                           outcome: str,
                           cached_note: Optional[str] = None) -> None:
        try:
            print("\n# Backtest results:")
            print(f"Symbol: {symbol}")
            print(f"Prompt: {prompt_name}")
            print(f"Timeframe: {timeframe}")
            print(f"Analyzer recommendation: {recommendation.upper() if recommendation else 'N/A'}")
            side = recommendation.upper() if recommendation else 'N/A'
            print(f"Side: {side}")
            print(f"Entry: {entry if entry is not None else 'N/A'}")
            print(f"SL: {sl if sl is not None else 'N/A'}")
            print(f"TP: {tp if tp is not None else 'N/A'}")
            if confidence is not None:
                print(f"Conf: {float(confidence):.2f}")
            else:
                print("Conf: N/A")
            print(f"Result: --> {outcome.upper()}")
            if cached_note:
                print(cached_note)
            print("")
        except Exception:
            # Fallback to previous single-line print on any unexpected formatting issue
            print(f"    {prompt_name}: {recommendation.upper()} @ {entry}, SL: {sl}, TP: {tp}, Conf: {confidence} → {outcome.upper()}")


    def _print_header(
        self,
        prompts: List[str],
        symbols: List[str],
        num_images: Optional[int],
        start_date: Optional[str],
        end_date: Optional[str]
    ):
        """Print backtest header."""
        print("\n" + "=" * 100)
        print("IMAGE BACKTEST: Testing prompts on historical chart images")
        print("=" * 100)
        print(f"Prompts: {', '.join(prompts)}")
        print(f"Symbols: {', '.join(symbols)}")
        if num_images:
            print(f"Images per symbol: {num_images}")
        if start_date:
            print(f"Start date: {start_date}")
        if end_date:
            print(f"End date: {end_date}")
        print("=" * 100)

    def _print_summary(self, metrics: List[Dict[str, Any]], duration: float):
        """Print results summary."""
        print("\n" + "=" * 100)
        print("RESULTS SUMMARY")
        print("=" * 100)

        for m in metrics:
            print(f"\nPrompt: {m['prompt_name']}")
            print(f"  Total Trades: {m['total_trades']}")
            print(f"  Wins: {m['wins']}")
            print(f"  Losses: {m['losses']}")
            print(f"  Expired: {m['expired']}")
            print(f"  Win Rate: {m['win_rate']:.2%}")
            print(f"  Profit Factor: {m['profit_factor']:.2f}")
            print(f"  Expectancy: {m['expectancy']:+.4f}")
            print(f"  Avg RR: {m['avg_rr']:.2f}")
            print(f"  Avg Confidence: {m['avg_confidence']:.2f}")

        # Find winner
        if len(metrics) > 1:
            best = max(metrics, key=lambda x: x['win_rate'])
            print(f"\n🏆 Winner: {best['prompt_name']} ({best['win_rate']:.2%} win rate)")

        print(f"\nDuration: {duration/60:.1f} minutes")
        print("=" * 100)

    def _save_results(self, metrics: List[Dict[str, Any]]):
        """Save results to CSV files."""
        import csv

        # Summary CSV intentionally omitted per requirements

        # Save detailed trades
        trades = self.results_aggregator.get_trades()
        if trades:
            trades_path = self.output_dir / "image_backtest_trades.csv"
            with open(trades_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)

            logger.info(f"Saved trades to: {trades_path}")

        # Save all analyses (including HOLDs and errors)
        analyses = self.results_aggregator.get_analyses()
        if analyses:
            analyses_path = self.output_dir / "image_backtest_analyses.csv"
            with open(analyses_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=analyses[0].keys())
                writer.writeheader()
                writer.writerows(analyses)

            logger.info(f"Saved analyses to: {analyses_path}")


    def _verify_persistence_and_repair(self) -> Dict[str, Any]:
        """Ensure all in-memory analyses/trades were persisted for this run; attempt repair with retries.
        Returns a summary dict to surface in logs/results.
        """
        result: Dict[str, Any] = {
            "verification_ok": False,
            "expected_trades": 0,
            "expected_analyses": 0,
            "db_trades": 0,
            "db_analyses": 0,
            "repaired_trades": 0,
            "repaired_analyses": 0,
        }
        run_id = getattr(self, "_current_run_id", None)
        if run_id is None:
            return result
        try:
            # Prepare expected sets
            trades: List[Dict[str, Any]] = self.results_aggregator.get_trades()
            analyses: List[Dict[str, Any]] = self.results_aggregator.get_analyses()
            exp_t = len(trades)
            exp_a = len(analyses)
            result["expected_trades"] = exp_t
            result["expected_analyses"] = exp_a

            # Read current DB counts
            with self.backtest_store._connect() as conn:  # type: ignore[attr-defined]
                c = conn.cursor()
                c.execute("SELECT COUNT(1) FROM trades WHERE run_id = ?", (run_id,))
                db_t = int(c.fetchone()[0] or 0)
                c.execute("SELECT COUNT(1) FROM analyses WHERE run_id = ?", (run_id,))
                db_a = int(c.fetchone()[0] or 0)
            result["db_trades"] = db_t
            result["db_analyses"] = db_a

            repaired_t = 0
            repaired_a = 0

            # Attempt to insert any missing trades
            if db_t < exp_t:
                for row in trades:
                    try:
                        with self.backtest_store._connect() as conn:  # type: ignore[attr-defined]
                            c = conn.cursor()
                            c.execute(
                                "SELECT 1 FROM trades WHERE run_id=? AND prompt_name=? AND image_path=? LIMIT 1",
                                (run_id, row.get("prompt_name"), row.get("image_path")),
                            )
                            exists = c.fetchone() is not None
                        if not exists:
                            self.backtest_store.add_trade(run_id, row)
                            repaired_t += 1
                    except Exception:
                        # Ignore and continue; add_trade has its own retry
                        pass

            # Attempt to insert any missing analyses
            if db_a < exp_a:
                for row in analyses:
                    try:
                        with self.backtest_store._connect() as conn:  # type: ignore[attr-defined]
                            c = conn.cursor()
                            c.execute(
                                "SELECT 1 FROM analyses WHERE run_id=? AND prompt_name=? AND image_path=? LIMIT 1",
                                (run_id, row.get("prompt_name"), row.get("image_path")),
                            )
                            exists = c.fetchone() is not None
                        if not exists:
                            self.backtest_store.add_analysis(run_id, row)
                            repaired_a += 1
                    except Exception:
                        pass

            # Final recount
            with self.backtest_store._connect() as conn:  # type: ignore[attr-defined]
                c = conn.cursor()
                c.execute("SELECT COUNT(1) FROM trades WHERE run_id = ?", (run_id,))
                db_t2 = int(c.fetchone()[0] or 0)
                c.execute("SELECT COUNT(1) FROM analyses WHERE run_id = ?", (run_id,))
                db_a2 = int(c.fetchone()[0] or 0)

            result["db_trades"] = db_t2
            result["db_analyses"] = db_a2
            result["repaired_trades"] = repaired_t
            result["repaired_analyses"] = repaired_a
            result["verification_ok"] = (db_t2 == exp_t and db_a2 == exp_a)

            return result
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return result

"""
> import os
> os.environ['BACKTEST_MAX_WORKERS_PROMPTS']='3'
> from prompt_performance.backtest_with_images import ImageBacktester, PROMPT_REGISTRY
>
> bt = ImageBacktester()
> res = bt.backtest_with_images(
>     prompts=list(PROMPT_REGISTRY.keys()),
>     symbols=['AVAXUSDT'],
>     num_images=3,
>     verbose=False,
> )
> print({k: res.get(k) for k in ['success','total_images','total_trades','duration_seconds']})
"""