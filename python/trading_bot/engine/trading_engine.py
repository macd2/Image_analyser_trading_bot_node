"""
Trading Engine - Clean, efficient trading cycle with WebSocket state.
Main orchestrator for chart capture, analysis, and trade execution.
"""

import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from trading_bot.config.settings_v2 import ConfigV2
from trading_bot.core.state_manager import StateManager
from trading_bot.core.websocket_manager import BybitWebSocketManager
from trading_bot.core.shared_websocket_manager import SharedWebSocketManager
from trading_bot.engine.order_executor import OrderExecutor
from trading_bot.engine.position_sizer import PositionSizer
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode
from trading_bot.db.client import get_connection, execute, release_connection, query

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Clean trading engine with WebSocket-based state management.
    
    Features:
    - Real-time state from WebSocket (no polling)
    - Cycle-based trading workflow
    - Full audit trail in database
    - Slot-based position management
    """
    
    def __init__(
        self,
        config: Optional[ConfigV2] = None,
        testnet: bool = False,
        paper_trading: bool = True,
        run_id: Optional[str] = None,
        instance_id: Optional[str] = None,
    ):
        """
        Initialize trading engine.

        Args:
            config: Configuration object (loads from DB if None)
            testnet: Use testnet if True
            paper_trading: Paper trading mode if True
            run_id: Parent run ID for audit trail
            instance_id: Instance ID to load config from (required if config is None)
        """
        if config:
            self.config = config
        elif instance_id:
            self.config = ConfigV2.from_instance(instance_id)
        else:
            raise ValueError("Either config or instance_id must be provided")
        self.testnet = testnet
        self.paper_trading = paper_trading
        self.run_id = run_id  # Track parent run for audit trail
        self.instance_id = instance_id  # Store instance_id for StateManager

        # Database connection (needed before StateManager)
        self._db = get_connection()

        # Core components
        # StateManager now supports paper trading mode (uses database instead of WebSocket)
        self.state_manager = StateManager(
            db_connection=self._db,
            paper_trading=self.paper_trading,
            instance_id=self.instance_id
        )
        self.order_executor = OrderExecutor(testnet=testnet)
        self.position_sizer = PositionSizer(
            order_executor=self.order_executor,
            risk_percentage=self.config.trading.risk_percentage,
            min_position_value=self.config.trading.min_position_value_usd,
            max_loss_usd=self.config.trading.max_loss_usd,
            confidence_weighting=self.config.trading.use_enhanced_position_sizing,
            use_kelly_criterion=self.config.trading.use_kelly_criterion,
            kelly_fraction=self.config.trading.kelly_fraction,
            kelly_window=self.config.trading.kelly_window,
        )

        # Position monitor for tracking orders and exits (including spread-based)
        self.position_monitor = EnhancedPositionMonitor(
            order_executor=self.order_executor,
            mode=MonitorMode.EVENT_DRIVEN if not paper_trading else MonitorMode.POLLING,
            poll_interval=5.0,
            master_tightening_enabled=self.config.trading.enable_tightening,
            tightening_enabled=self.config.trading.enable_tightening,
            db_connection=self._db,
        )

        # WebSocket manager (shared singleton for multi-instance support)
        self.ws_manager: Optional[SharedWebSocketManager] = None

        # Register execution callback for real-time fill notifications
        # This enables WebSocket-based fill tracking instead of polling
        self.state_manager.set_on_fill(
            lambda exec_record: self.position_monitor.on_execution_update(
                exec_record, self.instance_id or "default", self.run_id or ""
            )
        )

        # Engine state
        self._running = False
        self._stop_event = threading.Event()
        self._cycle_count = 0

        # Callbacks
        self._on_cycle_complete: Optional[Callable] = None
        self._on_trade_executed: Optional[Callable] = None
    
    def start(self) -> bool:
        """
        Start the trading engine.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Engine already running")
            return True
        
        logger.info("=" * 60)
        logger.info("🚀 STARTING TRADING ENGINE")
        logger.info(f"   Instance: {self.instance_id}")
        logger.info(f"   Mode: {'PAPER' if self.paper_trading else 'LIVE'}")
        logger.info(f"   Network: {'TESTNET' if self.testnet else 'MAINNET'}")
        logger.info("=" * 60)

        # MULTI-INSTANCE: Use shared WebSocket manager (singleton)
        # Multiple instances share the same WebSocket connection
        self.ws_manager = SharedWebSocketManager(testnet=self.testnet)

        # Subscribe this instance to WebSocket messages
        # StateManager will filter messages based on order_link_id prefix
        self.ws_manager.subscribe(
            subscriber_id=self.instance_id or "default",
            on_order=self.state_manager.handle_order_message,
            on_position=self.state_manager.handle_position_message,
            on_execution=self.state_manager.handle_execution_message,
            on_wallet=self.state_manager.handle_wallet_message,
        )

        # Connect WebSocket (if not already connected by another instance)
        if not self.ws_manager.connect():
            logger.error("Failed to connect shared WebSocket")
            return False

        self._running = True
        self._stop_event.clear()

        logger.info(f"✅ Trading engine started (subscribers: {self.ws_manager.get_subscriber_count()})")
        return True
    
    def stop(self) -> None:
        """Stop the trading engine."""
        logger.info(f"Stopping trading engine (instance: {self.instance_id})...")

        self._running = False
        self._stop_event.set()

        # MULTI-INSTANCE: Unsubscribe from shared WebSocket
        # WebSocket will only disconnect if no subscribers remain
        if self.ws_manager:
            self.ws_manager.unsubscribe(self.instance_id or "default")
            # Don't call disconnect() - let the shared manager handle it
            self.ws_manager = None

        # Release database connection back to pool (PostgreSQL) or close (SQLite)
        if self._db:
            release_connection(self._db)
            self._db = None

        logger.info("Trading engine stopped")
    
    def _on_ws_connect(self) -> None:
        """Handle WebSocket connection."""
        logger.info("📡 WebSocket connected - receiving real-time updates")
    
    def _on_ws_disconnect(self) -> None:
        """Handle WebSocket disconnection."""
        logger.warning("📡 WebSocket disconnected")

    def _get_closed_trades_for_kelly(self) -> List[Dict[str, Any]]:
        """
        Get closed trades for Kelly Criterion calculation.
        Returns trades with pnl_percent field for Kelly analysis.

        CRITICAL: Uses fresh connection to avoid stale connection errors.
        """
        conn = None
        try:
            # Get fresh connection for this operation
            conn = get_connection()

            # Query closed trades with PnL data
            # Join through runs table to filter by instance_id (trades table doesn't have instance_id)
            rows = query(
                conn,
                """
                SELECT t.pnl_percent FROM trades t
                JOIN cycles c ON t.cycle_id = c.id
                JOIN runs r ON c.run_id = r.id
                WHERE r.instance_id = ?
                AND t.status IN ('closed', 'filled')
                AND t.pnl_percent IS NOT NULL
                ORDER BY t.closed_at DESC
                LIMIT 100
                """,
                (self.instance_id,)
            )

            # Convert to list of dicts with pnl_percent
            trades = [{"pnl_percent": float(row.get("pnl_percent", 0))} for row in rows]
            return trades
        except Exception as e:
            logger.warning(f"Failed to fetch closed trades for Kelly: {e}")
            return []
        finally:
            if conn:
                release_connection(conn)

    def can_open_trade(self, symbol: str) -> Dict[str, Any]:
        """
        Check if a new trade can be opened for symbol.
        
        Returns:
            Dict with can_trade, reason, and slot info
        """
        max_slots = self.config.trading.max_concurrent_trades
        
        # Check if symbol already has position
        if self.state_manager.has_position(symbol):
            return {
                "can_trade": False,
                "reason": f"Position already exists for {symbol}",
            }
        
        # Check if symbol has pending order
        if self.state_manager.has_open_order(symbol):
            return {
                "can_trade": False,
                "reason": f"Pending order exists for {symbol}",
            }
        
        # Check slot availability
        available = self.state_manager.get_available_slots(max_slots)
        if available <= 0:
            return {
                "can_trade": False,
                "reason": f"No slots available (max: {max_slots})",
                "slots_used": self.state_manager.count_slots_used(),
            }
        
        return {
            "can_trade": True,
            "reason": "Slot available",
            "slots_available": available,
            "slots_used": self.state_manager.count_slots_used(),
        }

    def _insert_rejected_trade(
        self,
        trade_id: str,
        symbol: str,
        signal: Dict[str, Any],
        rejection_reason: str,
        recommendation_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        rr_ratio: Optional[float] = None,
    ) -> None:
        """Insert a rejected trade into the database for audit trail.

        CRITICAL: Uses fresh connection to avoid stale connection errors.
        """
        conn = None
        try:
            # Get fresh connection for this operation
            conn = get_connection()

            # Determine side from recommendation
            recommendation = signal.get("recommendation", "").upper()
            side = "Buy" if recommendation in ("BUY", "LONG") else "Sell"

            # Use provided rr_ratio or try to get from signal, default to 0
            final_rr_ratio = rr_ratio if rr_ratio is not None else signal.get("rr_ratio", 0)

            # Extract strategy information from signal for traceability
            strategy_uuid = signal.get("strategy_uuid")
            strategy_type = signal.get("strategy_type")
            strategy_name = signal.get("strategy_name")

            execute(conn, """
                INSERT INTO trades (
                    id, recommendation_id, run_id, cycle_id, symbol, side,
                    entry_price, quantity, stop_loss, take_profit,
                    status, rejection_reason, dry_run, confidence, rr_ratio,
                    timeframe, prompt_name, created_at,
                    strategy_uuid, strategy_type, strategy_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?)
            """, (
                trade_id,
                recommendation_id,
                self.run_id,
                cycle_id,
                symbol,
                side,
                signal.get("entry_price", 0),
                0,  # quantity = 0 for rejected trades
                signal.get("stop_loss", 0),
                signal.get("take_profit", 0),
                "rejected",
                rejection_reason,
                self.paper_trading,  # Pass boolean directly
                signal.get("confidence", 0),
                final_rr_ratio,
                signal.get("timeframe"),
                signal.get("prompt_name"),
                timestamp.isoformat() if timestamp else datetime.now(timezone.utc).isoformat(),
                strategy_uuid,
                strategy_type,
                strategy_name,
            ))

            logger.debug(f"Inserted rejected trade {trade_id} for {symbol}: {rejection_reason}")
        except Exception as e:
            logger.error(f"Failed to insert rejected trade {trade_id}: {e}")
        finally:
            if conn:
                release_connection(conn)

    def execute_signal(
        self,
        symbol: str,
        signal: Dict[str, Any],
        recommendation_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
        strategy: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a trading signal.

        Args:
            symbol: Trading symbol
            signal: Signal dict with recommendation, entry, tp, sl, confidence
            recommendation_id: ID of the recommendation that generated this signal
            cycle_id: ID of the cycle that generated this signal
            strategy: Strategy instance for strategy-specific validation (optional)

        Returns:
            Execution result dict
        """
        # MULTI-INSTANCE: Generate trade_id with instance_id prefix for WebSocket filtering
        # Format: {instance_id}_{uuid} so StateManager can identify ownership
        trade_uuid = str(uuid.uuid4())[:8]
        trade_id = f"{self.instance_id}_{trade_uuid}" if self.instance_id else trade_uuid
        timestamp = datetime.now(timezone.utc)

        # Validate signal
        recommendation = signal.get("recommendation", "").upper()
        if recommendation not in ("BUY", "SELL", "LONG", "SHORT"):
            rejection_reason = f"Invalid recommendation: {recommendation}"
            self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
            return {
                "id": trade_id,
                "status": "rejected",
                "error": rejection_reason,
                "timestamp": timestamp,
            }

        # Check if we can trade
        slot_check = self.can_open_trade(symbol)
        if not slot_check["can_trade"]:
            rejection_reason = slot_check["reason"]
            self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
            return {
                "id": trade_id,
                "status": "rejected",
                "error": rejection_reason,
                "timestamp": timestamp,
            }

        # Validate confidence
        confidence = signal.get("confidence", 0)
        min_confidence = self.config.trading.min_confidence_threshold
        if confidence < min_confidence:
            rejection_reason = f"Confidence {confidence:.2f} below threshold {min_confidence}"
            self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
            return {
                "id": trade_id,
                "status": "rejected",
                "error": rejection_reason,
                "timestamp": timestamp,
            }

        # Validate signal using strategy-specific validation if strategy provided
        if strategy:
            validation_result = strategy.validate_signal(signal)
            if not validation_result.get("valid", False):
                rejection_reason = validation_result.get("error", "Signal validation failed")
                self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
                return {
                    "id": trade_id,
                    "status": "rejected",
                    "error": rejection_reason,
                    "timestamp": timestamp,
                }
        else:
            # Fallback to basic validation if no strategy provided
            entry = signal.get("entry_price", 0)
            tp = signal.get("take_profit", 0)
            sl = signal.get("stop_loss", 0)

            if not all([entry, tp, sl]):
                rejection_reason = "Missing entry, TP, or SL price"
                self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
                return {
                    "id": trade_id,
                    "status": "rejected",
                    "error": rejection_reason,
                    "timestamp": timestamp,
                }

        # Paper trading mode
        if self.paper_trading:
            return self._execute_paper_trade(
                trade_id, symbol, signal, recommendation_id, cycle_id, timestamp, strategy
            )

        # Live trading
        return self._execute_live_trade(
            trade_id, symbol, signal, recommendation_id, cycle_id, timestamp, strategy
        )

    def _execute_paper_trade(
        self,
        trade_id: str,
        symbol: str,
        signal: Dict[str, Any],
        recommendation_id: Optional[str],
        cycle_id: Optional[str],
        timestamp: datetime,
        strategy: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute paper trade (simulation)."""
        side = "Buy" if signal["recommendation"].upper() in ("BUY", "LONG") else "Sell"

        # Check if this is a spread-based strategy with pre-calculated position sizes
        is_spread_based = signal.get("strategy_type") == "spread_based" and signal.get("units_x") is not None

        if is_spread_based:
            # Use strategy-provided quantities for spread-based trades
            qty = abs(signal.get("units_x", 0))
            pair_qty = abs(signal.get("units_y", 0))
            sizing = {
                "position_size": qty,
                "pair_position_size": pair_qty,
                "sizing_method": "spread_based_dynamic",
                "risk_pct_used": 0.02,  # Placeholder
                "risk_amount": 0,  # Will be calculated from spread risk
                "kelly_metrics": None,
            }
        else:
            # Use PositionSizer for price-based strategies
            wallet = self.order_executor.get_wallet_balance()
            balance = wallet.get("available", 10000)  # Default for paper

            # Get trade history for Kelly Criterion if enabled
            trade_history = None
            if self.config.trading.use_kelly_criterion:
                trade_history = self._get_closed_trades_for_kelly()

            sizing = self.position_sizer.calculate_position_size(
                symbol=symbol,
                entry_price=signal["entry_price"],
                stop_loss=signal["stop_loss"],
                wallet_balance=balance,
                confidence=signal.get("confidence", 0.75),
                trade_history=trade_history,
                strategy=strategy,
            )

            if "error" in sizing:
                return {
                    "id": trade_id,
                    "status": "rejected",
                    "error": sizing["error"],
                    "timestamp": timestamp,
                }

            pair_qty = None

        # Calculate RR ratio for logging
        entry = signal.get("entry_price", 0)
        tp = signal.get("take_profit", 0)
        sl = signal.get("stop_loss", 0)
        is_long = signal["recommendation"].upper() in ("BUY", "LONG")
        risk = abs(sl - entry)
        reward = abs(tp - entry) if is_long else abs(entry - tp)
        rr_ratio = reward / risk if risk > 0 else 0

        # Record paper trade
        trade = {
            "id": trade_id,
            "run_id": self.run_id,
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "qty": sizing["position_size"],
            "pair_qty": pair_qty,  # For spread-based trades
            "entry_price": signal["entry_price"],
            "take_profit": signal["take_profit"],
            "stop_loss": signal["stop_loss"],
            "rr_ratio": rr_ratio,
            "confidence": signal.get("confidence"),
            "timeframe": signal.get("timeframe"),  # Store timeframe for chart display
            "status": "paper_trade",
            "recommendation_id": recommendation_id,
            "timestamp": timestamp,
            # Strategy tracking and traceability
            "strategy_uuid": signal.get("strategy_uuid"),
            "strategy_type": signal.get("strategy_type"),
            "strategy_name": signal.get("strategy_name"),
            "ranking_context": signal.get("ranking_context"),
            "strategy_metadata": signal.get("strategy_metadata"),  # For exit logic and monitoring
            "wallet_balance_at_trade": wallet.get("available") if not is_spread_based else None,
            "kelly_metrics": sizing.get("kelly_metrics"),  # From position sizer
        }

        self._record_trade(trade, sizing, strategy)

        # Log detailed position sizing info for audit trail
        sizing_details = (
            f"📝 PAPER TRADE: {symbol} {side} {sizing['position_size']} "
            f"@ {signal['entry_price']} (RR: {rr_ratio:.2f}) | "
            f"Sizing: {sizing['sizing_method'].upper()} | "
            f"Risk: {sizing['risk_pct_used']:.2%} | "
            f"Risk Amount: ${sizing['risk_amount']:.2f} | "
            f"Confidence: {signal.get('confidence', 0.75):.2f}"
        )
        logger.info(sizing_details)

        return trade

    def _execute_live_trade(
        self,
        trade_id: str,
        symbol: str,
        signal: Dict[str, Any],
        recommendation_id: Optional[str],
        cycle_id: Optional[str],
        timestamp: datetime,
        strategy: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute live trade on exchange."""
        side = "Buy" if signal["recommendation"].upper() in ("BUY", "LONG") else "Sell"

        # Get wallet balance
        wallet = self.order_executor.get_wallet_balance()
        if "error" in wallet:
            rejection_reason = f"Failed to get balance: {wallet['error']}"
            self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
            return {
                "id": trade_id,
                "status": "rejected",
                "error": rejection_reason,
                "timestamp": timestamp,
            }

        # Check if this is a spread-based strategy with pre-calculated position sizes
        is_spread_based = signal.get("strategy_type") == "spread_based" and signal.get("units_x") is not None

        if is_spread_based:
            # Use strategy-provided quantities for spread-based trades
            qty = abs(signal.get("units_x", 0))
            pair_qty = abs(signal.get("units_y", 0))
            sizing = {
                "position_size": qty,
                "pair_position_size": pair_qty,
                "sizing_method": "spread_based_dynamic",
                "risk_pct_used": 0.02,  # Placeholder
                "risk_amount": 0,  # Will be calculated from spread risk
                "kelly_metrics": None,
            }
        else:
            # Use PositionSizer for price-based strategies
            # Get trade history for Kelly Criterion if enabled
            trade_history = None
            if self.config.trading.use_kelly_criterion:
                trade_history = self._get_closed_trades_for_kelly()

            sizing = self.position_sizer.calculate_position_size(
                symbol=symbol,
                entry_price=signal["entry_price"],
                stop_loss=signal["stop_loss"],
                wallet_balance=wallet["available"],
                confidence=signal.get("confidence", 0.75),
                trade_history=trade_history,
                strategy=strategy,
                position_size_multiplier=signal.get("position_size_multiplier", 1.0),
            )

            if "error" in sizing:
                rejection_reason = sizing["error"]
                self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp)
                return {
                    "id": trade_id,
                    "status": "rejected",
                    "error": rejection_reason,
                    "timestamp": timestamp,
                }

            pair_qty = None

        # Set leverage
        leverage = self.config.trading.leverage

        if is_spread_based:
            # For spread-based trades, set leverage for both symbols
            pair_symbol = signal.get("pair_symbol")
            self.order_executor.set_leverage(symbol, leverage)
            if pair_symbol:
                self.order_executor.set_leverage(pair_symbol, leverage)

            # Place coordinated orders for both symbols
            result = self.order_executor.place_spread_based_orders(
                symbol_x=symbol,
                symbol_y=pair_symbol,
                qty_x=signal.get("units_x", 0),
                qty_y=signal.get("units_y", 0),
                price_x=signal["entry_price"],
                price_y=signal.get("pair_entry_price", signal["entry_price"]),  # Fallback to main entry price
                order_link_id=trade_id,
            )

            # Register spread-based orders with position monitor for tracking
            if "error" not in result:
                self.position_monitor.on_spread_based_orders_placed(
                    instance_id=self.instance_id,
                    run_id=self.run_id,
                    trade_id=trade_id,
                    symbol_x=symbol,
                    symbol_y=pair_symbol,
                    order_id_x=result.get("order_id_x"),
                    order_id_y=result.get("order_id_y"),
                    qty_x=signal.get("units_x", 0),
                    qty_y=signal.get("units_y", 0),
                    price_x=signal["entry_price"],
                    price_y=signal.get("pair_entry_price", signal["entry_price"]),
                    strategy_metadata=signal.get("strategy_metadata"),
                )
        else:
            # For price-based trades, set leverage for main symbol only
            self.order_executor.set_leverage(symbol, leverage)

            # Place single order
            result = self.order_executor.place_limit_order(
                symbol=symbol,
                side=side,
                qty=sizing["position_size"],
                price=signal["entry_price"],
                take_profit=signal["take_profit"],
                stop_loss=signal["stop_loss"],
                order_link_id=trade_id,
            )

        if "error" in result:
            trade = {
                "id": trade_id,
                "run_id": self.run_id,
                "cycle_id": cycle_id,
                "symbol": symbol,
                "status": "failed",
                "error": result["error"],
                "timestamp": timestamp,
            }
            self._record_trade(trade)
            return trade

        # Record successful trade
        trade = {
            "id": trade_id,
            "run_id": self.run_id,
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "qty": sizing["position_size"],
            "pair_qty": pair_qty,  # For spread-based trades
            "entry_price": signal["entry_price"],
            "take_profit": signal["take_profit"],
            "stop_loss": signal["stop_loss"],
            "rr_ratio": rr_ratio,
            "confidence": signal.get("confidence"),
            "timeframe": signal.get("timeframe"),  # Store timeframe for chart display
            "order_id": result.get("order_id") or result.get("order_id_x"),  # Handle both single and spread orders
            "order_id_pair": result.get("order_id_y"),  # For spread-based trades
            "status": "submitted",
            "recommendation_id": recommendation_id,
            "timestamp": timestamp,
            # Strategy tracking and traceability
            "strategy_uuid": signal.get("strategy_uuid"),
            "strategy_type": signal.get("strategy_type"),
            "strategy_name": signal.get("strategy_name"),
            "ranking_context": signal.get("ranking_context"),
            "strategy_metadata": signal.get("strategy_metadata"),  # For exit logic and monitoring
            "wallet_balance_at_trade": wallet.get("available") if not is_spread_based else None,
            "kelly_metrics": sizing.get("kelly_metrics"),  # From position sizer
        }

        self._record_trade(trade, sizing, strategy)

        # Log detailed position sizing info for audit trail
        sizing_details = (
            f"🚀 LIVE TRADE: {symbol} {side} {sizing['position_size']} "
            f"@ {signal['entry_price']} (Order: {result.get('order_id')}) | "
            f"Sizing: {sizing['sizing_method'].upper()} | "
            f"Risk: {sizing['risk_pct_used']:.2%} | "
            f"Risk Amount: ${sizing['risk_amount']:.2f} | "
            f"Confidence: {signal.get('confidence', 0.75):.2f}"
        )
        logger.info(sizing_details)

        return trade

    def _record_trade(self, trade: Dict[str, Any], sizing: Optional[Dict[str, Any]] = None, strategy: Optional[Any] = None) -> None:
        """Record trade to database with position sizing metrics and strategy tracking.

        CRITICAL: Uses fresh connection for each trade to avoid stale connection errors.
        The engine's self._db connection may be closed by the database server, so we
        get a new connection for each trade recording operation.
        """
        conn = None
        try:
            # Get fresh connection for this operation
            conn = get_connection()

            # Get timeframe from trade or fallback to recommendation
            timeframe = trade.get("timeframe")
            if not timeframe and trade.get("recommendation_id"):
                try:
                    rec_result = query(conn, """
                        SELECT timeframe FROM recommendations WHERE id = ?
                    """, (trade.get("recommendation_id"),))
                    if rec_result:
                        timeframe = rec_result[0].get("timeframe")
                except Exception as e:
                    logger.debug(f"Could not fetch timeframe from recommendation: {e}")

            # Extract position sizing metrics from sizing dict
            position_size_usd = sizing.get("position_value") if sizing else None
            risk_amount_usd = sizing.get("risk_amount") if sizing else None
            risk_percentage = sizing.get("risk_percentage") if sizing else None
            confidence_weight = sizing.get("confidence_weight") if sizing else None
            risk_per_unit = sizing.get("risk_per_unit") if sizing else None
            sizing_method = sizing.get("sizing_method") if sizing else None
            risk_pct_used = sizing.get("risk_pct_used") if sizing else None

            # Extract strategy tracking and traceability data
            strategy_uuid = trade.get("strategy_uuid")
            strategy_type = trade.get("strategy_type")
            strategy_name = trade.get("strategy_name")
            ranking_context = trade.get("ranking_context")  # Can be dict or JSON string
            strategy_metadata = trade.get("strategy_metadata")  # JSON dict for exit logic
            wallet_balance_at_trade = trade.get("wallet_balance_at_trade")
            kelly_metrics = trade.get("kelly_metrics")  # Can be dict or JSON string

            # Capture position sizing reproducibility data
            position_sizing_inputs = None
            position_sizing_outputs = None
            order_parameters = None
            execution_timestamp = trade.get("timestamp")

            if sizing:
                import json
                position_sizing_inputs = json.dumps({
                    "entry_price": sizing.get("entry_price"),
                    "stop_loss": sizing.get("stop_loss"),
                    "wallet_balance": sizing.get("wallet_balance"),
                    "confidence": sizing.get("confidence"),
                    "risk_percentage": sizing.get("risk_percentage"),
                    "kelly_fraction": sizing.get("kelly_fraction"),
                })
                position_sizing_outputs = json.dumps({
                    "position_size": sizing.get("position_size"),
                    "position_value": sizing.get("position_value"),
                    "risk_amount": sizing.get("risk_amount"),
                    "sizing_method": sizing.get("sizing_method"),
                    "risk_pct_used": sizing.get("risk_pct_used"),
                })

            # Capture order parameters for reproducibility
            order_parameters = json.dumps({
                "symbol": trade.get("symbol"),
                "side": trade.get("side"),
                "entry_price": trade.get("entry_price"),
                "take_profit": trade.get("take_profit"),
                "stop_loss": trade.get("stop_loss"),
                "quantity": trade.get("qty"),
                "order_id": trade.get("order_id"),
            })

            # Convert dicts to JSON strings for database storage
            import json

            # Convert strategy_metadata dict to JSON string if present
            strategy_metadata_json = None
            if strategy_metadata:
                if isinstance(strategy_metadata, dict):
                    strategy_metadata_json = json.dumps(strategy_metadata)
                else:
                    strategy_metadata_json = strategy_metadata

            # Convert ranking_context dict to JSON string if present
            ranking_context_json = None
            if ranking_context:
                if isinstance(ranking_context, dict):
                    ranking_context_json = json.dumps(ranking_context)
                else:
                    ranking_context_json = ranking_context

            # Convert kelly_metrics dict to JSON string if present
            kelly_metrics_json = None
            if kelly_metrics:
                if isinstance(kelly_metrics, dict):
                    kelly_metrics_json = json.dumps(kelly_metrics)
                else:
                    kelly_metrics_json = kelly_metrics

            execute(conn, """
                INSERT INTO trades
                (id, recommendation_id, run_id, cycle_id, symbol, side, entry_price, take_profit,
                 stop_loss, quantity, pair_quantity, status, order_id, order_id_pair, confidence, rr_ratio, timeframe, dry_run, created_at,
                 position_size_usd, risk_amount_usd, risk_percentage, confidence_weight, risk_per_unit, sizing_method, risk_pct_used,
                 strategy_uuid, strategy_type, strategy_name, ranking_context, strategy_metadata, wallet_balance_at_trade, kelly_metrics,
                 position_sizing_inputs, position_sizing_outputs, order_parameters, execution_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?)
            """, (
                trade["id"],
                trade.get("recommendation_id"),
                trade.get("run_id"),
                trade.get("cycle_id"),
                trade["symbol"],
                trade.get("side"),
                trade.get("entry_price"),
                trade.get("take_profit"),
                trade.get("stop_loss"),
                trade.get("qty"),
                trade.get("pair_qty"),  # For spread-based trades
                trade["status"],
                trade.get("order_id"),
                trade.get("order_id_pair"),  # For spread-based trades
                trade.get("confidence"),
                trade.get("rr_ratio"),
                timeframe,  # Use timeframe from trade or recommendation
                self.paper_trading,  # Pass boolean directly
                trade["timestamp"].isoformat(),
                # Position sizing metrics from position sizer
                position_size_usd,
                risk_amount_usd,
                risk_percentage,
                confidence_weight,
                risk_per_unit,
                sizing_method,
                risk_pct_used,
                # Strategy tracking and traceability
                strategy_uuid,
                strategy_type,
                strategy_name,
                ranking_context_json,
                strategy_metadata_json,
                wallet_balance_at_trade,
                kelly_metrics_json,
                # Reproducibility data
                position_sizing_inputs,
                position_sizing_outputs,
                order_parameters,
                execution_timestamp.isoformat() if execution_timestamp else None,
            ))
        except Exception as e:
            logger.error(f"Failed to record trade: {e}")
        finally:
            if conn:
                release_connection(conn)

    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "running": self._running,
            "paper_trading": self.paper_trading,
            "testnet": self.testnet,
            "cycle_count": self._cycle_count,
            "websocket": self.ws_manager.get_stats() if self.ws_manager else None,
            "state": self.state_manager.get_stats(),
        }
