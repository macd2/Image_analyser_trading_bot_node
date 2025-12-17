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

        # Check for tightening opportunities
        state = self._position_state[position_key]
        self._check_all_tightening(position, state, instance_id, run_id, trade_id, strategy)

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

    def _check_all_orders(self) -> None:
        """Check all tracked orders for age-based cancellation"""
        if not self.age_cancellation_config.enabled:
            return

        now = datetime.now(timezone.utc)
        orders_to_cancel = []

        for order_id, order_info in self._order_state.items():
            timeframe = order_info.get("timeframe", "1h")
            max_age_bars = self.age_cancellation_config.max_age_bars.get(timeframe, 0)

            if max_age_bars <= 0:
                continue

            # Calculate order age in bars
            created_time = datetime.fromisoformat(order_info["created_time"])
            age_seconds = (now - created_time).total_seconds()
            bar_seconds = self._timeframe_to_seconds(timeframe)
            age_bars = age_seconds / bar_seconds if bar_seconds > 0 else 0

            if age_bars >= max_age_bars:
                orders_to_cancel.append((order_id, order_info, age_bars))

        # Cancel aged orders
        for order_id, order_info, age_bars in orders_to_cancel:
            self._cancel_aged_order(
                order_id, order_info, age_bars
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
    ) -> None:
        """Check all tightening strategies for a position

        If strategy is provided, uses strategy.get_monitoring_metadata() to determine
        what monitoring to apply. Otherwise uses default configuration.
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
            Dict with exit details if should exit, None otherwise
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

            return None

        except Exception as e:
            logger.error(f"Error checking strategy exit: {e}")
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
        age_bars: float,
    ) -> None:
        """Cancel an order that has aged beyond threshold"""

        symbol = order_info["symbol"]
        instance_id = order_info["instance_id"]
        run_id = order_info["run_id"]

        # Cancel order via executor
        result = self.executor.cancel_order(symbol=symbol, order_id=order_id)

        if "error" not in result:
            logger.info(
                f"[{instance_id}] 🚫 ORDER CANCELLED: {symbol} order {order_id} "
                f"aged {age_bars:.1f} bars"
            )

            self._log_position_action(
                instance_id, run_id, None, symbol,
                "order_cancelled_age", f"Order {order_id} cancelled after {age_bars:.1f} bars"
            )

            # Remove from tracking
            del self._order_state[order_id]

            # Callback
            if self._on_order_cancelled:
                self._on_order_cancelled(order_id, symbol, age_bars)
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

