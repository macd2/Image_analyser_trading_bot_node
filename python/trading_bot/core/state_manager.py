"""
State Manager for real-time trading state.
Maintains in-memory cache of positions, orders, and wallet data from WebSocket.
Syncs to database for persistence and audit trail.

For paper trading mode, queries database instead of using WebSocket data.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from trading_bot.db.client import execute, query, get_connection, release_connection, get_boolean_comparison

logger = logging.getLogger(__name__)


@dataclass
class OrderState:
    """In-memory order state."""
    order_id: str
    order_link_id: str
    symbol: str
    side: str  # Buy, Sell
    order_type: str  # Market, Limit
    price: float
    qty: float
    status: str  # New, PartiallyFilled, Filled, Cancelled, Rejected
    filled_qty: float = 0.0
    avg_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    category: str = "linear"


@dataclass
class PositionState:
    """In-memory position state."""
    symbol: str
    side: str  # Buy (long), Sell (short), "" (no position)
    size: float
    entry_price: float
    mark_price: float
    unrealised_pnl: float
    leverage: str
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    liq_price: Optional[float] = None
    position_value: float = 0.0
    updated_time: Optional[str] = None
    category: str = "linear"


@dataclass
class WalletState:
    """In-memory wallet state."""
    coin: str
    available_balance: float
    wallet_balance: float
    equity: float
    unrealised_pnl: float = 0.0
    updated_time: Optional[str] = None


@dataclass
class ExecutionRecord:
    """Execution record from WebSocket."""
    exec_id: str
    order_id: str
    symbol: str
    side: str
    exec_price: float
    exec_qty: float
    exec_value: float
    exec_fee: float
    exec_pnl: float
    exec_time: str
    is_maker: bool
    category: str = "linear"


class StateManager:
    """
    Manages real-time trading state from WebSocket streams.

    Features:
    - In-memory cache for fast access (no API calls needed)
    - Thread-safe updates
    - Database sync for persistence
    - Event callbacks for state changes
    - Paper trading mode: Uses database instead of WebSocket for position/slot checking
    """

    def __init__(self, db_connection=None, paper_trading: bool = False, instance_id: Optional[str] = None):
        """
        Initialize StateManager.

        Args:
            db_connection: Optional database connection for persistence
            paper_trading: If True, use database for position/slot checking instead of WebSocket
            instance_id: Instance ID for filtering database queries and WebSocket messages
        """
        self._db = db_connection
        self._lock = threading.RLock()
        self.paper_trading = paper_trading
        self.instance_id = instance_id

        # In-memory state (used for live trading via WebSocket)
        # MULTI-INSTANCE SUPPORT: Track by (instance_id, symbol) for proper isolation
        self._orders: Dict[str, OrderState] = {}  # order_id -> OrderState
        self._positions: Dict[tuple, PositionState] = {}  # (instance_id, symbol) -> PositionState
        self._wallet: Dict[str, WalletState] = {}  # coin -> WalletState (shared across instances)
        self._executions: List[ExecutionRecord] = []  # Recent executions

        # Track symbols with open positions/orders (instance-aware)
        # Format: Set of (instance_id, symbol) tuples
        self._symbols_with_positions: Set[tuple] = set()
        self._symbols_with_orders: Set[tuple] = set()

        # Callbacks for state changes
        self._on_order_update: Optional[Callable] = None
        self._on_position_update: Optional[Callable] = None
        self._on_fill: Optional[Callable] = None

        # Stats
        self._update_count = 0
        self._last_update_time: Optional[datetime] = None
    
    # ==================== ORDER HANDLING ====================
    
    def handle_order_message(self, message: Dict) -> None:
        """
        Handle order stream message from WebSocket.
        
        Message format:
        {
            "topic": "order",
            "data": [
                {
                    "orderId": "...",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "orderStatus": "New",
                    ...
                }
            ]
        }
        """
        if not message.get("data"):
            return
        
        with self._lock:
            for order_data in message["data"]:
                self._update_order(order_data)
    
    def _update_order(self, data: Dict) -> None:
        """
        Update order state from WebSocket data.

        MULTI-INSTANCE: Only tracks orders that belong to this instance.
        Ownership determined by order_link_id prefix matching instance_id.
        """
        order_id = data.get("orderId", "")
        if not order_id:
            return

        order_link_id = data.get("orderLinkId", "")

        # MULTI-INSTANCE FILTER: Only track orders from this instance
        # Order link IDs are formatted as: {instance_id}_{trade_id} or similar
        if self.instance_id and order_link_id:
            if not order_link_id.startswith(self.instance_id):
                # This order belongs to a different instance, ignore it
                logger.debug(f"Ignoring order from different instance: {order_link_id}")
                return

        status = data.get("orderStatus", "")
        symbol = data.get("symbol", "")

        # Create or update order state
        order = OrderState(
            order_id=order_id,
            order_link_id=order_link_id,
            symbol=symbol,
            side=data.get("side", ""),
            order_type=data.get("orderType", ""),
            price=float(data.get("price", 0) or 0),
            qty=float(data.get("qty", 0) or 0),
            status=status,
            filled_qty=float(data.get("cumExecQty", 0) or 0),
            avg_price=float(data.get("avgPrice", 0) or 0),
            stop_loss=float(data.get("stopLoss", 0) or 0) or None,
            take_profit=float(data.get("takeProfit", 0) or 0) or None,
            created_time=data.get("createdTime"),
            updated_time=data.get("updatedTime"),
            category=data.get("category", "linear"),
        )

        self._orders[order_id] = order
        self._update_count += 1
        self._last_update_time = datetime.now(timezone.utc)

        # Track symbols with active orders (instance-aware)
        instance_symbol_key = (self.instance_id, symbol)
        if status in ("New", "PartiallyFilled"):
            self._symbols_with_orders.add(instance_symbol_key)
        elif status in ("Filled", "Cancelled", "Rejected"):
            # Check if any other orders for this (instance, symbol) combination
            has_other_orders = any(
                o.symbol == symbol and o.order_id != order_id
                and o.status in ("New", "PartiallyFilled")
                and (not self.instance_id or o.order_link_id.startswith(self.instance_id))
                for o in self._orders.values()
            )
            if not has_other_orders:
                self._symbols_with_orders.discard(instance_symbol_key)

        logger.debug(f"[{self.instance_id}] Order update: {symbol} {order_id[:8]}... -> {status}")

        # Callback
        if self._on_order_update:
            self._on_order_update(order)

    # ==================== POSITION HANDLING ====================

    def handle_position_message(self, message: Dict) -> None:
        """Handle position stream message from WebSocket."""
        if not message.get("data"):
            return

        with self._lock:
            for pos_data in message["data"]:
                self._update_position(pos_data)

    def _update_position(self, data: Dict) -> None:
        """
        Update position state from WebSocket data.

        MULTI-INSTANCE: Tracks positions by (instance_id, symbol) key.
        All position updates are tracked since we can't filter by order_link_id here.
        Each instance will see all positions but only act on its own symbols.
        """
        symbol = data.get("symbol", "")
        if not symbol:
            return

        size = float(data.get("size", 0) or 0)
        side = data.get("side", "")

        position = PositionState(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=float(data.get("entryPrice", 0) or 0),
            mark_price=float(data.get("markPrice", 0) or 0),
            unrealised_pnl=float(data.get("unrealisedPnl", 0) or 0),
            leverage=data.get("leverage", "1"),
            take_profit=float(data.get("takeProfit", 0) or 0) or None,
            stop_loss=float(data.get("stopLoss", 0) or 0) or None,
            liq_price=float(data.get("liqPrice", 0) or 0) or None,
            position_value=float(data.get("positionValue", 0) or 0),
            updated_time=data.get("updatedTime"),
            category=data.get("category", "linear"),
        )

        # Store position with instance-aware key
        instance_symbol_key = (self.instance_id, symbol)
        self._positions[instance_symbol_key] = position
        self._update_count += 1
        self._last_update_time = datetime.now(timezone.utc)

        # Track symbols with open positions (instance-aware)
        if size > 0 and side:
            self._symbols_with_positions.add(instance_symbol_key)
        else:
            self._symbols_with_positions.discard(instance_symbol_key)

        logger.debug(f"[{self.instance_id}] Position update: {symbol} {side} size={size}")

        # Callback
        if self._on_position_update:
            self._on_position_update(position)

    # ==================== EXECUTION HANDLING ====================

    def handle_execution_message(self, message: Dict) -> None:
        """Handle execution stream message from WebSocket."""
        if not message.get("data"):
            return

        with self._lock:
            for exec_data in message["data"]:
                self._record_execution(exec_data)

    def _record_execution(self, data: Dict) -> None:
        """Record execution from WebSocket data."""
        exec_record = ExecutionRecord(
            exec_id=data.get("execId", ""),
            order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            exec_price=float(data.get("execPrice", 0) or 0),
            exec_qty=float(data.get("execQty", 0) or 0),
            exec_value=float(data.get("execValue", 0) or 0),
            exec_fee=float(data.get("execFee", 0) or 0),
            exec_pnl=float(data.get("execPnl", 0) or 0),
            exec_time=data.get("execTime", ""),
            is_maker=data.get("isMaker", False),
            category=data.get("category", "linear"),
        )

        self._executions.append(exec_record)
        self._update_count += 1
        self._last_update_time = datetime.now(timezone.utc)

        # Keep only last 100 executions in memory
        if len(self._executions) > 100:
            self._executions = self._executions[-100:]

        logger.info(
            f"Execution: {exec_record.symbol} {exec_record.side} "
            f"qty={exec_record.exec_qty} @ {exec_record.exec_price} "
            f"pnl={exec_record.exec_pnl}"
        )

        # Persist to database
        self._persist_execution(exec_record)

        # Callback
        if self._on_fill:
            self._on_fill(exec_record)

    def _persist_execution(self, exec_record: ExecutionRecord) -> None:
        """Persist execution to database."""
        conn = None
        try:
            # Get fresh connection for this operation
            conn = get_connection()
            execute(conn, """
                INSERT INTO executions
                (id, order_id, exec_id, symbol, side, exec_price, exec_qty,
                 exec_value, exec_fee, exec_pnl, is_maker, exec_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                exec_record.order_id,
                exec_record.exec_id,
                exec_record.symbol,
                exec_record.side,
                exec_record.exec_price,
                exec_record.exec_qty,
                exec_record.exec_value,
                exec_record.exec_fee,
                exec_record.exec_pnl,
                exec_record.is_maker,  # Pass boolean directly
                exec_record.exec_time,
            ))
        except Exception as e:
            logger.error(f"Failed to persist execution: {e}")
        finally:
            if conn:
                release_connection(conn)

    # ==================== WALLET HANDLING ====================

    def handle_wallet_message(self, message: Dict) -> None:
        """Handle wallet stream message from WebSocket."""
        if not message.get("data"):
            return

        with self._lock:
            for wallet_data in message["data"]:
                for coin_data in wallet_data.get("coin", []):
                    self._update_wallet(coin_data)

    def _update_wallet(self, data: Dict) -> None:
        """Update wallet state from WebSocket data."""
        coin = data.get("coin", "")
        if not coin:
            return

        wallet = WalletState(
            coin=coin,
            available_balance=float(data.get("availableToWithdraw", 0) or 0),
            wallet_balance=float(data.get("walletBalance", 0) or 0),
            equity=float(data.get("equity", 0) or 0),
            unrealised_pnl=float(data.get("unrealisedPnl", 0) or 0),
            updated_time=datetime.now(timezone.utc).isoformat(),
        )

        self._wallet[coin] = wallet
        self._update_count += 1
        self._last_update_time = datetime.now(timezone.utc)

        logger.debug(f"Wallet update: {coin} balance={wallet.wallet_balance}")

    # ==================== QUERY METHODS ====================

    def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderState]:
        """Get all open orders, optionally filtered by symbol."""
        with self._lock:
            orders = [
                o for o in self._orders.values()
                if o.status in ("New", "PartiallyFilled")
            ]
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders

    def get_order(self, order_id: str) -> Optional[OrderState]:
        """Get order by ID."""
        with self._lock:
            return self._orders.get(order_id)

    def get_position(self, symbol: str) -> Optional[PositionState]:
        """
        Get position for symbol (for this instance).

        MULTI-INSTANCE: Uses (instance_id, symbol) key for lookup.
        """
        with self._lock:
            instance_symbol_key = (self.instance_id, symbol)
            return self._positions.get(instance_symbol_key)

    def get_open_positions(self) -> List[PositionState]:
        """
        Get all open positions (size > 0) for this instance.

        MULTI-INSTANCE: Only returns positions belonging to this instance.
        """
        with self._lock:
            return [
                p for (inst_id, sym), p in self._positions.items()
                if inst_id == self.instance_id and p.size > 0 and p.side
            ]

    def get_wallet_balance(self, coin: str = "USDT") -> Optional[WalletState]:
        """Get wallet balance for coin."""
        with self._lock:
            return self._wallet.get(coin)

    def has_position(self, symbol: str) -> bool:
        """
        Check if symbol has an open position (for this instance).

        In paper trading mode: Queries database for open positions.
        In live trading mode: Uses WebSocket data (real-time).

        MULTI-INSTANCE: Checks using (instance_id, symbol) key.
        """
        if self.paper_trading:
            # Paper trading: Check database
            positions = self._get_db_open_positions()
            has_pos = any(p['symbol'] == symbol for p in positions)
            logger.debug(f"[{self.instance_id}] [Paper Trading] DB check for {symbol}: {has_pos}")
            return has_pos
        else:
            # Live trading: Use WebSocket data with instance-aware key
            with self._lock:
                instance_symbol_key = (self.instance_id, symbol)
                return instance_symbol_key in self._symbols_with_positions

    def has_open_order(self, symbol: str) -> bool:
        """
        Check if symbol has an open order (for this instance).

        In paper trading mode: Checks database for pending paper trades (status='paper_trade').
        In live trading mode: Uses WebSocket data (real-time).

        MULTI-INSTANCE: Checks using (instance_id, symbol) key.
        """
        if self.paper_trading:
            # Paper trading: Check database for pending orders (not yet filled by simulator)
            pending_orders = self._get_db_pending_orders()
            has_order = any(p['symbol'] == symbol for p in pending_orders)
            logger.debug(f"[{self.instance_id}] [Paper Trading] DB check for pending order {symbol}: {has_order}")
            return has_order
        else:
            # Live trading: Use WebSocket data with instance-aware key
            with self._lock:
                instance_symbol_key = (self.instance_id, symbol)
                return instance_symbol_key in self._symbols_with_orders

    def count_slots_used(self) -> int:
        """
        Count total slots used (positions + entry orders) for this instance.

        In paper trading mode: Queries database for open positions AND pending orders.
        In live trading mode: Uses WebSocket data (real-time).

        MULTI-INSTANCE: Only counts slots for this instance.
        """
        if self.paper_trading:
            # Paper trading: Count both filled positions and pending orders
            filled_positions = self._get_db_open_positions()
            pending_orders = self._get_db_pending_orders()

            # Get unique symbols (a symbol can't have both pending order and position)
            filled_symbols = {p['symbol'] for p in filled_positions}
            pending_symbols = {p['symbol'] for p in pending_orders}
            all_symbols = filled_symbols | pending_symbols

            count = len(all_symbols)
            logger.debug(
                f"[{self.instance_id}] [Paper Trading] DB-based slot count: {count} "
                f"(filled: {len(filled_symbols)}, pending: {len(pending_symbols)})"
            )
            return count
        else:
            # Live trading: Use WebSocket data (instance-aware)
            with self._lock:
                # Unique (instance_id, symbol) tuples with either position or order
                # Filter to only this instance's slots
                instance_slots = {
                    (inst_id, sym) for (inst_id, sym) in
                    (self._symbols_with_positions | self._symbols_with_orders)
                    if inst_id == self.instance_id
                }
                return len(instance_slots)

    def get_available_slots(self, max_slots: int) -> int:
        """Get number of available trading slots."""
        return max(0, max_slots - self.count_slots_used())

    def get_recent_executions(self, limit: int = 10) -> List[ExecutionRecord]:
        """Get recent executions."""
        with self._lock:
            return self._executions[-limit:]

    # ==================== CALLBACKS ====================

    def set_on_order_update(self, callback: Callable) -> None:
        """Set callback for order updates."""
        self._on_order_update = callback

    def set_on_position_update(self, callback: Callable) -> None:
        """Set callback for position updates."""
        self._on_position_update = callback

    def set_on_fill(self, callback: Callable) -> None:
        """Set callback for fills/executions."""
        self._on_fill = callback

    # ==================== STATS ====================

    def get_stats(self) -> Dict[str, Any]:
        """
        Get state manager statistics for this instance.

        MULTI-INSTANCE: Returns stats filtered to this instance only.
        """
        with self._lock:
            # Filter to this instance's data
            instance_positions = [
                (inst_id, sym) for (inst_id, sym) in self._symbols_with_positions
                if inst_id == self.instance_id
            ]
            instance_orders = [
                (inst_id, sym) for (inst_id, sym) in self._symbols_with_orders
                if inst_id == self.instance_id
            ]

            return {
                "instance_id": self.instance_id,
                "update_count": self._update_count,
                "last_update": self._last_update_time.isoformat() if self._last_update_time else None,
                "orders_count": len(self._orders),
                "open_orders_count": len([o for o in self._orders.values() if o.status in ("New", "PartiallyFilled")]),
                "positions_count": len(instance_positions),
                "symbols_with_orders": [sym for (_, sym) in instance_orders],
                "symbols_with_positions": [sym for (_, sym) in instance_positions],
                "slots_used": self.count_slots_used(),
                "wallet_coins": list(self._wallet.keys()),
            }

    def clear(self) -> None:
        """Clear all state (for testing or reset)."""
        with self._lock:
            self._orders.clear()
            self._positions.clear()
            self._wallet.clear()
            self._executions.clear()
            self._symbols_with_positions.clear()
            self._symbols_with_orders.clear()
            self._update_count = 0
            self._last_update_time = None
            logger.info("State manager cleared")

    # ==================== DATABASE QUERIES (PAPER TRADING) ====================

    def _get_db_open_positions(self) -> List[Dict[str, Any]]:
        """
        Query database for open positions for this instance (paper trading only).
        Uses centralized database layer to respect DB_TYPE environment variable.

        Returns:
            List of open position records with symbol, side, status
        """
        if not self.instance_id:
            logger.warning("No instance_id provided - cannot query database positions")
            return []

        conn = None
        try:
            conn = get_connection()

            # Query for open dry-run positions for this instance
            # Open positions: status IN ('filled', 'partially_filled', 'paper_trade') AND pnl IS NULL
            # Use database-agnostic boolean comparison
            dry_run_check = get_boolean_comparison('t.dry_run', True)

            results = query(conn, f"""
                SELECT DISTINCT t.symbol, t.side, t.status, t.id
                FROM trades t
                JOIN cycles c ON t.cycle_id = c.id
                JOIN runs r ON c.run_id = r.id
                WHERE r.instance_id = ?
                  AND {dry_run_check}
                  AND t.status IN ('filled', 'partially_filled', 'paper_trade')
                  AND t.pnl IS NULL
            """, (self.instance_id,))

            positions = [dict(row.items()) for row in results]
            logger.debug(f"[DB Query] Found {len(positions)} open positions for instance {self.instance_id}")

            return positions

        except Exception as e:
            logger.error(f"Error querying database for open positions: {e}")
            return []
        finally:
            if conn:
                release_connection(conn)

    def _get_db_open_positions_count(self) -> int:
        """
        Get count of open positions from database (paper trading only).
        Uses centralized database layer to respect DB_TYPE environment variable.

        Returns:
            Number of open positions for this instance
        """
        positions = self._get_db_open_positions()
        return len(positions)

    def _get_db_pending_orders(self) -> List[Dict[str, Any]]:
        """
        Query database for pending paper trade orders (not yet filled by simulator).
        Uses centralized database layer to respect DB_TYPE environment variable.

        Returns:
            List of pending order records with symbol, side, status
        """
        if not self.instance_id:
            logger.warning("No instance_id provided - cannot query database pending orders")
            return []

        conn = None
        try:
            conn = get_connection()

            # Query for pending paper trade orders for this instance
            # Pending orders: status = 'paper_trade' (waiting for simulator to fill)
            # Use database-agnostic boolean comparison
            dry_run_check = get_boolean_comparison('t.dry_run', True)

            results = query(conn, f"""
                SELECT DISTINCT t.symbol, t.side, t.status, t.id
                FROM trades t
                JOIN cycles c ON t.cycle_id = c.id
                JOIN runs r ON c.run_id = r.id
                WHERE r.instance_id = ?
                  AND {dry_run_check}
                  AND t.status = 'paper_trade'
                  AND t.pnl IS NULL
            """, (self.instance_id,))

            pending_orders = [dict(row.items()) for row in results]
            logger.debug(f"[DB Query] Found {len(pending_orders)} pending orders for instance {self.instance_id}")

            return pending_orders

        except Exception as e:
            logger.error(f"Error querying database for pending orders: {e}")
            return []
        finally:
            if conn:
                release_connection(conn)

