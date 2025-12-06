"""
State Manager for real-time trading state.
Maintains in-memory cache of positions, orders, and wallet data from WebSocket.
Syncs to database for persistence and audit trail.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set, Callable
from dataclasses import dataclass, field
from trading_bot.db.client import execute

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
    """
    
    def __init__(self, db_connection=None):
        """
        Initialize StateManager.
        
        Args:
            db_connection: Optional database connection for persistence
        """
        self._db = db_connection
        self._lock = threading.RLock()
        
        # In-memory state
        self._orders: Dict[str, OrderState] = {}  # order_id -> OrderState
        self._positions: Dict[str, PositionState] = {}  # symbol -> PositionState
        self._wallet: Dict[str, WalletState] = {}  # coin -> WalletState
        self._executions: List[ExecutionRecord] = []  # Recent executions
        
        # Track symbols with open positions/orders
        self._symbols_with_positions: Set[str] = set()
        self._symbols_with_orders: Set[str] = set()
        
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
        """Update order state from WebSocket data."""
        order_id = data.get("orderId", "")
        if not order_id:
            return
        
        status = data.get("orderStatus", "")
        symbol = data.get("symbol", "")
        
        # Create or update order state
        order = OrderState(
            order_id=order_id,
            order_link_id=data.get("orderLinkId", ""),
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

        # Track symbols with active orders
        if status in ("New", "PartiallyFilled"):
            self._symbols_with_orders.add(symbol)
        elif status in ("Filled", "Cancelled", "Rejected"):
            # Check if any other orders for this symbol
            has_other_orders = any(
                o.symbol == symbol and o.order_id != order_id
                and o.status in ("New", "PartiallyFilled")
                for o in self._orders.values()
            )
            if not has_other_orders:
                self._symbols_with_orders.discard(symbol)

        logger.debug(f"Order update: {symbol} {order_id[:8]}... -> {status}")

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
        """Update position state from WebSocket data."""
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

        self._positions[symbol] = position
        self._update_count += 1
        self._last_update_time = datetime.now(timezone.utc)

        # Track symbols with open positions
        if size > 0 and side:
            self._symbols_with_positions.add(symbol)
        else:
            self._symbols_with_positions.discard(symbol)

        logger.debug(f"Position update: {symbol} {side} size={size}")

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
        if not self._db:
            return

        try:
            execute(self._db, """
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
                1 if exec_record.is_maker else 0,
                exec_record.exec_time,
            ))
            self._db.commit()
        except Exception as e:
            logger.error(f"Failed to persist execution: {e}")

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
        """Get position for symbol."""
        with self._lock:
            return self._positions.get(symbol)

    def get_open_positions(self) -> List[PositionState]:
        """Get all open positions (size > 0)."""
        with self._lock:
            return [
                p for p in self._positions.values()
                if p.size > 0 and p.side
            ]

    def get_wallet_balance(self, coin: str = "USDT") -> Optional[WalletState]:
        """Get wallet balance for coin."""
        with self._lock:
            return self._wallet.get(coin)

    def has_position(self, symbol: str) -> bool:
        """Check if symbol has an open position."""
        with self._lock:
            return symbol in self._symbols_with_positions

    def has_open_order(self, symbol: str) -> bool:
        """Check if symbol has an open order."""
        with self._lock:
            return symbol in self._symbols_with_orders

    def count_slots_used(self) -> int:
        """Count total slots used (positions + entry orders)."""
        with self._lock:
            # Unique symbols with either position or order
            symbols = self._symbols_with_positions | self._symbols_with_orders
            return len(symbols)

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
        """Get state manager statistics."""
        with self._lock:
            return {
                "update_count": self._update_count,
                "last_update": self._last_update_time.isoformat() if self._last_update_time else None,
                "orders_count": len(self._orders),
                "open_orders_count": len([o for o in self._orders.values() if o.status in ("New", "PartiallyFilled")]),
                "positions_count": len(self._symbols_with_positions),
                "symbols_with_orders": list(self._symbols_with_orders),
                "symbols_with_positions": list(self._symbols_with_positions),
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

