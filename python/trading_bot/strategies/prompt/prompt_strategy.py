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

    # Strategy type identification
    STRATEGY_TYPE = "price_based"
    STRATEGY_NAME = "PromptStrategy"
    STRATEGY_VERSION = "1.0"

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

        # Get prompt_name from strategy_config if not provided as parameter
        if not prompt_name:
            prompt_name = self.get_config_value('prompt_name', None)
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
        if self.prompt_name:
            try:
                self._prompt_function = get_prompt_function(self.prompt_name)
            except Exception as e:
                self.logger.warning(f"Failed to load prompt function '{self.prompt_name}': {e}")
    
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
            # Check if stop was requested before starting
            if self._stop_requested:
                self.logger.info("Stop requested - aborting analysis cycle")
                return recommendations

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
        # Check if stop was requested before starting parallel analysis
        if self._stop_requested:
            self.logger.info("Stop requested - aborting parallel analysis")
            return []

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

        # Add strategy UUID for traceability
        result["strategy_uuid"] = self.strategy_uuid
        result["strategy_type"] = self.STRATEGY_TYPE
        result["strategy_name"] = self.STRATEGY_NAME

        self.logger.info(f"   📊 {normalized_symbol}: {recommendation} (conf: {confidence:.2%}, RR: {result['risk_reward']:.2f})")
        
        # Validate output format
        try:
            self._validate_output(result)
        except ValueError as e:
            self.logger.error(f"Output validation failed for {normalized_symbol}: {e}")
            result["error"] = str(e)

        return result

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Validate price-based signal.

        Checks:
        - RR ratio >= min_rr (default 1.0)
        - Entry/SL/TP prices are in correct order
        - Prices are reasonable (not zero or negative)

        Args:
            signal: Signal dict with entry_price, stop_loss, take_profit

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        min_rr = self.get_config_value("min_rr", 1.0)

        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        if not all([entry, sl, tp]):
            raise ValueError(f"Missing price levels: entry={entry}, sl={sl}, tp={tp}")

        if entry <= 0 or sl <= 0 or tp <= 0:
            raise ValueError(f"Prices must be positive: entry={entry}, sl={sl}, tp={tp}")

        # Determine direction based on entry vs SL
        is_long = entry > sl

        if is_long:
            if not (sl < entry < tp):
                raise ValueError(
                    f"Long signal prices in wrong order: SL({sl}) < Entry({entry}) < TP({tp})"
                )
            rr_ratio = (tp - entry) / (entry - sl)
        else:
            if not (tp < entry < sl):
                raise ValueError(
                    f"Short signal prices in wrong order: TP({tp}) < Entry({entry}) < SL({sl})"
                )
            rr_ratio = (entry - tp) / (sl - entry)

        if rr_ratio < min_rr:
            raise ValueError(
                f"RR ratio {rr_ratio:.2f} below minimum {min_rr}"
            )

        return True

    def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate price-based risk metrics.

        Returns:
            Dict with: risk_per_unit, reward_per_unit, risk_reward_ratio
        """
        entry = signal.get("entry_price")
        sl = signal.get("stop_loss")
        tp = signal.get("take_profit")

        is_long = entry > sl

        if is_long:
            risk_per_unit = entry - sl
            reward_per_unit = tp - entry
        else:
            risk_per_unit = sl - entry
            reward_per_unit = entry - tp

        rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0

        return {
            "risk_per_unit": risk_per_unit,
            "reward_per_unit": reward_per_unit,
            "risk_reward_ratio": rr_ratio,
        }

    def get_exit_condition(self) -> Dict[str, Any]:
        """
        Get price-based exit condition metadata.

        Returns:
            Dict with TP and SL prices for simulator to check
        """
        return {
            "type": "price_level",
            "description": "Exit when price touches TP or SL level",
        }

    def get_monitoring_metadata(self) -> Dict[str, Any]:
        """
        Get price-based monitoring metadata.

        Returns:
            Dict with price levels and RR ratio for position monitor
        """
        return {
            "type": "price_level",
            "enable_position_tightening": self.get_config_value("enable_position_tightening", True),
            "enable_sl_tightening": self.get_config_value("enable_sl_tightening", True),
            "rr_tightening_steps": self.get_config_value("rr_tightening_steps", []),
        }

    def should_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Check if price-based trade should exit.

        For price-based strategies, exit when price touches TP or SL.

        Args:
            trade: Trade record with entry_price, stop_loss, take_profit
            current_candle: Current candle {timestamp, open, high, low, close}
            pair_candle: Not used for price-based (None)

        Returns:
            Dict with 'should_exit' bool and 'exit_details' dict
        """
        try:
            entry_price = trade.get("entry_price")
            stop_loss = trade.get("stop_loss")
            take_profit = trade.get("take_profit")
            current_price = current_candle.get("close")

            if not all([entry_price, stop_loss, take_profit, current_price]):
                return {
                    "should_exit": False,
                    "exit_details": {
                        "reason": "no_exit",
                        "error": "Missing required price data",
                    }
                }

            # Determine direction
            is_long = entry_price > stop_loss

            # Check if price touched TP or SL
            if is_long:
                tp_touched = current_price >= take_profit
                sl_touched = current_price <= stop_loss
            else:
                tp_touched = current_price <= take_profit
                sl_touched = current_price >= stop_loss

            if tp_touched:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "tp_touched",
                        "price": current_price,
                        "tp": take_profit,
                        "sl": stop_loss,
                        "distance_to_tp": abs(current_price - take_profit),
                        "distance_to_sl": abs(current_price - stop_loss),
                        "direction": "long" if is_long else "short",
                    }
                }

            if sl_touched:
                return {
                    "should_exit": True,
                    "exit_details": {
                        "reason": "sl_touched",
                        "price": current_price,
                        "tp": take_profit,
                        "sl": stop_loss,
                        "distance_to_tp": abs(current_price - take_profit),
                        "distance_to_sl": abs(current_price - stop_loss),
                        "direction": "long" if is_long else "short",
                    }
                }

            # No exit condition met
            return {
                "should_exit": False,
                "exit_details": {
                    "reason": "no_exit",
                    "price": current_price,
                    "tp": take_profit,
                    "sl": stop_loss,
                    "distance_to_tp": abs(current_price - take_profit),
                    "distance_to_sl": abs(current_price - stop_loss),
                    "direction": "long" if is_long else "short",
                }
            }

        except Exception as e:
            self.logger.error(f"Error in should_exit: {e}")
            return {
                "should_exit": False,
                "exit_details": {
                    "reason": "error",
                    "error": str(e),
                }
            }

    @classmethod
    def get_required_settings(cls) -> Dict[str, Any]:
        """
        Get price-based strategy settings schema.

        Returns:
            Dict with settings schema for PromptStrategy
        """
        return {
            "enable_position_tightening": {
                "type": "bool",
                "default": True,
                "description": "Enable position tightening (moving SL to breakeven or profit)",
            },
            "enable_sl_tightening": {
                "type": "bool",
                "default": True,
                "description": "Enable stop loss tightening based on RR ratio",
            },
            "rr_tightening_steps": {
                "type": "list",
                "default": [],
                "description": "List of RR ratio thresholds for SL tightening (e.g., [2.0, 3.0, 4.0])",
            },
            "min_rr": {
                "type": "float",
                "default": 1.0,
                "description": "Minimum risk/reward ratio for signal validation",
            },
        }

