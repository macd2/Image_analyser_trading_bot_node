"""
Enhanced Position Monitor Service - Comprehensive position/trade monitoring.

This service handles everything from trade execution to closure:
- Real-time position monitoring (event-driven or polling)
- RR-based stop loss tightening
- TP proximity trailing stop feature
- Age-based tightening for unprofitable positions
- Age-based order cancellation
- Compatible with both live and paper trading

Can run either:
1. Event-driven (via WebSocket callbacks)
2. Polling mode (checks every few seconds)
"""

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from trading_bot.core.state_manager import PositionState, OrderState
from trading_bot.engine.order_executor import OrderExecutor
from trading_bot.config.settings_v2 import TradingConfig
from trading_bot.db.client import execute

logger = logging.getLogger(__name__)


class MonitorMode(Enum):
    """Monitor operation mode"""
    EVENT_DRIVEN = "event_driven"  # React to WebSocket events
    POLLING = "polling"  # Check positions every N seconds


@dataclass
class TPProximityConfig:
    """TP Proximity trailing stop configuration"""
    enabled: bool = False
    threshold_pct: float = 1.0  # Activate when within X% of TP
    trailing_pct: float = 1.0  # Trail X% behind price


@dataclass
class AgeTighteningConfig:
    """Age-based tightening configuration"""
    enabled: bool = False
    max_tightening_pct: float = 30.0  # Max 30% tightening
    min_profit_threshold: float = 1.0  # Only below 1R profit
    age_bars: Dict[str, float] = field(default_factory=dict)  # Timeframe -> bars


@dataclass
class AgeCancellationConfig:
    """Age-based order cancellation configuration"""
    enabled: bool = False
    max_age_bars: Dict[str, float] = field(default_factory=dict)  # Timeframe -> max bars
    max_age_seconds: Optional[int] = None  # Time-based cancellation (e.g., 300 = 5 minutes)


@dataclass
class TighteningStep:
    """RR tightening step configuration"""
    threshold: float  # RR threshold (e.g., 2.0 = 2R profit)
    sl_position: float  # New SL position as RR (e.g., 1.2 = lock in 1.2R)


@dataclass
class PositionTrackingState:
    """
    Internal state for tracking a position.

    MULTI-INSTANCE: Tracked by (instance_id, symbol) key externally.
    """
    instance_id: str  # Instance that owns this position
    symbol: str
    entry_price: float
    original_sl: float
    current_sl: float
    take_profit: float
    side: str
    entry_time: datetime
    timeframe: str
    last_tightening_step: int = -1
    tp_proximity_activated: bool = False
    age_tightening_applied: bool = False
    # Spread-based trading fields
    is_spread_based: bool = False
    pair_symbol: Optional[str] = None
    pair_entry_price: Optional[float] = None
    pair_side: Optional[str] = None
    pair_fill_price: Optional[float] = None
    order_id_x: Optional[str] = None
    order_id_y: Optional[str] = None
    fill_price_x: Optional[float] = None
    fill_price_y: Optional[float] = None
    both_filled: bool = False
    # Partial fill handling (Phase 3)
    first_leg_fill_time: Optional[datetime] = None  # When first leg filled
    partial_fill_timeout_seconds: int = 60  # 1 minute timeout for second leg


