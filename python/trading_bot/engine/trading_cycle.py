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
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable, List, Tuple

from trading_bot.config.settings_v2 import Config
from trading_bot.core.bybit_api_manager import BybitAPIManager
from trading_bot.core.error_logger import set_cycle_id, clear_cycle_id
from trading_bot.core.utils import (  # type: ignore
    get_current_cycle_boundary,  # type: ignore
    seconds_until_next_boundary,  # type: ignore
)
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.db.client import get_connection, release_connection, execute, query
from trading_bot.services.sl_adjuster import StopLossAdjuster

logger = logging.getLogger(__name__)


def convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy types to native Python types for JSON serialization.

    Handles:
    - numpy scalars (np.float64, np.int64, etc.) -> float/int
    - numpy arrays -> list
    - dicts -> recursively convert values
    - lists -> recursively convert items
    """
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.floating, np.integer)):
            return obj.item()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, dict):
            return {k: convert_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [convert_numpy_types(item) for item in obj]
        else:
            return obj
    except ImportError:
        # numpy not available, return as-is
        return obj


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
        heartbeat_callback: Optional[Callable] = None,
    ):
        """
        Initialize trading cycle.

        Args:
            config: Configuration object
            execute_signal_callback: Callback to execute signals (from TradingEngine)
            testnet: Use testnet if True
            run_id: Parent run UUID for audit trail
            prompt_name: Name of the prompt function to use for analysis (deprecated - use database config)
            paper_trading: Whether in paper trading mode (for database-based position checks)
            instance_id: Instance ID for filtering database queries in paper trading mode
            heartbeat_callback: Callback to update heartbeat after each step
        """
        self.config = config or Config.load()
        self.testnet = testnet
        self.execute_signal = execute_signal_callback
        self.run_id = run_id  # Track parent run for audit trail
        self.prompt_name = prompt_name  # Instance-level prompt selection (deprecated)
        self.paper_trading = paper_trading
        self.instance_id = instance_id
        self.heartbeat_callback = heartbeat_callback  # Callback to update heartbeat

        # API manager for market data
        self.api_manager = BybitAPIManager(self.config, use_testnet=testnet)  # type: ignore[arg-type]

        # Initialize strategy using factory (loads strategy from database config)
        self.strategy = StrategyFactory.create(
            instance_id=instance_id or "default",
            config=self.config,
            run_id=run_id,
            heartbeat_callback=heartbeat_callback,
        )

        # SL Adjuster for pre-execution adjustments
        self.sl_adjuster = StopLossAdjuster()

        # Cycle state
        self._running = False
        self._cycle_count = 0
        self._last_cycle_time: Optional[datetime] = None

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
        # Request stop from strategy to halt long-running analysis
        if self.strategy:
            self.strategy.request_stop()
        logger.info("Trading cycle stopped")

    def _get_existing_recommendations_for_boundary(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get existing recommendations for symbols in the current cycle boundary.
        Filters by instance_id to ensure each instance only sees its own recommendations.

        Args:
            symbols: List of symbols to check

        Returns:
            Dict mapping symbol -> recommendation_data (empty dict if no recommendation exists)
        """
        # If no symbols provided, return empty dict
        if not symbols:
            return {}

        conn = None
        try:
            conn = get_connection()
            current_boundary = get_current_cycle_boundary(self.timeframe)
            boundary_iso = current_boundary.isoformat()

            # Query for recommendations matching current boundary
            # Filter by instance_id if available to ensure instance-specific tracking
            if self.instance_id:
                # Get cycle_id for this instance's current boundary
                cycles = query(conn, """
                    SELECT id FROM cycles
                    WHERE boundary_time = ? AND run_id IN (
                        SELECT id FROM runs WHERE instance_id = ?
                    )
                """, (boundary_iso, self.instance_id))

                if not cycles:
                    # No cycles for this instance at this boundary yet
                    return {symbol: {} for symbol in symbols}

                cycle_ids = [c['id'] for c in cycles]
                placeholders = ','.join(['?' for _ in cycle_ids])

                existing_recs = query(conn, f"""
                    SELECT * FROM recommendations
                    WHERE cycle_id IN ({placeholders}) AND symbol IN ({','.join(['?' for _ in symbols])})
                """, (*cycle_ids, *symbols))
            else:
                # No instance filtering - check all recommendations for boundary
                # If no symbols, return empty dict
                if not symbols:
                    return {}

                existing_recs = query(conn, """
                    SELECT * FROM recommendations
                    WHERE cycle_boundary = ? AND symbol IN ({})
                """.format(','.join(['?' for _ in symbols])),
                (boundary_iso, *symbols))

            # Build result dict: symbol -> recommendation data
            result = {symbol: {} for symbol in symbols}
            for rec in existing_recs:
                symbol = rec['symbol']
                result[symbol] = dict(rec)  # Convert UnifiedRow to dict

            existing_symbols = [s for s in symbols if result[s]]
            if existing_symbols:
                instance_label = f" (instance: {self.instance_id})" if self.instance_id else ""
                logger.info(f"   ✅ Found existing recommendations for boundary {boundary_iso}{instance_label}: {', '.join(sorted(existing_symbols))}")

            return result

        except Exception as e:
            logger.warning(f"Failed to check existing recommendations: {e}")
            # On error, assume no existing recommendations (proceed with analysis)
            return {symbol: {} for symbol in symbols}
        finally:
            if conn:
                release_connection(conn)

    def _print_cycle_summary(self, results: Dict[str, Any], cycle_id: str, cycle_start: datetime, chart_paths: Dict[str, str]) -> None:
        """
        Print detailed cycle summary with all step information.

        Args:
            results: Cycle results dictionary
            cycle_id: Cycle ID
            cycle_start: Cycle start time
            chart_paths: Dictionary of captured chart paths
        """
        cycle_end = datetime.now(timezone.utc)
        total_duration = (cycle_end - cycle_start).total_seconds()
        boundary = get_current_cycle_boundary(self.timeframe)
        boundary_end = boundary + timedelta(hours=int(self.timeframe.rstrip('h')))

        # Determine LIVE or DRYRUN
        mode = "DRYRUN" if self.paper_trading else "LIVE"

        # Build recommendations summary by type
        buy_signals = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "BUY"]
        sell_signals = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "SELL"]
        hold_signals = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "HOLD"]

        # Print main cycle header
        logger.info(f"[CYCLE_SUMMARY] 📊 CYCLE #{self._cycle_count} COMPLETE - {self.timeframe} - [{cycle_id}] - {mode}")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Timeframe: {self.timeframe}")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Boundary: {boundary.strftime('%Y-%m-%d %H:%M:%S')} UTC to {boundary_end.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Prompt: {self.prompt_name}")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Model: gpt-4-vision")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Instance: {self.instance_id or 'default'}")
        logger.info(f"[CYCLE_SUMMARY]    ├─ Total duration: {total_duration:.1f}s")

        # Symbols analyzed
        logger.info(f"[CYCLE_SUMMARY]    ├─ Symbols analyzed: {results['symbols_analyzed']}")
        if results['symbols_analyzed'] > 0 and chart_paths:
            symbols_list = ', '.join(sorted(chart_paths.keys()))
            logger.info(f"[CYCLE_SUMMARY]    │  ├─ {symbols_list}")

        # Recommendations generated
        logger.info(f"[CYCLE_SUMMARY]    ├─ Recommendations generated: {len(results['recommendations'])}")
        if results['recommendations']:
            logger.info(f"[CYCLE_SUMMARY]    │  ├─ BUY: {len(buy_signals)} ({', '.join([r['symbol'] for r in buy_signals[:5]])}{'...' if len(buy_signals) > 5 else ''})")
            logger.info(f"[CYCLE_SUMMARY]    │  ├─ SELL: {len(sell_signals)} ({', '.join([r['symbol'] for r in sell_signals[:5]])}{'...' if len(sell_signals) > 5 else ''})")
            logger.info(f"[CYCLE_SUMMARY]    │  └─ HOLD: {len(hold_signals)} ({', '.join([r['symbol'] for r in hold_signals[:5]])}{'...' if len(hold_signals) > 5 else ''})")

        # Actionable signals
        logger.info(f"[CYCLE_SUMMARY]    ├─ Actionable signals: {len(results['actionable_signals'])}")
        if results['actionable_signals']:
            for sig in results['actionable_signals'][:6]:
                entry = sig.get('entry_price', 'N/A')
                sl = sig.get('stop_loss', 'N/A')
                tp = sig.get('take_profit', 'N/A')
                logger.info(f"[CYCLE_SUMMARY]    │  ├─ {sig['symbol']}: {sig.get('recommendation', 'N/A')} @ {entry} (SL: {sl}, TP: {tp})")

        # Selected for execution
        logger.info(f"[CYCLE_SUMMARY]    ├─ Selected for execution: {len(results['selected_signals'])}")
        if results['selected_signals']:
            for sig in results['selected_signals']:
                entry = sig.get('entry_price', 'N/A')
                sl = sig.get('stop_loss', 'N/A')
                tp = sig.get('take_profit', 'N/A')
                logger.info(f"[CYCLE_SUMMARY]    │  ├─ {sig['symbol']}: {sig.get('recommendation', 'N/A')} @ {entry} (SL: {sl}, TP: {tp})")

        # Trades executed
        executed_trades = [t for t in results['trades_executed'] if t.get('status') != 'rejected']
        rejected_trades = [t for t in results['trades_executed'] if t.get('status') == 'rejected']

        logger.info(f"[CYCLE_SUMMARY]    ├─ Trades executed: {len(executed_trades)}")
        if executed_trades:
            for trade in executed_trades:
                order_id = trade.get('id', 'N/A')
                side = trade.get('side', 'N/A')
                entry = trade.get('entry_price', 'N/A')
                sl = trade.get('stop_loss', 'N/A')
                tp = trade.get('take_profit', 'N/A')
                logger.info(f"[CYCLE_SUMMARY]    │  ├─ {trade.get('symbol', 'N/A')}: {side} @ {entry} (SL: {sl}, TP: {tp}) (Order ID: {order_id}) ✅")

        # Rejected trades
        logger.info(f"[CYCLE_SUMMARY]    ├─ Rejected trades: {len(rejected_trades)}")
        if rejected_trades:
            for trade in rejected_trades:
                error = trade.get('error', 'Unknown reason')
                logger.info(f"[CYCLE_SUMMARY]    │  ├─ {trade.get('symbol', 'N/A')}: {error}")

        # Errors
        logger.info(f"[CYCLE_SUMMARY]    ├─ Errors: {len(results['errors'])}")
        if results['errors']:
            for error in results['errors'][:3]:
                if isinstance(error, dict):
                    if 'symbol' in error:
                        logger.info(f"[CYCLE_SUMMARY]    │  ├─ {error.get('symbol', 'N/A')}: {error.get('error', 'Unknown error')}")
                    else:
                        logger.info(f"[CYCLE_SUMMARY]    │  ├─ {error.get('error', 'Unknown error')}")
                else:
                    logger.info(f"[CYCLE_SUMMARY]    │  ├─ {str(error)}")

        # Determine overall status
        status = "✅ Success" if len(results['errors']) == 0 else "⚠️ Completed with errors"
        logger.info(f"[CYCLE_SUMMARY]    └─ Status: {status}")



    def _print_step_2_summary(self, analyzed_count: int, successful_count: int, failed_count: int, duration: float, analysis_results: List[Dict[str, Any]]) -> None:
        """Print summary for STEP 2: Parallel Analysis"""
        logger.info(f"[STEP_2_SUMMARY] 🤖 STEP 2 COMPLETE: Parallel Analysis")
        logger.info(f"[STEP_2_SUMMARY]    ├─ Analyzed: {analyzed_count} charts")
        logger.info(f"[STEP_2_SUMMARY]    ├─ Successful: {successful_count}")
        logger.info(f"[STEP_2_SUMMARY]    ├─ Failed: {failed_count}")
        logger.info(f"[STEP_2_SUMMARY]    ├─ Analysis results:")

        # Show top 5 results
        for result in analysis_results[:5]:
            if not result.get("error"):
                rec = result.get("recommendation", "N/A")
                conf = result.get("confidence", 0)
                rr = result.get("risk_reward", 0)
                logger.info(f"[STEP_2_SUMMARY]    │  ├─ {result['symbol']}: {rec} (conf: {conf:.2f}, RR: {rr:.2f})")

        if len(analysis_results) > 5:
            logger.info(f"[STEP_2_SUMMARY]    │  └─ ... ({len(analysis_results) - 5} more)")

        logger.info(f"[STEP_2_SUMMARY]    ├─ Duration: {duration:.1f}s")
        logger.info(f"[STEP_2_SUMMARY]    └─ Status: ✅ Success")

    def _print_step_3_summary(self, total_recommendations: int, actionable_count: int, buy_count: int, sell_count: int, hold_count: int) -> None:
        """Print summary for STEP 3: Collect Recommendations"""
        logger.info(f"[STEP_3_SUMMARY] 📊 STEP 3 COMPLETE: Collecting Recommendations")
        logger.info(f"[STEP_3_SUMMARY]    ├─ Total recommendations: {total_recommendations}")
        logger.info(f"[STEP_3_SUMMARY]    ├─ Actionable signals: {actionable_count}")
        logger.info(f"[STEP_3_SUMMARY]    │  ├─ BUY: {buy_count}")
        logger.info(f"[STEP_3_SUMMARY]    │  ├─ SELL: {sell_count}")
        logger.info(f"[STEP_3_SUMMARY]    │  └─ HOLD: {hold_count}")
        logger.info(f"[STEP_3_SUMMARY]    └─ Status: ✅ Success")

    def _print_step_4_summary(self, ranked_signals: List[Dict[str, Any]]) -> None:
        """Print summary for STEP 4: Rank Signals"""
        logger.info(f"[STEP_4_SUMMARY] 🏆 STEP 4 COMPLETE: Ranking Signals by Quality")
        logger.info(f"[STEP_4_SUMMARY]    ├─ Total signals ranked: {len(ranked_signals)}")
        logger.info(f"[STEP_4_SUMMARY]    ├─ Top ranked signals:")

        for i, sig in enumerate(ranked_signals[:5]):
            logger.info(f"[STEP_4_SUMMARY]    │  ├─ #{i+1}: {sig['symbol']} (score: {sig['ranking_score']:.3f}, conf: {sig['confidence']:.2f}, RR: {sig.get('risk_reward', 0):.2f})")

        if len(ranked_signals) > 5:
            logger.info(f"[STEP_4_SUMMARY]    │  └─ ... ({len(ranked_signals) - 5} more)")

        logger.info(f"[STEP_4_SUMMARY]    └─ Status: ✅ Success")

    def _print_step_5_summary(self, available_slots: int, max_trades: int) -> None:
        """Print summary for STEP 5: Check Available Slots"""
        logger.info(f"[STEP_5_SUMMARY] 📦 STEP 5 COMPLETE: Checking Available Slots")
        logger.info(f"[STEP_5_SUMMARY]    ├─ Available slots: {available_slots}/{max_trades}")
        logger.info(f"[STEP_5_SUMMARY]    └─ Status: ✅ Success")

    def _print_step_6_summary(self, selected_signals: List[Dict[str, Any]], available_slots: int) -> None:
        """Print summary for STEP 6: Select Best Signals"""
        logger.info(f"[STEP_6_SUMMARY] 🎯 STEP 6 COMPLETE: Selecting Best Signals")
        logger.info(f"[STEP_6_SUMMARY]    ├─ Selected: {len(selected_signals)} signals")
        logger.info(f"[STEP_6_SUMMARY]    ├─ Available slots: {available_slots}")
        logger.info(f"[STEP_6_SUMMARY]    ├─ Selected signals:")

        for sig in selected_signals:
            entry = sig.get('entry_price', 'N/A')
            sl = sig.get('stop_loss', 'N/A')
            tp = sig.get('take_profit', 'N/A')
            logger.info(f"[STEP_6_SUMMARY]    │  ├─ {sig['symbol']}: {sig.get('recommendation', 'N/A')} @ {entry} (SL: {sl}, TP: {tp})")

        logger.info(f"[STEP_6_SUMMARY]    └─ Status: ✅ Success")

    def _print_step_7_summary(self, trades_executed: List[Dict[str, Any]], selected_count: int) -> None:
        """Print summary for STEP 7: Execute Signals"""
        successful_trades = [t for t in trades_executed if t.get('status') != 'rejected']
        rejected_trades = [t for t in trades_executed if t.get('status') == 'rejected']

        logger.info(f"[STEP_7_SUMMARY] 🚀 STEP 7 COMPLETE: Executing Signals")
        logger.info(f"[STEP_7_SUMMARY]    ├─ Selected for execution: {selected_count}")
        logger.info(f"[STEP_7_SUMMARY]    ├─ Trades executed: {len(successful_trades)}")

        if successful_trades:
            for trade in successful_trades:
                order_id = trade.get('id', 'N/A')
                side = trade.get('side', 'N/A')
                entry = trade.get('entry_price', 'N/A')
                logger.info(f"[STEP_7_SUMMARY]    │  ├─ {trade.get('symbol', 'N/A')}: {side} @ {entry} (Order ID: {order_id}) ✅")

        logger.info(f"[STEP_7_SUMMARY]    ├─ Rejected trades: {len(rejected_trades)}")
        if rejected_trades:
            for trade in rejected_trades:
                error = trade.get('error', 'Unknown reason')
                logger.info(f"[STEP_7_SUMMARY]    │  ├─ {trade.get('symbol', 'N/A')}: {error}")

        logger.info(f"[STEP_7_SUMMARY]    └─ Status: ✅ Success")

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
            # STEP 0-2: Run strategy analysis cycle (handles chart capture, cleaning, and analysis)
            logger.info(f"\n🤖 STEP 0-2: Running strategy analysis cycle...")
            analysis_start = datetime.now(timezone.utc)

            # Get all symbols from watchlist (strategy will capture charts for these)
            # For now, we get symbols from config - strategy will handle chart capture
            try:
                # Run strategy analysis cycle (handles steps 0-2 internally)
                newly_analyzed = await self.strategy.run_analysis_cycle(
                    symbols=[],  # Strategy uses watchlist symbols internally
                    timeframe=self.timeframe,
                    cycle_id=cycle_id,
                )

                # Extract chart_paths from results for logging purposes
                chart_paths = {r.get("symbol"): r.get("chart_path") for r in newly_analyzed if r.get("chart_path")}

            except Exception as e:
                logger.error(f"Strategy analysis cycle failed: {e}", extra={
                    'event': 'strategy_cycle_failed',
                    'cycle_id': cycle_id,
                }, exc_info=True)
                results["errors"].append({"error": f"Strategy analysis failed: {str(e)}"})
                return results

            analysis_duration = (datetime.now(timezone.utc) - analysis_start).total_seconds()

            # Count successful and failed analyses
            successful_analyses = [a for a in newly_analyzed if not a.get("error")]
            failed_analyses = [a for a in newly_analyzed if a.get("error")]
            self._print_step_2_summary(len(newly_analyzed), len(successful_analyses), len(failed_analyses), analysis_duration, successful_analyses)
            if self.heartbeat_callback:
                self.heartbeat_callback()

            # STEP 3: Collect all recommendations (both newly analyzed and existing)
            logger.info(f"\n📊 STEP 3: Collecting recommendations...")
            actionable_signals: List[Dict[str, Any]] = []

            # Get symbols that were analyzed
            analyzed_symbols = [r.get("symbol") for r in newly_analyzed if r.get("symbol")]

            # Check for existing recommendations for symbols not analyzed
            existing_recs_map = self._get_existing_recommendations_for_boundary(analyzed_symbols)
            symbols_with_existing_recs = [s for s in analyzed_symbols if existing_recs_map.get(s)]

            # Combine newly analyzed results with existing recommendations
            all_analyses = newly_analyzed if newly_analyzed else []

            # Process newly analyzed results
            for analysis_result in all_analyses:
                if analysis_result.get("error"):
                    results["errors"].append({
                        "symbol": analysis_result.get("symbol"),
                        "error": analysis_result.get("error")
                    })
                    continue

                if analysis_result.get("recommendation"):
                    # Record recommendation to database
                    # Ensure analysis is a dict (sometimes it might be a string)
                    analysis_data = analysis_result.get("analysis", {})
                    if isinstance(analysis_data, str):
                        try:
                            analysis_data = json.loads(analysis_data)
                        except (json.JSONDecodeError, TypeError):
                            analysis_data = {}

                    rec_id = self._record_recommendation(analysis_result, analysis_data)
                    if rec_id:
                        analysis_result["recommendation_id"] = rec_id

                    results["recommendations"].append(analysis_result)

                    # Collect actionable signals (BUY/SELL/LONG/SHORT)
                    rec = analysis_result.get("recommendation", "").upper()
                    if rec in ("BUY", "SELL", "LONG", "SHORT"):
                        actionable_signals.append(analysis_result)

            # Add existing recommendations to results (so they're available for processing)
            for symbol in symbols_with_existing_recs:
                rec_data = existing_recs_map[symbol]
                if rec_data:
                    # Parse raw_response to extract market_data_snapshot and other analysis data
                    market_data_snapshot = {}
                    analysis_data = {}
                    raw_response_str = rec_data.get("raw_response", "{}")

                    if raw_response_str:
                        try:
                            if isinstance(raw_response_str, str):
                                analysis_data = json.loads(raw_response_str)
                            else:
                                analysis_data = raw_response_str

                            # Extract market_data_snapshot from the parsed JSON
                            market_data_snapshot = analysis_data.get("market_data_snapshot", {})
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.warning(f"Could not parse raw_response for {symbol}: {e}")
                            market_data_snapshot = {}

                    # Convert database record to analysis result format
                    rec_result = {
                        "symbol": symbol,
                        "recommendation": rec_data.get("recommendation", "HOLD"),
                        "confidence": rec_data.get("confidence", 0),
                        "entry_price": rec_data.get("entry_price"),
                        "stop_loss": rec_data.get("stop_loss"),
                        "take_profit": rec_data.get("take_profit"),
                        "risk_reward": rec_data.get("risk_reward"),
                        "reasoning": rec_data.get("reasoning", ""),
                        "chart_path": rec_data.get("chart_path"),
                        "timeframe": rec_data.get("timeframe"),
                        "cycle_id": cycle_id,
                        "recommendation_id": rec_data.get("id"),  # Already has ID from DB
                        "from_existing": True,  # Mark as existing recommendation
                        "market_data_snapshot": market_data_snapshot,  # Include for price sanity check
                        "raw_response": analysis_data,  # Include full analysis data
                    }
                    results["recommendations"].append(rec_result)

                    # Collect actionable signals from existing recs too
                    rec = rec_data.get("recommendation", "HOLD").upper()
                    if rec in ("BUY", "SELL", "LONG", "SHORT"):
                        actionable_signals.append(rec_result)

            # symbols_analyzed = ALL symbols with recommendations for current boundary
            # (both newly analyzed + existing from previous analysis in same boundary)
            # This is instance-specific - each instance tracks its own boundary analysis
            results["symbols_analyzed"] = len(analyzed_symbols)

            results["actionable_signals"] = actionable_signals

            # Count recommendations by type
            buy_recs = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "BUY"]
            sell_recs = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "SELL"]
            hold_recs = [r for r in results["recommendations"] if r.get("recommendation", "").upper() == "HOLD"]

            self._print_step_3_summary(len(results["recommendations"]), len(actionable_signals), len(buy_recs), len(sell_recs), len(hold_recs))
            if self.heartbeat_callback:
                self.heartbeat_callback()

            # STEP 4: Rank signals by quality
            logger.info(f"\n🏆 STEP 4: Ranking {len(actionable_signals)} signals by quality...")
            ranked_signals = self._rank_signals_by_quality(actionable_signals)
            results["ranked_signals"] = ranked_signals

            self._print_step_4_summary(ranked_signals)
            if self.heartbeat_callback:
                self.heartbeat_callback()

            # STEP 5: Check available slots
            logger.info(f"\n📦 STEP 5: Checking available slots...")
            available_slots = self._get_available_slots()
            max_trades = self.config.trading.max_concurrent_trades if self.config and self.config.trading else 0
            self._print_step_5_summary(available_slots, max_trades)
            if self.heartbeat_callback:
                self.heartbeat_callback()

            # STEP 6: Select best signals for available slots
            logger.info(f"\n🎯 STEP 6: Selecting best {available_slots} signal(s)...")
            selected_signals = ranked_signals[:available_slots] if available_slots > 0 else []
            results["selected_signals"] = selected_signals

            self._print_step_6_summary(selected_signals, available_slots)
            if self.heartbeat_callback:
                self.heartbeat_callback()

            # STEP 7: Execute selected signals
            logger.info(f"\n🚀 STEP 7: Executing {len(selected_signals)} selected signal(s)...")
            for signal in selected_signals:
                trade_result = await self._execute_selected_signal(signal, cycle_id)
                if trade_result:
                    results["trades_executed"].append(trade_result)

            self._print_step_7_summary(results["trades_executed"], len(selected_signals))
            if self.heartbeat_callback:
                self.heartbeat_callback()

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

        # Print detailed cycle summary
        self._print_cycle_summary(results, cycle_id, cycle_start, chart_paths)

        return results



    def _rank_signals_by_quality(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank actionable signals by quality score.

        Scoring formula:
        score = (confidence * 0.4) + (risk_reward_normalized * 0.3) +
                (setup_quality * 0.2) + (market_environment * 0.1)

        Args:
            signals: List of actionable signals

        Returns:
            Signals sorted by ranking_score (highest first) with ranking context stored
        """
        total_signals_analyzed = len(signals)

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
        ranked_signals = sorted(signals, key=lambda x: x.get("ranking_score", 0), reverse=True)

        # Add ranking context to each signal for complete traceability
        for ranking_position, signal in enumerate(ranked_signals, 1):
            signal["ranking_context"] = {
                "ranking_score": signal.get("ranking_score", 0),
                "ranking_position": ranking_position,
                "total_signals_analyzed": total_signals_analyzed,
                "total_signals_ranked": len(ranked_signals),
                "ranking_weights": self.SIGNAL_WEIGHTS,
            }

        return ranked_signals

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
                    data_agent=None,        # SlotManager gets its own connections
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

        symbol = signal.get("symbol", "UNKNOWN")
        recommendation = signal.get("recommendation")
        if recommendation is None:
            logger.error("Critical error: recommendation is None - cannot build signal")
            return None
        analysis = signal.get("analysis", {})

        # Build signal dict for trading engine
        trade_signal = self._build_signal(
            analysis,
            recommendation,
            signal.get("confidence", 0),
            symbol
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

    def _build_signal(self, analysis: Dict[str, Any], recommendation: str, confidence: float, symbol: str = "UNKNOWN") -> Optional[Dict[str, Any]]:
        """Build trading signal from analysis with price sanity check."""
        try:
            # Extract price levels - check if they exist and are non-zero
            entry_raw = analysis.get("entry_price")
            tp_raw = analysis.get("take_profit")
            sl_raw = analysis.get("stop_loss")

            # Convert to float, handling None and empty values
            try:
                entry = float(entry_raw) if entry_raw is not None else 0.0
                tp = float(tp_raw) if tp_raw is not None else 0.0
                sl = float(sl_raw) if sl_raw is not None else 0.0
            except (ValueError, TypeError):
                logger.warning("   ⚠️ Invalid price level format in analysis")
                return None

            # Check if all price levels are present and non-zero
            if entry <= 0 or tp <= 0 or sl <= 0:
                logger.warning(f"   ⚠️ Missing price levels in analysis for {symbol}")
                logger.debug(f"      entry_price={entry}, take_profit={tp}, stop_loss={sl}")
                return None

            # PRICE SANITY CHECK: Verify AI-extracted price is reasonable
            # Compare entry_price from AI with last_price from market data
            market_data = analysis.get("market_data_snapshot", {})
            last_price_raw = market_data.get("last_price")

            if last_price_raw and last_price_raw != 'N/A':
                try:
                    market_price = float(last_price_raw)
                    if market_price > 0:
                        # Calculate deviation percentage
                        deviation = abs(entry - market_price) / market_price * 100

                        # Allow up to 20% deviation (configurable threshold)
                        # This accounts for limit orders slightly away from current price
                        MAX_PRICE_DEVIATION_PERCENT = 20.0

                        if deviation > MAX_PRICE_DEVIATION_PERCENT:
                            symbol = analysis.get("symbol", "UNKNOWN")
                            logger.error(f"   ❌ PRICE SANITY CHECK FAILED for {symbol}!")
                            logger.error(f"      AI Entry: ${entry:.6f}")
                            logger.error(f"      Market Price: ${market_price:.6f}")
                            logger.error(f"      Deviation: {deviation:.1f}% (max allowed: {MAX_PRICE_DEVIATION_PERCENT}%)")
                            logger.error(f"      🚫 Signal REJECTED to prevent wrong chart price being used")
                            return None
                        else:
                            logger.info(f"   ✅ Price sanity check passed (deviation: {deviation:.2f}%)")
                except (ValueError, TypeError) as e:
                    logger.warning(f"   ⚠️ Could not validate price sanity: {e}")
                    # Continue anyway - better to trade than miss opportunity due to parse error

            # Extract strategy information for traceability
            # First check if strategy info is already in the analysis (from strategy output)
            strategy_uuid = analysis.get("strategy_uuid")
            strategy_type = analysis.get("strategy_type")
            strategy_name = analysis.get("strategy_name")

            # Fallback to self.strategy if not in analysis
            if not strategy_uuid and hasattr(self, 'strategy') and self.strategy:
                strategy_uuid = getattr(self.strategy, 'strategy_uuid', None)
            if not strategy_type and hasattr(self, 'strategy') and self.strategy:
                strategy_type = getattr(self.strategy, 'STRATEGY_TYPE', None)
            if not strategy_name and hasattr(self, 'strategy') and self.strategy:
                strategy_name = getattr(self.strategy, 'STRATEGY_NAME', None)

            return {
                "recommendation": recommendation,
                "confidence": confidence,
                "entry_price": entry,
                "take_profit": tp,
                "stop_loss": sl,
                "setup_quality": analysis.get("setup_quality", 0.5),
                "position_size_multiplier": analysis.get("position_size_multiplier", 1.0),
                "risk_reward": analysis.get("risk_reward", 0),
                "market_environment": analysis.get("market_environment", 0.5),
                "timeframe": self.timeframe,  # Include timeframe for chart display
                # Strategy tracking for traceability
                "strategy_uuid": strategy_uuid,
                "strategy_type": strategy_type,
                "strategy_name": strategy_name,
                "strategy_metadata": analysis.get("strategy_metadata"),  # For exit logic and monitoring
            }
        except Exception as e:
            logger.error(f"Failed to build signal: {e}")
            return None

    def _record_recommendation(self, result: Dict[str, Any], analysis: Dict[str, Any]) -> Optional[str]:
        """Record recommendation to database with full audit trail for reproducibility.

        Stores everything needed to reproduce the trade decision:
        - raw_response: Full AI response text
        - market_data_snapshot: All market data fed to AI
        - analysis_prompt: The exact prompt used
        - model_name: Which model made the decision
        - prompt_version: Which prompt version was used

        For existing recommendations (from previous analysis in same boundary),
        returns the existing recommendation_id without re-recording.

        Returns:
            recommendation_id if successful, None if failed
        """
        import json

        # Ensure analysis is a dict (defensive check)
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except (json.JSONDecodeError, TypeError):
                analysis = {}
        elif not isinstance(analysis, dict):
            analysis = {}

        # If this is an existing recommendation from previous analysis, return its ID
        if result.get("from_existing") and result.get("recommendation_id"):
            logger.info(f"   ℹ️  Using existing recommendation ID: {result.get('recommendation_id')}")
            return result.get("recommendation_id")

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

            conn = None
            try:
                conn = get_connection()

                # Capture reproducibility data if strategy is available
                reproducibility_data = {}
                if hasattr(self, 'strategy') and self.strategy:
                    try:
                        reproducibility_data = self.strategy.capture_reproducibility_data(
                            analysis_result=analysis,
                            chart_path=result.get("chart_path"),
                            market_data=analysis.get("market_data_snapshot", {}),
                            model_version=model_name,
                            model_params=analysis.get("model_params", {}),
                            prompt_version=prompt_version,
                            prompt_content=analysis.get("analysis_prompt", ""),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to capture reproducibility data: {e}")

                # Prepare reproducibility columns - convert numpy types before JSON serialization
                chart_hash = reproducibility_data.get('chart_hash')
                model_version = reproducibility_data.get('model_version')
                model_params = json.dumps(convert_numpy_types(reproducibility_data.get('model_params', {})))
                market_data_snapshot = json.dumps(convert_numpy_types(reproducibility_data.get('market_data_snapshot', {})))
                strategy_config_snapshot = json.dumps(convert_numpy_types(reproducibility_data.get('strategy_config_snapshot', {})))
                confidence_components = json.dumps(convert_numpy_types(reproducibility_data.get('confidence_components', {})))
                setup_quality_components = json.dumps(convert_numpy_types(reproducibility_data.get('setup_quality_components', {})))
                market_environment_components = json.dumps(convert_numpy_types(reproducibility_data.get('market_environment_components', {})))
                validation_results = json.dumps(convert_numpy_types(reproducibility_data.get('validation_results', {})))

                # Extract strategy metadata for exit logic and monitoring - convert numpy types
                strategy_metadata = result.get("strategy_metadata")
                strategy_metadata_json = None
                if strategy_metadata:
                    strategy_metadata_json = json.dumps(convert_numpy_types(strategy_metadata))

                execute(conn, """
                    INSERT INTO recommendations
                    (id, cycle_id, symbol, timeframe, recommendation, confidence,
                     entry_price, stop_loss, take_profit, risk_reward,
                     reasoning, chart_path, prompt_name, prompt_version, model_name,
                     raw_response, analyzed_at, cycle_boundary, created_at,
                     chart_hash, model_version, model_params, market_data_snapshot,
                     strategy_config_snapshot, confidence_components, setup_quality_components,
                     market_environment_components, validation_results, strategy_metadata,
                     strategy_uuid, strategy_type, strategy_name, setup_quality, market_environment)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rec_id,
                    result.get("cycle_id"),  # Link to parent cycle
                    result.get("symbol"),
                    result.get("timeframe"),
                    rec_value,
                    float(round(convert_numpy_types(result.get("confidence", 0)), 3)),
                    float(convert_numpy_types(analysis.get("entry_price"))) if analysis.get("entry_price") is not None else None,
                    float(convert_numpy_types(analysis.get("stop_loss"))) if analysis.get("stop_loss") is not None else None,
                    float(convert_numpy_types(analysis.get("take_profit"))) if analysis.get("take_profit") is not None else None,
                    float(convert_numpy_types(analysis.get("risk_reward_ratio", analysis.get("risk_reward")))) if analysis.get("risk_reward_ratio", analysis.get("risk_reward")) is not None else None,
                    analysis.get("summary", ""),
                    result.get("chart_path"),
                    prompt_name,
                    prompt_version,
                    model_name,
                    raw_response,
                    now_iso,  # analyzed_at
                    get_current_cycle_boundary(self.timeframe).isoformat(),  # cycle_boundary
                    now_iso,  # created_at - explicit to match format with other tables
                    # Reproducibility columns
                    chart_hash,
                    model_version,
                    model_params,
                    market_data_snapshot,
                    strategy_config_snapshot,
                    confidence_components,
                    setup_quality_components,
                    market_environment_components,
                    validation_results,
                    strategy_metadata_json,
                    # Strategy tracking and traceability
                    result.get("strategy_uuid"),
                    result.get("strategy_type"),
                    result.get("strategy_name"),
                    float(convert_numpy_types(result.get("setup_quality", 0.5))) if result.get("setup_quality") is not None else None,
                    float(convert_numpy_types(result.get("market_environment", 0.5))) if result.get("market_environment") is not None else None,
                ))
                logger.info(f"📝 Recorded recommendation {rec_id} with full audit trail (prompt: {prompt_name}, model: {model_name})")
                return rec_id
            finally:
                if conn:
                    release_connection(conn)
        except Exception as e:
            # Log detailed error information for debugging
            logger.error(f"Failed to record recommendation {rec_id}: {type(e).__name__}: {e}")
            logger.error(f"   Symbol: {result.get('symbol')}, Cycle: {result.get('cycle_id')}")

            # Check if it's a connection error that might be retryable
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ['connection', 'closed', 'timeout', 'pool']):
                logger.error(f"   Connection error detected - this is retryable")

            # Return None to indicate failure - caller should handle this
            return None

    def _record_cycle_start(self, cycle_id: str, cycle_start: datetime) -> None:
        """Record cycle start to database (so recommendations can reference it)."""
        conn = None
        try:
            conn = get_connection()
            now_iso = datetime.now(timezone.utc).isoformat()

            execute(conn, """
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
        finally:
            if conn:
                release_connection(conn)

    def _record_cycle(self, results: Dict[str, Any]) -> None:
        """Update cycle in database with final results."""
        conn = None
        try:
            conn = get_connection()
            # Match the actual cycles table schema
            status = "completed" if not results["errors"] else "failed"

            execute(conn, """
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
                self._update_run_aggregates(results, conn)
        except Exception as e:
            logger.error(f"Failed to record cycle: {e}")
        finally:
            if conn:
                release_connection(conn)

    def _update_run_aggregates(self, results: Dict[str, Any], conn=None) -> None:
        """Update run's aggregate metrics after cycle completes."""
        should_release = False
        try:
            if conn is None:
                conn = get_connection()
                should_release = True

            execute(conn, """
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
        finally:
            if should_release and conn:
                release_connection(conn)

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

