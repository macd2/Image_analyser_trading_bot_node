"""
PromptStrategy - Independent chart-based trading strategy.

Combines sourcer, cleaner, and analyzer into a single self-contained module.
Replicates all functionality from the current trading cycle:
- Capture charts from TradingView watchlist
- Clean outdated chart files
- Analyze charts using OpenAI Assistant API
- Return standardized recommendations

This strategy is instance-aware and preserves all logging, error handling,
and configuration from the original trading cycle.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable

from openai import OpenAI

from trading_bot.config.settings_v2 import Config
from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.core.error_logger import set_cycle_id, clear_cycle_id
from trading_bot.core.utils import normalize_symbol_for_bybit, get_current_cycle_boundary
from trading_bot.core.prompts.prompt_registry import get_prompt_function
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.db.client import get_connection, release_connection, query_one, execute

from .sourcer import ChartSourcer
from .cleaner import ChartCleaner
from .analyzer import ChartAnalyzer

logger = logging.getLogger(__name__)


class PromptStrategy(BaseAnalysisModule):
    """
    Independent prompt-based trading strategy.
    
    Orchestrates chart capture, cleaning, and analysis in a single
    self-contained module that can be swapped with other strategies.
    """
    
    # Signal ranking weights (same as trading cycle)
    SIGNAL_WEIGHTS = {
        "confidence": 0.4,
        "risk_reward": 0.3,
        "setup_quality": 0.2,
        "market_environment": 0.1,
    }
    
    def __init__(
        self,
        config: Config,
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        heartbeat_callback: Optional[Callable] = None,
        testnet: bool = False,
        paper_trading: bool = False,
        prompt_name: Optional[str] = None,
    ):
        """Initialize prompt strategy with all components."""
        super().__init__(
            config=config,
            instance_id=instance_id,
            run_id=run_id,
            strategy_config=strategy_config,
            heartbeat_callback=heartbeat_callback,
        )
        
        self.testnet = testnet
        self.paper_trading = paper_trading
        self.prompt_name = prompt_name
        self._cycle_count = 0

        # Initialize components
        self.api_manager = BybitAPIManager(config, use_testnet=testnet)
        self.openai_client = OpenAI(api_key=config.openai.api_key)
        self.sourcer = ChartSourcer(config=config)
        self.cleaner = ChartCleaner(
            enable_backup=True,
            enable_age_based_cleaning=True,
            max_file_age_hours=24,
            enable_cycle_based_cleaning=True,
        )
        self.analyzer = ChartAnalyzer(
            openai_client=self.openai_client,
            config=config,
            api_manager=self.api_manager,
            skip_boundary_validation=False,
        )
        
        # Get prompt function
        self._prompt_function = None
        if prompt_name:
            try:
                self._prompt_function = get_prompt_function(prompt_name)
            except Exception as e:
                self.logger.warning(f"Failed to load prompt function '{prompt_name}': {e}")
    
    async def run_analysis_cycle(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Run analysis cycle.

        The strategy manages its own symbols and timeframe from the watchlist.
        These parameters are kept for interface compatibility but the strategy
        determines what to analyze based on captured charts.

        Args:
            symbols: Ignored - strategy uses watchlist symbols
            timeframe: Ignored - strategy uses configured timeframe
            cycle_id: Cycle identifier for audit trail

        Returns:
            List of recommendation dicts matching BaseAnalysisModule output format
        """
        set_cycle_id(cycle_id)
        self._cycle_count += 1
        cycle_start = datetime.now(timezone.utc)

        # Get configured timeframe (strategy manages its own timeframe)
        configured_timeframe = self.config.trading.timeframe if self.config.trading else "1h"

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"🔄 PROMPT STRATEGY CYCLE #{self._cycle_count} [{cycle_id}] - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        self.logger.info(f"{'='*60}")

        recommendations: List[Dict[str, Any]] = []

        try:
            # STEP 0: Clean outdated charts
            self.logger.info(f"\n🧹 STEP 0: Cleaning outdated charts...")
            charts_dir = self.config.paths.charts if self.config.paths else "data/charts"
            try:
                moved = self.cleaner.clean_outdated_files(
                    charts_dir,
                    dry_run=False,
                    timeframe_filter=configured_timeframe
                )
                cleaned_count = len(moved) if moved else 0
                self.logger.info(f"   ✓ Cleaned {cleaned_count} outdated chart files")
            except Exception as e:
                self.logger.warning(f"Chart cleanup failed (non-fatal): {e}")

            if self.heartbeat_callback:
                self._heartbeat("Cleaning outdated charts")

            # STEP 1: Capture charts
            self.logger.info(f"\n📷 STEP 1: Capturing charts from watchlist...")
            self.logger.info(f"   Timeframe: {configured_timeframe}")
            
            if not await self.sourcer.setup_browser_session():
                self.logger.error("Failed to setup browser session")
                return recommendations
            
            try:
                target_chart = self.config.tradingview.target_chart if self.config.tradingview else None
                chart_paths = await self.sourcer.capture_all_watchlist_screenshots(
                    target_chart=target_chart,
                    timeframe=configured_timeframe,
                )

                if not chart_paths:
                    self.logger.warning("No charts captured from watchlist")
                    return recommendations

                self.logger.info(f"   ✓ Captured {len(chart_paths)} charts")
                if self.heartbeat_callback:
                    self._heartbeat(f"Captured {len(chart_paths)} charts")

                # STEP 2: Analyze charts in parallel
                self.logger.info(f"\n🤖 STEP 2: Analyzing {len(chart_paths)} charts in PARALLEL...")
                recommendations = await self._analyze_all_charts_parallel(
                    chart_paths, configured_timeframe, cycle_id
                )
                
                self.logger.info(f"   ✓ Analyzed {len(recommendations)} charts")
                if self.heartbeat_callback:
                    self._heartbeat(f"Analyzed {len(recommendations)} charts")
                
            finally:
                await self.sourcer.cleanup_browser_session()
        
        except Exception as e:
            self.logger.error(f"Strategy cycle error: {e}", exc_info=True)
        
        finally:
            clear_cycle_id()
        
        return recommendations
    
    async def _analyze_all_charts_parallel(
        self,
        chart_paths: Dict[str, str],
        timeframe: str,
        cycle_id: str,
    ) -> List[Dict[str, Any]]:
        """Analyze all charts in parallel using asyncio.gather()."""
        tasks = [
            self._analyze_chart_async(symbol, path, timeframe, cycle_id)
            for symbol, path in chart_paths.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        recommendations = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Analysis task failed: {result}")
                continue
            if result and not result.get("skipped"):
                recommendations.append(result)
        
        return recommendations
    
    async def _analyze_chart_async(
        self,
        symbol: str,
        chart_path: str,
        timeframe: str,
        cycle_id: str,
    ) -> Dict[str, Any]:
        """Analyze single chart asynchronously."""
        normalized_symbol = normalize_symbol_for_bybit(symbol)
        
        result: Dict[str, Any] = {
            "symbol": normalized_symbol,
            "timeframe": timeframe,
            "cycle_id": cycle_id,
            "chart_path": chart_path,
        }
        
        # Run analyzer in thread pool
        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: self.analyzer.analyze_chart(
                image_path=chart_path,
                use_assistant=True,
                target_timeframe=timeframe,
                prompt_function=self._prompt_function,
            )
        )
        
        if not analysis or analysis.get("error") or analysis.get("skipped"):
            result["skipped"] = True
            result["skip_reason"] = analysis.get("skip_reason", "unknown") if analysis else "analysis_failed"
            return result
        
        # Extract fields
        recommendation = analysis.get("recommendation", "hold").upper()
        confidence = float(analysis.get("confidence", 0))
        
        result["recommendation"] = recommendation
        result["confidence"] = confidence
        result["analysis"] = analysis
        result["risk_reward"] = float(analysis.get("risk_reward_ratio", analysis.get("risk_reward", 0)) or 0)
        result["setup_quality"] = float(analysis.get("setup_quality", 0.5) or 0.5)
        result["market_environment"] = float(analysis.get("market_environment", 0.5) or 0.5)
        result["entry_price"] = analysis.get("entry_price")
        result["stop_loss"] = analysis.get("stop_loss")
        result["take_profit"] = analysis.get("take_profit")
        
        self.logger.info(f"   📊 {normalized_symbol}: {recommendation} (conf: {confidence:.2%}, RR: {result['risk_reward']:.2f})")
        
        # Validate output format
        try:
            self._validate_output(result)
        except ValueError as e:
            self.logger.error(f"Output validation failed for {normalized_symbol}: {e}")
            result["error"] = str(e)
        
        return result