class EnhancedPositionMonitor:
    """
    Comprehensive position monitor with advanced features.
    
    Features:
    - RR-based stop loss tightening
    - TP proximity trailing stops
    - Age-based tightening
    - Age-based order cancellation
    - Event-driven or polling mode
    """
    
    DEFAULT_TIGHTENING_STEPS = [
        TighteningStep(threshold=2.0, sl_position=1.2),
        TighteningStep(threshold=2.5, sl_position=2.0),
        TighteningStep(threshold=3.0, sl_position=2.5),
    ]
    
    def __init__(
        self,
        order_executor: OrderExecutor,
        mode: MonitorMode = MonitorMode.EVENT_DRIVEN,
        poll_interval: float = 5.0,
        master_tightening_enabled: bool = True,
        tightening_enabled: bool = True,
        tightening_steps: Optional[List[TighteningStep]] = None,
        tp_proximity_config: Optional[TPProximityConfig] = None,
        age_tightening_config: Optional[AgeTighteningConfig] = None,
        age_cancellation_config: Optional[AgeCancellationConfig] = None,
        db_connection=None,
    ):
        """
        Initialize enhanced position monitor.

        Args:
            order_executor: OrderExecutor for modifying stops/orders
            mode: EVENT_DRIVEN or POLLING
            poll_interval: Seconds between checks (polling mode)
            master_tightening_enabled: Master switch - disables ALL tightening if False
            tightening_enabled: Enable RR-based tightening
            tightening_steps: Custom tightening steps
            tp_proximity_config: TP proximity configuration
            age_tightening_config: Age-based tightening config
            age_cancellation_config: Age-based cancellation config
            db_connection: Database connection for persistence
        """
        self.executor = order_executor
        self.mode = mode
        self.poll_interval = poll_interval
        self.master_tightening_enabled = master_tightening_enabled
        self.tightening_enabled = tightening_enabled
        self.tightening_steps = tightening_steps or self.DEFAULT_TIGHTENING_STEPS
        self.tp_proximity_config = tp_proximity_config or TPProximityConfig()
        self.age_tightening_config = age_tightening_config or AgeTighteningConfig()
        self.age_cancellation_config = age_cancellation_config or AgeCancellationConfig()
        self._db = db_connection

        # Tracking state
        # MULTI-INSTANCE: Track by (instance_id, symbol) for proper isolation
        self._position_state: Dict[tuple, PositionTrackingState] = {}  # (instance_id, symbol) -> state
        self._order_state: Dict[str, Dict] = {}  # order_id -> order info (includes instance_id)

        # Threading for polling mode
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Callbacks
        self._on_position_closed: Optional[Callable] = None
        self._on_sl_tightened: Optional[Callable] = None
        self._on_order_cancelled: Optional[Callable] = None
    
    def start(self) -> None:
        """Start the monitor (for polling mode)"""
        if self.mode == MonitorMode.POLLING and not self._running:
            self._running = True
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            logger.info(f"Enhanced position monitor started in POLLING mode (interval: {self.poll_interval}s)")

    def stop(self) -> None:
        """Stop the monitor"""
        if self._running:
            self._running = False
            self._stop_event.set()
            if self._monitor_thread:
                self._monitor_thread.join(timeout=5.0)
            logger.info("Enhanced position monitor stopped")

    def set_callbacks(
        self,
        on_position_closed: Optional[Callable] = None,
        on_sl_tightened: Optional[Callable] = None,
        on_order_cancelled: Optional[Callable] = None,
    ) -> None:
        """Set event callbacks"""
        self._on_position_closed = on_position_closed
        self._on_sl_tightened = on_sl_tightened
        self._on_order_cancelled = on_order_cancelled

    # ==================== WEBSOCKET EVENT HANDLERS ====================

    def on_execution_update(self, execution: Any, instance_id: str, run_id: str) -> None:
        """
        Handle execution update from WebSocket (real-time fill notification).

        This is called when an order is filled via the execution stream.
        For spread-based trades, tracks fills for both legs and triggers exit when both filled.

        Args:
            execution: ExecutionRecord from WebSocket (has order_id, symbol, exec_qty, exec_price, etc.)
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail

        MULTI-INSTANCE: Filters orders by instance_id via order_link_id prefix.
        """
        order_id = execution.order_id
        symbol = execution.symbol
        exec_qty = execution.exec_qty
        exec_price = execution.exec_price

        # Check if this order is tracked
        if order_id not in self._order_state:
            return

        order_info = self._order_state[order_id]

        # Verify instance match (order_link_id contains instance_id prefix)
        if order_info.get("instance_id") != instance_id:
            return

        logger.info(
            f"[{instance_id}] 📊 EXECUTION: {symbol} {execution.side} "
            f"qty={exec_qty} @ {exec_price}"
        )

        # For spread-based trades, track fills for both legs
        if order_info.get("is_spread_based"):
            self._handle_spread_execution(
                order_id, order_info, execution, instance_id, run_id
            )
            # Check for partial fill timeout (Phase 3)
            self._check_partial_fill_timeouts(instance_id, run_id)
        else:
            # For regular trades, just log the execution
            self._log_position_action(
                instance_id, run_id, order_info.get("trade_id"), symbol,
                "order_filled", f"Order {order_id} filled: {exec_qty} @ {exec_price}"
            )

    def _handle_spread_execution(
        self,
        order_id: str,
        order_info: Dict[str, Any],
        execution: Any,
        instance_id: str,
        run_id: str,
    ) -> None:
        """
        Handle execution for spread-based trades.

        Tracks fills for both legs (X and Y symbols) and triggers exit when both filled.
        Implements partial fill handling: if one leg fills but other doesn't within 1 minute,
        close the filled leg and cancel the unfilled order.
        """
        symbol = execution.symbol
        exec_qty = execution.exec_qty
        exec_price = execution.exec_price

        # Determine which leg this is (X or Y)
        order_id_x = order_info.get("order_id_x")
        order_id_y = order_info.get("order_id_y")
        symbol_x = order_info.get("symbol")
        symbol_y = order_info.get("pair_symbol")

        if order_id == order_id_x:
            # X leg filled
            order_info["fill_price_x"] = exec_price
            order_info["fill_qty_x"] = exec_qty
            logger.info(f"[{instance_id}] ✅ X leg filled: {symbol_x} {exec_qty} @ {exec_price}")
        elif order_id == order_id_y:
            # Y leg filled
            order_info["fill_price_y"] = exec_price
            order_info["fill_qty_y"] = exec_qty
            logger.info(f"[{instance_id}] ✅ Y leg filled: {symbol_y} {exec_qty} @ {exec_price}")
        else:
            return

        # IMPORTANT: Update BOTH order entries with fill info so timeout check works
        # regardless of which order_id we're iterating over
        if order_id_x in self._order_state:
            self._order_state[order_id_x]["fill_price_x"] = order_info.get("fill_price_x")
            self._order_state[order_id_x]["fill_qty_x"] = order_info.get("fill_qty_x")
            self._order_state[order_id_x]["fill_price_y"] = order_info.get("fill_price_y")
            self._order_state[order_id_x]["fill_qty_y"] = order_info.get("fill_qty_y")
        if order_id_y in self._order_state:
            self._order_state[order_id_y]["fill_price_x"] = order_info.get("fill_price_x")
            self._order_state[order_id_y]["fill_qty_x"] = order_info.get("fill_qty_x")
            self._order_state[order_id_y]["fill_price_y"] = order_info.get("fill_price_y")
            self._order_state[order_id_y]["fill_qty_y"] = order_info.get("fill_qty_y")

        # Check if both legs are now filled
        fill_price_x = order_info.get("fill_price_x")
        fill_price_y = order_info.get("fill_price_y")

        if fill_price_x and fill_price_y and not order_info.get("both_filled"):
            order_info["both_filled"] = True

            # Update BOTH order entries with both_filled flag
            if order_id_x in self._order_state:
                self._order_state[order_id_x]["both_filled"] = True
            if order_id_y in self._order_state:
                self._order_state[order_id_y]["both_filled"] = True

            logger.info(
                f"[{instance_id}] 🎯 BOTH LEGS FILLED: {symbol_x} @ {fill_price_x}, "
                f"{symbol_y} @ {fill_price_y}"
            )

            self._log_position_action(
                instance_id, run_id, order_info.get("trade_id"), symbol,
                "spread_both_filled",
                f"Both legs filled: {symbol_x} @ {fill_price_x}, {symbol_y} @ {fill_price_y}"
            )
        elif (fill_price_x or fill_price_y) and not order_info.get("first_leg_fill_time"):
            # First leg filled, start 1-minute timeout for second leg
            order_info["first_leg_fill_time"] = datetime.now(timezone.utc)
            filled_leg = "X" if fill_price_x else "Y"
            unfilled_leg = "Y" if fill_price_x else "X"
            logger.info(
                f"[{instance_id}] ⏱️ PARTIAL FILL: {filled_leg} leg filled, "
                f"waiting {order_info.get('partial_fill_timeout_seconds', 60)}s for {unfilled_leg} leg"
            )

            self._log_position_action(
                instance_id, run_id, order_info.get("trade_id"), symbol,
                "spread_partial_fill",
                f"First leg ({filled_leg}) filled, waiting for second leg ({unfilled_leg})"
            )

    # ==================== EVENT HANDLERS ====================

    def on_position_update(self, position: PositionState, instance_id: str, run_id: str, trade_id: Optional[str] = None, strategy: Optional[Any] = None) -> None:
        """
        Handle position update from WebSocket (event-driven mode).

        Args:
            position: Position state from WebSocket
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking (optional)
            strategy: Strategy instance for strategy-specific monitoring (optional)

        MULTI-INSTANCE: Uses (instance_id, symbol) key for tracking.
        """
        symbol = position.symbol
        position_key = (instance_id, symbol)

        # Skip empty positions
        if position.size == 0 or not position.side:
            if position_key in self._position_state:
                logger.info(f"[{instance_id}] Position closed: {symbol}")
                self._log_position_action(
                    instance_id, run_id, trade_id, symbol,
                    "position_closed", "Position closed by exchange"
                )
                del self._position_state[position_key]
            return

        # Initialize or update position state
        if position_key not in self._position_state:
            self._position_state[position_key] = PositionTrackingState(
                instance_id=instance_id,
                symbol=symbol,
                entry_price=position.entry_price,
                original_sl=position.stop_loss or 0.0,
                current_sl=position.stop_loss or 0.0,
                take_profit=position.take_profit or 0.0,
                side=position.side,
                entry_time=datetime.now(timezone.utc),
                timeframe="",  # Will be set from trade data
            )
            logger.info(f"[{instance_id}] Tracking new position: {symbol} {position.side}")
            self._log_position_action(
                instance_id, run_id, trade_id, symbol,
                "position_opened", f"Started tracking {position.side} position"
            )

        # Check for tightening opportunities and strategy exits
        state = self._position_state[position_key]

        # Fetch trade data and current candle for strategy exit checking
        trade = None
        current_candle = None
        if strategy:
            trade = self._fetch_trade_data_for_strategy_exit(symbol, trade_id)
            if trade:
                timeframe = state.timeframe or "1h"
                current_candle = self._fetch_current_candle_for_strategy_exit(symbol, timeframe)

        self._check_all_tightening(
            position, state, instance_id, run_id, trade_id, strategy,
            current_candle=current_candle,
            trade=trade
        )

    def on_order_update(self, order: OrderState, instance_id: str, run_id: str, timeframe: str) -> None:
        """
        Handle order update from WebSocket (for age-based cancellation).

        Args:
            order: Order state from WebSocket
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            timeframe: Timeframe for age calculation

        MULTI-INSTANCE: Stores instance_id with order state.
        """
        order_id = order.order_id

        # Track unfilled orders
        if order.status in ["New", "PartiallyFilled"]:
            if order_id not in self._order_state:
                self._order_state[order_id] = {
                    "instance_id": instance_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "created_time": order.created_time or datetime.now(timezone.utc).isoformat(),
                    "timeframe": timeframe,
                    "instance_id": instance_id,
                    "run_id": run_id,
                }
                logger.debug(f"[{instance_id}] Tracking order: {order_id} ({order.symbol})")

        # Remove filled/cancelled orders
        elif order.status in ["Filled", "Cancelled", "Rejected"]:
            if order_id in self._order_state:
                del self._order_state[order_id]

    def on_spread_based_orders_placed(
        self,
        instance_id: str,
        run_id: str,
        trade_id: str,
        symbol_x: str,
        symbol_y: str,
        order_id_x: str,
        order_id_y: str,
        qty_x: float,
        qty_y: float,
        price_x: float,
        price_y: float,
        strategy_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register spread-based orders for tracking.
        Called when place_spread_based_orders() succeeds.

        Args:
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking
            symbol_x: Main symbol (e.g., BTCUSDT)
            symbol_y: Pair symbol (e.g., ETHUSDT)
            order_id_x: Order ID for symbol X
            order_id_y: Order ID for symbol Y
            qty_x: Quantity for symbol X
            qty_y: Quantity for symbol Y
            price_x: Entry price for symbol X
            price_y: Entry price for symbol Y
            strategy_metadata: Strategy metadata for exit logic
        """
        position_key = (instance_id, symbol_x)

        # Initialize spread-based position tracking
        if position_key not in self._position_state:
            self._position_state[position_key] = PositionTrackingState(
                instance_id=instance_id,
                symbol=symbol_x,
                entry_price=price_x,
                original_sl=0.0,  # Will be set from trade data
                current_sl=0.0,
                take_profit=0.0,
                side="Buy" if qty_x > 0 else "Sell",
                entry_time=datetime.now(timezone.utc),
                timeframe="",
                is_spread_based=True,
                pair_symbol=symbol_y,
                pair_entry_price=price_y,
                pair_side="Buy" if qty_y > 0 else "Sell",
                order_id_x=order_id_x,
                order_id_y=order_id_y,
            )

            logger.info(
                f"[{instance_id}] Spread-based orders registered: "
                f"{symbol_x} {qty_x} @ {price_x} (ID: {order_id_x}) | "
                f"{symbol_y} {qty_y} @ {price_y} (ID: {order_id_y})"
            )
            self._log_position_action(
                instance_id, run_id, trade_id, symbol_x,
                "spread_orders_placed",
                f"Spread orders placed for {symbol_x}/{symbol_y}"
            )

    def on_spread_based_order_filled(
        self,
        instance_id: str,
        run_id: str,
        trade_id: str,
        symbol: str,
        order_id: str,
        fill_price: float,
        fill_qty: float,
    ) -> None:
        """
        Handle fill for one leg of a spread-based trade.
        Checks if both legs are filled.

        Args:
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking
            symbol: Symbol that was filled
            order_id: Order ID that was filled
            fill_price: Fill price
            fill_qty: Fill quantity
        """
        # Find the position tracking state
        position_key = None
        for key, state in self._position_state.items():
            if key[0] == instance_id and state.is_spread_based:
                if state.symbol == symbol or state.pair_symbol == symbol:
                    position_key = key
                    break

        if not position_key:
            logger.warning(f"[{instance_id}] No spread position found for {symbol}")
            return

        state = self._position_state[position_key]

        # Update fill info for the appropriate leg
        if symbol == state.symbol:
            state.fill_price_x = fill_price
            state.order_id_x = order_id
            logger.debug(f"[{instance_id}] Main symbol {symbol} filled @ {fill_price}")
        elif symbol == state.pair_symbol:
            state.fill_price_y = fill_price
            state.order_id_y = order_id
            logger.debug(f"[{instance_id}] Pair symbol {symbol} filled @ {fill_price}")

        # Check if both legs are filled
        if state.fill_price_x is not None and state.fill_price_y is not None:
            state.both_filled = True
            logger.info(
                f"[{instance_id}] Spread-based trade FULLY FILLED: "
                f"{state.symbol} @ {state.fill_price_x} | "
                f"{state.pair_symbol} @ {state.fill_price_y}"
            )
            self._log_position_action(
                instance_id, run_id, trade_id, state.symbol,
                "spread_both_filled",
                f"Both legs filled: {state.symbol} @ {state.fill_price_x}, "
                f"{state.pair_symbol} @ {state.fill_price_y}"
            )

    # ==================== POLLING MODE ====================

    def _monitor_loop(self) -> None:
        """Main monitoring loop for polling mode"""
        while self._running and not self._stop_event.is_set():
            try:
                self._check_all_positions()
                self._check_all_orders()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}", exc_info=True)

            # Wait for next interval
            self._stop_event.wait(self.poll_interval)

    def _check_all_positions(self) -> None:
        """Check all tracked positions (polling mode)"""
        # This would be called in polling mode to check positions
        # For now, positions are primarily tracked via event-driven updates
        pass

    def _check_partial_fill_timeouts(self, instance_id: str, run_id: str) -> None:
        """
        Check for partial fill timeouts (Phase 3).

        If one leg of a spread-based trade fills but the other doesn't within 1 minute:
        1. Close the filled leg via market order
        2. Cancel the unfilled order
        3. Log the event

        MULTI-INSTANCE: Filters by instance_id.
        """
        now = datetime.now(timezone.utc)
        processed_pairs = set()  # Track processed order pairs to avoid double-handling

        for order_id, order_info in list(self._order_state.items()):
            # Skip non-spread-based orders
            if not order_info.get("is_spread_based"):
                continue

            # Skip if instance doesn't match
            if order_info.get("instance_id") != instance_id:
                continue

            # Skip if both legs already filled
            if order_info.get("both_filled"):
                continue

            # Skip if no partial fill yet
            first_fill_time = order_info.get("first_leg_fill_time")
            if not first_fill_time:
                continue

            # Skip if we already processed this pair
            pair_key = (order_info.get("order_id_x"), order_info.get("order_id_y"))
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)

            # Check if timeout exceeded
            timeout_seconds = order_info.get("partial_fill_timeout_seconds", 60)
            elapsed = (now - first_fill_time).total_seconds()

            if elapsed > timeout_seconds:
                self._handle_partial_fill_timeout(
                    order_id, order_info, instance_id, run_id, elapsed
                )

    def _handle_partial_fill_timeout(
        self,
        order_id: str,
        order_info: Dict[str, Any],
        instance_id: str,
        run_id: str,
        elapsed_seconds: float,
    ) -> None:
        """
        Handle partial fill timeout: close filled leg and cancel unfilled order.

        Args:
            order_id: Order ID that triggered timeout
            order_info: Order tracking info
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            elapsed_seconds: Seconds elapsed since first fill
        """
        order_id_x = order_info.get("order_id_x")
        order_id_y = order_info.get("order_id_y")

        # Determine symbol_x and symbol_y based on order_id_x and order_id_y
        # NOT based on the current order_info's symbol (which might be either X or Y)
        if order_id == order_id_x:
            symbol_x = order_info.get("symbol")
            symbol_y = order_info.get("pair_symbol")
        else:
            # order_id == order_id_y, so swap them
            symbol_x = order_info.get("pair_symbol")
            symbol_y = order_info.get("symbol")

        fill_price_x = order_info.get("fill_price_x")
        fill_price_y = order_info.get("fill_price_y")
        fill_qty_x = order_info.get("fill_qty_x")
        fill_qty_y = order_info.get("fill_qty_y")
        trade_id = order_info.get("trade_id")

        logger.warning(
            f"[{instance_id}] ⚠️ PARTIAL FILL TIMEOUT ({elapsed_seconds:.1f}s): "
            f"X={fill_price_x is not None}, Y={fill_price_y is not None}"
        )

        # Determine which leg filled and which didn't
        if fill_price_x and not fill_price_y:
            # X filled, Y didn't - close X and cancel Y
            filled_symbol = symbol_x
            filled_qty = fill_qty_x
            unfilled_symbol = symbol_y
            unfilled_order_id = order_id_y
            filled_leg = "X"
            unfilled_leg = "Y"
        elif fill_price_y and not fill_price_x:
            # Y filled, X didn't - close Y and cancel X
            filled_symbol = symbol_y
            filled_qty = fill_qty_y
            unfilled_symbol = symbol_x
            unfilled_order_id = order_id_x
            filled_leg = "Y"
            unfilled_leg = "X"
        else:
            # Both filled or neither filled - shouldn't happen
            logger.warning(f"[{instance_id}] Unexpected partial fill state: X={fill_price_x}, Y={fill_price_y}")
            return

        logger.info(
            f"[{instance_id}] 🔄 PARTIAL FILL RECOVERY: "
            f"Closing {filled_leg} leg ({filled_symbol}) and cancelling {unfilled_leg} leg ({unfilled_symbol})"
        )

        # Step 1: Close the filled leg via market order
        close_result = self.executor.close_position(symbol=filled_symbol)

        if "error" in close_result:
            logger.error(
                f"[{instance_id}] Failed to close {filled_leg} leg ({filled_symbol}): {close_result['error']}"
            )
            self._log_position_action(
                instance_id, run_id, trade_id, filled_symbol,
                "partial_fill_close_failed",
                f"Failed to close {filled_leg} leg: {close_result['error']}"
            )
        else:
            logger.info(f"[{instance_id}] ✅ Closed {filled_leg} leg ({filled_symbol})")
            self._log_position_action(
                instance_id, run_id, trade_id, filled_symbol,
                "partial_fill_closed",
                f"Closed {filled_leg} leg ({filled_symbol}) after {elapsed_seconds:.1f}s timeout"
            )

        # Step 2: Cancel the unfilled order
        cancel_result = self.executor.cancel_order(
            symbol=unfilled_symbol,
            order_id=unfilled_order_id
        )

        if "error" in cancel_result:
            logger.error(
                f"[{instance_id}] Failed to cancel {unfilled_leg} leg ({unfilled_symbol}): {cancel_result['error']}"
            )
            self._log_position_action(
                instance_id, run_id, trade_id, unfilled_symbol,
                "partial_fill_cancel_failed",
                f"Failed to cancel {unfilled_leg} leg: {cancel_result['error']}"
            )
        else:
            logger.info(f"[{instance_id}] ✅ Cancelled {unfilled_leg} leg ({unfilled_symbol})")
            self._log_position_action(
                instance_id, run_id, trade_id, unfilled_symbol,
                "partial_fill_cancelled",
                f"Cancelled {unfilled_leg} leg ({unfilled_symbol}) after {elapsed_seconds:.1f}s timeout"
            )

        # Mark as handled so we don't retry
        order_info["partial_fill_handled"] = True

    def _check_all_orders(
        self,
        age_cancellation_config: Optional[AgeCancellationConfig] = None
    ) -> None:
        """Check all tracked orders for age-based cancellation (bar-based or time-based)

        Args:
            age_cancellation_config: Optional config override (e.g., from strategy)
        """
        # Use provided config or fall back to global
        config = age_cancellation_config or self.age_cancellation_config

        if not config.enabled:
            return

        now = datetime.now(timezone.utc)
        orders_to_cancel = []

        for order_id, order_info in self._order_state.items():
            created_time = datetime.fromisoformat(order_info["created_time"])
            age_seconds = (now - created_time).total_seconds()

            # Check time-based cancellation first (if configured)
            if config.max_age_seconds and config.max_age_seconds > 0:
                if age_seconds >= config.max_age_seconds:
                    orders_to_cancel.append((order_id, order_info, age_seconds, "time"))
                    continue

            # Check bar-based cancellation (if configured)
            timeframe = order_info.get("timeframe", "1h")
            max_age_bars = config.max_age_bars.get(timeframe, 0)

            if max_age_bars <= 0:
                continue

            # Calculate order age in bars
            bar_seconds = self._timeframe_to_seconds(timeframe)
            age_bars = age_seconds / bar_seconds if bar_seconds > 0 else 0

            if age_bars >= max_age_bars:
                orders_to_cancel.append((order_id, order_info, age_bars, "bars"))

        # Cancel aged orders
        for order_data in orders_to_cancel:
            order_id = order_data[0]
            order_info = order_data[1]
            age_value = order_data[2]
            age_type = order_data[3]
            self._cancel_aged_order(
                order_id, order_info, age_value, age_type
            )

    # ==================== TIGHTENING LOGIC ====================

    def _check_all_tightening(
        self,
        position: PositionState,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
        strategy: Optional[Any] = None,
        current_candle: Optional[Dict[str, Any]] = None,
        trade: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Check all tightening strategies for a position

        If strategy is provided, uses strategy.get_monitoring_metadata() to determine
        what monitoring to apply. Otherwise uses default configuration.

        Args:
            position: Current position state from exchange
            state: Internal tracking state
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking
            strategy: Strategy instance for strategy-specific monitoring
            current_candle: Current candle for strategy exit checks
            trade: Trade record for strategy exit checks
        """

        # Master switch - if disabled, skip ALL tightening
        if not self.master_tightening_enabled:
            return

        # Get strategy-specific monitoring metadata if available
        monitoring_metadata = None
        if strategy:
            try:
                monitoring_metadata = strategy.get_monitoring_metadata()
            except Exception as e:
                logger.warning(f"Failed to get monitoring metadata from strategy: {e}")

        # Check if strategy specifies age-based cancellation override
        # (e.g., spread-based strategies ALWAYS have age-based cancellation enabled)
        strategy_age_cancellation_config = None
        if monitoring_metadata and "enable_age_cancellation" in monitoring_metadata:
            # Strategy overrides global config
            strategy_age_cancellation_config = AgeCancellationConfig(
                enabled=monitoring_metadata["enable_age_cancellation"],
                max_age_bars=monitoring_metadata.get("age_cancellation_bars", {}),
                max_age_seconds=monitoring_metadata.get("age_cancellation_seconds")
            )
            logger.debug(
                f"[{instance_id}] Using strategy-specific age cancellation config: "
                f"enabled={strategy_age_cancellation_config.enabled}, "
                f"seconds={strategy_age_cancellation_config.max_age_seconds}, "
                f"bars={strategy_age_cancellation_config.max_age_bars}"
            )
            # Check orders with strategy's config
            self._check_all_orders(age_cancellation_config=strategy_age_cancellation_config)

        # 0. STRATEGY-SPECIFIC EXIT CHECK (highest priority)
        # Check if strategy says to exit BEFORE any tightening
        if strategy and current_candle and trade:
            try:
                # For spread-based trades, fetch pair candle for exit logic
                pair_candle = None
                if state.is_spread_based and state.pair_symbol:
                    pair_candle = self._fetch_current_candle_for_strategy_exit(
                        state.pair_symbol, state.timeframe or "1h"
                    )

                exit_result = self.check_strategy_exit(
                    trade=trade,
                    current_candle=current_candle,
                    pair_candle=pair_candle,
                    strategy=strategy,
                    instance_id=instance_id,
                    run_id=run_id,
                    trade_id=trade_id,
                )

                if exit_result and exit_result.get("should_exit"):
                    # Strategy says to exit - close the position
                    logger.info(f"[{instance_id}] Strategy exit triggered for {position.symbol}: {exit_result.get('exit_reason')}")

                    # For spread-based trades, close both symbols
                    if state.is_spread_based:
                        self._close_spread_based_position(
                            state, instance_id, run_id, trade_id, exit_result
                        )
                    else:
                        self._close_position_for_strategy_exit(
                            position, state, instance_id, run_id, trade_id,
                            exit_result
                        )
                    return  # Exit early - don't apply other tightening
                else:
                    # Strategy says to hold - sync strategy-calculated stops/TPs to exchange
                    # This ensures exchange orders always match strategy logic
                    if exit_result:
                        self._sync_strategy_stops(
                            position=position,
                            exit_result=exit_result,
                            instance_id=instance_id,
                            run_id=run_id,
                            trade_id=trade_id,
                        )
            except Exception as e:
                logger.error(f"Error checking strategy exit for {position.symbol}: {e}", exc_info=True)

        # 1. RR-based tightening (standard)
        # Check if enabled in strategy metadata or use default config
        enable_rr_tightening = True
        if monitoring_metadata:
            enable_rr_tightening = monitoring_metadata.get("enable_rr_tightening", self.tightening_enabled)
        else:
            enable_rr_tightening = self.tightening_enabled

        if enable_rr_tightening:
            self._check_rr_tightening(position, state, instance_id, run_id, trade_id)

        # 2. TP proximity trailing stop
        # Check if enabled in strategy metadata or use default config
        enable_tp_proximity = False
        if monitoring_metadata:
            enable_tp_proximity = monitoring_metadata.get("enable_tp_proximity", self.tp_proximity_config.enabled)
        else:
            enable_tp_proximity = self.tp_proximity_config.enabled

        if enable_tp_proximity:
            self._check_tp_proximity(position, state, instance_id, run_id, trade_id)

        # 3. Age-based tightening
        if self.age_tightening_config.enabled:
            self._check_age_tightening(position, state, instance_id, run_id, trade_id)

    def check_strategy_exit(
        self,
        trade: Dict[str, Any],
        current_candle: Dict[str, Any],
        pair_candle: Optional[Dict[str, Any]] = None,
        strategy: Optional[Any] = None,
        instance_id: Optional[str] = None,
        run_id: Optional[str] = None,
        trade_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Check if position should exit using strategy.should_exit().

        This method is called by real-time monitoring to check if a position
        should be closed based on strategy-specific exit conditions.

        Args:
            trade: Trade record with entry_price, stop_loss, take_profit, strategy_metadata
            current_candle: Current candle {timestamp, open, high, low, close}
            pair_candle: Pair candle for spread-based strategies (optional)
            strategy: Strategy instance with should_exit() method
            instance_id: Instance ID for logging
            run_id: Run ID for logging
            trade_id: Trade ID for logging

        Returns:
            Dict with exit details if should exit, or full exit_result if holding (for stop/TP syncing).
            Returns None only if strategy is not provided or error occurs.
        """
        if not strategy:
            return None

        try:
            # Call strategy.should_exit()
            exit_result = strategy.should_exit(
                trade=trade,
                current_candle=current_candle,
                pair_candle=pair_candle,
            )

            # Check if should exit
            if exit_result.get("should_exit"):
                exit_details = exit_result.get("exit_details", {})
                reason = exit_details.get("reason", "strategy_exit")

                # Log the exit decision
                if instance_id and run_id and trade_id:
                    self._log_position_action(
                        instance_id, run_id, trade_id, trade.get("symbol", "unknown"),
                        "strategy_exit_triggered",
                        f"Strategy exit: {reason} - Details: {exit_details}"
                    )

                return {
                    "should_exit": True,
                    "exit_price": current_candle.get("close"),
                    "exit_reason": reason,
                    "exit_details": exit_details,
                }

            # Return full result even when holding (should_exit=False)
            # This allows _sync_strategy_stops() to access exit_details for stop/TP syncing
            return exit_result

        except Exception as e:
            logger.error(f"Error checking strategy exit: {e}")
            return None

    def _close_position_for_strategy_exit(
        self,
        position: PositionState,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
        exit_result: Dict[str, Any],
    ) -> None:
        """
        Close a position based on strategy exit signal.

        Args:
            position: Current position state
            state: Internal tracking state
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking
            exit_result: Exit result from strategy.should_exit()
        """
        try:
            symbol = position.symbol
            exit_reason = exit_result.get("exit_reason", "strategy_exit")
            exit_details = exit_result.get("exit_details", {})

            logger.info(
                f"[{instance_id}] Closing {symbol} position due to strategy exit: {exit_reason}"
            )

            # Close the position at market
            result = self.executor.close_position(symbol=symbol)

            if "error" in result:
                logger.error(
                    f"[{instance_id}] Failed to close {symbol} position: {result['error']}"
                )
                self._log_position_action(
                    instance_id, run_id, trade_id, symbol,
                    "strategy_exit_close_failed",
                    f"Failed to close position: {result['error']}"
                )
            else:
                logger.info(
                    f"[{instance_id}] Successfully closed {symbol} position"
                )
                self._log_position_action(
                    instance_id, run_id, trade_id, symbol,
                    "strategy_exit_closed",
                    f"Position closed by strategy exit: {exit_reason} - Details: {exit_details}"
                )

                # Remove from tracking
                position_key = (instance_id, symbol)
                if position_key in self._position_state:
                    del self._position_state[position_key]

        except Exception as e:
            logger.error(
                f"[{instance_id}] Error closing position for strategy exit: {e}",
                exc_info=True
            )

    def _close_spread_based_position(
        self,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
        exit_result: Dict[str, Any],
    ) -> None:
        """
        Close a spread-based position by closing BOTH symbols via market orders.

        Args:
            state: Position tracking state
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking
            exit_result: Exit result from strategy.should_exit()
        """
        try:
            symbol_x = state.symbol
            symbol_y = state.pair_symbol
            exit_reason = exit_result.get("exit_reason", "strategy_exit")
            exit_details = exit_result.get("exit_details", {})

            logger.info(
                f"[{instance_id}] Closing spread-based position: "
                f"{symbol_x} / {symbol_y} due to strategy exit: {exit_reason}"
            )

            # Close both symbols via market orders
            errors = []

            # Close main symbol
            result_x = self.executor.close_position(symbol=symbol_x)
            if "error" in result_x:
                errors.append(f"{symbol_x}: {result_x['error']}")
                logger.error(f"[{instance_id}] Failed to close {symbol_x}: {result_x['error']}")
            else:
                logger.info(f"[{instance_id}] Closed {symbol_x} position")

            # Close pair symbol
            if symbol_y:
                result_y = self.executor.close_position(symbol=symbol_y)
                if "error" in result_y:
                    errors.append(f"{symbol_y}: {result_y['error']}")
                    logger.error(f"[{instance_id}] Failed to close {symbol_y}: {result_y['error']}")
                else:
                    logger.info(f"[{instance_id}] Closed {symbol_y} position")

            if errors:
                error_msg = " | ".join(errors)
                self._log_position_action(
                    instance_id, run_id, trade_id, symbol_x,
                    "spread_exit_close_failed",
                    f"Failed to close spread position: {error_msg}"
                )
            else:
                logger.info(
                    f"[{instance_id}] Successfully closed spread-based position: "
                    f"{symbol_x} / {symbol_y}"
                )
                self._log_position_action(
                    instance_id, run_id, trade_id, symbol_x,
                    "spread_exit_closed",
                    f"Spread position closed by strategy exit: {exit_reason} - Details: {exit_details}"
                )

                # Remove from tracking
                position_key = (instance_id, symbol_x)
                if position_key in self._position_state:
                    del self._position_state[position_key]

        except Exception as e:
            logger.error(f"Error closing spread-based position: {e}", exc_info=True)

    def _sync_strategy_stops(
        self,
        position: PositionState,
        exit_result: Dict[str, Any],
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
    ) -> bool:
        """
        Sync strategy-calculated stops/TPs to exchange orders.

        Called every monitoring cycle to keep exchange orders synchronized with
        strategy-calculated levels (even when holding position).

        Args:
            position: Current position state
            exit_result: Result from strategy.should_exit()
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking

        Returns:
            True if any updates were made, False otherwise
        """
        exit_details = exit_result.get("exit_details", {})

        # Extract strategy-provided levels (optional)
        stop_level = exit_details.get("stop_level")
        tp_level = exit_details.get("tp_level")

        # If strategy doesn't provide custom levels, skip sync
        if not stop_level and not tp_level:
            return False

        symbol = position.symbol
        updated = False

        # Update stop loss if changed (tolerance: 0.0001)
        if stop_level and abs(stop_level - position.stop_loss) > 0.0001:
            try:
                result = self.executor.set_trading_stop(
                    symbol=symbol,
                    stop_loss=stop_level,
                )

                if "error" not in result:
                    updated = True
                    logger.info(
                        f"[{instance_id}] 📍 SL SYNCED: {symbol} "
                        f"{position.stop_loss:.4f} → {stop_level:.4f}"
                    )

                    if instance_id and run_id and trade_id:
                        self._log_position_action(
                            instance_id, run_id, trade_id, symbol,
                            "strategy_stop_synced",
                            f"SL: {position.stop_loss:.4f} → {stop_level:.4f}"
                        )
                else:
                    logger.error(f"Failed to sync SL for {symbol}: {result.get('error')}")
            except Exception as e:
                logger.error(f"Error syncing SL for {symbol}: {e}")

        # Update take profit if changed (tolerance: 0.0001)
        if tp_level and abs(tp_level - position.take_profit) > 0.0001:
            try:
                result = self.executor.set_trading_stop(
                    symbol=symbol,
                    take_profit=tp_level,
                )

                if "error" not in result:
                    updated = True
                    logger.info(
                        f"[{instance_id}] 📍 TP SYNCED: {symbol} "
                        f"{position.take_profit:.4f} → {tp_level:.4f}"
                    )

                    if instance_id and run_id and trade_id:
                        self._log_position_action(
                            instance_id, run_id, trade_id, symbol,
                            "strategy_tp_synced",
                            f"TP: {position.take_profit:.4f} → {tp_level:.4f}"
                        )
                else:
                    logger.error(f"Failed to sync TP for {symbol}: {result.get('error')}")
            except Exception as e:
                logger.error(f"Error syncing TP for {symbol}: {e}")

        return updated

    def _fetch_trade_data_for_strategy_exit(
        self,
        symbol: str,
        trade_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch trade data from database for strategy exit checking.

        Args:
            symbol: Symbol to fetch trade for
            trade_id: Trade ID (optional, for filtering)

        Returns:
            Trade record with strategy_metadata or None if not found
        """
        if not self._db:
            logger.warning("No database connection available for fetching trade data")
            return None

        try:
            from trading_bot.db.client import query

            # Fetch the most recent open trade for this symbol
            trades = query(
                self._db,
                """
                SELECT id, symbol, side, entry_price, stop_loss, take_profit,
                       strategy_name, strategy_type, strategy_metadata
                FROM trades
                WHERE symbol = ? AND status IN ('open', 'paper_trade')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [symbol]
            )

            if trades and len(trades) > 0:
                trade = trades[0]
                # Parse strategy_metadata if it's a string
                if isinstance(trade.get("strategy_metadata"), str):
                    import json
                    try:
                        trade["strategy_metadata"] = json.loads(trade["strategy_metadata"])
                    except:
                        trade["strategy_metadata"] = {}
                return trade

            return None

        except Exception as e:
            logger.error(f"Error fetching trade data for {symbol}: {e}", exc_info=True)
            return None

    def _fetch_current_candle_for_strategy_exit(
        self,
        symbol: str,
        timeframe: str = "1h",
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the most recent candle for a symbol for strategy exit checking.

        Args:
            symbol: Symbol to fetch candle for
            timeframe: Timeframe (default: 1h)

        Returns:
            Candle dict with {timestamp, open, high, low, close} or None if not found
        """
        if not self._db:
            logger.warning("No database connection available for fetching candle data")
            return None

        try:
            from trading_bot.db.client import query

            # Fetch the most recent candle for this symbol
            candles = query(
                self._db,
                """
                SELECT timestamp, open, high, low, close
                FROM klines
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                [symbol, timeframe]
            )

            if candles and len(candles) > 0:
                return candles[0]

            return None

        except Exception as e:
            logger.error(f"Error fetching candle data for {symbol}: {e}", exc_info=True)
            return None

    def _check_rr_tightening(
        self,
        position: PositionState,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
    ) -> None:
        """Check and apply RR-based stop loss tightening"""

        entry = state.entry_price
        original_sl = state.original_sl
        current_price = position.mark_price

        if not all([entry, original_sl, current_price]):
            return

        # Calculate current RR
        risk = abs(entry - original_sl)
        if risk == 0:
            return

        # Calculate profit in R
        if position.side == "Buy":
            profit = current_price - entry
        else:
            profit = entry - current_price

        current_rr = profit / risk

        # Check each tightening step
        for i, step in enumerate(self.tightening_steps):
            if i <= state.last_tightening_step:
                continue  # Already applied

            if current_rr >= step.threshold:
                # Calculate new SL
                new_sl = self._calculate_new_sl(
                    entry, original_sl, position.side, step.sl_position
                )

                # Apply tightening
                success = self._apply_tightening(
                    position.symbol, new_sl, instance_id, run_id, trade_id,
                    f"RR tightening at {step.threshold}R -> {step.sl_position}R"
                )

                if success:
                    state.last_tightening_step = i
                    state.current_sl = new_sl

                    logger.info(
                        f"[{instance_id}] 🔒 SL TIGHTENED: {position.symbol} at {step.threshold}R -> "
                        f"SL moved to {step.sl_position}R ({new_sl:.4f})"
                    )

    def _check_tp_proximity(
        self,
        position: PositionState,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
    ) -> None:
        """Check and apply TP proximity trailing stop"""

        if state.tp_proximity_activated:
            return  # Already activated

        if not state.take_profit or state.take_profit == 0:
            return

        current_price = position.mark_price
        entry = state.entry_price
        tp = state.take_profit

        # Calculate distance to TP
        if position.side == "Buy":
            distance_to_tp = tp - current_price
            total_distance = tp - entry
        else:
            distance_to_tp = current_price - tp
            total_distance = entry - tp

        if total_distance == 0:
            return

        distance_pct = (distance_to_tp / total_distance) * 100

        # Check if within threshold
        if distance_pct <= self.tp_proximity_config.threshold_pct:
            # Activate trailing stop
            trailing_distance = current_price * (self.tp_proximity_config.trailing_pct / 100)

            if position.side == "Buy":
                new_sl = current_price - trailing_distance
            else:
                new_sl = current_price + trailing_distance

            # Only tighten if new SL is better
            if self._is_better_sl(new_sl, state.current_sl, position.side):
                success = self._apply_tightening(
                    position.symbol, new_sl, instance_id, run_id, trade_id,
                    f"TP proximity trailing activated (within {distance_pct:.1f}% of TP)"
                )

                if success:
                    state.tp_proximity_activated = True
                    state.current_sl = new_sl

                    logger.info(
                        f"[{instance_id}] 🎯 TP PROXIMITY TRAILING: {position.symbol} "
                        f"activated at {distance_pct:.1f}% from TP, SL -> {new_sl:.4f}"
                    )

    def _check_age_tightening(
        self,
        position: PositionState,
        state: PositionTrackingState,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
    ) -> None:
        """Check and apply age-based tightening for unprofitable positions"""

        if state.age_tightening_applied:
            return  # Already applied

        # Only apply to unprofitable positions
        current_price = position.mark_price
        entry = state.entry_price
        original_sl = state.original_sl

        risk = abs(entry - original_sl)
        if risk == 0:
            return

        # Calculate current profit in R
        if position.side == "Buy":
            profit = current_price - entry
        else:
            profit = entry - current_price

        current_rr = profit / risk

        # Only apply if below profit threshold
        if current_rr >= self.age_tightening_config.min_profit_threshold:
            return

        # Calculate position age in bars
        now = datetime.now(timezone.utc)
        age_seconds = (now - state.entry_time).total_seconds()
        bar_seconds = self._timeframe_to_seconds(state.timeframe)
        age_bars = age_seconds / bar_seconds if bar_seconds > 0 else 0

        # Check if age threshold reached
        timeframe = state.timeframe or "1h"
        age_threshold = self.age_tightening_config.age_bars.get(timeframe, 0)

        if age_threshold > 0 and age_bars >= age_threshold:
            # Calculate tightened SL
            max_tightening = self.age_tightening_config.max_tightening_pct / 100
            tightening_amount = risk * max_tightening

            if position.side == "Buy":
                new_sl = original_sl + tightening_amount
            else:
                new_sl = original_sl - tightening_amount

            # Only apply if better than current SL
            if self._is_better_sl(new_sl, state.current_sl, position.side):
                success = self._apply_tightening(
                    position.symbol, new_sl, instance_id, run_id, trade_id,
                    f"Age-based tightening after {age_bars:.1f} bars ({max_tightening*100:.0f}% tighter)"
                )

                if success:
                    state.age_tightening_applied = True
                    state.current_sl = new_sl

                    logger.info(
                        f"[{instance_id}] ⏰ AGE TIGHTENING: {position.symbol} "
                        f"after {age_bars:.1f} bars, SL tightened by {max_tightening*100:.0f}% -> {new_sl:.4f}"
                    )

    # ==================== HELPER METHODS ====================

    def _calculate_new_sl(
        self,
        entry: float,
        original_sl: float,
        side: str,
        sl_position: float,
    ) -> float:
        """Calculate new SL price based on RR position"""
        risk = abs(entry - original_sl)

        if side == "Buy":
            # Long: SL is below entry, move up
            return entry + (risk * sl_position)
        else:
            # Short: SL is above entry, move down
            return entry - (risk * sl_position)

    def _is_better_sl(self, new_sl: float, current_sl: float, side: str) -> bool:
        """Check if new SL is better (tighter) than current SL"""
        if side == "Buy":
            # For longs, higher SL is better
            return new_sl > current_sl
        else:
            # For shorts, lower SL is better
            return new_sl < current_sl

    def _apply_tightening(
        self,
        symbol: str,
        new_sl: float,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
        reason: str,
    ) -> bool:
        """Apply SL tightening to position"""

        result = self.executor.set_trading_stop(
            symbol=symbol,
            stop_loss=new_sl,
        )

        if "error" in result:
            logger.error(f"[{instance_id}] Failed to tighten SL for {symbol}: {result['error']}")
            self._log_position_action(
                instance_id, run_id, trade_id, symbol,
                "sl_tightening_failed", f"{reason} - Error: {result['error']}"
            )
            return False

        # Log successful tightening
        self._log_position_action(
            instance_id, run_id, trade_id, symbol,
            "sl_tightened", f"{reason} - New SL: {new_sl:.4f}"
        )

        # Callback
        if self._on_sl_tightened:
            self._on_sl_tightened(symbol, new_sl, reason)

        return True

    def _cancel_aged_order(
        self,
        order_id: str,
        order_info: Dict[str, Any],
        age_value: float,
        age_type: str = "bars",
    ) -> None:
        """Cancel an order that has aged beyond threshold

        Args:
            order_id: Order ID to cancel
            order_info: Order info dict
            age_value: Age value (bars or seconds)
            age_type: Type of age measurement ("bars" or "time")
        """

        symbol = order_info["symbol"]
        instance_id = order_info["instance_id"]
        run_id = order_info["run_id"]

        # Cancel order via executor
        result = self.executor.cancel_order(symbol=symbol, order_id=order_id)

        if "error" not in result:
            # Format age message based on type
            if age_type == "time":
                age_msg = f"{int(age_value)} seconds"
            else:
                age_msg = f"{age_value:.1f} bars"

            logger.info(
                f"[{instance_id}] 🚫 ORDER CANCELLED: {symbol} order {order_id} "
                f"aged {age_msg}"
            )

            self._log_position_action(
                instance_id, run_id, None, symbol,
                "order_cancelled_age", f"Order {order_id} cancelled after {age_msg}"
            )

            # Remove from tracking
            del self._order_state[order_id]

            # Callback
            if self._on_order_cancelled:
                self._on_order_cancelled(order_id, symbol, age_value)
        else:
            logger.error(
                f"[{instance_id}] Failed to cancel aged order {order_id}: {result['error']}"
            )

    def _timeframe_to_seconds(self, timeframe: str) -> float:
        """Convert timeframe string to seconds"""
        timeframe_map = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
            "1w": 604800,
        }
        return timeframe_map.get(timeframe, 3600)  # Default to 1h

    # ==================== AUDIT TRAIL ====================

    def _log_position_action(
        self,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str],
        symbol: str,
        action: str,
        details: str,
    ) -> None:
        """
        Log position monitoring action to database for audit trail.

        Logs all monitor actions with full context (instance_id, run_id, trade_id).
        """

        if not self._db:
            return

        try:
            import uuid
            log_id = str(uuid.uuid4())[:12]
            timestamp = datetime.now(timezone.utc).isoformat()

            # Log to position_snapshots with full context
            execute(self._db, """
                INSERT INTO position_snapshots (
                    symbol, snapshot_reason, snapshot_time
                ) VALUES (?, ?, ?)
            """, (
                symbol,
                f"[{instance_id}][{run_id}][{trade_id or 'N/A'}] [{action}] {details}",
                timestamp,
            ))
            self._db.commit()

            # Also log to error_logs for critical actions
            if action in ["sl_tightening_failed", "order_cancel_failed"]:
                execute(self._db, """
                    INSERT INTO error_logs (
                        id, timestamp, level, run_id, trade_id, symbol,
                        component, event, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id,
                    timestamp,
                    "ERROR",
                    run_id,
                    trade_id,
                    symbol,
                    "position_monitor",
                    action,
                    f"[{instance_id}] {details}",
                ))
                self._db.commit()

            # Log successful tightening actions to error_logs as INFO for audit trail
            elif action in ["sl_tightened", "position_closed", "order_cancelled_age"]:
                execute(self._db, """
                    INSERT INTO error_logs (
                        id, timestamp, level, run_id, trade_id, symbol,
                        component, event, message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_id,
                    timestamp,
                    "INFO",
                    run_id,
                    trade_id,
                    symbol,
                    "position_monitor",
                    action,
                    f"[{instance_id}] {details}",
                ))
                self._db.commit()

        except Exception as e:
            logger.error(f"Failed to log position action: {e}")

    # ==================== PUBLIC API ====================

    def get_position_state(self, instance_id: str, symbol: str) -> Optional[PositionTrackingState]:
        """
        Get tracked state for a position.

        MULTI-INSTANCE: Requires instance_id for lookup.
        """
        position_key = (instance_id, symbol)
        return self._position_state.get(position_key)

    def get_all_positions(self, instance_id: Optional[str] = None) -> Dict[tuple, PositionTrackingState]:
        """
        Get all tracked positions.

        MULTI-INSTANCE: If instance_id provided, filters to that instance only.
        """
        if instance_id:
            return {
                key: state for key, state in self._position_state.items()
                if key[0] == instance_id
            }
        return self._position_state.copy()

    def get_tracked_orders(self) -> Dict[str, Dict]:
        """Get all tracked orders"""
        return self._order_state.copy()

    def register_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        side: str,
        timeframe: str,
        instance_id: str,
        run_id: str,
        trade_id: Optional[str] = None,
    ) -> None:
        """
        Manually register a position for tracking (useful for paper trading).

        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Initial stop loss
            take_profit: Take profit target
            side: "Buy" or "Sell"
            timeframe: Timeframe for age calculations
            instance_id: Instance ID for audit trail
            run_id: Run ID for audit trail
            trade_id: Trade ID for linking

        MULTI-INSTANCE: Uses (instance_id, symbol) key for tracking.
        """
        position_key = (instance_id, symbol)
        self._position_state[position_key] = PositionTrackingState(
            instance_id=instance_id,
            symbol=symbol,
            entry_price=entry_price,
            original_sl=stop_loss,
            current_sl=stop_loss,
            take_profit=take_profit,
            side=side,
            entry_time=datetime.now(timezone.utc),
            timeframe=timeframe,
        )

        logger.info(f"[{instance_id}] Manually registered position: {symbol} {side}")
        self._log_position_action(
            instance_id, run_id, trade_id, symbol,
            "position_registered", f"Manual registration: {side} @ {entry_price}"
        )

    @classmethod
    def from_config(
        cls,
        config: TradingConfig,
        executor: OrderExecutor,
        mode: MonitorMode = MonitorMode.EVENT_DRIVEN,
        poll_interval: float = 5.0,
        db_connection = None,
    ) -> 'EnhancedPositionMonitor':
        """
        Create EnhancedPositionMonitor from TradingConfig.

        Args:
            config: TradingConfig instance with all settings
            executor: OrderExecutor for placing/modifying orders
            mode: EVENT_DRIVEN or POLLING
            poll_interval: Seconds between polls (if POLLING mode)
            db_connection: Database connection for audit trail

        Returns:
            Configured EnhancedPositionMonitor instance
        """
        # Build tightening steps from config
        tightening_steps = []
        for name, step in config.rr_tightening_steps.items():
            tightening_steps.append(
                TighteningStep(
                    threshold=step.threshold,
                    sl_position=step.sl_position,
                )
            )

        # Sort by threshold
        tightening_steps.sort(key=lambda x: x.threshold)

        # TP Proximity config
        tp_proximity_config = TPProximityConfig(
            enabled=config.enable_tp_proximity_trailing,
            threshold_pct=config.tp_proximity_threshold_pct,
            trailing_pct=config.tp_proximity_trailing_pct,
        )

        # Age-based tightening config
        age_tightening_config = AgeTighteningConfig(
            enabled=config.age_tightening_enabled,
            max_tightening_pct=config.age_tightening_max_pct,
            min_profit_threshold=config.age_tightening_min_profit_threshold,
            age_bars=config.age_tightening_bars,
        )

        # Age-based cancellation config
        age_cancellation_config = AgeCancellationConfig(
            enabled=config.age_cancellation_enabled,
            max_age_bars=config.age_cancellation_max_bars,
        )

        return cls(
            order_executor=executor,
            mode=mode,
            poll_interval=poll_interval,
            master_tightening_enabled=config.enable_position_tightening,
            tightening_enabled=config.enable_sl_tightening,
            tightening_steps=tightening_steps,
            tp_proximity_config=tp_proximity_config,
            age_tightening_config=age_tightening_config,
            age_cancellation_config=age_cancellation_config,
            db_connection=db_connection,
        )

