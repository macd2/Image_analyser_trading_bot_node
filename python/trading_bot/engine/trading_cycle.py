"""
Trading Cycle - Orchestrates chart capture, analysis, and signal execution.
This is the core production cycle that runs at timeframe boundaries.

MULTISTEP PROCESS:
1. Capture all charts from watchlist
2. Analyze ALL charts in PARALLEL using asyncio.gather()
3. Collect all recommendations (wait for all to complete)
4. Rank signals by quality (confidence, risk-reward, setup quality)
5. Check available slots and allocate to best signals
6. Execute only the selected best signals
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, List, Tuple

from trading_bot.config.settings_v2 import Config
from trading_bot.core.analyzer import ChartAnalyzer
from trading_bot.core.sourcer import ChartSourcer
from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.core.cleaner import ChartCleaner
from trading_bot.core.error_logger import set_cycle_id, clear_cycle_id
from trading_bot.core.utils import (  # type: ignore
    get_current_cycle_boundary,  # type: ignore
    seconds_until_next_boundary,  # type: ignore
    normalize_symbol_for_bybit,
)
from trading_bot.core.prompts.prompt_registry import get_prompt_function
from trading_bot.db.client import get_connection, execute
from openai import OpenAI

logger = logging.getLogger(__name__)


class TradingCycle:
    """
    Orchestrates complete trading cycle with MULTISTEP PROCESS:

    1. Wait for cycle boundary
    2. Capture charts for all configured symbols
    3. Analyze ALL charts in PARALLEL (asyncio.gather)
    4. Collect ALL recommendations (wait for completion)
    5. Rank signals by quality (confidence, RR, setup)
    6. Check available slots
    7. Allocate slots to BEST signals only
    8. Execute selected signals
    """

    # No default timeframe - must be configured explicitly

    # Signal ranking weights for scoring
    SIGNAL_WEIGHTS = {
        "confidence": 0.4,
        "risk_reward": 0.3,
        "setup_quality": 0.2,
        "market_environment": 0.1,
    }

    def __init__(
        self,
        config: Optional[Config] = None,
        execute_signal_callback: Optional[Callable] = None,
        testnet: bool = False,
        run_id: Optional[str] = None,
        prompt_name: Optional[str] = None,
        paper_trading: bool = False,
        instance_id: Optional[str] = None,
    ):
        """
        Initialize trading cycle.

        Args:
            config: Configuration object
            execute_signal_callback: Callback to execute signals (from TradingEngine)
            testnet: Use testnet if True
            run_id: Parent run UUID for audit trail
            prompt_name: Name of the prompt function to use for analysis
            paper_trading: Whether in paper trading mode (for database-based position checks)
            instance_id: Instance ID for filtering database queries in paper trading mode
        """
        self.config = config or Config.load()
        self.testnet = testnet
        self.execute_signal = execute_signal_callback
        self.run_id = run_id  # Track parent run for audit trail
        self.prompt_name = prompt_name  # Instance-level prompt selection
        self.paper_trading = paper_trading
        self.instance_id = instance_id

        # Database
        self._db = get_connection()

        # API manager for market data
        self.api_manager = BybitAPIManager(self.config, use_testnet=testnet)  # type: ignore[arg-type]

        # Initialize OpenAI client
        self.openai_client = OpenAI(api_key=self.config.openai.api_key)

        # Core components
        self.sourcer = ChartSourcer(config=self.config)  # type: ignore[arg-type]
        self.analyzer = ChartAnalyzer(
            openai_client=self.openai_client,
            config=self.config,
            api_manager=self.api_manager,
        )
        self.cleaner = ChartCleaner(
            enable_backup=True,
            enable_age_based_cleaning=True,
            max_file_age_hours=24,
            enable_cycle_based_cleaning=True,
        )

        # Cycle state
        self._running = False
        self._cycle_count = 0
        self._last_cycle_time: Optional[datetime] = None

        # Resolve prompt function from prompt_name - REQUIRED, no defaults
        if not self.prompt_name:
            raise ValueError("prompt_name is required. Configure prompt in instance settings before starting bot.")
        self._prompt_function = get_prompt_function(self.prompt_name)
        logger.info(f"📝 Using prompt: {self.prompt_name}")

        # Symbols come from TradingView watchlist (captured at runtime)
        self.timeframe = self._load_timeframe()

    def _load_timeframe(self) -> str:
        """Load trading timeframe from instance config."""
        if hasattr(self.config, 'trading') and hasattr(self.config.trading, 'timeframe'):
            return self.config.trading.timeframe
        raise ValueError("trading.timeframe not configured. Set timeframe in instance settings before starting bot.")

    def start(self) -> None:
        """Start the trading cycle loop."""
        self._running = True
        logger.info("=" * 60)
        logger.info("🔄 TRADING CYCLE STARTED")
        logger.info(f"   Symbols: From TradingView watchlist")
        logger.info(f"   Timeframe: {self.timeframe}")
        logger.info("=" * 60)

    def stop(self) -> None:
        """Stop the trading cycle loop."""
        self._running = False
        logger.info("Trading cycle stopped")

    async def run_cycle_async(self) -> Dict[str, Any]:
        """
        Run a single trading cycle asynchronously with MULTISTEP PROCESS.

        STEPS:
        1. Capture all charts from watchlist
        2. Analyze ALL charts in PARALLEL
        3. Collect ALL recommendations
        4. Rank signals by quality
        5. Check available slots
        6. Execute BEST signals only

        Returns:
            Cycle result with recommendations and trades
        """
        cycle_id = str(uuid.uuid4())[:8]
        cycle_start = datetime.now(timezone.utc)
        self._cycle_count += 1

        # Set cycle context for error logging
        set_cycle_id(cycle_id)

        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 CYCLE #{self._cycle_count} [{cycle_id}] - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info(f"{'='*60}")

        results: Dict[str, Any] = {
            "cycle_id": cycle_id,
            "started_at": cycle_start.isoformat(),
            "symbols_analyzed": 0,
            "recommendations": [],
            "actionable_signals": [],
            "ranked_signals": [],
            "selected_signals": [],
            "trades_executed": [],
            "errors": [],
        }

        chart_paths: Dict[str, str] = {}

        # Record cycle BEFORE analysis starts (so recommendations can reference it)
        self._record_cycle_start(cycle_id, cycle_start)

        try:
            # STEP 0: Clean outdated charts
            charts_dir = self.config.paths.charts if self.config.paths else "data/charts"
            try:
                moved = self.cleaner.clean_outdated_files(charts_dir, dry_run=False)
                if moved:
                    logger.info(f"🧹 Cleaned {len(moved)} outdated charts")
            except Exception as e:
                logger.warning(f"Chart cleanup failed (non-fatal): {e}")

            # STEP 1: Capture all charts from watchlist
            target_chart = self.config.tradingview.target_chart if self.config.tradingview else None
            logger.info(f"\n📷 STEP 1: Capturing charts via watchlist...")
            logger.info(f"   Target chart: {target_chart or 'None (using default)'}")
            logger.info(f"   Timeframe: {self.timeframe}")

            if not await self.sourcer.setup_browser_session():
                logger.error("Failed to setup browser session", extra={
                    'event': 'browser_setup_failed',
                    'cycle_id': cycle_id,
                })
                results["errors"].append({"error": "Browser setup failed"})
                return results

            try:
                chart_paths = await self.sourcer.capture_all_watchlist_screenshots(
                    target_chart=target_chart,
                    timeframe=self.timeframe,
                )

                if not chart_paths:
                    logger.warning("No charts captured from watchlist")
                    results["errors"].append({"error": "No charts captured"})
                    return results

                logger.info(f"✅ Captured {len(chart_paths)} charts from watchlist")

                # STEP 2: Analyze ALL charts in PARALLEL
                logger.info(f"\n🤖 STEP 2: Analyzing {len(chart_paths)} charts in PARALLEL...")
                analysis_start = datetime.now(timezone.utc)

                all_analyses = await self._analyze_all_charts_parallel(chart_paths, cycle_id)

                analysis_duration = (datetime.now(timezone.utc) - analysis_start).total_seconds()
                logger.info(f"✅ Parallel analysis completed in {analysis_duration:.1f}s")

                # STEP 3: Collect all recommendations
                logger.info(f"\n📊 STEP 3: Collecting recommendations...")
                actionable_signals: List[Dict[str, Any]] = []

                for analysis_result in all_analyses:
                    if analysis_result.get("error"):
                        results["errors"].append({
                            "symbol": analysis_result.get("symbol"),
                            "error": analysis_result.get("error")
                        })
                        continue

                    results["symbols_analyzed"] += 1
                    if analysis_result.get("recommendation"):
                        results["recommendations"].append(analysis_result)

                        # Collect actionable signals (BUY/SELL/LONG/SHORT)
                        rec = analysis_result.get("recommendation", "").upper()
                        if rec in ("BUY", "SELL", "LONG", "SHORT"):
                            actionable_signals.append(analysis_result)

                results["actionable_signals"] = actionable_signals
                logger.info(f"   Total analyzed: {results['symbols_analyzed']}")
                logger.info(f"   Actionable signals: {len(actionable_signals)}")

                # STEP 4: Rank signals by quality
                logger.info(f"\n🏆 STEP 4: Ranking {len(actionable_signals)} signals by quality...")
                ranked_signals = self._rank_signals_by_quality(actionable_signals)
                results["ranked_signals"] = ranked_signals

                for i, sig in enumerate(ranked_signals[:5]):  # Log top 5
                    logger.info(f"   #{i+1}: {sig['symbol']} - score: {sig['ranking_score']:.3f} "
                               f"(conf: {sig['confidence']:.2f}, RR: {sig.get('risk_reward', 0):.2f})")

                # STEP 5: Check available slots
                logger.info(f"\n📦 STEP 5: Checking available slots...")
                available_slots = self._get_available_slots()
                logger.info(f"   Available slots: {available_slots}")

                # STEP 6: Select best signals for available slots
                logger.info(f"\n🎯 STEP 6: Selecting best {available_slots} signal(s)...")
                selected_signals = ranked_signals[:available_slots] if available_slots > 0 else []
                results["selected_signals"] = selected_signals

                for sig in selected_signals:
                    logger.info(f"   ✅ Selected: {sig['symbol']} (score: {sig['ranking_score']:.3f})")

                # STEP 7: Execute selected signals
                logger.info(f"\n🚀 STEP 7: Executing {len(selected_signals)} selected signal(s)...")
                for signal in selected_signals:
                    trade_result = await self._execute_selected_signal(signal, cycle_id)
                    if trade_result:
                        results["trades_executed"].append(trade_result)

            finally:
                await self.sourcer.cleanup_browser_session()

        except Exception as e:
            logger.error(f"Cycle error: {e}", extra={
                'event': 'cycle_failed',
                'cycle_id': cycle_id,
                'context': {'cycle_number': self._cycle_count},
            }, exc_info=True)
            results["errors"].append({"cycle": True, "error": str(e)})

        # Record cycle and clear context
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        self._last_cycle_time = cycle_start
        self._record_cycle(results)
        clear_cycle_id()

        logger.info(f"\n📊 CYCLE #{self._cycle_count} COMPLETE")
        logger.info(f"   Analyzed: {results['symbols_analyzed']}/{len(chart_paths)}")
        logger.info(f"   Actionable signals: {len(results['actionable_signals'])}")
        logger.info(f"   Selected for execution: {len(results['selected_signals'])}")
        logger.info(f"   Trades executed: {len(results['trades_executed'])}")
        logger.info(f"   Errors: {len(results['errors'])}")

        return results

    async def _analyze_all_charts_parallel(
        self, chart_paths: Dict[str, str], cycle_id: str
    ) -> List[Dict[str, Any]]:
        """
        Analyze ALL charts in PARALLEL using asyncio.gather().

        This is the key optimization - instead of sequential processing,
        we launch all AI analyses concurrently and wait for all to complete.

        Args:
            chart_paths: Dict of {symbol: chart_path}
            cycle_id: Current cycle ID

        Returns:
            List of analysis results (one per symbol)
        """
        async def analyze_single(symbol: str, chart_path: str) -> Dict[str, Any]:
            """Wrapper to analyze a single chart with error handling."""
            try:
                return await self._analyze_chart_async(symbol, chart_path, cycle_id)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)
                return {
                    "symbol": symbol,
                    "error": str(e),
                    "chart_path": chart_path,
                }

        # Create tasks for all charts
        tasks = [
            analyze_single(symbol, chart_path)
            for symbol, chart_path in chart_paths.items()
        ]

        # Run ALL analyses in parallel
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    async def _analyze_chart_async(
        self, symbol: str, chart_path: str, cycle_id: str
    ) -> Dict[str, Any]:
        """
        Async wrapper for chart analysis.

        Runs the synchronous analyzer in executor to not block the event loop.
        """
        normalized_symbol = normalize_symbol_for_bybit(symbol)

        result: Dict[str, Any] = {
            "symbol": normalized_symbol,
            "timeframe": self.timeframe,
            "cycle_id": cycle_id,
            "chart_path": chart_path,
        }

        # Run sync analyzer in thread pool to not block
        loop = asyncio.get_event_loop()
        analysis = await loop.run_in_executor(
            None,
            lambda: self.analyzer.analyze_chart(
                image_path=chart_path,
                use_assistant=True,
                target_timeframe=self.timeframe,
                prompt_function=self._prompt_function,
            )
        )

        if not analysis or analysis.get("error") or analysis.get("skipped"):
            skip_reason = analysis.get("skip_reason", "unknown") if analysis else "analysis_failed"
            result["skipped"] = True
            result["skip_reason"] = skip_reason
            return result

        # Extract key fields
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

        # Record recommendation to DB
        rec_id = self._record_recommendation(result, analysis)
        result["recommendation_id"] = rec_id

        logger.info(f"   📊 {normalized_symbol}: {recommendation} (conf: {confidence:.2%}, RR: {result['risk_reward']:.2f})")

        return result

    def _rank_signals_by_quality(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank actionable signals by quality score.

        Scoring formula:
        score = (confidence * 0.4) + (risk_reward_normalized * 0.3) +
                (setup_quality * 0.2) + (market_environment * 0.1)

        Args:
            signals: List of actionable signals

        Returns:
            Signals sorted by ranking_score (highest first)
        """
        for signal in signals:
            # Normalize risk-reward (cap at 5 for scoring)
            rr = min(signal.get("risk_reward", 0), 5) / 5  # Normalize to 0-1

            # Calculate composite score
            score = (
                signal.get("confidence", 0) * self.SIGNAL_WEIGHTS["confidence"] +
                rr * self.SIGNAL_WEIGHTS["risk_reward"] +
                signal.get("setup_quality", 0.5) * self.SIGNAL_WEIGHTS["setup_quality"] +
                signal.get("market_environment", 0.5) * self.SIGNAL_WEIGHTS["market_environment"]
            )

            signal["ranking_score"] = round(score, 4)

        # Sort by score descending
        return sorted(signals, key=lambda x: x.get("ranking_score", 0), reverse=True)

    def _get_available_slots(self) -> int:
        """
        Get number of available slots for new trades.

        Uses SlotManager if available, otherwise uses config max_concurrent_trades.
        """
        try:
            # Get max_concurrent_trades from config (REQUIRED - no defaults for trading settings)
            if not self.config or not self.config.trading:
                raise ValueError("Config and trading settings are required")

            max_trades = self.config.trading.max_concurrent_trades
            if max_trades is None:
                raise ValueError("max_concurrent_trades must be configured in instance settings")

            # Integrate with SlotManager for real position counting
            # Use the centralized slot management system for accurate slot calculation
            try:
                # Create a temporary SlotManager instance for slot calculation
                # Need OrderExecutor for API access, not ChartSourcer
                from trading_bot.engine.order_executor import OrderExecutor
                from trading_bot.core.slot_manager import SlotManager

                # Create OrderExecutor for API access
                order_executor = OrderExecutor(testnet=self.testnet)

                slot_manager = SlotManager(
                    trader=order_executor,  # OrderExecutor has get_positions() and get_open_orders()
                    data_agent=self._db,    # Use database connection for data access
                    config=self.config,
                    paper_trading=self.paper_trading,
                    instance_id=self.instance_id
                )
                available_slots, slot_details = slot_manager.get_available_order_slots()
                logger.info(f"📊 SlotManager integration: {available_slots}/{max_trades} slots available")
                return available_slots
            except Exception as slot_error:
                logger.warning(f"SlotManager integration failed, using fallback: {slot_error}")
                # Fallback to config-based calculation if SlotManager fails
                return max_trades
        except Exception as e:
            logger.error(f"Error getting available slots: {e}")
            raise ValueError(f"Cannot determine available slots: {e}")

    async def _execute_selected_signal(
        self, signal: Dict[str, Any], cycle_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a selected signal through the trading engine.

        Args:
            signal: Ranked signal to execute
            cycle_id: Current cycle ID

        Returns:
            Trade result or None if no callback
        """
        if not self.execute_signal:
            logger.warning("No execute_signal callback configured")
            return None

        symbol = signal.get("symbol")
        recommendation = signal.get("recommendation")
        if recommendation is None:
            logger.error("Critical error: recommendation is None - cannot build signal")
            return None
        analysis = signal.get("analysis", {})

        # Build signal dict for trading engine
        trade_signal = self._build_signal(
            analysis,
            recommendation,
            signal.get("confidence", 0)
        )

        if not trade_signal:
            logger.warning(f"Could not build trade signal for {symbol}")
            return None

        logger.info(f"   🚀 Executing: {symbol} {recommendation}")

        trade_result = self.execute_signal(
            symbol=symbol,
            signal=trade_signal,
            recommendation_id=signal.get("recommendation_id"),
            cycle_id=cycle_id,  # Pass cycle_id for audit trail
        )

        if trade_result.get("status") == "rejected":
            logger.info(f"   ❌ {symbol} rejected: {trade_result.get('error')}")
        else:
            logger.info(f"   ✅ {symbol} submitted: {trade_result.get('id')}")

        return trade_result

    async def _process_captured_chart(self, symbol: str, chart_path: str, cycle_id: str) -> Optional[Dict[str, Any]]:
        """
        Process an already-captured chart: analyze and generate signal.

        Args:
            symbol: Trading symbol from watchlist
            chart_path: Path to captured chart image
            cycle_id: Current cycle ID

        Returns:
            Processing result with recommendation and trade info
        """
        normalized_symbol = normalize_symbol_for_bybit(symbol)
        logger.info(f"\n📈 Analyzing {normalized_symbol} ({self.timeframe})")

        result: Dict[str, Any] = {
            "symbol": normalized_symbol,
            "timeframe": self.timeframe,
            "cycle_id": cycle_id,
            "chart_path": chart_path,
        }

        # Analyze chart with AI
        logger.info(f"   🤖 Analyzing with AI...")
        analysis = self.analyzer.analyze_chart(
            image_path=chart_path,
            use_assistant=True,
            target_timeframe=self.timeframe,
            prompt_function=self._prompt_function,
        )

        if not analysis or analysis.get("error") or analysis.get("skipped"):
            skip_reason = analysis.get("skip_reason", "unknown") if analysis else "analysis_failed"
            logger.info(f"   ⏭️ Skipped: {skip_reason}")
            result["skipped"] = True
            result["skip_reason"] = skip_reason
            return result

        # Extract recommendation
        recommendation = analysis.get("recommendation", "hold").upper()
        confidence = float(analysis.get("confidence", 0))

        logger.info(f"   📊 Analysis: {recommendation} (confidence: {confidence:.2%})")

        result["recommendation"] = recommendation
        result["confidence"] = confidence
        result["analysis"] = analysis

        # Record recommendation
        rec_id = self._record_recommendation(result, analysis)
        result["recommendation_id"] = rec_id

        # Check if actionable signal
        if recommendation in ("BUY", "SELL", "LONG", "SHORT"):
            # Build signal for trading engine
            signal = self._build_signal(analysis, recommendation, confidence)

            if signal and self.execute_signal:
                logger.info(f"   🚀 Executing signal: {recommendation}")
                trade_result = self.execute_signal(
                    symbol=normalized_symbol,
                    signal=signal,
                    recommendation_id=rec_id,
                    cycle_id=cycle_id,  # Pass cycle_id for audit trail
                )
                result["trade_executed"] = True
                result["trade_result"] = trade_result

                if trade_result.get("status") == "rejected":
                    logger.info(f"   ❌ Trade rejected: {trade_result.get('error')}")
                else:
                    logger.info(f"   ✅ Trade submitted: {trade_result.get('id')}")
        else:
            logger.info(f"   ⏸️ Hold signal - no trade action")

        return result

    def _build_signal(self, analysis: Dict[str, Any], recommendation: str, confidence: float) -> Optional[Dict[str, Any]]:
        """Build trading signal from analysis."""
        try:
            entry = float(analysis.get("entry_price", 0))
            tp = float(analysis.get("take_profit", 0))
            sl = float(analysis.get("stop_loss", 0))

            if not all([entry, tp, sl]):
                logger.warning("   ⚠️ Missing price levels in analysis")
                return None

            return {
                "recommendation": recommendation,
                "confidence": confidence,
                "entry_price": entry,
                "take_profit": tp,
                "stop_loss": sl,
                "setup_quality": analysis.get("setup_quality", 0.5),
                "risk_reward": analysis.get("risk_reward", 0),
                "market_environment": analysis.get("market_environment", 0.5),
                "timeframe": self.timeframe,  # Include timeframe for chart display
            }
        except Exception as e:
            logger.error(f"Failed to build signal: {e}")
            return None

    def _record_recommendation(self, result: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Record recommendation to database with full audit trail for reproducibility.

        Stores everything needed to reproduce the trade decision:
        - raw_response: Full AI response text
        - market_data_snapshot: All market data fed to AI
        - analysis_prompt: The exact prompt used
        - model_name: Which model made the decision
        - prompt_version: Which prompt version was used
        """
        import json
        rec_id = str(uuid.uuid4())[:8]
        try:
            # Map recommendation to schema-compliant value
            rec_value = result.get("recommendation", "HOLD").upper()
            if rec_value in ("BUY", "LONG"):
                rec_value = "LONG"
            elif rec_value in ("SELL", "SHORT"):
                rec_value = "SHORT"
            else:
                rec_value = "HOLD"

            # Build comprehensive raw_response JSON with full audit trail
            # This contains everything needed to reproduce the trade decision
            raw_response = json.dumps({
                # The full analysis result from AI
                "analysis_result": analysis,
                # Market data that was fed to the AI for this decision
                "market_data_snapshot": analysis.get("market_data_snapshot", {}),
                # The exact prompt used
                "analysis_prompt": analysis.get("analysis_prompt", ""),
                # Raw text response from the model
                "model_raw_response": analysis.get("raw_response", ""),
                # Validation info (timestamp, boundary, etc.)
                "validation_info": analysis.get("validation", {}),
                "timestamp_extracted": analysis.get("timestamp"),
                "normalized_timeframe": analysis.get("normalized_timeframe"),
                # Decision matrix corrections if any
                "llm_original_recommendation": analysis.get("llm_original_recommendation"),
            }, default=str)

            # Get prompt info from analysis (set by analyzer)
            prompt_name = analysis.get("prompt_id", analysis.get("prompt_version", "trading_cycle"))
            prompt_version = analysis.get("prompt_version", "1.0")
            model_name = analysis.get("assistant_model", self.config.openai.model)

            # Use consistent ISO timestamp format across all tables
            now_iso = datetime.now(timezone.utc).isoformat()

            execute(self._db, """
                INSERT INTO recommendations
                (id, cycle_id, symbol, timeframe, recommendation, confidence,
                 entry_price, stop_loss, take_profit, risk_reward,
                 reasoning, chart_path, prompt_name, prompt_version, model_name,
                 raw_response, analyzed_at, cycle_boundary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec_id,
                result.get("cycle_id"),  # Link to parent cycle
                result.get("symbol"),
                result.get("timeframe"),
                rec_value,
                round(result.get("confidence", 0), 3),
                analysis.get("entry_price"),
                analysis.get("stop_loss"),
                analysis.get("take_profit"),
                analysis.get("risk_reward_ratio", analysis.get("risk_reward")),
                analysis.get("summary", ""),
                result.get("chart_path"),
                prompt_name,
                prompt_version,
                model_name,
                raw_response,
                now_iso,  # analyzed_at
                get_current_cycle_boundary(self.timeframe).isoformat(),  # cycle_boundary
                now_iso,  # created_at - explicit to match format with other tables
            ))
            logger.info(f"📝 Recorded recommendation {rec_id} with full audit trail (prompt: {prompt_name}, model: {model_name})")
        except Exception as e:
            logger.error(f"Failed to record recommendation: {e}", exc_info=True)
        return rec_id

    def _record_cycle_start(self, cycle_id: str, cycle_start: datetime) -> None:
        """Record cycle start to database (so recommendations can reference it)."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()

            execute(self._db, """
                INSERT INTO cycles
                (id, run_id, timeframe, cycle_number, boundary_time, status,
                 charts_captured, analyses_completed, recommendations_generated,
                 trades_executed, started_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle_id,
                self.run_id,  # Link to parent run
                self.timeframe,
                self._cycle_count,
                get_current_cycle_boundary(self.timeframe).isoformat(),
                "running",  # Initial status
                0,  # Will be updated later
                0,  # Will be updated later
                0,  # Will be updated later
                0,  # Will be updated later
                cycle_start.isoformat(),
                now_iso,  # created_at
            ))
        except Exception as e:
            logger.error(f"Failed to record cycle start: {e}")

    def _record_cycle(self, results: Dict[str, Any]) -> None:
        """Update cycle in database with final results."""
        try:
            # Match the actual cycles table schema
            status = "completed" if not results["errors"] else "failed"

            execute(self._db, """
                UPDATE cycles SET
                    status = ?,
                    charts_captured = ?,
                    analyses_completed = ?,
                    recommendations_generated = ?,
                    trades_executed = ?,
                    completed_at = ?
                WHERE id = ?
            """, (
                status,
                results["symbols_analyzed"],  # charts_captured
                results["symbols_analyzed"],  # analyses_completed
                len(results["recommendations"]),
                len(results["trades_executed"]),
                results.get("completed_at"),
                results["cycle_id"],
            ))

            # Update run aggregates
            if self.run_id:
                self._update_run_aggregates(results)
        except Exception as e:
            logger.error(f"Failed to record cycle: {e}")

    def _update_run_aggregates(self, results: Dict[str, Any]) -> None:
        """Update run's aggregate metrics after cycle completes."""
        try:
            execute(self._db, """
                UPDATE runs SET
                    total_cycles = total_cycles + 1,
                    total_recommendations = total_recommendations + ?,
                    total_trades = total_trades + ?
                WHERE id = ?
            """, (
                len(results["recommendations"]),
                len(results["trades_executed"]),
                self.run_id,
            ))
        except Exception as e:
            logger.error(f"Failed to update run aggregates: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get trading cycle status."""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "last_cycle": self._last_cycle_time.isoformat() if self._last_cycle_time else None,
            "symbols": "TradingView watchlist",  # Symbols come from watchlist at runtime
            "timeframe": self.timeframe,
            "next_boundary": get_current_cycle_boundary(self.timeframe).isoformat(),
            "seconds_until_next": seconds_until_next_boundary(self.timeframe),
        }

