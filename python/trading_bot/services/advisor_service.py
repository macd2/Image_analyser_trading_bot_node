import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable
import pandas as pd
import json

from trading_bot.db.client import get_connection, execute, query
from trading_bot.services.base_strategy import BaseStrategy
from trading_bot.services.alex_strategy import AlexStrategy
from trading_bot.services.market_regime_strategy import MarketRegimeStrategy

logger = logging.getLogger(__name__)

class AdvisorService:
    """
    Main advisor service that orchestrates TA-based analysis.

    Features:
    - Multiple strategy support
    - Node-based execution pipeline
    - Full traceability with database logging
    - Integration with trading cycle
    """

    # Strategy registry
    STRATEGY_REGISTRY = {
        "alex_strategy": AlexStrategy,
        "market_regime": MarketRegimeStrategy,
    }

    def __init__(self, config: Dict[str, Any], db_connection=None, instance_id: str = None):
        """
        Initialize advisor service.

        Args:
            config: Configuration dictionary
            db_connection: Database connection (optional)
            instance_id: Instance ID for database operations
        """
        self.config = config
        self.instance_id = instance_id
        self.db = db_connection or get_connection()

        # Load strategies
        self.strategies: Dict[str, BaseStrategy] = {}
        self.nodes: List[Dict[str, Any]] = []

        # Traceability
        self.trace_log: List[Dict[str, Any]] = []

        # Initialize from database if instance_id provided
        if instance_id:
            self._load_from_database()

    def _load_from_database(self) -> None:
        """Load advisor configuration from database."""
        try:
            # Load instance advisor settings
            settings = query(self.db, """
                SELECT strategy_id, config, enabled
                FROM advisor_instance_settings
                WHERE instance_id = ?
            """, (self.instance_id,))

            if settings:
                setting = settings[0]
                if setting['enabled'] and setting['strategy_id']:
                    self._load_strategy(setting['strategy_id'], setting['config'])

            # Load advisor nodes
            nodes = query(self.db, """
                SELECT id, strategy_id, config, enabled, execution_order
                FROM advisor_nodes
                WHERE instance_id = ?
                ORDER BY execution_order
            """, (self.instance_id,))

            for node in nodes:
                if node['enabled']:
                    self._load_node(node)

        except Exception as e:
            logger.error(f"Failed to load advisor configuration from database: {e}")

    def _load_strategy(self, strategy_id: str, config: Dict[str, Any]) -> None:
        """Load a strategy by ID."""
        try:
            # Get strategy definition from database
            strategy_def = query(self.db, """
                SELECT name, config_schema
                FROM advisor_strategies
                WHERE id = ?
            """, (strategy_id,))

            if not strategy_def:
                logger.error(f"Strategy {strategy_id} not found in database")
                return

            strategy_name = strategy_def[0]['name']

            if strategy_name in self.STRATEGY_REGISTRY:
                strategy_class = self.STRATEGY_REGISTRY[strategy_name]
                self.strategies[strategy_id] = strategy_class(config)
                logger.info(f"Loaded strategy: {strategy_name}")
            else:
                logger.error(f"Strategy {strategy_name} not in registry")

        except Exception as e:
            logger.error(f"Failed to load strategy {strategy_id}: {e}")

    def _load_node(self, node_data: Dict[str, Any]) -> None:
        """Load an advisor node."""
        self.nodes.append({
            "id": node_data['id'],
            "strategy_id": node_data['strategy_id'],
            "config": node_data['config'],
            "execution_order": node_data['execution_order']
        })

    async def analyze_market_data(self, symbol: str, timeframe: str, candle_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Run advisor analysis on candle data.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe of the data
            candle_data: DataFrame with OHLCV data

        Returns:
            Dictionary with TA analysis results
        """
        analysis_id = str(uuid.uuid4())[:8]
        analysis_start = datetime.now(timezone.utc)

        result = {
            "analysis_id": analysis_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "strategies_applied": [],
            "signals": [],
            "confidence": 0.0,
            "recommendation": "HOLD",
            "reasoning": "",
            "trace_log": [],
            "errors": []
        }

        try:
            # Run through all enabled nodes in order
            for node in sorted(self.nodes, key=lambda x: x.get('execution_order', 0)):
                node_result = await self._execute_node(node, symbol, timeframe, candle_data)

                if node_result:
                    result["strategies_applied"].append(node["strategy_id"])
                    result["trace_log"].append(node_result.get("trace", {}))

                    # Aggregate signals
                    if "signals" in node_result:
                        result["signals"].extend(node_result["signals"])

                    # Update confidence (weighted average)
                    node_confidence = node_result.get("confidence", 0)
                    result["confidence"] = (result["confidence"] + node_confidence) / 2

                    # Update recommendation if stronger signal
                    node_recommendation = node_result.get("recommendation", "HOLD")
                    if node_recommendation != "HOLD" and node_confidence > result["confidence"]:
                        result["recommendation"] = node_recommendation
                        result["reasoning"] = node_result.get("reasoning", "")

            # Log to database for traceability
            self._log_analysis(result, analysis_start)

        except Exception as e:
            error_msg = f"Advisor analysis failed: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        return result

    async def _execute_node(self, node: Dict[str, Any], symbol: str, timeframe: str,
                          candle_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Execute a single advisor node."""
        strategy_id = node["strategy_id"]

        if strategy_id not in self.strategies:
            logger.warning(f"Strategy {strategy_id} not loaded for node {node['id']}")
            return None

        strategy = self.strategies[strategy_id]
        node_start = datetime.now(timezone.utc)

        try:
            # Execute strategy analysis
            analysis_result = await strategy.analyze(candle_data, symbol, timeframe)

            # Add trace information
            analysis_result["trace"] = {
                "node_id": node["id"],
                "strategy_id": strategy_id,
                "execution_time_ms": (datetime.now(timezone.utc) - node_start).total_seconds() * 1000,
                "timestamp": node_start.isoformat()
            }

            # Log node execution
            self._log_node_execution(node, analysis_result, node_start)

            return analysis_result

        except Exception as e:
            logger.error(f"Node {node['id']} execution failed: {e}")
            return None

    async def enhance_prompt(self, market_data: Dict[str, Any], base_prompt: str) -> str:
        """
        Inject TA context into prompt before sending to AI assistant.

        Args:
            market_data: Market data dictionary
            base_prompt: Original prompt

        Returns:
            Enhanced prompt with TA context
        """
        try:
            # Extract symbol and timeframe from market data
            symbol = market_data.get("symbol", "UNKNOWN")
            timeframe = market_data.get("timeframe", "1h")

            # Get candle data (this would need to be fetched from database/API)
            # For now, we'll add placeholder TA context
            ta_context = self._generate_ta_context(market_data)

            # Enhance prompt with TA context
            enhanced_prompt = f"""{base_prompt}

TECHNICAL ANALYSIS CONTEXT:
{ta_context}

Consider this technical analysis context in your recommendation.
"""

            # Log prompt enhancement
            self._log_operation("enhance_prompt", {
                "symbol": symbol,
                "timeframe": timeframe,
                "ta_context": ta_context
            })

            return enhanced_prompt

        except Exception as e:
            logger.error(f"Prompt enhancement failed: {e}")
            return base_prompt

    async def enhance_recommendation(self, ai_recommendation: Dict[str, Any],
                                   ta_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add TA confirmation to AI recommendation.

        Args:
            ai_recommendation: AI-generated recommendation
            ta_analysis: TA analysis results

        Returns:
            Enhanced recommendation with TA confirmation
        """
        enhanced = ai_recommendation.copy()

        # Add TA confirmation flag
        ta_signals = ta_analysis.get("signals", [])
        ta_confidence = ta_analysis.get("confidence", 0)
        ta_recommendation = ta_analysis.get("recommendation", "HOLD")

        # Check if TA confirms AI recommendation
        ai_rec = ai_recommendation.get("recommendation", "HOLD").upper()
        ta_confirms = (ta_recommendation == ai_rec) and ta_confidence > 0.6

        enhanced["ta_confirmation"] = {
            "confirmed": ta_confirms,
            "confidence": ta_confidence,
            "recommendation": ta_recommendation,
            "signals": ta_signals,
            "strategies_applied": ta_analysis.get("strategies_applied", [])
        }

        # Adjust overall confidence based on TA confirmation
        ai_confidence = ai_recommendation.get("confidence", 0.5)
        if ta_confirms:
            # Boost confidence if TA confirms
            enhanced["confidence"] = min(1.0, ai_confidence * 1.2)
            enhanced["reasoning"] = f"{ai_recommendation.get('reasoning', '')} [TA Confirmed]"
        else:
            # Reduce confidence if TA disagrees
            enhanced["confidence"] = max(0.1, ai_confidence * 0.8)
            enhanced["reasoning"] = f"{ai_recommendation.get('reasoning', '')} [TA Disagrees: {ta_recommendation}]"

        # Log enhancement
        self._log_operation("enhance_recommendation", {
            "ai_recommendation": ai_rec,
            "ta_recommendation": ta_recommendation,
            "ta_confirms": ta_confirms,
            "confidence_adjustment": enhanced["confidence"] - ai_confidence
        })

        return enhanced

    def _generate_ta_context(self, market_data: Dict[str, Any]) -> str:
        """Generate TA context string from market data."""
        # This is a placeholder - in real implementation, this would
        # analyze actual candle data and generate meaningful TA context
        symbol = market_data.get("symbol", "UNKNOWN")
        timeframe = market_data.get("timeframe", "1h")
        last_price = market_data.get("last_price", 0)

        return f"""
Symbol: {symbol}
Timeframe: {timeframe}
Last Price: {last_price}

Technical Analysis Indicators:
- RSI: Neutral
- MACD: Bullish crossover
- Bollinger Bands: Price near upper band
- Volume: Above average
- Trend: Bullish on higher timeframes
"""

    def _log_analysis(self, analysis_result: Dict[str, Any], start_time: datetime) -> None:
        """Log analysis to database for traceability."""
        try:
            analysis_id = analysis_result["analysis_id"]
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            execute(self.db, """
                INSERT INTO advisor_logs
                (id, instance_id, operation, input_data, output_data, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                analysis_id,
                self.instance_id,
                "full_analysis",
                json.dumps({
                    "symbol": analysis_result["symbol"],
                    "timeframe": analysis_result["timeframe"],
                    "strategies_count": len(analysis_result["strategies_applied"])
                }),
                json.dumps({
                    "recommendation": analysis_result["recommendation"],
                    "confidence": analysis_result["confidence"],
                    "signals_count": len(analysis_result["signals"]),
                    "strategies_applied": analysis_result["strategies_applied"]
                }),
                duration_ms,
                datetime.now(timezone.utc).isoformat()
            ))

        except Exception as e:
            logger.error(f"Failed to log analysis: {e}")

    def _log_node_execution(self, node: Dict[str, Any], result: Dict[str, Any], start_time: datetime) -> None:
        """Log node execution to database."""
        try:
            log_id = str(uuid.uuid4())[:8]
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            execute(self.db, """
                INSERT INTO advisor_logs
                (id, instance_id, node_id, operation, input_data, output_data, duration_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                log_id,
                self.instance_id,
                node["id"],
                "node_execution",
                json.dumps({
                    "node_id": node["id"],
                    "strategy_id": node["strategy_id"],
                    "config": node["config"]
                }),
                json.dumps({
                    "recommendation": result.get("recommendation", "HOLD"),
                    "confidence": result.get("confidence", 0),
                    "signals": result.get("signals", [])
                }),
                duration_ms,
                datetime.now(timezone.utc).isoformat()
            ))

        except Exception as e:
            logger.error(f"Failed to log node execution: {e}")

    def _log_operation(self, operation: str, data: Dict[str, Any]) -> None:
        """Log an operation to trace log."""
        self.trace_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "data": data
        })

    def get_trace_log(self) -> List[Dict[str, Any]]:
        """Get traceable log of all operations."""
        return self.trace_log.copy()

    def register_strategy(self, name: str, strategy_class: type) -> None:
        """Register a new strategy class."""
        if issubclass(strategy_class, BaseStrategy):
            self.STRATEGY_REGISTRY[name] = strategy_class
            logger.info(f"Registered strategy: {name}")
        else:
            raise ValueError(f"Strategy class must inherit from BaseStrategy")

    async def close(self):
        """Clean up resources."""
        if self.db:
            self.db.close()