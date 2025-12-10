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
from trading_bot.db.client import get_connection, execute

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
        )

        # WebSocket manager (shared singleton for multi-instance support)
        self.ws_manager: Optional[SharedWebSocketManager] = None

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
        """Insert a rejected trade into the database for audit trail."""
        try:
            # Determine side from recommendation
            recommendation = signal.get("recommendation", "").upper()
            side = "Buy" if recommendation in ("BUY", "LONG") else "Sell"

            # Use provided rr_ratio or try to get from signal, default to 0
            final_rr_ratio = rr_ratio if rr_ratio is not None else signal.get("rr_ratio", 0)

            execute(self._db, """
                INSERT INTO trades (
                    id, recommendation_id, run_id, cycle_id, symbol, side,
                    entry_price, quantity, stop_loss, take_profit,
                    status, rejection_reason, dry_run, confidence, rr_ratio,
                    timeframe, prompt_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ))

            logger.debug(f"Inserted rejected trade {trade_id} for {symbol}: {rejection_reason}")
        except Exception as e:
            logger.error(f"Failed to insert rejected trade {trade_id}: {e}")

    def execute_signal(
        self,
        symbol: str,
        signal: Dict[str, Any],
        recommendation_id: Optional[str] = None,
        cycle_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a trading signal.

        Args:
            symbol: Trading symbol
            signal: Signal dict with recommendation, entry, tp, sl, confidence
            recommendation_id: ID of the recommendation that generated this signal
            cycle_id: ID of the cycle that generated this signal

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

        # Validate RR ratio
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

        # Calculate RR ratio correctly for both LONG and SHORT
        is_long = recommendation in ("BUY", "LONG")
        risk = abs(sl - entry)
        reward = abs(tp - entry) if is_long else abs(entry - tp)
        rr_ratio = reward / risk if risk > 0 else 0

        min_rr = self.config.trading.min_rr
        if rr_ratio < min_rr:
            rejection_reason = f"RR ratio {rr_ratio:.2f} below minimum {min_rr}"
            self._insert_rejected_trade(trade_id, symbol, signal, rejection_reason, recommendation_id, cycle_id, timestamp, rr_ratio)
            return {
                "id": trade_id,
                "status": "rejected",
                "error": rejection_reason,
                "timestamp": timestamp,
            }

        # Paper trading mode
        if self.paper_trading:
            return self._execute_paper_trade(
                trade_id, symbol, signal, rr_ratio, recommendation_id, cycle_id, timestamp
            )

        # Live trading
        return self._execute_live_trade(
            trade_id, symbol, signal, rr_ratio, recommendation_id, cycle_id, timestamp
        )

    def _execute_paper_trade(
        self,
        trade_id: str,
        symbol: str,
        signal: Dict[str, Any],
        rr_ratio: float,
        recommendation_id: Optional[str],
        cycle_id: Optional[str],
        timestamp: datetime,
    ) -> Dict[str, Any]:
        """Execute paper trade (simulation)."""
        side = "Buy" if signal["recommendation"].upper() in ("BUY", "LONG") else "Sell"

        # Calculate position size
        wallet = self.order_executor.get_wallet_balance()
        balance = wallet.get("available", 10000)  # Default for paper

        sizing = self.position_sizer.calculate_position_size(
            symbol=symbol,
            entry_price=signal["entry_price"],
            stop_loss=signal["stop_loss"],
            wallet_balance=balance,
            confidence=signal.get("confidence", 0.75),
        )

        if "error" in sizing:
            return {
                "id": trade_id,
                "status": "rejected",
                "error": sizing["error"],
                "timestamp": timestamp,
            }

        # Record paper trade
        trade = {
            "id": trade_id,
            "run_id": self.run_id,
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": side,
            "qty": sizing["position_size"],
            "entry_price": signal["entry_price"],
            "take_profit": signal["take_profit"],
            "stop_loss": signal["stop_loss"],
            "rr_ratio": rr_ratio,
            "confidence": signal.get("confidence"),
            "timeframe": signal.get("timeframe"),  # Store timeframe for chart display
            "status": "paper_trade",
            "recommendation_id": recommendation_id,
            "timestamp": timestamp,
        }

        self._record_trade(trade)

        logger.info(
            f"📝 PAPER TRADE: {symbol} {side} {sizing['position_size']} "
            f"@ {signal['entry_price']} (RR: {rr_ratio:.2f})"
        )

        return trade

    def _execute_live_trade(
        self,
        trade_id: str,
        symbol: str,
        signal: Dict[str, Any],
        rr_ratio: float,
        recommendation_id: Optional[str],
        cycle_id: Optional[str],
        timestamp: datetime,
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

        # Calculate position size
        sizing = self.position_sizer.calculate_position_size(
            symbol=symbol,
            entry_price=signal["entry_price"],
            stop_loss=signal["stop_loss"],
            wallet_balance=wallet["available"],
            confidence=signal.get("confidence", 0.75),
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

        # Set leverage
        leverage = self.config.trading.leverage
        self.order_executor.set_leverage(symbol, leverage)

        # Place order
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
            "entry_price": signal["entry_price"],
            "take_profit": signal["take_profit"],
            "stop_loss": signal["stop_loss"],
            "rr_ratio": rr_ratio,
            "confidence": signal.get("confidence"),
            "timeframe": signal.get("timeframe"),  # Store timeframe for chart display
            "order_id": result.get("order_id"),
            "status": "submitted",
            "recommendation_id": recommendation_id,
            "timestamp": timestamp,
        }

        self._record_trade(trade)

        logger.info(
            f"🚀 LIVE TRADE: {symbol} {side} {sizing['position_size']} "
            f"@ {signal['entry_price']} (Order: {result.get('order_id')})"
        )

        return trade

    def _record_trade(self, trade: Dict[str, Any]) -> None:
        """Record trade to database."""
        if not self._db:
            return

        try:
            execute(self._db, """
                INSERT INTO trades
                (id, recommendation_id, run_id, cycle_id, symbol, side, entry_price, take_profit,
                 stop_loss, quantity, status, order_id, confidence, rr_ratio, timeframe, dry_run, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                trade["status"],
                trade.get("order_id"),
                trade.get("confidence"),
                trade.get("rr_ratio"),
                trade.get("timeframe"),  # Store timeframe for chart display
                self.paper_trading,  # Pass boolean directly
                trade["timestamp"].isoformat(),
            ))
        except Exception as e:
            logger.error(f"Failed to record trade: {e}")

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
